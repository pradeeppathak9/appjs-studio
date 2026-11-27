# Asset storage: local disk or an S3-compatible bucket

Studio keeps three kinds of files, under the same keys in either store:

| Key | What | Written by |
|---|---|---|
| `assets/<job_id>/<attempt>-<idx>.<ext>` | generated images and videos | worker |
| `inputs/<job_id>/<slot>.<ext>` | photos users send with a template call (often faces) | API |
| `uploads/<upload_id>.<ext>` | creators' reference images and template covers | API |
| `tmp/` | downloads still in progress, a job's input copies for providers | always local, `DATA_DIR/tmp` |

`ASSET_STORE=local` (the default) keeps everything under `DATA_DIR`. `ASSET_STORE=s3` puts the first
three in a bucket (Cloudflare R2, Backblaze B2, AWS S3, MinIO, ...) and keeps only `tmp/` on disk.
Code: `studio/storage/` (`local.py`, `s3.py`, `make_store` in `__init__.py`).

## How files are served

The API routes do not change: `GET /v1/app/assets/{id}`, `/v1/app/inputs/{id}`,
`/v1/app/templates/{slug}/cover`, `/v1/assets/{id}`, `/v1/inputs/{id}`, `/v1/apps/{id}/uploads/{id}`
check access exactly as before. Then:

- local: the API streams the file (`200`).
- s3: the API answers `307` to a **presigned GET URL** on the private bucket, valid
  `S3_URL_EXPIRY_S` (default 3600 s), carrying the file's content type and `inline; filename=...`.
  The redirect itself may be cached for 5 minutes (`Cache-Control: private, max-age=300`).
- s3 with `S3_PUBLIC_BASE_URL`: assets and uploads redirect to `<base>/<key>` (a public custom domain
  or CDN in front of the bucket; stable URLs that browsers and the CDN cache). **Input photos always
  get presigned URLs**, so a user's photo is never on a permanent public URL. Keys contain random UUIDs,
  but anyone who has an asset URL can open it while it exists: only set this if that's acceptable.

Clients:
- Android (`../restyle`, OkHttp) follows redirects by default and drops `Authorization` when the host
  changes. Nothing to change.
- The console (`web/`) shows files with `<img>` / `<video>` tags, which follow redirects. Nothing to change.
- restyle-web fetches images with `fetch()` and its headers (`X-App-Key`, `X-Device-Id`,
  `Authorization`). The browser follows the redirect cross-origin, drops `Authorization`, and sends a
  CORS preflight to the bucket for the other headers. **The bucket needs a CORS rule** (below), or the
  images fail to load in the web app. Check this on staging before switching production.

## Setting up Cloudflare R2

Done by hand in the Cloudflare dashboard (Studio never creates buckets or keys):

1. R2 → Create bucket, e.g. `appjs-studio` (location hint: Asia-Pacific). Leave public access off.
2. R2 → Manage API tokens → Create token: **Object Read & Write**, scoped to that bucket only. Note
   the Access Key ID, Secret Access Key and the S3 endpoint `https://<account id>.r2.cloudflarestorage.com`.
3. Bucket → Settings → CORS policy (for restyle-web; use your real RESTYLE_DOMAIN):

   ```json
   [
     {
       "AllowedOrigins": ["https://<RESTYLE_DOMAIN>"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedHeaders": ["x-app-key", "x-device-id", "accept", "authorization"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

   Add `http://localhost:5180` while testing restyle-web locally against the bucket.
4. Optional CDN: bucket → Settings → Custom domains → connect e.g. `img.<your domain>`, then set
   `S3_PUBLIC_BASE_URL=https://img.<your domain>` (see the trade-off above).
5. In Studio's `.env` (on the server: `studio/deploy/.env`; never commit it):

   ```bash
   ASSET_STORE=s3
   S3_BUCKET=appjs-studio
   S3_ENDPOINT_URL=https://<account id>.r2.cloudflarestorage.com
   S3_REGION=auto
   S3_ACCESS_KEY_ID=...
   S3_SECRET_ACCESS_KEY=...
   # S3_PUBLIC_BASE_URL=https://img.<your domain>
   # S3_URL_EXPIRY_S=3600
   ```

   Both the api and the worker need these (in prod they share `.env`). Keep the `./data` volume: `tmp/`
   is still there.

Other providers: AWS S3 → leave `S3_ENDPOINT_URL` unset and set `S3_REGION=ap-south-1`; Backblaze B2 →
`S3_ENDPOINT_URL=https://s3.<region>.backblazeb2.com`, `S3_REGION=<region>`; MinIO → its URL.

## One-time migration from `data/`

Run on the server, from `studio/deploy/`, with [rclone](https://rclone.org) installed. Configure a
remote once with `rclone config` (new remote `r2`, type `s3`, provider `Cloudflare`, the key pair and
endpoint above, `no_check_bucket = true`), then:

```bash
rclone copy ./data r2:appjs-studio --exclude 'tmp/**' --exclude '*.part' --transfers 16 --checksum --progress
```

(Without a saved remote: replace `r2:appjs-studio` with `:s3:appjs-studio` and add `--s3-provider
Cloudflare --s3-endpoint https://<account id>.r2.cloudflarestorage.com --s3-access-key-id ...
--s3-secret-access-key ... --s3-no-check-bucket`.)

Order, so no file is missed:
1. `rclone copy` as above while Studio still runs on local disk (copies the bulk).
2. Set the `ASSET_STORE=s3` settings, redeploy (`fab deploy`, only when you decide to).
3. Run the same `rclone copy` again: it uploads only what was written between steps 1 and 2.
4. Check: `rclone check ./data r2:appjs-studio --one-way --exclude 'tmp/**' --exclude '*.part'`,
   then open a few old generations in the console.
5. Keep `./data` (and its backups) until you're confident, then remove everything but `tmp/`.

Database rows store keys (`assets.path`, `job_inputs.path`, `uploads.path`), not full paths, so
nothing in Postgres changes. To go back, copy the bucket into `./data` the same way and set
`ASSET_STORE=local`. `fab backup` dumps the database and `./data`; once on R2 the files are no longer in
that backup (R2 is durable, but deletes are final: consider bucket versioning or a periodic
`rclone sync` to another place).

## Lifecycle: deleting old input photos

Input photos are only needed while a job runs (and for "My creations" to show what was sent). A rule
that deletes `inputs/` after **30 days** (decided 2026-11-26) limits how long users' faces are kept:

R2 → bucket → Settings → Object lifecycle rules → Add rule: name `expire-inputs`, prefix `inputs/`,
action "Delete uploaded objects after **30** days". Or with any S3 API client:

```json
{
  "Rules": [
    {"ID": "expire-inputs", "Status": "Enabled", "Filter": {"Prefix": "inputs/"},
     "Expiration": {"Days": 30}},
    {"ID": "abort-multipart", "Status": "Enabled", "Filter": {"Prefix": ""},
     "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}}
  ]
}
```

Never put `assets/` or `uploads/` in it: uploads are template covers and reference images that live
until a template stops using them. After 30 days, `inputs[].url` of older jobs returns `404` from the
bucket; clients should show a placeholder. The privacy policy should say input photos are kept for
30 days.

## Tests

`uv run pytest` runs on the local store, plus `tests/test_s3_store.py` against moto's S3 server on
localhost (no network, no keys). `STUDIO_TEST_ASSET_STORE=s3 uv run pytest` runs the whole suite with
the S3 store, following the API's redirects to moto.

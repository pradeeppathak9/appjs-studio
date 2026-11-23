# App API (Android and other client apps)

An **app** is a workspace in the console. An admin creates it and its **app keys** (Admin → Apps →
the app → Keys) and sets optional usage limits; the app's editors build its templates and their order
in the app's dashboard. The client app uses the key to list
its templates, run one with the user's photo, and download the result.

Base URL: `http://<server>:8010` (put it behind HTTPS before release; see "Security").

## Headers on every call

| Header | Required | Value |
|---|---|---|
| `X-App-Key` | yes | `cak_...`, created in the console (shown once) |
| `X-Device-Id` | strongly recommended | a random id generated once per install and kept (1–128 chars: letters, digits, `. _ : -`). Used for per-device limits and to keep each device's jobs private. Not a hardware id. |
| `Authorization` | after sign-in | `Bearer cas_...`, the user's session from a sign-in call below. Required for templates, runs and results when the app has **Require sign-in** on, and always to run a template that costs credits. |

## Sign-in (apps with users)

Users sign in **per app**: a Restyle account is separate from any other app's. An admin turns the
methods on (one or both) in the console (Admin → Apps → the app → App settings → Sign-in).

### App config: `GET /v1/app`

Call on start, before sign-in, to decide which buttons to show:

```json
{
  "app": {"slug": "reelify", "name": "Reelify", "description": "", "platform": "android"},
  "sign_in": {
    "google": true, "phone": true, "google_client_id": "1234-abc.apps.googleusercontent.com",
    "phone_provider": "msg91", "firebase_project_id": null
  },
  "require_login": true,
  "payments": {"provider": "razorpay", "mode": "test", "razorpay_key_id": "rzp_test_…"}
}
```

`payments.provider` is `none`, `razorpay` or `phonepe`, as set in the console (Admin → Apps → the app →
App settings). `none` means purchases aren't possible yet: show plans without a buy action.

`sign_in.phone_provider` (set per app in the console; `null` when phone sign-in is off) picks the phone flow:

- `msg91`: our server texts the code and checks it, with the two calls below.
- `firebase`: the app verifies the number with Firebase Authentication, then exchanges Firebase's ID token
  with `POST /v1/app/auth/firebase`. `sign_in.firebase_project_id` is the project the app's
  `google-services.json` must be from.

Each app accepts only its own flow: the other one is 403 `sign_in_method_disabled`. Accounts are keyed by
phone number either way, so moving an app from one to the other keeps its users' accounts.

### Phone number (`msg91`): `POST /v1/app/auth/otp/send`, then `POST /v1/app/auth/otp/verify`

```
POST /v1/app/auth/otp/send     {"phone": "9876543210"}        (10 digits = India; or +<country><number>)
-> 200 {"challenge_id": "…", "phone": "+919876543210", "expires_in_s": 300, "resend_after_s": 30}

POST /v1/app/auth/otp/verify   {"challenge_id": "…", "code": "123456"}
-> 200 {"token": "cas_…", "expires_at": "…", "is_new": true, "user": {…}}
```

- A code is valid for 5 minutes and for 5 tries. A wrong code is 400 `otp_invalid` with
  `details: [{"attempts_left": n}]`; an expired, used or exhausted one is 400 `otp_expired` (ask for a new one).
- Asking again within `resend_after_s` is 429 `rate_limited` with `details: [{"retry_after_s": n}]`. There are also
  hourly limits per number, per device and per network.
- For Play Store review, the server can have fixed test numbers (`OTP_TEST_NUMBERS`): no SMS is sent.

### Phone number (`firebase`): `POST /v1/app/auth/firebase`

Sign the number in with the Firebase Auth SDK (`PhoneAuthProvider.verifyPhoneNumber`, then
`signInWithCredential`; Firebase sends the SMS and can read it automatically), then send the signed-in
user's ID token:

```
val idToken = Firebase.auth.currentUser!!.getIdToken(false).await().token
POST /v1/app/auth/firebase   {"id_token": "eyJ…"}
-> 200 {"token": "cas_…", "expires_at": "…", "is_new": true, "user": {…}}
```

The session is ours from here on: sign out of Firebase after the exchange if the app doesn't use it
otherwise. A token from another Firebase project, expired, or from a sign-in other than phone is 401
`invalid_token`. Test numbers for Play review are set in the Firebase console (Authentication → Sign-in
method → Phone → Phone numbers for testing).

### Google: `POST /v1/app/auth/google`

Get an ID token with Credential Manager (`GetSignInWithGoogleOption` or `GetGoogleIdOption`) for
**`sign_in.google_client_id`** (the OAuth *Web* client id, not the Android one), and send it:

```
POST /v1/app/auth/google   {"id_token": "eyJ…"}
-> 200 {"token": "cas_…", "expires_at": "…", "is_new": false, "user": {…}}
```

A token for another client id, expired, or for an unverified email is 401 `invalid_token`.

### The session

- Keep `token` in encrypted storage and send it as `Authorization: Bearer <token>` on every call.
- It lasts 90 days and is extended each day it is used. A 401 `unauthenticated` with a token means it ended
  (signed out elsewhere, blocked, account deleted): clear it and show sign-in.
- `POST /v1/app/auth/logout` ends it. `DELETE /v1/app/me` deletes the account (required by Play): personal data
  is removed, every session ends, remaining credits are lost.

### The user: `GET /v1/app/me`

```json
{
  "id": "…", "name": "Priya", "email": null, "phone": "+919876543210", "photo_url": null,
  "sign_in": "phone", "credits": 38,
  "subscription": {"id": "…", "plan": {"id": "…", "slug": "monthly", "name": "Monthly"}, "status": "active",
                   "provider": "manual", "current_period_start": "…", "current_period_end": "…",
                   "next_credit_grant_at": null, "created_at": "…"},
  "created_at": "…"
}
```

`PATCH /v1/app/me {"name": "…"}` renames. `GET /v1/app/me/credits` is the credit history, newest first
(`reason`: `signup`, `subscription_grant`, `generation`, `refund`, `admin_adjust`).

## Credits and plans

- Credits belong to the user **in this app**: a balance and a history (`GET /v1/app/me/credits`) per app account.
- Each template has a `credit_cost` (in the template list). The server checks the balance and charges it
  when the run is accepted (202), in the same transaction as the job, so parallel runs can't overspend.
  The 202 response carries `credits`, the balance after the charge: show it at once. If the job
  **fails**, the credits come back automatically (a `refund` entry); refresh `GET /v1/app/me` after a
  failure to show it. Short on credits: 402 `insufficient_credits` with
  `details: [{"credits": 1, "required": 2}]` → show the Subscribe screen.
- A template that costs credits always needs a signed-in user, even when the app doesn't require sign-in
  (the app key alone can be pulled out of an APK). Without a session it is 401 `unauthenticated`:
  show sign-in. Free templates (`credit_cost` 0) run without one.
- `GET /v1/app/plans` lists the plans to show on the Subscribe screen, in order:
  `{"id", "slug", "name", "description", "price_minor", "currency", "billing_period", "credits_per_month", "badge"}`.
  `price_minor` is in paise (19900 = ₹199). Every plan grants `credits_per_month` each month, yearly ones too.
- **Payments are not connected yet.** Until they are, an admin gives a plan to a user in the console
  (Admin → Apps → the app → Users). Show prices, and a "coming soon"/contact action instead of a purchase.

## Endpoints

### List templates — `GET /v1/app/templates`

Needs the user's session when the app has **Require sign-in** on (401 `unauthenticated` otherwise).
Returns the app and its **active** templates, in the order set in the app's dashboard. Draft and
deleted templates are never returned.

```json
{
  "app": {"slug": "pixel-fun", "name": "Pixel Fun", "description": "", "platform": "android"},
  "templates": [
    {
      "id": "7d4c…", "slug": "ghibli-gemini", "title": "Ghibli Image Generation",
      "description": "Turns a photo into a hand-painted anime film still.",
      "media_type": "image", "version": 3,
      "inputs": [{"name": "photo", "label": "Your photo", "required": true}],
      "variables": [{"name": "mood", "label": "Mood", "default": "sunny", "max_length": 60,
                     "choices": ["sunny", "rainy"]}],
      "model": "gemini-nano-banana-2.1", "allowed_models": [],
      "has_reference_images": false,
      "cover_url": "/v1/app/templates/ghibli-gemini/cover?v=3",
      "credit_cost": 2
    }
  ]
}
```

How to build the screen from it:
- One card per template: `title`, `description`, cover image from `cover_url` (send the same headers;
  it changes when the template changes, so it is safe to cache by URL), or a placeholder when `null`.
- `inputs`: one image picker per entry; `label` is the text to show; `name` is the form field name.
- `variables`: a text field per entry (max `max_length`), or a dropdown when `choices` is set;
  prefill with `default`. Users may leave them unchanged.
- `allowed_models`: if not empty, the user may pick one of these instead of `model` (optional).
- `GET /v1/app/templates/{slug}` returns one template in the same shape.

The list can change at any time (editors add, reorder, deactivate or delete templates). Fetch it on app
start / pull-to-refresh; don't hard-code slugs.

### Run a template — `POST /v1/app/templates/{slug}/generations`

`multipart/form-data`:
- one **file** per input slot, field name = the slot `name` (e.g. `photo`). PNG, JPEG or WebP,
  at most 10 MB. Downscale large camera photos on the device first (long side ~2048 px is enough);
  the server downscales to 2048 anyway and strips EXIF/GPS.
- `variables` (optional): JSON object as a string, e.g. `{"mood": "rainy"}`.
- `model` (optional): one of `allowed_models`.

Response `202` with the job (see below), `status: "queued"`, plus `credits`: the signed-in user's
balance after paying for this run (`null` without a signed-in user).

### Poll a job — `GET /v1/app/generations/{id}`

Poll every 2 s (back off to 5 s after 30 s) until `status` is `succeeded` or `failed`. Image jobs
usually take 5–30 s; video can take minutes.

```json
{
  "id": "1f0e…", "status": "succeeded", "media_type": "image",
  "template": {"id": "7d4c…", "slug": "ghibli-gemini", "title": "Ghibli Image Generation", "version": 3},
  "inputs": [{"id": "…", "slot": "photo", "url": "/v1/app/inputs/…", "mime_type": "image/jpeg", "width": 768, "height": 1024}],
  "assets": [{"id": "…", "url": "/v1/app/assets/…", "mime_type": "image/png", "width": 768, "height": 1024,
              "size_bytes": 1234567, "duration_seconds": null}],
  "error": null, "attempt": 1, "max_attempts": 3,
  "created_at": "…", "started_at": "…", "finished_at": "…"
}
```

- `assets[].url`: download with the same headers. Use `mime_type` to choose image vs. video view.
- `failed` jobs carry `error.code`: `content_policy` (the provider refused this photo/prompt; tell the
  user to try another photo), `timeout`, `provider_unavailable`, `worker_lost`, `invalid_request`,
  `internal_error`. A job may show `queued` again with `attempt` > 1 while it is retried; keep polling.
- `GET /v1/app/generations` lists the signed-in user's recent jobs (without a session: this device's,
  needs `X-Device-Id`), newest first. Use it for "My creations".

A job can only be read by the app that created it: a signed-in user's job only by that user (on any
device); a job made without a session only with the same device id.

## Errors

Every error is JSON: `{"error": {"code": "...", "message": "...", "field": "...", "details": [...]}}`.

| Status | `code` | Meaning / what to do |
|---|---|---|
| 401 | `unauthenticated` | missing, wrong or revoked `X-App-Key` (the build has an old key), or the user's session is missing or has ended (sign in again), or a template that costs credits was run without signing in |
| 401 | `invalid_token` | the Google or Firebase ID token was refused |
| 400 | `otp_invalid` / `otp_expired` | wrong code (`attempts_left` in details) / ask for a new code |
| 402 | `insufficient_credits` | not enough credits for this template; `details` has `credits` and `required` |
| 403 | `app_disabled` | the app was switched off in the console; show a maintenance message |
| 403 | `account_blocked` | the user was blocked by an admin |
| 403 | `sign_in_method_disabled` | this sign-in method is off for the app |
| 404 | `not_found` | template no longer enabled/active, or job not visible; refresh the list |
| 413 | `payload_too_large` | photo over 10 MB |
| 422 | `validation_error` | `details[]` has `{field, message}`: `photo` (not an image / missing), `variables.mood`, `model` |
| 429 | `rate_limited` | the app's daily limit or this device's hourly limit is reached; ask the user to try later |
| 503 | `provider_unavailable` | the model behind the template isn't available on the server right now |

## Kotlin (OkHttp) sketch

```kotlin
val client = OkHttpClient.Builder()
    .addInterceptor { chain ->
        val req = chain.request().newBuilder()
            .header("X-App-Key", BuildConfig.STUDIO_APP_KEY)
            .header("X-Device-Id", installId)          // UUID generated once, stored in prefs
        session.token?.let { req.header("Authorization", "Bearer $it") }   // after sign-in
        val res = chain.proceed(req.build())
        if (res.code == 401 && session.token != null) session.clear()       // ended: show sign-in
        res
    }.build()

// sign in with a phone code
val sent = post("$base/v1/app/auth/otp/send", """{"phone":"9876543210"}""")   // -> challenge_id
val signIn = post("$base/v1/app/auth/otp/verify", """{"challenge_id":"$id","code":"$code"}""")
session.token = signIn.token                                                 // EncryptedSharedPreferences

// or with Google: Credential Manager ID token for config.sign_in.google_client_id
val signIn = post("$base/v1/app/auth/google", """{"id_token":"${credential.idToken}"}""")

// list
val catalog = client.newCall(Request.Builder().url("$base/v1/app/templates").build()).execute()

// run
val body = MultipartBody.Builder().setType(MultipartBody.FORM)
    .addFormDataPart("photo", "photo.jpg", jpegBytes.toRequestBody("image/jpeg".toMediaType()))
    .addFormDataPart("variables", """{"mood":"rainy"}""")
    .build()
val job = client.newCall(Request.Builder()
    .url("$base/v1/app/templates/ghibli-gemini/generations").post(body).build()).execute()

// poll GET $base/v1/app/generations/{id} until status is succeeded/failed,
// then load assets[0].url (prefix with $base) through the same client.
```

With Glide/Coil, load `cover_url` and asset URLs through the same OkHttp client so the headers are sent.

## Try it with curl

```bash
KEY=cak_...; DEV=test-device-1; B=http://<server>:8010
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" $B/v1/app
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" -H "Content-Type: application/json" \
     -d '{"phone":"9876543210"}' $B/v1/app/auth/otp/send          # dev server: the code is in the api log
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" -H "Content-Type: application/json" \
     -d '{"challenge_id":"<id>","code":"<code>"}' $B/v1/app/auth/otp/verify
AUTH="Authorization: Bearer cas_..."                                # add -H "$AUTH" below when sign-in is required
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" -H "$AUTH" $B/v1/app/me
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" $B/v1/app/templates
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" -F photo=@me.jpg -F 'variables={"mood":"rainy"}' \
     $B/v1/app/templates/ghibli-gemini/generations
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" $B/v1/app/generations/<job id>
curl -H "X-App-Key: $KEY" -H "X-Device-Id: $DEV" -o out.png $B/v1/app/assets/<asset id>
```

## Security

- An app key shipped inside an APK **can be extracted**. Treat it as an identifier, not a secret:
  anyone with it can run the app's enabled templates. What limits the damage:
  - per-app **daily job limit** and per-device **hourly limit** (set them in the console);
  - **key rotation**: create a new key, ship it in an update, then revoke the old one;
  - **disable** the app in the console to stop all calls at once.
- Stronger options for later: Google Play Integrity attestation per request, or calling this API from
  your own backend instead of from the device.
- Serve the API over **HTTPS** before release; on plain HTTP the key and users' photos cross the
  network unencrypted. (Android also blocks cleartext HTTP by default.)
- Users' photos are stored on the server with the job and sent to the AI provider behind the
  template. Cover this in the app's privacy policy.
- The session token is the user's identity: keep it in encrypted storage, never log it. Credits are only
  ever changed by the server; the app shows the balance from `/v1/app/me`.

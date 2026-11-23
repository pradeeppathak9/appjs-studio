# Restyle web

The Restyle app in the browser: sign in (Google or a phone code), pick a style, add a photo, get the
styled image, and see your creations, credits and plans. It is a client of AppJs Studio's per-app API
(`/v1/app/*`, contract: [`../studio/docs/APPS_API.md`](../studio/docs/APPS_API.md)), like the Android
app in [`../restyle`](../restyle), with the same wording and look.

React 19, Vite, TanStack Query, React Router; plain CSS with the Android design's tokens.

## Develop

Needs Studio running on :8010 (`cd ../studio && docker compose up -d`).

```bash
cp .env.example .env.local      # VITE_APP_KEY = the restyle-ai app key (same as appjs.appKey on Android)
npm ci
npm run dev                     # http://localhost:5180, /v1 is forwarded to Studio
npm run typecheck && npm run lint && npm test && npm run build
```

The dev server proxies `/v1` to Studio, so the page and the API share one origin (no CORS). Locally,
Studio's `OTP_DEV_CODE` makes every phone sign-in code that value. Generating calls a real AI provider
and spends the account's credits.

## Docker

```bash
docker build -t restyle-web .
docker run -p 8081:80 -e APP_KEY=cak_... -e STUDIO_API=http://api:8000 --network studio_default restyle-web
```

- `APP_KEY` is written into `/config.js` when the container starts, so one image serves any environment.
- nginx forwards only `/v1/app` and `/v1/app/*` to `STUDIO_API` (the console and admin API are not
  reachable through this site) and keeps the browser's `Host`, which Studio checks on writes made
  before sign-in.
- In production it runs next to Studio: [`../studio/deploy`](../studio/deploy) (`RESTYLE_DOMAIN`).

## Layout

```
src/lib/api.ts        Studio client: headers, errors, endpoints
src/lib/session.ts    session token + device id (localStorage)
src/lib/queries.ts    TanStack Query hooks; images behind the API are fetched as blobs
src/lib/styles.ts     templates → styles (category and colour hints, same as Android)
src/lib/image.ts      crop to 1:1 / 4:5 / 9:16 and downscale before upload
src/lib/format.ts     prices, labels, error messages (Android wording)
src/pages/            Login, Home, Create, Result, Creations, Account (profile, subscribe)
docker/               nginx config template and the start script that writes /config.js
```

## Notes

- Google sign-in uses Google Identity Services with the app's OAuth **Web** client id (from
  `GET /v1/app`). Add the site's origin (e.g. `http://localhost:5180`, `https://restyle.example.com`) to
  that client's Authorized JavaScript origins.
- Phone sign-in works when the app uses MSG91 codes; Firebase phone sign-in is Android-only for now.
- Payments aren't connected (same as Android): the plans screen explains that support activates plans.

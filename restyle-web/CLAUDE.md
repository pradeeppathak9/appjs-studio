# restyle-web

The Restyle web app: a browser client of AppJs Studio's `/v1/app/*` (contract: `../studio/docs/APPS_API.md`),
matching the Android app in `../restyle` (same wording, flows and look). Read README.md first.

- Commands: `npm run dev` (:5180, proxies /v1 to Studio on :8010; key in `.env.local`), and the check:
  `npm run typecheck && npm run lint && npm test && npm run build`.
- Don't generate images while testing unless asked: it calls a paid provider and spends credits.
- If the API has to change, change Studio first (routes + APPS_API.md + tests), then this app and the
  Android app.
- The app key is public by design (like the APK's). Never put other secrets in the page or `config.js`.
- `docker/default.conf.template` must keep forwarding only `/v1/app` and `/v1/app/*`, and keep `Host`.

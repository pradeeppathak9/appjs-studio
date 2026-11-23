# AutoRev console

React 19 + TypeScript + Vite, with Mantine for UI and TanStack Query for data. Same stack and look as
the AppJs Studio console.

```bash
npm ci
VITE_API_URL=http://localhost:8000 npm run dev   # http://localhost:3000 (allowed by the API's CORS_ORIGINS)
npm run typecheck && npm run lint && npm test && npm run build
```

`VITE_API_URL` defaults to `https://api.autorev.postkaro.app` and is baked in at build time (the
Dockerfile takes it as a build arg). The production image serves `dist/` with nginx.

API types come from the backend's OpenAPI schema: export it to `openapi.json`, then `npm run gen:api`.

```bash
cd ../backend && uv run --python 3.12 --no-project --with-requirements requirements.txt \
  python -c "import json; from app.main import app; print(json.dumps(app.openapi()))" > ../frontend/openapi.json
```

## Layout

- `src/components/Layout.tsx`: app shell (sidebar, app switcher, user menu, theme)
- `src/pages/`: ported pages (sign-in, apps, account, app and admin layouts)
- `src/legacy/`: pages not yet ported from the old Create React App console. They render inside the new
  shell on a light panel; each moves to `src/pages/` as it is rewritten.

## Create a user (local backend)

```bash
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "secret123", "full_name": "Test User"}'
```

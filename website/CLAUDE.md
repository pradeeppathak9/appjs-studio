# website

Company website for APPJS Technologies Private Limited (Delhi, CIN U62011DL2023PTC423950), the
entity that owns MarktMakrs.

- Everything is in one `index.html`: inline CSS (tokens on `:root`), schema.org Organization JSON-LD
  in `<head>`, sections `#about`, `#products`, `#company`, `#contact`. No build, no JS framework.
- `privacy.html` and `terms.html` (served at `/privacy` and `/terms` by Caddy's `try_files {path}.html`) are the
  company's privacy policy and terms of service. They cover Restyle AI (whose login page links to them) and are
  the URLs in the Google OAuth branding for Restyle. Keep their facts in step with what `../studio` actually
  stores and does (no automatic photo deletion yet, credits refunded on failed jobs, Delete account in the app).
- Preview: open `index.html` directly, or `python3 -m http.server` from this folder.
- MarktMakrs is one of the company's products. Its legal links (privacy, terms, refund) point at
  `marktmakrs.in`; keep them in step with `../marktmakrs` and its `docs/phonepe-website-compliance-plan.md`.
- The company contact email (JSON-LD, Company information, Contact) is `contactappdojs@gmail.com`.
- `<head>` carries the `facebook-domain-verification` meta tag for Meta Business: don't remove it.
- The canonical link is `https://appjs.tech/` (served by Caddy in `../infra`).
- Company details (name, CIN, address, founding year) appear in both the JSON-LD and the page body:
  change both together.

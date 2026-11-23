# website

Company website for APPJS Technologies Private Limited (Delhi, CIN U62011DL2023PTC423950), the
entity that owns MarktMakrs.

- Everything is in one `index.html`: inline CSS (tokens on `:root`), schema.org Organization JSON-LD
  in `<head>`, sections `#about`, `#products`, `#company`, `#contact`. No build, no JS framework.
- Preview: open `index.html` directly, or `python3 -m http.server` from this folder.
- Legal links (privacy, terms, refund) and the support email point at `marktmakrs.in`. Keep them in
  step with `../marktmakrs` and its `docs/phonepe-website-compliance-plan.md`.
- The canonical link is `https://appjs.tech/` (served by Caddy in `../infra`).
- Company details (name, CIN, address, founding year) appear in both the JSON-LD and the page body:
  change both together.

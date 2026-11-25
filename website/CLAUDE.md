# website

Company website for APPJS Technologies Private Limited (Delhi, CIN U62011DL2023PTC423950), the
entity behind Restyle AI and MarktMakrs.

- `index.html` holds the whole home page: inline CSS (tokens on `:root`: navy, blue accent, Inter), schema.org
  Organization JSON-LD in `<head>`, sections `#apps`, `#about`, `#company`, `#contact`. No build, no JS framework.
  `assets/` has the app icons and the MarktMakrs screenshot (copied from `../restyle-web/public` and
  `~/Work/marktmakrs/frontend/public`); the Restyle phone in the hero is drawn in HTML/CSS.
- The company's offering is "apps" (not "software" or "products") in copy, nav, footer and Company information.
- `privacy.html` and `terms.html` (served at `/privacy` and `/terms` by Caddy's `try_files {path}.html`) are the
  company's privacy policy and terms of service. They cover Restyle AI (whose login page links to them) and are
  the URLs in the Google OAuth branding for Restyle. Keep their facts in step with what `../studio` actually
  stores and does (no automatic photo deletion yet, credits refunded on failed jobs, Delete account in the app).
- Preview: open `index.html` directly, or `python3 -m http.server` from this folder.
- Apps (Restyle AI, MarktMakrs) are named only where apps are listed: the `#apps` cards, the hero mockups, the
  "Apps" row in Company information, the footer's Apps list and the JSON-LD `owns`. The rest of
  the site, and `privacy.html` / `terms.html`, don't mention MarktMakrs or link to its policies.
- The company contact email (JSON-LD, Company information, Contact) is `contactappdojs@gmail.com`.
- `<head>` carries the `facebook-domain-verification` meta tag for Meta Business: don't remove it.
- The canonical link is `https://appjs.tech/` (served by Caddy in `../infra`).
- Company details (name, CIN, address, founding year) appear in both the JSON-LD and the page body:
  change both together.

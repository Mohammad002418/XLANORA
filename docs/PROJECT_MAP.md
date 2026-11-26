# XLANORA: Project Map

Role: Staff Software Engineer / Tech Lead. This file is the architectural source of truth for the XLANORA website.

## 1. Assumptions (confirm before build)

| # | Assumption | Basis |
|---|---|---|
| A1 | Marketing website for XLANORA, a service-business brand (exact offer not yet specified). | Brand logo and reference layout. |
| A2 | Audience is global: customers in any country, not only Saudi Arabia. Launch in English (LTR, default) and Arabic (RTL). Structure allows more languages later. | Client instruction (updated). Arabic kept because the brand's visual references are Arabic-market. |
| A3 | Site is informational plus lead capture (contact / quote request). No e-commerce, no user accounts in v1. | Scope-creep rule: smallest set that meets the goal. |
| A4 | Visual reference: the freelance template (Webflow, screenshot). Use its structure only (sticky nav, hero with a large headline and a circular image, CTA button, service tags). Do not copy its visuals, colours, or copy. | Client instruction. |
| A5 | Brand: XLANORA logo (blue gradient X with orbit stroke, navy geometric wordmark). Brand colours are derived from the logo. | Logo file. |

Open questions (blocking for final copy and content, not for the skeleton):
1. What services does XLANORA sell, and what is the primary CTA (call, WhatsApp, form, booking)?
2. Which photos are real team or project photos, and which are AI-generated stand-ins for placeholders? Some images are labelled with other brand names (for example "Riyadh Design Collective", "Riyadh Smart Home Services"). Confirm these are placeholders and not a competitor's brand.
3. Is there a required domain or hosting provider?
4. Do you need a CMS, or are content edits made by a developer?
5. Which languages beyond English and Arabic are needed at launch? Which markets and currencies are targeted? Global reach affects the language switch, currency display, and legal pages (privacy, terms, cookies per region).

## 2. TECH_STACK

Principle: simplicity first. The brochure-style site needs no framework runtime.

| Layer | Choice | Reason |
|---|---|---|
| Output | Static site (HTML, CSS, vanilla JS) | No server, cheap hosting, fast. |
| Build | None in v1. Optional: a single small generator later if pages multiply. | Avoid tooling not yet needed. |
| Styling | Plain CSS with custom properties (design tokens). Logical properties (`margin-inline-start`) so RTL is automatic. | Keeps RTL correct without a library. |
| i18n | One HTML file per page per language (`/en/`, `/ar/`, later `/fr/` etc.) with `lang` and `dir` set on `<html>`. Copy kept in each file. Hreflang tags link the versions for search engines. | Simple and SEO-correct for a global audience. Adding a language = copying a folder. |
| Forms | Form posts to a hosted form service (e.g. Formspree or the host's native form handler). | No backend to maintain. |
| Images | Pre-optimised WebP/AVIF with `srcset`, plus `loading="lazy"` below the fold. | Performance. |
| Analytics | Optional, privacy-respecting (e.g. Plausible). Decided later. | Not required for v1. |
| Hosting | Any static host (Netlify, Cloudflare Pages, Vercel). Decided with the client. | Static hosting covers all needs. |
| Version check | Confirm current stable versions of any tool actually used (in the build phase, not here). | Required by protocol. Not pinned in this document. |

Rejected for v1: Webflow/WordPress (vendor lock-in, unnecessary for this scope), a SPA framework (no app-like behaviour needed), a CMS (no content editors identified).

## 3. SYSTEM_FLOW

```
Visitor
  |
  v
Static host (CDN)
  |-- /            -> redirect by language (Accept-Language / saved choice), default /en/
  |-- /en/         -> English (LTR) pages, default
  |-- /ar/         -> Arabic (RTL) pages
  |-- /<lang>/     -> future languages, same structure
  |-- /assets/     -> optimised images, logo, CSS, JS
  |
Lead capture
  |-- Contact form submit -> hosted form service -> email to XLANORA team
  |-- WhatsApp / phone links (no backend)
```

No server-side logic, no database, no auth in v1.

## 4. SITEMAP (per language)

| Page | Purpose | Notes |
|---|---|---|
| Home | Hero, value proposition, services overview, primary CTA | Hero follows the template structure (headline, circular image, CTA). |
| Services | List of services with short descriptions | One section per service. Count depends on answer to Q1. |
| About | Who XLANORA is, team, approach | Uses real team photos when provided. |
| Work / Projects | Selected work | Optional in v1. Can be added later. |
| Contact | Form, phone, WhatsApp, address (if any) | Single primary CTA. |

Blog (template has one) is excluded from v1 under scope control.

Global-audience additions (v1, minimal): a Privacy and Terms page per language, cookie notice if analytics is added, and contact details that show time zone or region where relevant.

## 5. DESIGN TOKENS (initial, to refine in build)

Colour (derived from logo, 5 named values):
- `--xl-navy` `#0B1F5C`: wordmark, text on light
- `--xl-blue` `#0A5BFF`: primary accent, CTA
- `--xl-sky` `#00B2FF`: highlight, orbit gradient end
- `--xl-ink` `#0E1426`: body text
- `--xl-paper` `#F7F9FD`: background

Type: one family, two weights, clear scale. Arabic and Latin need a matched pair. Candidate pairs will be chosen in build (for example an Arabic grotesque with a matching Latin face). Do not use the template's typeface.

Layout: left-aligned for Latin, right-aligned for Arabic (logical alignment via `text-align: start`). Single column on mobile, max content width about 1200px.

Shape: no card-grid default. Use the logo's diagonal orbit stroke as one recurring graphic element, and keep everything else quiet.

## 6. COMPONENTS

- Header: logo, nav links, language switch, primary CTA. Collapses to a menu on mobile.
- Hero: headline, one-line subtitle, primary CTA, one image.
- Service block: title, description, optional image.
- Contact form: name, phone, message, submit. Client-side validation with clear messages.
- Footer: logo, links, language switch, contact.
- Floating WhatsApp button (only if confirmed in Q1).

## 7. QUALITY FLOOR

- Responsive down to 360px. No horizontal scroll.
- Visible keyboard focus on every interactive element.
- Respect `prefers-reduced-motion`. Motion limited to one page-load moment.
- Contrast at least WCAG AA.
- Arabic font loaded and tested for legibility.
- Works for visitors worldwide: fast on slow connections (small page weight), no region-locked content, no assumed local phone format in the form.
- Lighthouse performance target agreed in build.

## 8. ASSET INVENTORY

| Folder | Contents | Status |
|---|---|---|
| `assets/brand/` | XLANORA logo | Use for header, footer, favicon (needs vector version for best quality). |
| `assets/reference/` | Freelance template screenshot | Reference only. Not shipped. |
| `assets/photos/` | 11 AI-generated images (Gemini) | Placeholders. Some show other brand names. Replace before launch (see Q2). |

Note: the logo is a JPEG. A vector (SVG) version is needed for crisp rendering and a favicon.

## 9. SCOPE CONTROL (out of scope for v1)

- Blog, e-commerce, booking system, user accounts, CMS, analytics dashboards, chat widgets.
- Any new feature must be added to this file and approved before work starts.

## 10. NEXT STEPS

1. Client answers Q1 to Q4.
2. Confirm A1 to A5 (A2 now global) or correct them.
3. Build the skeleton: folder layout, tokens, header, footer, home hero, RTL and LTR switch.
4. Review skeleton against the freelance reference for structure only, then fill in content pages.

## 11. SKILL STATUS

- `frontend-design`: loaded. Applied: design plan reviewed against the brief, no template defaults.
- `ui-ux-pro-max`: NOT installed at `~/.claude/skills/ui-ux-pro-max`. This plan was built without it. Install it and this plan can be re-checked against its rules.

## 12. BUILD STATUS (live)

- Scope: option A assumed (this map is the scope; booking marketplace deferred). Owner has not yet confirmed. See `docs/ORPHANS_AND_PENDING.md` C1.
- Step 1 done: skeleton at `site/` (EN and AR home pages, tokens, header with language switch, hero, footer, root redirect to `/en/`, hreflang tags).
- Not yet built: Services, About, Work, Contact pages; contact form; circular-image orbit accent; Arabic font pair confirmed; image optimisation (WebP/AVIF); Privacy and Terms pages.
- Not verified in a browser. Structure and links checked by script only.
- Next-js scaffold at project root (`app/`, `components/`, `package.json`) is not used by `site/`. Keep or remove after C1.
- Step 2 done (owner approved the plan; name XLANORA, blue palette from the logo, five page types, services from the photos and this map): `build/content.py` and `build/build.py` generate EN and AR pages into `site/`. Pages: Home, Services, Service detail (x3), About, Contact.
- Step 3 done: contact form with validation, honeypot and an email address `mohamedtarigosman@gmail.com` (stored in content, sent only if SMTP is configured).
- Step 4 done: local database (`server/app.py`, SQLite, `server/schema.sql`) and Supabase version (`supabase/migrations/001_init.sql` with RLS).
- Step 5 done: tests. `tests/test_server.py` and `tests/test_site.py` (44 pass). Browser test on phone (360 px) and desktop: 101 of 101 pass.
- Not yet done: Supabase SQL not run against a live PostgreSQL in this sandbox; Google Fonts not loaded in the sandbox; no real prices; image labels to confirm (see ORPHANS_AND_PENDING).
- Step 6 done (latest): nine services (the original three plus Graphic Design, Web Development, Video Editing, Digital Marketing, Translation Services, Social Media Management). Added to content, labels, both databases (SQLite migration in `server/app.py`, Supabase `003_services.sql`), contact form and sign-up dropdowns, and the services page collage. Fixed: sign-up and contact form rejected new services (duplicate hard-coded lists in JS now read the dropdowns); header button padding; logo background; `netlify.toml` pointed at the Next.js scaffold; `site/_headers` was not generated (now generated from the server's header list); smooth transitions for buttons, cards and the mobile menu. Tests: 86 unit, 101 page checks, 35 account checks, 48 new-service checks, 14 Supabase RLS checks on PostgreSQL 16.

- Step 7 done (booking system, V7): `server/bookings.py` and `server/schema.sql` (local, SQLite) and `supabase/migrations/004_bookings.sql` + `005_availability_rpc.sql` (Supabase). Freelancer dashboard: services, weekly hours (one window per day), bookings (accept, reject, complete). Client dashboard: search with category, keyword, max price and sort; slot picker; booking with note; my bookings with cancel. Password change on both backends. Database rules refuse overlaps, past times, wrong lengths, foreign services and client-side writes. Tests: 150 unit (2 skipped: forgot-password and email verification, not built), 34 browser checks (`tests/e2e_booking.py`), 13 Supabase booking checks and 15 RLS notices on PostgreSQL 16.
- Not built: the Supabase dashboard path is written but was not run against a live Supabase project (none available here); it was checked only through the PostgreSQL functions. Admin dashboard, email verification and forgot-password (need SMTP), server-side anti-spam on Supabase, lead privacy decision, Next.js scaffold removal, "load more" for long request lists on the dashboard.
- Step 8 done (V8): public Portfolio section (`portfolio.html`, both languages) and freelancer portfolio management on the dashboard, in both versions. Local: `portfolio_items` table, `/api/portfolio` and `/api/my/portfolio`. Supabase: `006_portfolio.sql` (RLS, category trigger, https-only links, `list_portfolio`). Tests: 164 unit (162 pass, 2 skipped), `tests/e2e_site.py` (27 browser checks: every page in EN and AR on phone and desktop, plus the portfolio flow), `tests/supabase_portfolio_test.sql` (9 checks). Fixes: Supabase requests were blocked by the content-security policy (now `*.supabase.co` is allowed); image policy now allows https images for portfolio items; filter button alignment. Full guide: `docs/XLANORA_GUIDE.md`.

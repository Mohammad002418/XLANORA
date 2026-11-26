# ORPHANS & PENDING

Live list. Updated at the end of every task. An item leaves this list only when it works end to end and is verified.

## Open conflicts (need owner decision before build)

| # | Conflict | Sources | Options |
|---|---|---|---|
| C1 | Two different scopes: a booking marketplace (Next.js, Supabase, auth, bookings) versus a brochure website (static HTML/CSS/JS, no backend, forms only). | `docs/ARCHITECTURE.md` (phase spec) vs `docs/PROJECT_MAP.md` (SYSTEM_FLOW, TECH_STACK) | A. PROJECT_MAP is the new scope; booking marketplace is deferred. B. Both: marketing site first, marketplace as a later module. C. Marketplace only; drop the brochure site. |
| C2 | Tech stack: Next.js with Supabase versus static site with no framework. | Phase spec section 2 vs PROJECT_MAP section 2 | Follows from C1. |
| C3 | Phase 1 scaffold was built for Next.js. Under a static site, `package.json`, `next.config.mjs`, `app/`, `components/` are not used. | Phase 1 files | Keep, replace, or archive after C1 is answered. |
| C4 | Phase-gate rule versus "full execution without stopping" in the execution prompt. | Owner's phase rule vs `docs/EXECUTION_ENGINE.md` | Current rule: stop at the end of each phase for approval. |

## Pending (blocked by owner answers)

- Services offered and primary CTA (PROJECT_MAP Q1).
- Real team photos versus placeholders (Q2).
- Domain and hosting provider (Q3).
- CMS need (Q4).
- Languages beyond EN/AR, and target markets and currencies (Q5).
- Arabic brand name and wordmark usage.
- Licensed image sources for hero, services, and team.

## Assets to resolve

- `assets/photos/*`: AI-generated stand-ins. Three images show other brand names: `planning-woman-blueprints.jpg` ("Riyadh Design Collective" on a sign and a door), `architect-woman.jpg` ("Riyadh Design Collective" on the badge and sign), and `smart-home-technician.jpg` ("Riyadh Smart Home Services" on a sign; the shirt badge text is not legible). Confirm they are placeholders, or replace them before launch.
- `assets/reference/freelance-template-screenshot.png`: reference only. Must not ship. Do not copy its visuals, colors or copy.
- `assets/brand/logo-original.jpg`: the owner's logo (JPEG). A vector version (SVG) is still needed for the header and favicon.
- `public/brand/logo-mark.svg` (created in Phase 1): this is my placeholder, not the owner's logo. It should be replaced with the real logo.

## Known gaps in the current build

- Supabase version (`supabase/migrations/001_init.sql`): written, not run against a live PostgreSQL (none available in the sandbox). Run it once in the Supabase SQL editor and test a submission.
- SMTP email is coded but not configured. Owner needs to set the SMTP variables (see README).
- Services have no real prices. Pages say "request a quote".
- The service text, team section copy and the "Why XLANORA" points are written by me and need the owner's review.
- Photos: three show other brand names (see Assets to resolve). All 11 photos are used as the owner asked.
- Google Fonts not loaded in the sandbox. Real browsers load them normally.

- `npm install`, `npm run build`, and `npm run typecheck` have not been run (package installs are blocked in this environment).
- Skill `ui-ux-pro-max` is not installed (noted in PROJECT_MAP section 11), so the design plan has not been checked against its rules.
- Phase 1 has no tests yet.

# Reusable prompt: build a full marketplace website from a name, a logo and details

Use this prompt with an AI coding assistant that can read and write files and run tests. Copy the prompt
below, replace every `{{PLACEHOLDER}}` with your own details, and attach your logo file. The prompt was
written from the XLANORA project, so the result uses the same features, the same security rules and the
same tests. It does not include any real account, password, key or domain.

Arabic summary: انسخ الأمر أدناه، واستبدل كل قيمة بين {{ }} بمعلومات موقعك (الاسم، الشعار، الفئات، المدينة، العملة، اللغات، البريد). أرفق ملف الشعار. يبني المساعد الموقع بالوظائف نفسها: تسجيل وتحقق من البريد، بحث وفلترة وترتيب، حجز بدون تعارض، طلبات دفع مباشر، تقييمات، صور وفيديو، لغتان مع RTL، robots.txt وsitemap، واختبارات. ولا يُضاف أي حساب أو مفتاح سري داخل الواجهة.

---

## The prompt

```
You are a senior full-stack engineer. Build a complete, working, bilingual marketplace website called
{{SITE_NAME}}. Work in phases and test each phase before moving on. Do not claim a feature works unless
you ran it and saw it work. Do not add fake buttons, placeholder handlers or features that only look
real.

### 1. The business
- Name: {{SITE_NAME}}. Tagline: {{TAGLINE}}. Logo: the attached file {{LOGO_FILE}}. Use it in the header,
  the footer and the browser icon. Keep its colours as the brand palette: {{BRAND_COLOURS}}.
- What it sells: {{WHAT_IT_SELLS}} (for example: freelance services, tutoring, home repairs).
- Service categories (start with these; the admin can add more later): {{CATEGORIES}}.
- Cities or regions: {{CITIES}}.
- Default currency: {{CURRENCY}}. If a second currency is needed, show the conversion as an estimate
  with the rate written in the configuration ({{SECOND_CURRENCY}} at {{RATE}}).
- Languages: English and Arabic, with full right-to-left layout for Arabic. Default: {{DEFAULT_LANGUAGE}}.
- Contact e-mail shown on the site: {{CONTACT_EMAIL}}. Domain, if any: {{DOMAIN}} (otherwise leave a
  placeholder and say so).
- Business rules: {{BUSINESS_RULES}} (for example: "no online payment; customer and provider agree the
  payment directly and each confirms it; no commission; a rating is allowed only after a completed,
  verified booking").

### 2. Roles and permissions
- Customer: register, verify the e-mail, search and filter services, view provider profiles and
  reviews, book an available time, cancel an eligible booking, keep a private wishlist, get e-mail
  alerts for a category, edit only their own profile, change only their own password.
- Provider (freelancer): publish up to {{MAX_ACTIVE_SERVICES}} active services with prices and
  descriptions, set weekly working hours, accept or reject bookings, mark a booking delivered, upload a
  profile photo, and manage a portfolio with photos and short videos.
- Administrator: created from the command line only (never through the website), with an inbox for
  contact messages, moderation of services and reviews, and category management.
- Enforce roles on the server for every request. Never trust a role, a price, an owner id or an
  administrator flag sent by the browser.

### 3. Features that must work end to end
1. Accounts: registration, e-mail verification, login, logout, password change from the user's own
   profile page only, and a "forgot password" flow that does not reveal whether an address exists.
2. Search: a real database search (not a filter on text already in the page) by service name, category,
   provider name, city and price range, with sorting and a result count. Empty results show a helpful
   message with a way to clear the filters.
3. Bookings: show free times for the next weeks, prevent past times, prevent double booking with a
   database constraint (not only in the browser), validate every time on the server, and support
   cancellation with the correct status change.
4. Direct payment orders: no payment gateway and no commission. The customer sees a clear notice to
   contact the provider before paying. Each side confirms the payment separately (method, amount,
   currency, optional note). Delivery is confirmed before a rating can be written. Either side can
   report a problem. Every change is recorded in an activity history.
5. Reviews: 1 to 5 stars and an optional comment, once per completed booking, moderated by the
   administrator.
6. Portfolio and photos: images up to 10 MB (JPEG, PNG or WebP) and videos up to 50 MB (MP4, WebM or
   MOV). Check the real file type from its first bytes, not only from the browser's claim. Show the
   limits in the upload text. Show videos with native controls. Replacing a file deletes the old one.
7. Public pages: home, services with filters, provider profile, about, contact, and login/register.
   Private pages must not be indexed.
8. SEO: a robots.txt that blocks private pages (dashboards, admin, login, account pages) and a
   sitemap.xml listing the public pages in both languages, generated at build time from the real
   public URL.
9. Contact form: messages go to the administrator inbox; the form shows success and error states.
10. Notifications: clear success and error messages after every action; loading and empty states on
    every list.

### 4. Two versions, one behaviour
- Version A (local): a small backend with a SQLite database and an API. It needs no paid service.
- Version B (Supabase): PostgreSQL migrations with row-level security, security-definer functions for
  the sensitive steps, storage buckets with size and type limits, and the same screens. The browser
  only ever receives the public anon key. The service-role key must never appear in the browser, the
  repository or the logs.
- Both versions must behave the same for every feature in section 3. Write a test that proves it.

### 5. Security rules (non-negotiable)
- No secrets in the repository. Configuration comes from environment variables; provide an example
  file with empty values.
- No hard-coded accounts, passwords or e-mail addresses anywhere in the code or the seed data.
- Validate all input on the server. Escape all output. Use textContent in the browser, never innerHTML
  with user data.
- Add a Content-Security-Policy and the usual headers (no framing, no MIME sniffing).
- Passwords are hashed with a slow, salted algorithm. Sessions are random tokens stored hashed, in
  HttpOnly cookies with SameSite protection.
- Rate-limit login and registration. Refuse oversized request bodies before reading them.
- Never disable TLS certificate checks or any other security control to make something run.

### 6. Build and deploy
- Static pages are generated by a build script (Python or Node) into a publish folder. The build
  writes robots.txt and sitemap.xml.
- Deploy target: Netlify (static site from the publish folder, with the security headers in a _headers
  file). The Supabase project is created by the owner; you prepare the migrations and the guide.
- Provide README.md (setup and run), docs/DEPLOY.md (the exact order of migrations and the dashboard
  settings to check) and docs/PUBLISH_GUIDE.md (step by step with GitHub, Supabase and Netlify, in
  English and Arabic).
- Do not connect any external account (GitHub, Supabase, Netlify) on the owner's behalf. Give the
  owner the steps instead.

### 7. Testing (required before you report success)
- Unit tests for the server rules: validation, roles, booking conflicts, upload checks, password change
  rules, the order workflow.
- Database tests for the Supabase version: row-level security for each role, the double-booking
  constraint, storage limits, and the order workflow. Run them on a fresh database.
- Browser tests (Playwright with Chrome) for: registration and login, logout, search and filters,
  booking and double-booking prevention, cancellation, uploading a photo and a video, the password form
  appearing only on the user's own profile, and the navigation's current-page state. Check both
  languages and a 390 px phone width with no horizontal scroll.
- Fix every failure you find. At the end, list exactly what you tested, what you could not test (for
  example, a live Supabase project or a live e-mail provider), and what remains.

### 8. Deliverables
1. The complete project as a folder and as a zip.
2. README.md, docs/DEPLOY.md, docs/PUBLISH_GUIDE.md.
3. The test results, with the number of checks that passed.
4. A short list of the decisions you made where the brief left room, and any open questions.

Start by proposing the architecture and the folder structure in one page. Then build phase by phase:
(1) setup and architecture, (2) public pages and design, (3) database and accounts, (4) search and
services, (5) bookings and orders, (6) dashboards, (7) security and tests, (8) deployment preparation.
Wait for my approval after each phase, and report what you built, which files changed, what the tests
showed, and what is still open.
```

---

## How to fill it in

| Placeholder | Example |
|---|---|
| `{{SITE_NAME}}` | Your brand name |
| `{{LOGO_FILE}}` | `logo.svg` or `logo.png`, attached |
| `{{BRAND_COLOURS}}` | `#0B5FFF` (primary), `#0E1A2B` (text) |
| `{{CATEGORIES}}` | Photography, Home maintenance, Education |
| `{{CITIES}}` | Riyadh, Jeddah, Dammam |
| `{{CURRENCY}}` | SAR |
| `{{MAX_ACTIVE_SERVICES}}` | 3 |
| `{{BUSINESS_RULES}}` | Write them exactly as you want them enforced |

Keep the business rules explicit. The assistant builds what the brief says, so a vague rule ("payments should be
safe") produces a vague result, while a precise one ("the customer pays the provider directly; both confirm the
payment") produces a working workflow.

## Checklist after the assistant reports "done"

1. Run the unit tests, the database tests on a fresh database, and the browser tests. Ask for the counts.
2. Open the site on a phone and in Arabic.
3. Search `grep -r "service_role" .` and check that it appears only in documentation, never in the browser code.
4. Create the administrator from the command line, not through the website.
5. Before going live, check the Supabase storage limits and the e-mail confirmation setting in the dashboard.

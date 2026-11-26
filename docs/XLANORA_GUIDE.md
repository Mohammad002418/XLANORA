# XLANORA: Complete Guide (V9)

XLANORA connects clients with independent freelancers in nine service areas. It is a bilingual (Arabic and English; Arabic is right-to-left) static website with accounts, bookings, a public portfolio, a financial system (commissions, earnings, payouts, subscriptions, refunds), and an administrator dashboard.

| Version | Backend | Where data lives | What works |
|---|---|---|---|
| **Local (SQLite)** | Python standard-library server | `server/data/xlanora.db` (created on first start) | everything, including finance and admin |
| **Supabase** | Supabase Auth + PostgreSQL + RLS | Your Supabase project | website, accounts, bookings, portfolio; finance and admin need the database migration and new functions (not wired yet) |

The rules (who may see what, no double bookings, money calculations) are enforced in the server or the database, not only in the browser.

For publishing, see `docs/DEPLOY.md`. For the security tests, see `docs/SECURITY_TEST_REPORT.md`. For the finance design, see `docs/FINANCE_PLAN.md`.

---

## 1. What the website contains

### Public pages (EN and AR)
- **Home:** hero, nine services, how it works, call to action.
- **Services** and one page per service (nine): Photography, Home Maintenance, Education and Training, Graphic Design, Web Development, Video Editing, Digital Marketing, Translation Services, Social Media Management.
- **Portfolio:** freelancers' work samples. Search by keyword, filter by category, sort by newest or title.
- **About**, **Contact** (rate-limited).
- **Sign in**, **Create account**.

### Account pages
- **Dashboard.** What you see depends on your role:
  - **Client:** search services, pick a date and a free time, add a note, request a booking, see "My bookings", cancel an eligible booking, pay for an accepted booking (sandbox), see your subscription and available plans.
  - **Freelancer:** My services, Weekly hours, Bookings (accept, reject, complete), My portfolio, **Earnings** (gross, commission, net, pending, available, reserved, paid out, history, payouts), request a payout, subscription and plans.
  - **Both:** change password.
- **Admin dashboard** (`admin.html`, EN and AR, marked noindex). Visible only to admin accounts. See section 3.

### Navigation
Home, Services, Portfolio, About, Contact, Dashboard (when signed in), "Request a quote", and the language switch. On phones the menu collapses into a button.

---

## 2. Roles and what each can do

| Action | Visitor | Client | Freelancer | Admin | Owner (server operator) |
|---|---|---|---|---|---|
| Browse services and portfolio | yes | yes | yes | yes | yes |
| Create an account | yes | yes (client) | yes (with specialty) | n/a | n/a |
| Book a free time | no | yes | no (not own services) | no | n/a |
| See booking contact details | no | after acceptance | after accepting | no special access | database |
| Accept, reject, complete bookings | no | no | own only | no | database |
| Manage services, hours, portfolio | no | no | own only | no | database |
| Pay for an accepted booking (sandbox) | no | own only | no | no | n/a |
| See own earnings, request payout | no | no | own only | no | n/a |
| Subscribe to a plan | own role's plans | yes (client plans) | yes (freelancer plans) | no | n/a |
| See all transactions, settings, reports | no | no | no | **yes** | database |
| Change commission, approve refunds, mark payouts | no | no | no | **yes** | n/a |
| Create admin accounts | no | no | no | no | **yes (CLI only)** |

**Rules that always apply (both versions):**
- A freelancer's service and portfolio category is their specialty.
- Bookings cannot overlap, cannot be in the past, cannot be longer than the service, and cannot be for an inactive service.
- Payment amounts come from the server's price, never from the browser. Commission and net amounts are calculated on the server.
- Freelancer money is shown as **available** only after the payment provider confirms eligibility. Before that it is pending.
- Portfolio and project links must start with `https://`.
- Passwords need 8 to 128 characters; stored as PBKDF2-SHA256 hashes (local) or by Supabase Auth.

---

## 3. Logins and owner access

### Accounts that users create
- **Client:** `register.html`, choose "Client".
- **Freelancer:** `register.html`, choose "Freelancer" and a specialty.
- **Sign in:** `login.html`. Sign out from the dashboard.
- **Forgot password:** not built (needs a mail service). Two tests skip on purpose.

### Administrator account
- **Created only from the server's command line.** There is no sign-up path to admin and no admin login button that creates access.
- The owner creates it once:
  ```bash
  python3 server/manage.py create-admin --email you@example.com --name "Your Name" --generate
  ```
  The generated password is printed one time. Save it in a password manager immediately. It is not stored in plain text, and it is not written in this guide, in chat, or in any file.
- Sign in as that account on `login.html`, then open `/en/admin.html` (or `/ar/admin.html`) directly. Non-admins see a refusal message there.
- Other commands: `promote-admin --email ...`, `demote-admin --email ...` (both CLI only), `commission-show`, `make-webhook-secret`.
- **Admin sign-in uses the same password form as everyone else.** Two-factor login is not built; treat the admin password and the owner's email account as the most important secrets in the project.
- If the admin password is lost: there is no reset command yet. Create another admin account with a different email, then fix the first one through the database only after confirming your identity outside the system.

### Owner (the person who runs the website)
The owner controls the hosting, the database, and the server command line. There is no owner account inside the website.
- **Local version:** the owner runs `server/app.py` and the CLI. Back up `server/data/xlanora.db` regularly. It is excluded from Git.
- **Supabase version:** the owner uses the Supabase dashboard (Authentication, SQL editor, Table editor, backups). The **service role key** must never appear in a frontend file, zip, or repository.
- **Netlify:** the owner deploys and manages environment variables there.

### Test accounts
Automated tests create their own accounts with fake names and use temporary databases. Never use real customer names, emails, or phone numbers in tests.

---

## 4. Financial system (V9)

### Money rules
- All money is stored as **integer halalas** (1 SAR = 100 halalas). No floating-point money.
- **Commission** is a percentage in basis points (1000 = 10%). It is set by the admin between 0% and 50%. Initial value: **10%**.
- Commission = `amount × rate ÷ 10,000`, **rounded down**. Net = gross − commission. Example: 500.00 SAR at 10% = 50.00 commission, 450.00 net.
- Maximum single payment: **50,000 SAR**.
- Changing the commission rate affects only new payments. Existing records keep the rate they were created with.

### Lifecycle
- **Payment:** pending → paid or failed; paid → refunded. Failed and refunded records never go back.
- **Freelancer earning:** pending → awaiting confirmation (after the booking is completed) → available (only after the provider confirms eligibility) → paid out. A cancelled or failed booking produces no earning.
- **Refund:** requested → processed or rejected. A refund cannot exceed the payment. Approving a refund is blocked if the freelancer's money is already available or paid out (the earning must be handled first).
- **Payout:** requested → paid or rejected. Requesting a payout reserves the available amount; rejecting releases it; marking it paid moves it to paid out.
- **Subscription:** pending → active or cancelled; active → cancelled or expired. A user can hold one active subscription at a time.

### Provider boundary
Payments go through a provider module (`server/finance.py`, class `SandboxProvider`). The only provider is a **sandbox**: no money moves, no card data is stored. Provider events arrive at `POST /api/payments/webhook/sandbox` and must be signed with HMAC-SHA256 over `timestamp.body`, with a timestamp within 300 seconds. Each event ID is stored once, so duplicates are ignored. The server can also re-check a payment's status with the provider.

**PayPal is not implemented.** It requires your business account and written authorization before any code is written for it.

### Dashboard and admin screens
- **Freelancer earnings panel:** totals, status history, payouts, and the payout button (enabled only when money is available).
- **Client payment:** the Pay button on an accepted booking. The page then shows the payment status.
- **Admin page:** summary metrics, commission setting, transactions (with filter and CSV download), refunds (approve or reject), payouts (mark paid or reject), subscription plans (create, enable or disable), subscriptions (cancel), and the audit log.
- CSV exports protect against spreadsheet formula injection (cells starting with `=`, `+`, `-`, `@`, tab, or carriage return get a leading apostrophe).

### Audit log
Every money movement, status change, commission change, and admin action is written to `financial_audit_logs`. The log is **append-only**: the database blocks updates and deletes.

### Limits of V9 finance
- Sandbox only. Real money is not moved and no real card or bank data is processed.
- Refunds are full-amount only.
- Finance and admin run on the local server. On Netlify with Supabase they show "offline" until the Edge Functions are built.
- No admin two-factor login.

---

## 5. Development

### Requirements
- Python 3.11 or newer (3.13 used in testing). No external Python packages for the website or server.
- Node.js 18 or newer (only for `node --check file.js`).
- Browser tests: Playwright for Python and Google Chrome.
- Database tests: PostgreSQL 16 (`psql`, `createdb`).

### Run the local version
```bash
python3 server/app.py --port 8000
```
Open `http://127.0.0.1:8000/en/` or `http://127.0.0.1:8000/ar/`. The database is created on first start. Use `--db /path/file.db` for another file.

### Rebuild the static pages after editing content
Pages in `site/en` and `site/ar` are generated. Edit the sources, then:
```bash
python3 build/build.py
```
Sources:
- `build/content.py`: services, home, about, contact, navigation.
- `build/content_auth.py`: sign-in, dashboard, booking (`bk_*`), portfolio (`pf_*`).
- `build/content_finance.py`: finance and admin text (`fn_*`).
- `build/build.py`: page layouts.

Every key must exist in English and Arabic (`tests/test_consistency.py` checks this). Never edit generated HTML directly.

### Important folders
```
build/                    page generator and all text (EN and AR)
site/                     the website that is served (generated pages + assets)
site/assets/js/           config.js, nav.js, auth.js, contact.js, bookings.js,
                          portfolio.js, finance.js (dashboard), admin.js (admin page)
site/assets/css/main.css  design tokens, responsive rules, finance and admin styles
server/app.py             HTTP server, routes, sessions, security headers
server/finance.py         money rules, commission math, sandbox provider, state machines
server/finance_store.py   finance database operations (under the same lock as the server)
server/bookings.py        booking, availability, portfolio validation (shared with tests)
server/manage.py          owner command-line tool (admin accounts, commission, sandbox events)
server/schema.sql         local database schema, triggers, finance tables
supabase/migrations/      001 to 007, run in order
tests/                    all automated tests (section 6)
docs/                     this guide, deployment, security report, finance plan, project map
```

### Key local routes
| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/health` | anyone | health check |
| GET | `/api/me` | signed in | current user (includes `is_admin`) |
| POST | `/api/auth/register`, `/api/auth/login`, `/api/auth/logout` | anyone / signed in | accounts (logout requires JSON) |
| POST | `/api/auth/password` | signed in | change password |
| POST | `/api/contact` | anyone (rate-limited) | contact message |
| GET | `/api/services`, `/api/services/{id}/slots?date=` | anyone | search, free times |
| GET, POST | `/api/my/services`; PUT, DELETE `/api/my/services/{id}` | freelancer | own services |
| GET, PUT | `/api/my/availability` | freelancer | weekly hours |
| GET, POST | `/api/bookings`; POST `/api/bookings/{id}/accept\|reject\|complete\|cancel\|pay` | role-dependent | bookings and payment start |
| GET | `/api/portfolio` | anyone | public portfolio |
| GET, POST | `/api/my/portfolio`; PUT, DELETE `/api/my/portfolio/{id}` | freelancer | own portfolio |
| GET | `/api/my/finance`, `/api/my/subscription`, `/api/plans` | signed in (finance: freelancers) | earnings, subscription, plans |
| POST | `/api/my/payouts`, `/api/my/subscriptions` | freelancer / client or freelancer | request payout, subscribe |
| GET | `/api/payments/{id}` | payer or admin | payment status (re-checked with the provider) |
| POST | `/api/payments/webhook/sandbox` | signed provider events only | payment events |
| GET | `/api/admin/summary`, `/transactions`, `/refunds`, `/payouts`, `/plans`, `/subscriptions`, `/audit`, `/report.csv` | admin | admin screens |
| PUT | `/api/admin/settings/commission` | admin | commission rate |
| POST | `/api/admin/refunds/{id}/approve\|reject`, `/api/admin/payouts/{id}/paid\|reject`, `/api/admin/subscriptions/{id}/cancel`, `/api/admin/plans` | admin | decisions |

Errors come back as `{"errors": {field: code}}` with HTTP 400, 401, 403, 404, 409, or 503. Finance errors use `{"errors": {"finance": code}}`.

---

## 6. Testing: everything and how to run it

Run all commands from the project folder. No test touches the real database.

### 6.1 Unit and integration tests (Python)
```bash
python3 -m unittest discover -s tests -v
```
**Result at this version: 289 tests, 287 pass, 2 skipped on purpose** (forgot-password and email verification need a mail service).

| File | What it covers |
|---|---|
| `test_server.py` | HTTP server, static files, security headers, rate limits, sessions |
| `test_auth.py` | registration, sign-in, sign-out, roles, password rules |
| `test_workflows.py` | client and freelancer journeys, permissions |
| `test_bookings.py` | booking workflow, services, double-booking protection, weekly hours |
| `test_portfolio.py` | portfolio publish, listing, search, https-only links, owner-only changes |
| `test_finance.py` (59) | commission math; payment lifecycle; cancellations and refunds; earnings and payouts; subscriptions; admin access; webhook security; database consistency |
| `test_security.py` (66) | OWASP Top 10 (2021) classes A01 to A10 and other risks; see `docs/SECURITY_TEST_REPORT.md` |
| `test_site.py` | generated pages |
| `test_consistency.py` | English and Arabic strings match; services match across code, schema, and content |
| `test_migration.py` | an older database is upgraded on start without losing data |

### 6.2 Browser tests (Playwright + Chrome)
Each script starts its own server on a spare port with a temporary database.
```bash
python3 tests/e2e_booking.py      # booking dashboard, two clients, one freelancer: 34 checks
python3 tests/e2e_site.py         # every page, EN and AR, 360 px and 1280 px; links, images, no sideways scroll; portfolio flow: 27 checks
python3 tests/e2e_v10.py           # V10 changes: homepage, About, removed finance and admin pages, three-service limit, AM/PM times, screenshots: 73 checks
```
If Chrome is not at `/usr/bin/google-chrome`, set `CHROME_PATH`. The site test reports external Google Fonts as blocked in sandboxes without internet; that is not a website error.

### 6.3 Database tests for the Supabase version (PostgreSQL 16)
Run on a **fresh test database**. The stand-in auth file (`tests/supabase_stub_auth.sql`) is for testing only, never production.
```bash
createdb xlanora_fin && psql -v ON_ERROR_STOP=1 -q -d xlanora_fin -f tests/supabase_stub_auth.sql
for f in supabase/migrations/00{1,2,3,4,5,6,7}_*.sql; do psql -v ON_ERROR_STOP=1 -q -d xlanora_fin -f "$f" || break; done
psql -v ON_ERROR_STOP=1 -q -d xlanora_fin -f tests/supabase_finance_test.sql
```
Other chains: `supabase_booking_test.sql` (14 checks, migrations 001 to 005) and `supabase_portfolio_test.sql` (9 checks, 001 to 006). `supabase_rls_test.sql` loads 001 to 003 itself. Each script ends with `ALL ... CHECKS PASSED`; a failure stops with a message starting with `FAIL`.

### 6.4 Test results at this version
| Suite | Result |
|---|---|
| Unit and integration (Python) | 289 run, 287 pass, 2 skipped on purpose |
| Browser: booking dashboard | 34 of 34 |
| Browser: every page, both languages, phone and desktop, portfolio flow | 27 of 27 |
| Browser: finance and admin | 25 of 25 |
| Database: finance (Supabase, migrations 001 to 007) | 17 of 17 |
| Database: booking (Supabase) | 14 of 14 |
| Database: portfolio (Supabase) | 9 of 9 |

**Not tested:** the Supabase browser path against a live project (none available here). Before launch, sign up, book, and publish once on the real project.

### 6.5 Known test gaps
- Forgot-password and email verification: not built.
- Load testing beyond the two-client booking race: not done.
- Admin two-factor: not built.
- Screen-reader testing: not done (automatic checks only: alt text, labels, heading structure).
- Live TLS and live payment providers: not tested (no provider exists).

---

## 7. Security summary
Full detail, the OWASP mapping, and the list of problems found and fixed are in `docs/SECURITY_TEST_REPORT.md`.
- **Passwords:** PBKDF2-SHA256, 310,000 iterations (local); Supabase Auth in the other version.
- **Sessions (local):** random token, stored as SHA-256 hash; cookie HttpOnly and SameSite=Strict; Secure with `XLANORA_SECURE_COOKIES=1`.
- **Rate limits:** contact 5 per 10 minutes; sign-in and sign-up 10 per 10 minutes per key.
- **Headers:** Content-Security-Policy (no inline scripts, `frame-ancestors 'none'`), X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy.
- **Output:** user text is inserted with `textContent`, never as HTML.
- **Money:** calculated on the server only; webhooks signed and replay-protected; audit log append-only.
- **Database:** row-level security on every table (Supabase). Clients cannot write bookings directly. Contact details hidden until acceptance.
- **Secrets:** no service-role key in the frontend; `.gitignore` excludes the live database.

### Open decisions and items
- Lead privacy: whether freelancers see a client's email and phone in the requests list before accepting (owner decision).
- Supabase contact form: no server-side anti-spam (needs an Edge Function or CAPTCHA).
- Portfolio image hosts see visitors' addresses. Consider an allowed-host policy.
- `list_services` in Supabase does not escape `%` and `_` in search text. Not an injection risk, but a search for `%` matches everything. Fix in the next migration.

---

## 8. Supabase version: setup
See `docs/DEPLOY.md`, Part 2 and Part 3. Summary:
1. Create the project; note the URL and the **anon** key.
2. Set the Site URL to the Netlify address.
3. Run migrations 001 to 007 in order in the SQL editor.
4. Set `backend: "supabase"`, `supabaseUrl`, and `supabaseAnonKey` in `site/assets/js/config.js`.
5. Deploy the `site` folder to Netlify (`netlify.toml` publishes `site` and runs `python3 build/build.py`).

---

## 9. Deployment checklist (summary)
- [ ] Unit suite passes (289, 2 skipped on purpose).
- [ ] Browser suites pass: booking (34), site (27), finance (25).
- [ ] Database suites pass on a fresh test database (finance 17, booking 14, portfolio 9).
- [ ] `python3 build/build.py` ran after the last content change.
- [ ] `config.js` contains the right backend and the anon key only.
- [ ] Admin password saved in a password manager, not in a file.
- [ ] A test account was created and deleted on the live site.
- [ ] Backups scheduled (local database file, or Supabase backups).

---

## 10. What is not built yet (honest list)
1. **Real payment provider** (PayPal or other). Needs business account, legal review, and written authorization.
2. **Supabase finance Edge Functions** (payments, webhooks, admin screens on Netlify).
3. **Admin two-factor login.**
4. **Forgot password and email verification** (need a mail service).
5. **Server-side anti-spam** for Supabase contact messages.
6. **Lead privacy decision** (what a freelancer sees about a client before accepting).
7. **Partial refunds** (refunds are full-amount only).
8. **Password reset command** for admins.
9. **Reviews and ratings.**
10. **Image uploads** for portfolio (links only).
11. **Removing the old Next.js scaffold** (the static site does not use it; its dependencies are not audited).
12. **Live Supabase browser test** (needs a real project).

---

## 11. Version history
- **V5:** nine services, new logo, service photos, role fixes.
- **V6:** audit, repairs, automated client and freelancer tests, bookings on the local version, Supabase 001 to 004.
- **V7:** booking dashboard for both versions, weekly hours, password change, booking browser tests, Supabase 005.
- **V8:** public portfolio and freelancer portfolio management, Supabase 006, full-site browser test.
- **V9 (this version):** financial system (commissions, earnings, payouts, refunds, subscriptions, sandbox provider with signed webhooks, append-only audit log), administrator dashboard with server-side access control and CLI-only admin creation, Supabase migration 007, OWASP Top 10 security test suite (66 tests; fixed a booking contact leak and logout CSRF), deployment guide, and security report. Unit tests went from 164 to 289.

# XLANORA: Publishing with GitHub, Supabase and Netlify (V10)

Read this first: **Netlify only hosts static files.** It cannot run the Python server. So:

| Feature | Local server (`server/app.py`) | Netlify + Supabase (static site) |
|---|---|---|
| Public pages, portfolio, services | yes | yes |
| Accounts, bookings, weekly hours | yes | yes (Supabase Auth and database) |
| Finance dashboard, payments, payouts, subscriptions | yes (sandbox provider) | **not wired**: shows "offline" |
| Admin inbox (`/en/admin.html`) | yes | yes (reads `contact_messages`; the database allows administrators only). Finance and the other admin tools: local server only |
| Real payment provider | **not built** | **not built** |

The site does not take payments. Customers and freelancers pay each other directly (bank transfer, cash or another agreed method) and the site only records what each side confirms. The older finance tables from migration 007 stay in the database but are no longer used; payouts and the commission setting are revoked from users in migration 014.

---

## Part 1. Put the project on GitHub

1. Create an empty repository on GitHub (private is recommended), for example `xlanora`. Do not add a README or license there.
2. On your computer, in the project folder:
   ```bash
   git init
   git add .
   git status            # check the list: there must be NO server/data/, NO *.db, NO .env, NO key files
   git commit -m "XLANORA V9"
   git branch -M main
   git remote add origin https://github.com/YOUR-USER/xlanora.git
   git push -u origin main
   ```
3. Before the first push, run `git status` again. If you see `server/data/`, `*.db`, `.env`, or any file containing a password or a service key, stop and remove it from the staging area with `git rm --cached <file>`.
4. Never commit the Supabase **service role** key, the webhook secret, or an admin password.

---

## Part 2. Set up Supabase (the live database and accounts)

1. Create a project at supabase.com. Choose a region near your users. Save the database password in a password manager.
2. **Project Settings, API:** copy the **Project URL** and the **anon public** key. Do not copy the service role key into any file.
3. **Authentication, URL configuration:** set the Site URL to your Netlify address (for example `https://your-site.netlify.app`). Keep email confirmation on.
4. **SQL editor:** run the migrations **in this exact order**, waiting for each to finish without errors:
   1. `supabase/migrations/001_init.sql`
   2. `002_accounts.sql`
   3. `003_services.sql`
   4. `004_bookings.sql`
   5. `005_availability_rpc.sql`
   6. `006_portfolio.sql`
   7. `007_finance.sql`
   8. `008_parity.sql` (three-active-service limit in the database, administrator inbox read rule, full contact service list)
   9. `009_photos.sql` (public `photos` bucket for profile and portfolio pictures, owner-only writes, `avatar_url` on profiles)
   10. `010_profiles_public.sql` (headline on profiles, users may change only their name and headline, public `freelancer_profiles` view without e-mail or admin flag)
   11. `011_wishlist.sql` (clients save freelancers to a private wishlist; RLS lets each client read, add and remove only their own saves; `is_freelancer()` security-definer helper)
   12. `012_reviews_alerts.sql` (reviews of 1 to 5 stars and a comment, allowed only after a completed booking and final once written; public review and rating views; `email_outbox` queue and `request_category_alert()` for category e-mail alerts, one per client and category every 24 hours)
   13. `013_verified_only.sql` (booking and reviewing require a confirmed e-mail, checked in the database through `is_verified()`; Supabase Auth must keep e-mail confirmation turned on so `email_confirmed_at` gets set when the user clicks the link)
   14. `014_direct_payment_orders.sql` (direct payment between customer and freelancer: payment method, separate payment confirmations, delivery confirmation before rating, reports, activity history; the 10% commission, payouts and payment routes are disabled; the agreed price is stored on each order)
   15. `015_payment_currency.sql` (each order records its currency, SAR or USD, shown with the SAR equivalent)
   16. `016_video_uploads.sql` (the `photos` bucket accepts up to 50 MB and MP4, WebM or MOV portfolio videos; run after 015)
5. Make one administrator in Supabase (SQL editor, after signing up with that account): `update public.profiles set is_admin = true where id = '<the user id>';`. Only the owner does this; the website can never grant it.
   Check the results: the finance tables (`payment_transactions`, `platform_commissions`, `freelancer_earnings`, `refunds`, `payouts`, `financial_audit_logs`, and the rest) must show row-level security enabled.
6. **Never run the migrations on a project that holds real customer data without a backup.** Use Supabase's backup settings, or a copy of the project, first.
7. Migrations are deployed separately from the website. Netlify never runs SQL.

The database tests (`tests/supabase_*_test.sql`) must run on a **separate test database**, never on the live project.

---

## Part 3. Configure the website for Supabase

1. Edit `site/assets/js/config.js`:
   ```js
   backend: "supabase",
   supabaseUrl: "https://YOUR-PROJECT.supabase.co",
   supabaseAnonKey: "YOUR-ANON-KEY",
   ```
2. Only the **anon** key goes here. It is public by design; security comes from row-level security.
3. Confirm the file contains no secret key: search `config.js` for the word "service" followed by "role" (with an underscore). The search must find nothing.
4. Build the pages: `python3 build/build.py`.

---

## Part 4. Deploy on Netlify

`netlify.toml` already contains the settings:

- Build command: `python3 build/build.py`
- Publish folder: `site`
- Python version: 3.11
- Security headers come from `site/_headers`.

Steps:
1. netlify.com, **Add new site, Import an existing project**, choose GitHub, pick the `xlanora` repository.
2. Confirm the build settings above. Deploy.
3. You get a free address such as `https://random-name.netlify.app`. You can rename it under **Site configuration, Change site name**.
4. Set the same address as the Site URL in Supabase (Part 2, step 3).
5. Environment variables: none are required for the static site. Do not add the service role key here.
6. Check the live site: open `/en/` and `/ar/`, sign up with a **test** account, make a booking, publish a portfolio item, then delete the test data.
7. Check the security headers with the browser's developer tools (Network, Response headers): Content-Security-Policy, X-Frame-Options, and X-Content-Type-Options should be present.

For HTTPS on your own domain later, add it under Netlify's Domain management; HTTPS certificates are automatic.

---

## Part 5. Run the full system on your own computer (local server)

This is the only place finance and admin features work today.

```bash
python3 server/app.py --port 8000
```
Open `http://127.0.0.1:8000/en/`.

### Environment variables (local server only)

| Variable | Purpose | Required? |
|---|---|---|
| `XLANORA_SANDBOX_WEBHOOK_SECRET` | secret for signed sandbox payment events; at least 32 characters. Create one with `python3 server/manage.py make-webhook-secret`. Without it, webhooks return 503 and stay off. | needed for payment tests |
| `XLANORA_SECURE_COOKIES` | set to `1` when served over HTTPS (cookie gets the Secure flag) | yes, behind HTTPS |
| `XLANORA_TRUST_PROXY` | set to `1` only behind a reverse proxy you control | only then |
| `XLANORA_DB` | database file path (default `server/data/xlanora.db`) | optional |
| `XLANORA_IP_SALT` | salt for hashing client addresses in rate limits and logs | recommended in production |
| `XLANORA_TZ_OFFSET_MINUTES` | local time offset for bookings (default 180, Riyadh) | optional |

Do not change `XLANORA_PBKDF2_ITERS` on an existing database; existing passwords would stop matching.

### Create the owner's admin account (once)

```bash
python3 server/manage.py create-admin --email you@example.com --name "Your Name" --generate
```
The command prints a generated password **one time only**. Copy it straight into your password manager. It is not stored in plain text anywhere, and it is not written in this guide, in the chat, or in any file. If you lose it, there is no password-reset command yet. Create a second admin account with `create-admin` using a different email, sign in with that, and then fix the first account through the database only after confirming your identity outside the system.

Other owner commands:
- `promote-admin --email ...` and `demote-admin --email ...`
- `commission-show` (current platform commission)
- `make-webhook-secret`
- `sandbox-pay <sbx_reference>`, `sandbox-fail <ref>`, `sandbox-eligible <ref>` (simulate provider events for testing; sandbox only)

Admin access is never granted from the website. The admin page at `/en/admin.html` (or `/ar/admin.html`) checks the server, and the server returns 403 to everyone else.

---

## Part 6. Before going live: checklist

- [ ] `python3 -m unittest discover -s tests` passes (289 tests, 2 skipped on purpose)
- [ ] `python3 tests/e2e_booking.py` (34 checks), `tests/e2e_site.py` (27), `tests/e2e_v10.py` (84) pass
- [ ] Supabase database tests pass on a fresh **test** database, migrations 001 to 010 in order, then `tests/supabase_parity_test.sql` (9 checks), `tests/supabase_photos_test.sql` (9 checks) and `tests/supabase_profiles_test.sql` (6 checks) on the same chain
- [ ] `python3 tests/e2e_supabase_mock.py` passes (15 checks; mock backend, no live project needed)
- [ ] In the Supabase dashboard, Storage, bucket `photos`: 50 MB limit and JPEG, PNG, WebP, MP4, WebM, MOV only (the database test cannot check Storage's own limits). On the free plan Supabase may cap uploads lower; if a video above that cap is refused, raise the limit in the Storage settings
- [ ] `config.js` has the anon key only; the service role key is nowhere in the repository or the site folder
- [ ] `git status` showed no database file, no `.env`, no secrets before the push
- [ ] The admin password is stored in your password manager, not in a file
- [ ] One test account per role was created, used, and deleted on the live site
- [ ] Supabase backups are on
- [ ] You understood the limits: no real payments, no admin two-factor, finance and admin not on Netlify

## Photos in the Supabase version

- Pictures are stored in the public bucket `photos`, in a folder named after the user. Anyone can view them; only the owner can add, replace or delete them.
- The file-type and size limits are set on the bucket (migrations 009 and 016) and enforced by Supabase Storage. Photos are limited to 10 MB and videos to 50 MB in the browser and on the local server; the bucket's own limit is 50 MB, which is the largest allowed size.
- A profile picture must be a link into the owner's own folder; a trigger refuses any other link.
- A replaced picture is deleted from the bucket. A removed portfolio item is only deactivated, so its photo stays.

## Part 7. Limits you must accept or fix before real money

1. **No real payment provider.** The sandbox simulates payments. Connecting a real provider (PayPal or another) needs your business account, a legal review, and written authorization. It is not active.
2. **Finance and admin do not run on Netlify.** They need the Python server or new Supabase functions.
3. **No admin two-factor login.**
4. **No live-domain HTTPS test in this project.** Check the padlock yourself after deploy.
5. **Forgot-password is not built**, so account recovery is manual.
6. **Refunds are full-amount only.**
7. Read `docs/SECURITY_TEST_REPORT.md` section 5 for the complete list.

## Category alerts and reviews (Supabase version)

- The search by category sends a request to the Edge Function `supabase/functions/category-alert/index.ts`, which uses the signed-in client's token. The database function checks the role, the category and the 24-hour limit, then the function sends the e-mails through Resend with the service role key. The browser never sees the service role key.
- Deploy and configure it step by step in `docs/PUBLISH_GUIDE.md`, section A10.
- Required secrets: `RESEND_API_KEY`, `ALERT_FROM`, `SITE_ORIGIN`.

## Contact messages: where they go

- **Every message is saved.** Both versions: the admin inbox at `/en/admin.html` (or `/ar/admin.html`), visible only to an administrator account. In the Supabase version, the database itself (migration 008) returns the rows only to a profile with `is_admin = true`.
- **Email copy (optional, local version):** set these in the server's environment. Without `SMTP_HOST` no email is sent, and the inbox still receives every message.

| Variable | Value |
|---|---|
| `SMTP_HOST` | your mail server, e.g. `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | the sending mailbox |
| `SMTP_PASSWORD` | an app password for that mailbox (never commit it) |
| `SMTP_FROM` | the sender address shown in the email |
| `CONTACT_TO` | optional; defaults to `contactxlanora@gmail.com` |

The owner must create the mailbox password and set it; it is never stored in the project.


## Search files
`build/build.py` writes `site/robots.txt` and `site/sitemap.xml`. Private pages are blocked in robots.txt and never listed in the sitemap. The sitemap address comes from `XLANORA_PUBLIC_URL`, or from Netlify's `URL` during a build. Rebuild after changing the domain.

## Payment currency
Orders store SAR or USD (`payment_currency`, migration 015). USD is shown at the fixed rate of 3.75 SAR per USD.

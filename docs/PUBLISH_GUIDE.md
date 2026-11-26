# XLANORA: How to Publish the Website (English)

> **Search files (new):** `build/build.py` now writes `robots.txt` and `sitemap.xml`. On Netlify the sitemap uses the site address that Netlify provides during the build. Private pages (dashboards, admin, sign-in, verification, the freelancer profile template) are blocked in `robots.txt`. After you connect your own domain, rebuild so the sitemap uses it.

> **Payment currency (new):** customers choose SAR or USD for each order. USD is shown at the fixed rate of 3.75 SAR per USD. Customers are told to contact the freelancer before paying.

> **Direct payment (new):** the site takes no money and no commission. Customers and freelancers pay each other directly. Run migration `014_direct_payment_orders.sql` in the Supabase version. The local version already includes this in `server/app.py`.

> **E-mail confirmation (new):** a user must confirm their e-mail before booking or leaving a review. In the Supabase version keep *Authentication → Providers → Email → Confirm email* turned on, and run migration `013_verified_only.sql`. In the local version, set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` and `XLANORA_PUBLIC_URL` (your public address) so the confirmation link reaches the user's inbox. Without SMTP the links stay queued in the outbox and nothing is sent.

This guide explains how to publish XLANORA on the internet with **GitHub**, **Supabase** and **Netlify**.
It covers the **two versions** of the project. Read the table first, then follow only the part you need.

| Version | What it is | Where it runs | Recommended for |
|---|---|---|---|
| **A. Supabase version** | A static website (`site/`) that talks to a Supabase database, accounts and storage. | Website on **Netlify**, database and accounts on **Supabase**, code on **GitHub**. | Public launch with a free Netlify address. **This is the version to publish.** |
| **B. Local server version** | A Python server (`server/app.py`) with a SQLite database file, admin tools and finance features. | Needs a computer or a server that runs Python. **Netlify cannot run it** (Netlify hosts static files). | Demos on your computer, or a separate Python host (Part B, section B6). |

Important facts before you start:
- Netlify publishes only the `site/` folder. The Python server is not part of the Netlify deploy.
- The **Supabase service role key must never appear in the website, in GitHub, or in `config.js`.** Only the **anon** key goes in the website.
- Payments are not included in version A. Bookings do not take money online.

---

## Part 0. Accounts and tools you need (one time)

1. **GitHub account**: https://github.com/signup
2. **Supabase account**: https://supabase.com (sign in with GitHub is fine)
3. **Netlify account**: https://app.netlify.com/signup (sign in with GitHub is fine)
4. **Resend account** (for the category e-mail alerts): https://resend.com/signup
5. **Node.js 20 or newer** on your computer (needed only for the Supabase CLI): https://nodejs.org
6. **Git** on your computer: https://git-scm.com/downloads
7. **Python 3.11 or newer** on your computer (needed to build the site and to run tests).

Check the tools in a terminal (Windows: PowerShell, macOS/Linux: Terminal):
```bash
git --version
node --version
python3 --version
```
If one command is "not found", install that tool first, then open a new terminal.

Keep these details in a password manager, not in any file: the Supabase database password, the Supabase anon key, the Resend API key, and any SMTP password.

---

## Part A. The Supabase version (recommended)

### A1. Check the project folder

1. Open the project folder `XLANORA_Project`.
2. Make sure these folders exist: `build/`, `site/`, `supabase/`, `server/`, `tests/`, `docs/`.
3. Make sure the folder `build/` contains `build.py`. If it is missing, Netlify will fail, so do not continue until it is there.
4. Build the site once on your computer:
   ```bash
   cd XLANORA_Project
   python3 build/build.py
   ```
   You should see lines that start with `wrote`. The output goes into `site/`.
5. Open `site/en/index.html` in your browser. The home page should show XLANORA.

### A2. Put the project on GitHub

1. Go to https://github.com/new.
2. Repository name: `xlanora` (or any name you like).
3. Choose **Private** (recommended while you test). Do **not** tick "Add a README" (the project already has one).
4. Click **Create repository**. GitHub shows a page with commands. Use the ones below.
5. In the terminal, inside `XLANORA_Project`:
   ```bash
   git init -b main
   git add .
   git status
   ```
   **Read the list from `git status` before you commit.** It must NOT contain:
   - a file named `.env` or any `.env.*` file (except `.env.example`)
   - `server/data/` or any `.db` file
   - a file with a real password or key in it

   If you see one of these, stop and add it to `.gitignore`, then run `git add .` again.
6. Commit:
   ```bash
   git commit -m "XLANORA first version"
   ```
   If Git asks for your name and e-mail, run these two commands once (use your own details):
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
7. Connect to GitHub and push. Replace `YOUR-USER` with your GitHub user name:
   ```bash
   git remote add origin https://github.com/YOUR-USER/xlanora.git
   git push -u origin main
   ```
   If GitHub asks you to sign in, use the browser window it opens, or create a personal access token in GitHub: **Settings > Developer settings > Personal access tokens**, and paste it as the password.
8. Refresh the GitHub page. You should see the folders `build`, `site`, `supabase`, and the file `netlify.toml`.

### A3. Create the Supabase project

1. Go to https://supabase.com/dashboard and click **New project**.
2. Organization: choose your organization (or create one).
3. Name: `xlanora`.
4. **Database password**: click *Generate a password*, copy it into your password manager. You need it later for the CLI.
5. Region: choose the one closest to your users (for Saudi Arabia, a nearby region such as Frankfurt or Mumbai is typical).
6. Click **Create new project** and wait 1 to 2 minutes until the dashboard opens.

### A4. Copy the two Supabase keys

1. In the Supabase dashboard, open **Project Settings** (gear icon) > **API**.
2. Copy **Project URL**. It looks like `https://abcdwxyz.supabase.co`.
3. Copy the **anon public** key (a long string starting with `eyJ...` or `sb_publishable_...`).
4. **Do not copy** the `service role` key here. It is secret and is used only on the server (Part A7).

### A5. Run the database migrations, in order

The database structure is in `supabase/migrations/`. Run every file **in number order**, once, on a new project.

Files, in order:
`001_init.sql`, `002_accounts.sql`, `003_services.sql`, `004_bookings.sql`, `005_availability_rpc.sql`, `006_portfolio.sql`, `007_finance.sql`, `008_parity.sql`, `009_photos.sql`, `010_profiles_public.sql`, `011_wishlist.sql`, `012_reviews_alerts.sql`, `013_verified_only.sql`, `014_direct_payment_orders.sql`, `015_payment_currency.sql`, `016_video_uploads.sql`

For each file:
1. Open the file on your computer in a text editor. Select all (Ctrl+A or Cmd+A), copy (Ctrl+C or Cmd+C).
2. In the Supabase dashboard, open **SQL Editor** (left menu) > **New query**.
3. Paste the text (Ctrl+V or Cmd+V).
4. Click **Run** (or press Ctrl+Enter / Cmd+Enter).
5. Wait for a green message such as *Success. No rows returned*. Some files show a list of notices (such as *policy does not exist, skipping*). Notices are normal. A red error is not normal.
6. If a file fails, **stop**. Fix the cause (usually a file was skipped or run twice) before running the next file. Do not skip a file.

Tip: After file 012, open **Table Editor**. You should see the tables `profiles`, `services`, `bookings`, `reviews`, `wishlist`, `email_outbox` and others.

### A6. Configure Supabase Authentication

1. Open **Authentication** > **URL Configuration**.
2. Set **Site URL** to the Netlify address you will get in Part A9, for example `https://xlanora.netlify.app`. For now you can enter `http://localhost` and change it later.
3. Under **Redirect URLs**, add the same address with `/**` at the end, for example `https://xlanora.netlify.app/**`.
4. Open **Authentication** > **Providers** and check that **Email** is enabled.
5. Decide on e-mail confirmation: **Authentication** > **Sign In / Providers** > **Email** > *Confirm email*. Keep it on (recommended).
6. Note: Supabase's built-in e-mail sender has a low hourly limit. For a real launch, set your own SMTP sender under **Project Settings** > **Authentication** > **SMTP Settings**.

### A7. Create the admin account

1. Open the website (locally, first, see A8) and register a normal account with your e-mail.
2. Confirm the e-mail if you turned on confirmation.
3. In the Supabase dashboard, open **SQL Editor** > **New query**, and run (replace the e-mail):
   ```sql
   update public.profiles
   set is_admin = true
   where id = (select id from auth.users where email = 'you@example.com');
   ```
4. Sign out and back in on the website. The admin page is `/en/admin.html`.

### A8. Set the website to use Supabase

1. Open `site/assets/js/config.js` in a text editor. This is a normal source file that Git tracks; the build does not overwrite it. Edit these three lines:
   ```js
   backend: "supabase",
   supabaseUrl: "https://YOUR-PROJECT.supabase.co",
   supabaseAnonKey: "YOUR-ANON-KEY",
   ```
2. Use the Project URL and the **anon public** key from Part A4.
3. The anon key is public by design, so it is safe to commit it to GitHub. Never put the `service role` key in this file.
4. Make sure the file has no secret: the words `service role` must not appear anywhere in `config.js`.
5. Rebuild: `python3 build/build.py`.
6. Test locally by opening `site/en/index.html` in a browser. Sign-up and search will call your Supabase project.

### A9. Deploy the website on Netlify (free subdomain)

1. Go to https://app.netlify.com and click **Add new site** > **Import an existing project**.
2. Choose **GitHub**, authorise Netlify, and select your repository `xlanora`.
3. Check these settings (they are already in `netlify.toml`, so they should fill in automatically):
   - **Branch to deploy:** `main`
   - **Build command:** `python3 build/build.py`
   - **Publish directory:** `site`
4. Click **Deploy site**. Wait 1 to 3 minutes.
5. If the deploy fails, open the **Deploy log**. The most common cause is a missing `build/` folder in GitHub (see A2 step 8).
6. Netlify gives you a free address such as `random-name-123.netlify.app`.
7. To choose a better name: **Site configuration** > **Change site name**. Pick a name that is free, for example `xlanora-sa`. Your address becomes `https://xlanora-sa.netlify.app`.
8. Go back to Supabase **Authentication** > **URL Configuration** and put this new address in **Site URL** and **Redirect URLs** (Part A6).

### A10. Set up the category e-mail alerts (Edge Function + Resend)

When a signed-in customer searches a category, every freelancer with that skill receives an e-mail. This runs on a Supabase Edge Function. It needs an e-mail service (Resend).

**Step 1 — Resend.**
1. Log in at https://resend.com.
2. Go to **Domains** > **Add domain** and add your domain (for example `xlanora.com`). Resend shows DNS records. Add them at your domain provider and wait until Resend shows **Verified**.
3. Go to **API Keys** > **Create API key**, give it *Sending access*, and copy the key (it starts with `re_`). Keep it secret.
4. Without a verified domain, Resend only sends to your own account e-mail, which is fine for a first test.

**Step 2 — install the Supabase CLI and log in.** Run these in the project folder (`npx` downloads the CLI when needed):
```bash
npx supabase --version
npx supabase login
```
A browser window opens. Approve it.

**Step 3 — link the project.** Find the project reference in the dashboard URL (`https://supabase.com/dashboard/project/THIS-PART`) or in **Project Settings** > **General**:
```bash
npx supabase link --project-ref YOUR-PROJECT-REF
```
Enter the database password from Part A3 if asked.

**Step 4 — set the secrets** (the values stay on Supabase, not in GitHub):
```bash
npx supabase secrets set RESEND_API_KEY=re_your_key_here
npx supabase secrets set ALERT_FROM="XLANORA <alerts@your-verified-domain.com>"
npx supabase secrets set SITE_ORIGIN=https://xlanora-sa.netlify.app
```
Check them with `npx supabase secrets list` (the values are hidden).

**Step 5 — deploy the function:**
```bash
npx supabase functions deploy category-alert
```
If the CLI asks to create `supabase/config.toml`, answer yes. The function file is `supabase/functions/category-alert/index.ts`.

**Step 6 — test it.** Sign in as a customer on the website, open **Services**, and choose a category. Within a minute, a freelancer with that skill should receive the e-mail (check the spam folder). In the Supabase dashboard, **Edge Functions** > `category-alert` > **Logs** shows each call. A second search in the same category within 24 hours sends nothing, by design.

### A11. Final test checklist on the live site

Run each line on the Netlify address, on a phone and on a computer.

- [ ] The home page opens in English and in Arabic (`/ar/`), and Arabic is right-to-left.
- [ ] **Register** a customer and a freelancer. Confirm the e-mail if you turned it on.
- [ ] **Sign in** and **sign out** with each account.
- [ ] A freelancer sets a service, the price, a headline, and a profile photo.
- [ ] The customer searches by category, and the freelancer with that skill gets the alert e-mail.
- [ ] The customer saves a freelancer (**Saved** page), then removes them.
- [ ] A booking: the customer books a free slot, the freelancer accepts, then marks it **completed**.
- [ ] After completion, the customer sees **Rate this freelancer**, chooses stars, writes a comment, and submits. The review appears on the profile. The form disappears for that booking.
- [ ] The **About** page shows the feedback section with the e-mail address.
- [ ] An ordinary visitor cannot open `/en/admin.html` data (the page should say access is denied).
- [ ] Open the browser's developer tools console on a few pages: there should be no red errors that stay.

### A12. Updating the live website later

1. Change the files on your computer, run `python3 build/build.py`, and test.
2. Commit and push:
   ```bash
   git add .
   git commit -m "Describe the change"
   git push
   ```
3. Netlify rebuilds and publishes automatically (about 1 to 3 minutes). Watch **Deploys** in Netlify.
4. If a new file `supabase/migrations/0NN_*.sql` was added, run it in the SQL Editor (Part A5), once.
5. If the Edge Function changed, run `npx supabase functions deploy category-alert` again.

### A13. Troubleshooting the Supabase version

| Symptom | Likely cause | Fix |
|---|---|---|
| Netlify deploy says `build.py: No such file` | `build/` was not pushed to GitHub | Check `.gitignore` does not contain `/build`. Run `git add build` then commit and push. |
| Page says "Could not load" or sign-in fails with *Invalid API key* | Wrong anon key in `config.js` | Copy the **anon public** key again (Part A4), rebuild, push. |
| Sign-in works but a page is empty, and the browser console says `relation ... does not exist` | A migration was skipped | Run the missing file from Part A5 in order. |
| Search by category sends no e-mail | Function not deployed, secrets missing, or no freelancer with that skill | Check Part A10 steps 4 to 6 and the function logs. |
| The browser console says a request to `functions/v1` was blocked | `SITE_ORIGIN` does not match the Netlify address | Set `SITE_ORIGIN` to exactly `https://your-site.netlify.app` (no trailing slash), then redeploy the function. |
| The console says a request to a script or style was blocked by Content Security Policy | A new external address was added without updating `site/_headers` | Keep only the addresses listed in `site/_headers`. |
| Password reset or confirmation e-mail never arrives | Supabase default sender limits, or spam filter | Set custom SMTP (Part A6 step 6). Check the spam folder. |
| Review button missing | The booking is not completed yet, or it was already reviewed | Complete the booking first, then refresh the profile. |

---

## Part B. The local server version

Netlify cannot run this version, because it needs a Python process and a database file. Use it on your own computer for demos, or on a server that can run Python.

### B1. Run it on your computer

1. Open a terminal in `XLANORA_Project`.
2. Start the server:
   ```bash
   python3 server/app.py --port 8000
   ```
3. Open `http://127.0.0.1:8000/en/` in your browser.
4. Stop the server with Ctrl+C.

The database file is created automatically at `server/data/xlanora.db`. It is ignored by Git. Back it up by copying this file while the server is stopped.

### B2. Create the owner's admin account (once)

```bash
python3 server/manage.py create-admin --email you@example.com --name "Your Name" --generate
```
The command prints a password one time. Copy it into your password manager immediately. Details are in `docs/DEPLOY.md`, Part 5.

### B3. E-mail settings (optional)

The server sends two kinds of e-mail, only when these variables are set. Without them, nothing is sent and the messages are still saved in the database.

| Variable | Example | Purpose |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | your mail server |
| `SMTP_PORT` | `587` | usually 587 (STARTTLS) |
| `SMTP_USER` | `alerts@your-domain.com` | the sending mailbox |
| `SMTP_PASSWORD` | an app password | never commit it |
| `SMTP_FROM` | `XLANORA <alerts@your-domain.com>` | sender shown in the e-mail |
| `CONTACT_TO` | the feedback address | where contact messages go |
| `XLANORA_PUBLIC_URL` | `https://your-site.example` | adds a link to the freelancer alert e-mails |

Freelancer alert e-mails are placed in an outbox table (`email_outbox`). When SMTP is set, they are sent; rows stay `queued` if sending is not configured, so nothing is lost.

### B4. Security settings for a public server

| Variable | Value |
|---|---|
| `XLANORA_SECURE_COOKIES` | `1` (when served over HTTPS) |
| `XLANORA_TRUST_PROXY` | `1` only behind a reverse proxy you control |
| `XLANORA_IP_SALT` | a long random text (keep it secret) |
| `XLANORA_SANDBOX_WEBHOOK_SECRET` | at least 32 characters, created with `python3 server/manage.py make-webhook-secret` |

Do not change `XLANORA_PBKDF2_ITERS` after users have registered.

### B5. Put it on GitHub

Follow Part A2, but the repository will also contain `server/`. The file `server/data/` must stay out of Git (it is already in `.gitignore`).

### B6. Host it on a Python server

Any host that runs a long-lived Python process will work (for example Render, Railway, Fly.io or your own Linux server). The general steps are the same:

1. Create a **Web Service** from your GitHub repository.
2. Runtime: **Python 3.11**.
3. Start command: `python3 server/app.py --host 0.0.0.0 --port $PORT` (use the port the host gives you; many hosts set `$PORT`).
4. Add the environment variables from B3 and B4.
5. Add a **persistent disk** and point `XLANORA_DB` to a file on that disk (for example `/data/xlanora.db`). Without a disk, the database is erased on every restart.
6. Use HTTPS (most hosts provide it). Set `XLANORA_SECURE_COOKIES=1`.
7. Run `create-admin` once from the host's shell.
8. Open the public address and run the checklist in section A11 (skip the Supabase-only items).

Back up the database file regularly. A simple way on a Linux server: stop nothing, run `sqlite3 /data/xlanora.db ".backup /data/backup-$(date +%F).db"`.

### B7. Troubleshooting the local version

| Symptom | Fix |
|---|---|
| `Address already in use` | Another program uses the port. Use `--port 8001`. |
| Sign-in works on the computer but not on the public address | Set `XLANORA_SECURE_COOKIES=1` only when the address is HTTPS. Otherwise leave it unset. |
| Freelancer e-mails are not sent | Check `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`. Look for `alert e-mail` lines in the server log. |
| Data disappeared after a restart | The database was on a temporary disk. Use a persistent disk (B6 step 5). |

---

## Part C. Before you launch (both versions)

- [ ] Check the contact address. The feedback address on the About page and the server default are both `contactxlanora@gmail.com`. Change it in one place (`build/content_reviews.py` and the server setting `CONTACT_TO`) if you ever use another address..
- [ ] Read the privacy and terms pages and fill in your business details.
- [ ] Keep the GitHub repository **private** unless you are ready to show the code.
- [ ] Turn on two-factor sign-in for GitHub, Netlify, Supabase and Resend.
- [ ] Never paste the Supabase `service role` key or a Resend key into a chat, an e-mail, a screenshot or the website.
- [ ] Rotate any key you think was exposed: Supabase **Project Settings** > **API** (for the service role), Resend **API Keys**.

---

# XLANORA: طريقة نشر الموقع (العربية)

> **ملفات محركات البحث (جديد):** يكتب `build/build.py` الآن الملفين `robots.txt` و`sitemap.xml`. في Netlify يستخدم خريطة الموقع العنوان الذي يوفره Netlify أثناء البناء. الصفحات الخاصة (لوحات التحكم، والإدارة، وتسجيل الدخول، والتحقق، وقالب الملف الشخصي للمستقل) محجوبة في `robots.txt`. بعد ربط نطاقك الخاص أعد البناء حتى تستخدم الخريطة نطاقك.

> **عملة الدفع (جديد):** يختار العميل الريال السعودي (SAR) أو الدولار الأمريكي (USD) لكل طلب. يُعرض الدولار بسعر ثابت هو 3.75 ريال لكل دولار. يُطلب من العميل التواصل مع المستقل قبل الدفع.

> **الدفع المباشر (جديد):** الموقع لا يأخذ أي مبلغ ولا عمولة. يدفع العميل والمستقل لبعضهما مباشرة. نفّذ الملف `014_direct_payment_orders.sql` في نسخة Supabase. النسخة المحلية تتضمن ذلك في `server/app.py`.

> **تأكيد البريد الإلكتروني (جديد):** يجب على المستخدم تأكيد بريده الإلكتروني قبل الحجز أو كتابة التقييم. في نسخة Supabase أبقِ *Authentication ← Providers ← Email ← Confirm email* مفعّلاً، ونفّذ الملف `013_verified_only.sql`. في النسخة المحلية اضبط `SMTP_HOST` و`SMTP_PORT` و`SMTP_USER` و`SMTP_PASSWORD` و`SMTP_FROM` و`XLANORA_PUBLIC_URL` (عنوانك العام) حتى يصل رابط التأكيد إلى البريد. بدون SMTP تبقى الروابط في قائمة الانتظار ولا يُرسل شيء.

يشرح هذا الدليل كيفية نشر XLANORA على الإنترنت باستخدام **GitHub** و**Supabase** و**Netlify**.
يغطي **النسختين** من المشروع. اقرأ الجدول أولاً، ثم اتبع الجزء الذي تحتاجه فقط.

| النسخة | ما هي | أين تعمل | مناسبة لـ |
|---|---|---|---|
| **أ. نسخة Supabase** | موقع ثابت (`site/`) يتصل بقاعدة بيانات Supabase والحسابات والتخزين. | الموقع على **Netlify**، وقاعدة البيانات والحسابات على **Supabase**، والكود على **GitHub**. | الإطلاق العام بعنوان Netlify مجاني. **هذه هي النسخة التي يجب نشرها.** |
| **ب. نسخة الخادم المحلي** | خادم Python (`server/app.py`) مع ملف قاعدة بيانات SQLite وأدوات الإدارة والمالية. | تحتاج إلى حاسوب أو خادم يشغّل Python. **Netlify لا يستطيع تشغيلها** لأنه يستضيف ملفات ثابتة فقط. | العروض التجريبية على حاسوبك، أو خادم Python منفصل (الجزء ب، القسم ب6). |

حقائق مهمة قبل البدء:
- Netlify ينشر مجلد `site/` فقط. خادم Python ليس جزءاً من نشر Netlify.
- **مفتاح `service role` في Supabase يجب ألا يظهر أبداً في الموقع أو في GitHub أو في `config.js`.** المفتاح العام **anon** فقط يوضع في الموقع.
- الدفع الإلكتروني غير موجود في النسخة أ. الحجوزات لا تأخذ مالاً عبر الإنترنت.

---

## الجزء 0. الحسابات والأدوات المطلوبة (مرة واحدة)

1. حساب **GitHub**: https://github.com/signup
2. حساب **Supabase**: https://supabase.com (يمكن الدخول بحساب GitHub)
3. حساب **Netlify**: https://app.netlify.com/signup (يمكن الدخول بحساب GitHub)
4. حساب **Resend** لإرسال تنبيهات البريد الإلكتروني عن التخصصات: https://resend.com/signup
5. **Node.js 20** أو أحدث على حاسوبك (لازم فقط لأداة Supabase CLI): https://nodejs.org
6. **Git** على حاسوبك: https://git-scm.com/downloads
7. **Python 3.11** أو أحدث على حاسوبك (لبناء الموقع وتشغيل الاختبارات).

تحقق من الأدوات في نافذة الأوامر (ويندوز: PowerShell، ماك/لينكس: Terminal):
```bash
git --version
node --version
python3 --version
```
إذا ظهرت رسالة "not found" لأي أمر، ثبّت الأداة أولاً ثم افتح نافذة جديدة.

احفظ هذه البيانات في مدير كلمات المرور وليس في ملف: كلمة مرور قاعدة بيانات Supabase، ومفتاح anon، ومفتاح Resend، وأي كلمة مرور SMTP.

---

## الجزء أ. نسخة Supabase (الموصى بها)

### أ1. تحقق من مجلد المشروع

1. افتح مجلد `XLANORA_Project`.
2. تأكد من وجود المجلدات: `build/` و`site/` و`supabase/` و`server/` و`tests/` و`docs/`.
3. تأكد أن `build/` يحتوي على الملف `build.py`. إذا كان غائباً، سيفشل Netlify، فلا تكمل قبل إضافته.
4. ابنِ الموقع مرة على حاسوبك:
   ```bash
   cd XLANORA_Project
   python3 build/build.py
   ```
   يجب أن ترى أسطراً تبدأ بكلمة `wrote`. الناتج يذهب إلى `site/`.
5. افتح `site/en/index.html` في المتصفح. يجب أن تظهر الصفحة الرئيسية لـ XLANORA.

### أ2. ضع المشروع على GitHub

1. اذهب إلى https://github.com/new.
2. اسم المستودع: `xlanora` (أو أي اسم تفضله).
3. اختر **Private** (موصى به أثناء الاختبار). **لا** تضع علامة على "Add a README".
4. اضغط **Create repository**. تعرض GitHub صفحة فيها أوامر. استخدم الأوامر التالية.
5. في نافذة الأوامر داخل `XLANORA_Project`:
   ```bash
   git init -b main
   git add .
   git status
   ```
   **اقرأ القائمة الناتجة من `git status` قبل الحفظ.** يجب ألا تحتوي على:
   - ملف باسم `.env` أو أي ملف `.env.*` (ما عدا `.env.example`)
   - المجلد `server/data/` أو أي ملف `.db`
   - ملف فيه كلمة مرور أو مفتاح حقيقي

   إذا ظهر أحدها، توقف وأضفه إلى `.gitignore` ثم أعد `git add .`.
6. احفظ التغييرات:
   ```bash
   git commit -m "XLANORA first version"
   ```
   إذا طلب Git اسمك وبريدك الإلكتروني، نفّذ هذين الأمرين مرة واحدة (بياناتك أنت):
   ```bash
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
7. اربط المستودع وارفع الملفات. استبدل `YOUR-USER` باسم مستخدمك في GitHub:
   ```bash
   git remote add origin https://github.com/YOUR-USER/xlanora.git
   git push -u origin main
   ```
   إذا طلب GitHub تسجيل الدخول، استخدم النافذة التي تفتحها، أو أنشئ رمزاً شخصياً من GitHub: **Settings > Developer settings > Personal access tokens** والصقه ككلمة مرور.
8. حدّث صفحة GitHub. يجب أن ترى المجلدات `build` و`site` و`supabase` والملف `netlify.toml`.

### أ3. أنشئ مشروع Supabase

1. اذهب إلى https://supabase.com/dashboard واضغط **New project**.
2. Organization: اختر منظمتك (أو أنشئ واحدة).
3. Name: `xlanora`.
4. **Database password**: اضغط *Generate a password* وانسخها إلى مدير كلمات المرور. ستحتاجها لاحقاً مع CLI.
5. Region: اختر الأقرب إلى المستخدمين (للسعودية، منطقة قريبة مثل Frankfurt أو Mumbai خيار شائع).
6. اضغط **Create new project** وانتظر دقيقة أو دقيقتين حتى تفتح لوحة التحكم.

### أ4. انسخ مفتاحي Supabase

1. في لوحة Supabase افتح **Project Settings** (أيقونة الترس) > **API**.
2. انسخ **Project URL**. يبدو هكذا: `https://abcdwxyz.supabase.co`.
3. انسخ مفتاح **anon public** (سلسلة طويلة تبدأ بـ `eyJ...` أو `sb_publishable_...`).
4. **لا تنسخ** مفتاح `service role` هنا. هو سري ويُستخدم على الخادم فقط (أ7).

### أ5. شغّل ملفات قاعدة البيانات بالترتيب

بنية قاعدة البيانات موجودة في `supabase/migrations/`. شغّل كل ملف **بحسب رقمه**، مرة واحدة، على مشروع جديد.

الملفات بالترتيب:
`001_init.sql`، `002_accounts.sql`، `003_services.sql`، `004_bookings.sql`، `005_availability_rpc.sql`، `006_portfolio.sql`، `007_finance.sql`، `008_parity.sql`، `009_photos.sql`، `010_profiles_public.sql`، `011_wishlist.sql`، `012_reviews_alerts.sql`، `013_verified_only.sql`، `014_direct_payment_orders.sql`، `015_payment_currency.sql`، `016_video_uploads.sql`

لكل ملف:
1. افتح الملف على حاسوبك في محرر نصوص. اختر الكل (Ctrl+A أو Cmd+A) وانسخ (Ctrl+C أو Cmd+C).
2. في لوحة Supabase افتح **SQL Editor** (القائمة اليسرى) > **New query**.
3. الصق النص (Ctrl+V أو Cmd+V).
4. اضغط **Run** (أو Ctrl+Enter / Cmd+Enter).
5. انتظر رسالة خضراء مثل *Success. No rows returned*. بعض الملفات تعرض تنبيهات (مثل *policy does not exist, skipping*). التنبيهات طبيعية. الخطأ الأحمر ليس طبيعياً.
6. إذا فشل ملف، **توقف**. أصلح السبب (غالباً ملف تم تخطيه أو تشغيله مرتين) قبل الملف التالي. لا تتخطَّ ملفاً.

نصيحة: بعد الملف 012 افتح **Table Editor**. يجب أن ترى الجداول `profiles` و`services` و`bookings` و`reviews` و`wishlist` و`email_outbox` وغيرها.

### أ6. إعداد المصادقة في Supabase

1. افتح **Authentication** > **URL Configuration**.
2. ضع في **Site URL** عنوان Netlify الذي ستحصل عليه في أ9، مثل `https://xlanora.netlify.app`. مؤقتاً يمكنك كتابة `http://localhost` وتغييره لاحقاً.
3. في **Redirect URLs** أضف العنوان نفسه مع `/**` في النهاية، مثل `https://xlanora.netlify.app/**`.
4. افتح **Authentication** > **Providers** وتأكد أن **Email** مفعّل.
5. قرّر تأكيد البريد: **Authentication** > **Sign In / Providers** > **Email** > *Confirm email*. أبقه مفعلاً (موصى به).
6. ملاحظة: مرسل البريد المدمج في Supabase له حد منخفض في الساعة. للإطلاق الحقيقي، أضف SMTP خاصاً بك من **Project Settings** > **Authentication** > **SMTP Settings**.

### أ7. أنشئ حساب المدير

1. افتح الموقع (محلياً، أولاً، انظر أ8) وسجّل حساباً عادياً ببريدك.
2. أكّد البريد إذا فعّلت التأكيد.
3. في لوحة Supabase افتح **SQL Editor** > **New query** ونفّذ (غيّر البريد):
   ```sql
   update public.profiles
   set is_admin = true
   where id = (select id from auth.users where email = 'you@example.com');
   ```
4. اخرج من الحساب وادخل مرة أخرى. صفحة الإدارة هي `/en/admin.html`.

### أ8. اجعل الموقع يستخدم Supabase

1. افتح `site/assets/js/config.js` في محرر نصوص. هذا ملف مصدر عادي تتتبعه Git، والبناء لا يستبدله. عدّل هذه الأسطر الثلاثة:
   ```js
   backend: "supabase",
   supabaseUrl: "https://YOUR-PROJECT.supabase.co",
   supabaseAnonKey: "YOUR-ANON-KEY",
   ```
2. استخدم Project URL ومفتاح **anon public** من أ4.
3. مفتاح anon عام بطبيعته، لذلك يمكن رفعه إلى GitHub بأمان. لا تضع مفتاح `service role` في هذا الملف أبداً.
4. تأكد أن كلمة `service role` غير موجودة في `config.js`.
5. أعد البناء: `python3 build/build.py`.
6. اختبر محلياً بفتح `site/en/index.html` في المتصفح. التسجيل والبحث سيستخدمان مشروع Supabase.

### أ9. انشر الموقع على Netlify (عنوان مجاني)

1. اذهب إلى https://app.netlify.com واضغط **Add new site** > **Import an existing project**.
2. اختر **GitHub**، ووافق على الربط، ثم اختر المستودع `xlanora`.
3. تحقق من الإعدادات (موجودة في `netlify.toml` فتُملأ تلقائياً):
   - **Branch to deploy:** `main`
   - **Build command:** `python3 build/build.py`
   - **Publish directory:** `site`
4. اضغط **Deploy site**. انتظر من دقيقة إلى ثلاث.
5. إذا فشل النشر، افتح **Deploy log**. السبب الأشيع هو غياب مجلد `build/` من GitHub (انظر أ2 الخطوة 8).
6. يعطيك Netlify عنواناً مجانياً مثل `random-name-123.netlify.app`.
7. لتغيير الاسم: **Site configuration** > **Change site name**. اختر اسماً متاحاً، مثل `xlanora-sa`. يصبح العنوان `https://xlanora-sa.netlify.app`.
8. ارجع إلى Supabase **Authentication** > **URL Configuration** وضع هذا العنوان في **Site URL** و**Redirect URLs** (أ6).

### أ10. إعداد تنبيهات البريد عن التخصصات (Edge Function + Resend)

عندما يبحث عميل مسجّل دخوله عن تخصص، يصل بريد إلى كل مستقل يملك هذا التخصص. يعمل هذا على Edge Function في Supabase، ويحتاج خدمة بريد (Resend).

**الخطوة 1: Resend.**
1. سجّل الدخول على https://resend.com.
2. اذهب إلى **Domains** > **Add domain** وأضف نطاقك (مثل `xlanora.com`). تعرض Resend سجلات DNS. أضفها عند مزود النطاق وانتظر حتى تظهر **Verified**.
3. اذهب إلى **API Keys** > **Create API key**، واختر صلاحية *Sending access*، وانسخ المفتاح (يبدأ بـ `re_`). احفظه سراً.
4. بدون نطاق موثّق، ترسل Resend فقط إلى بريد حسابك، وهذا يكفي للاختبار الأول.

**الخطوة 2: تثبيت Supabase CLI وتسجيل الدخول.** نفّذ داخل مجلد المشروع (يحمّل `npx` الأداة عند الحاجة):
```bash
npx supabase --version
npx supabase login
```
تفتح نافذة في المتصفح. وافق عليها.

**الخطوة 3: اربط المشروع.** اعثر على معرّف المشروع في رابط لوحة التحكم (`https://supabase.com/dashboard/project/هذا-الجزء`) أو في **Project Settings** > **General**:
```bash
npx supabase link --project-ref YOUR-PROJECT-REF
```
أدخل كلمة مرور قاعدة البيانات من أ3 إذا طُلبت.

**الخطوة 4: ضبط الأسرار** (تبقى القيم في Supabase وليس في GitHub):
```bash
npx supabase secrets set RESEND_API_KEY=re_your_key_here
npx supabase secrets set ALERT_FROM="XLANORA <alerts@your-verified-domain.com>"
npx supabase secrets set SITE_ORIGIN=https://xlanora-sa.netlify.app
```
تحقق بالأمر `npx supabase secrets list` (القيم مخفية).

**الخطوة 5: انشر الدالة:**
```bash
npx supabase functions deploy category-alert
```
إذا سأل CLI عن إنشاء `supabase/config.toml` فأجب بنعم. ملف الدالة هو `supabase/functions/category-alert/index.ts`.

**الخطوة 6: اختبرها.** سجّل دخول عميل في الموقع، افتح **Services** واختر تخصصاً. خلال دقيقة يجب أن يستلم مستقل بهذه المهارة بريداً (تحقق من مجلد الرسائل غير المرغوبة). في لوحة Supabase، **Edge Functions** > `category-alert` > **Logs** تعرض كل استدعاء. البحث الثاني في التخصص نفسه خلال 24 ساعة لا يرسل شيئاً، وهذا مقصود.

### أ11. قائمة الاختبار النهائية للموقع المنشور

نفّذ كل بند على عنوان Netlify، على الهاتف وعلى الحاسوب.

- [ ] تفتح الصفحة الرئيسية بالإنجليزية وبالعربية (`/ar/`)، والعربية من اليمين إلى اليسار.
- [ ] **سجّل** عميلاً ومستقلاً. أكّد البريد إذا فعّلت ذلك.
- [ ] **سجّل الدخول** و**الخروج** بكل حساب.
- [ ] يضيف المستقل خدمة وسعراً وعنواناً وصورة ملف.
- [ ] يبحث العميل بالتخصص، ويستلم المستقل صاحب المهارة بريد التنبيه.
- [ ] يحفظ العميل مستقلاً (صفحة **Saved**)، ثم يزيله.
- [ ] حجز: يحجز العميل موعداً متاحاً، يقبله المستقل، ثم يضع علامة **completed**.
- [ ] بعد الاكتمال يرى العميل **قيّم هذا المستقل**، ويختار النجوم ويكتب تعليقاً ويرسل. يظهر التقييم في الملف الشخصي، ويختفي النموذج لذلك الحجز.
- [ ] صفحة **عن الموقع** تعرض قسم الملاحظات مع عنوان البريد.
- [ ] الزائر العادي لا يستطيع فتح بيانات الإدارة في `/en/admin.html` (يجب أن تظهر رسالة رفض الوصول).
- [ ] لا توجد أخطاء حمراء دائمة في وحدة تحكم المتصفح على الصفحات الرئيسية.

### أ12. تحديث الموقع المنشور لاحقاً

1. غيّر الملفات على حاسوبك، ونفّذ `python3 build/build.py`، واختبر.
2. احفظ وارفع:
   ```bash
   git add .
   git commit -m "Describe the change"
   git push
   ```
3. يعيد Netlify البناء وينشر تلقائياً (من دقيقة إلى ثلاث). راقب **Deploys** في Netlify.
4. إذا أضفت ملف ترحيل جديداً `supabase/migrations/0NN_*.sql`، شغّله في SQL Editor (أ5) مرة واحدة.
5. إذا تغيرت الدالة، نفّذ `npx supabase functions deploy category-alert` من جديد.

### أ13. حل المشكلات في نسخة Supabase

| العَرَض | السبب المحتمل | الحل |
|---|---|---|
| Netlify يقول `build.py: No such file` | لم يُرفع مجلد `build/` إلى GitHub | تأكد أن `.gitignore` لا يحتوي على `/build`. نفّذ `git add build` ثم commit وpush. |
| الصفحة تقول "Could not load" أو يفشل الدخول بـ *Invalid API key* | مفتاح anon خاطئ في `config.js` | انسخ مفتاح **anon public** مرة أخرى (أ4)، وأعد البناء والرفع. |
| الدخول يعمل لكن صفحة فارغة، ووحدة التحكم تقول `relation ... does not exist` | تم تخطي ملف ترحيل | شغّل الملف الناقص من أ5 بالترتيب. |
| البحث بالتخصص لا يرسل بريداً | الدالة غير منشورة، أو الأسرار غير مضبوطة، أو لا يوجد مستقل بهذه المهارة | راجع أ10 الخطوات 4 إلى 6 وسجلات الدالة. |
| تقول وحدة التحكم إن طلب `functions/v1` محظور | `SITE_ORIGIN` لا يطابق عنوان Netlify | ضع `SITE_ORIGIN` بالضبط `https://your-site.netlify.app` (دون شرطة مائلة في النهاية)، ثم أعد نشر الدالة. |
| تقول وحدة التحكم إن سكربت أو ملف تنسيق محظور بسياسة الأمان (CSP) | أُضيف عنوان خارجي دون تحديث `site/_headers` | أبقِ العناوين المسموح بها كما هي في `site/_headers`. |
| رسالة إعادة التعيين أو التأكيد لا تصل | حدود مرسل Supabase الافتراضي، أو فلتر البريد المزعج | فعّل SMTP خاصاً (أ6 الخطوة 6). تحقق من مجلد الرسائل غير المرغوبة. |
| زر التقييم غير موجود | الحجز غير مكتمل بعد، أو تم تقييمه من قبل | أكمل الحجز أولاً، ثم حدّث الملف الشخصي. |

---

## الجزء ب. نسخة الخادم المحلي

لا يستطيع Netlify تشغيل هذه النسخة، لأنها تحتاج عملية Python دائمة وملف قاعدة بيانات. استخدمها على حاسوبك للعروض، أو على خادم يشغّل Python.

### ب1. شغّلها على حاسوبك

1. افتح نافذة أوامر داخل `XLANORA_Project`.
2. شغّل الخادم:
   ```bash
   python3 server/app.py --port 8000
   ```
3. افتح `http://127.0.0.1:8000/en/` في المتصفح.
4. أوقف الخادم بـ Ctrl+C.

يُنشأ ملف قاعدة البيانات تلقائياً في `server/data/xlanora.db`. وهو مستبعد من Git. للنسخ الاحتياطي انسخ هذا الملف والخادم متوقف.

### ب2. أنشئ حساب المدير (مرة واحدة)

```bash
python3 server/manage.py create-admin --email you@example.com --name "Your Name" --generate
```
يطبع الأمر كلمة مرور مرة واحدة. انسخها فوراً إلى مدير كلمات المرور. التفاصيل في `docs/DEPLOY.md` الجزء 5.

### ب3. إعدادات البريد (اختياري)

يرسل الخادم نوعين من البريد، فقط عند ضبط هذه المتغيرات. بدونها لا يُرسل شيء، لكن الرسائل تُحفظ في قاعدة البيانات.

| المتغير | مثال | الغرض |
|---|---|---|
| `SMTP_HOST` | `smtp.gmail.com` | خادم البريد |
| `SMTP_PORT` | `587` | عادة 587 (STARTTLS) |
| `SMTP_USER` | `alerts@your-domain.com` | صندوق الإرسال |
| `SMTP_PASSWORD` | كلمة مرور للتطبيقات | لا ترفعها أبداً |
| `SMTP_FROM` | `XLANORA <alerts@your-domain.com>` | المرسل الظاهر |
| `CONTACT_TO` | عنوان الملاحظات | وجهة رسائل التواصل |
| `XLANORA_PUBLIC_URL` | `https://your-site.example` | يضيف رابطاً في بريد التنبيه للمستقلين |

تُوضع بريد تنبيهات المستقلين في جدول `email_outbox`. عند ضبط SMTP تُرسل، وتبقى الصفوف `queued` إذا لم يكن الإرسال مضبوطاً، فلا يضيع شيء.

### ب4. إعدادات الأمان لخادم عام

| المتغير | القيمة |
|---|---|
| `XLANORA_SECURE_COOKIES` | `1` (عند التشغيل عبر HTTPS) |
| `XLANORA_TRUST_PROXY` | `1` فقط خلف وكيل عكسي تتحكم فيه |
| `XLANORA_IP_SALT` | نص طويل عشوائي (سري) |
| `XLANORA_SANDBOX_WEBHOOK_SECRET` | 32 حرفاً على الأقل، يُنشأ بـ `python3 server/manage.py make-webhook-secret` |

لا تغيّر `XLANORA_PBKDF2_ITERS` بعد تسجيل المستخدمين.

### ب5. ضعها على GitHub

اتبع أ2، لكن المستودع سيحتوي أيضاً على `server/`. يجب أن يبقى `server/data/` خارج Git (وهو موجود في `.gitignore`).

### ب6. استضفها على خادم Python

أي مستضيف يشغّل عملية Python دائمة يصلح (مثل Render أو Railway أو Fly.io أو خادم لينكس خاص بك). الخطوات العامة متشابهة:

1. أنشئ **Web Service** من مستودع GitHub.
2. Runtime: **Python 3.11**.
3. أمر التشغيل: `python3 server/app.py --host 0.0.0.0 --port $PORT` (استخدم المنفذ الذي يعطيه المستضيف، وكثيراً ما يضبط `$PORT`).
4. أضف متغيرات البيئة من ب3 و ب4.
5. أضف **قرصاً دائماً** (Persistent Disk) ووجّه `XLANORA_DB` إلى ملف عليه (مثل `/data/xlanora.db`). بدونه تُمحى قاعدة البيانات عند كل إعادة تشغيل.
6. استخدم HTTPS (معظم المستضيفين يوفرونه). اضبط `XLANORA_SECURE_COOKIES=1`.
7. شغّل `create-admin` مرة واحدة من صدفة المستضيف.
8. افتح العنوان العام ونفّذ قائمة أ11 (تخطَّ البنود الخاصة بـ Supabase).

انسخ ملف قاعدة البيانات احتياطياً بانتظام. طريقة بسيطة على خادم لينكس:
`sqlite3 /data/xlanora.db ".backup /data/backup-$(date +%F).db"`

### ب7. حل المشكلات في النسخة المحلية

| العَرَض | الحل |
|---|---|
| `Address already in use` | برنامج آخر يستخدم المنفذ. استخدم `--port 8001`. |
| يعمل الدخول على الحاسوب ولا يعمل على العنوان العام | اضبط `XLANORA_SECURE_COOKIES=1` فقط عندما يكون العنوان HTTPS. وإلا اتركه غير مضبوط. |
| بريد المستقلين لا يُرسل | تحقق من `SMTP_HOST` و`SMTP_USER` و`SMTP_PASSWORD`. ابحث عن أسطر `alert e-mail` في سجل الخادم. |
| اختفت البيانات بعد إعادة التشغيل | كانت قاعدة البيانات على قرص مؤقت. استخدم قرصاً دائماً (ب6 الخطوة 5). |

---

## الجزء ج. قبل الإطلاق (للنسختين)

- [ ] تحقق من عنوان التواصل. عنوان الملاحظات في صفحة "عن الموقع" والعنوان الافتراضي في الخادم هو `contactxlanora@gmail.com`. غيّره في مكان واحد (`build/content_reviews.py` وإعداد الخادم `CONTACT_TO`) إذا استخدمت عنواناً آخر.
- [ ] اقرأ صفحات الخصوصية والشروط واملأ بيانات نشاطك.
- [ ] اجعل مستودع GitHub **خاصاً** ما لم تكن مستعداً لعرض الكود.
- [ ] فعّل التحقق بخطوتين في GitHub وNetlify وSupabase وResend.
- [ ] لا تلصق أبداً مفتاح `service role` في Supabase أو مفتاح Resend في محادثة أو بريد أو لقطة شاشة أو الموقع.
- [ ] استبدل أي مفتاح تظن أنه تسرّب: Supabase **Project Settings** > **API** (لمفتاح service role)، وResend **API Keys**.

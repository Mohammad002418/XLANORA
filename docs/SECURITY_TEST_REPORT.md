# XLANORA Security Test Report (V9)

This report maps the automated security tests to the OWASP Top 10 (2021) and lists the real problems the tests found and fixed. It describes what was tested on this machine. It is not a third-party penetration test.

## 1. How to run the security tests

```bash
python3 -m unittest tests.test_security -v     # 66 security tests
python3 -m unittest discover -s tests -v       # full unit suite (289 tests, 2 skipped on purpose)
```

The security tests use temporary databases and fake accounts. They never touch `server/data/xlanora.db`.

## 2. Results

| Area | Test class (`tests/test_security.py`) | Result |
|---|---|---|
| A01 Broken Access Control | `A01BrokenAccessControl` | all pass |
| A02 Cryptographic Failures | `A02CryptographicFailures` | all pass |
| A03 Injection | `A03Injection` | all pass |
| A04 Insecure Design | `A04InsecureDesign` | all pass |
| A05 Security Misconfiguration | `A05SecurityMisconfiguration` | all pass |
| A06 Vulnerable and Outdated Components | `A06Components` | all pass (static check of dependencies; see limits) |
| A07 Identification and Authentication Failures | `A07Authentication` | all pass |
| A08 Software and Data Integrity Failures | `A08Integrity` | all pass |
| A09 Security Logging and Monitoring Failures | `A09Logging` | all pass |
| A10 Server-Side Request Forgery | `A10SSRF` | all pass |
| Other risks (CSRF, XSS, CSV injection, upload and input limits, secrets in files) | `OtherRisks` | all pass |

Finance security checks are in `tests/test_finance.py`, class `WebhookSecurityTests` (signature, timestamp, replay and duplicate events) and `AdminAccessTests` (admin-only routes). These run in the unit suite.

## 3. What each group checks

**A01 Broken access control.** A client cannot read another client's bookings, contact details, or payment records. A freelancer cannot change another freelancer's services, hours, or portfolio. Admin routes return 403 for non-admins and for signed-out visitors. Money amounts and commission rates in requests are ignored or rejected; the server calculates them.

**A02 Cryptographic failures.** Passwords use PBKDF2-SHA256 with 310,000 iterations. Session tokens are random and stored only as SHA-256 hashes. The session cookie is HttpOnly and SameSite=Strict, and is Secure when `XLANORA_SECURE_COOKIES=1`. Webhook signatures use HMAC-SHA256 and are compared in constant time.

**A03 Injection.** All database queries use parameters. Search input is treated as data. The static check looks for string-built SQL. User text is inserted into pages with `textContent`, never `innerHTML`. CSV exports prefix dangerous cells (starting with `=`, `+`, `-`, `@`, tab, or carriage return) to prevent spreadsheet formula injection.

**A04 Insecure design.** Double bookings are blocked in the database, not only in the browser. Refunds cannot exceed the payment. Payment, refund, earning, and payout records follow fixed state machines; illegal jumps return 409. A freelancer's money is only "available" after the provider confirms eligibility. Commission is calculated on the server with integer halalas and rounded down.

**A05 Security misconfiguration.** Responses carry Content-Security-Policy (`frame-ancestors 'none'`, no inline scripts), X-Frame-Options DENY, X-Content-Type-Options nosniff, a Referrer-Policy, and a Permissions-Policy. Error responses do not show stack traces. The admin page is marked `noindex`.

**A06 Vulnerable and outdated components.** The local version uses only the Python standard library; a test parses every server file and fails on any third-party import. The old Next.js scaffold is still in the repository and has not been audited (see limits).

**A07 Identification and authentication failures.** Sign-in and registration are rate-limited (10 per 10 minutes per key). Logout requires JSON, which stops cross-site logout attacks. Sessions end on sign-out. Admin accounts can only be created or promoted from the server command line (`server/manage.py`), never from the website.

**A08 Software and data integrity.** Webhook events are accepted only with a valid signature and a timestamp within 300 seconds. Each provider event ID is stored once (unique constraint), so repeated deliveries do nothing. Financial audit records are append-only: the local database and the Supabase migration both block updates and deletes.

**A09 Logging and monitoring.** Every money movement, status change, commission change, and admin action writes a row to `financial_audit_logs`. Client IP addresses are stored only as salted hashes.

**A10 SSRF.** The server makes no outbound requests based on user input. Portfolio images are loaded by visitors' browsers from `https://` addresses only. Portfolio project links must start with `https://`.

**Other risks.** Logout CSRF, XSS through profile or portfolio text, oversized request bodies (limit 8 KB for JSON), request bodies that are not JSON, secrets committed to files (`test_no_secrets_committed`), and the webhook secret being absent or too short (webhooks then return 503 and stay disabled).

## 4. Real problems found by the tests and fixed

| # | Problem | Severity | How found | Fix |
|---|---|---|---|---|
| 1 | Before a freelancer accepted a booking, the server still sent the client's email address in the booking response. | Medium (personal data exposure) | `A01` test on booking responses | Contact details are always removed, and included only after the booking is accepted or completed. |
| 2 | Logout accepted a plain form POST, so a malicious site could sign a user out (logout CSRF). | Low | `A07` / `OtherRisks` CSRF test | Logout now requires a JSON body. |

Two earlier items were test-quality problems, not product bugs: a wrong expected value in the enumeration test, and a static check that flagged comments and a fixed SQL column list as injection. Both were corrected with explanations in the test code. The static checks were not weakened: comments are still stripped only for full-line JavaScript comments, and the SQL exception covers only a fixed literal.

Finance problems found by the browser test (not security findings, but important): after a client pressed Pay, the dashboard refreshed a freelancer-only endpoint and got a 403. The refresh is now role-aware.

## 5. Limits of this report (be honest with yourself about these)

1. **No live TLS test.** HTTPS was not tested end to end. Netlify provides HTTPS; check the padlock on the real domain.
2. **No live Supabase test.** Supabase rules were tested on PostgreSQL 16 directly. Test sign-up, booking, and portfolio on the real project before launch.
3. **Dependency audit not run.** `npm audit` for the old Next.js scaffold was not run. Either remove the scaffold or run the audit.
4. **No third-party penetration test.** The tests cover known categories; a human tester may find other problems. Consider a professional review before taking real payments.
5. **Payments are sandbox only.** No real card or bank data is processed or stored. Real payments need an approved provider, a legal review, and written authorization. PayPal is not implemented.
6. **Admin two-factor authentication is not built.** The admin password is the only factor. Use a long generated password and keep the owner's email account secure.
7. **Open decisions.** Freelancers can see a client's email and phone in some lead lists (see the guide, section 6). Portfolio image hosts can see visitors' addresses.
8. **Supabase contact form has no server-side anti-spam** (needs an Edge Function or CAPTCHA).

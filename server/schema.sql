-- XLANORA local database (SQLite), version 2. Applied automatically by server/app.py on start.
-- Mirrors supabase/migrations/001_init.sql and 002_accounts.sql.

CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT NOT NULL UNIQUE CHECK (length(email) BETWEEN 5 AND 254),
    full_name      TEXT NOT NULL CHECK (length(full_name) BETWEEN 2 AND 80),
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('client', 'freelancer')),
    specialty      TEXT CHECK (specialty IS NULL OR specialty IN ('photography', 'home-maintenance', 'education-training', 'graphic-design', 'web-development', 'video-editing', 'digital-marketing', 'translation-services', 'social-media-management')),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    CHECK ((role = 'freelancer' AND specialty IS NOT NULL) OR (role = 'client' AND specialty IS NULL))
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash  TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    expires_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER REFERENCES users (id) ON DELETE SET NULL,
    name        TEXT NOT NULL CHECK (length(name) BETWEEN 2 AND 80),
    email       TEXT NOT NULL CHECK (length(email) BETWEEN 5 AND 254),
    phone       TEXT CHECK (phone IS NULL OR length(phone) <= 30),
    service     TEXT NOT NULL DEFAULT '' CHECK (service IN ('', 'photography', 'home-maintenance', 'education-training', 'graphic-design', 'web-development', 'video-editing', 'digital-marketing', 'translation-services', 'social-media-management', 'unsure')),
    message     TEXT NOT NULL CHECK (length(message) BETWEEN 10 AND 2000),
    ip_hash     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_contact_messages_created_at ON contact_messages (created_at);
CREATE INDEX IF NOT EXISTS idx_contact_messages_service ON contact_messages (service);
CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions (expires_at);

-- ---------- bookings (version 3) ----------
-- Services offered by freelancers. Category must match the freelancer's specialty (trigger below).
CREATE TABLE IF NOT EXISTS services (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id       INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title             TEXT NOT NULL CHECK (length(title) BETWEEN 3 AND 100),
    description       TEXT NOT NULL CHECK (length(description) BETWEEN 10 AND 1000),
    price_sar         INTEGER NOT NULL CHECK (price_sar BETWEEN 0 AND 100000),
    duration_minutes  INTEGER NOT NULL CHECK (duration_minutes BETWEEN 30 AND 480 AND duration_minutes % 30 = 0),
    category          TEXT NOT NULL CHECK (category IN ('photography', 'home-maintenance', 'education-training', 'graphic-design', 'web-development', 'video-editing', 'digital-marketing', 'translation-services', 'social-media-management')),
    active            INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TRIGGER IF NOT EXISTS services_category_matches_specialty
BEFORE INSERT ON services
WHEN NOT EXISTS (
    SELECT 1 FROM users u WHERE u.id = NEW.provider_id AND u.role = 'freelancer' AND u.specialty = NEW.category
)
BEGIN
    SELECT RAISE(ABORT, 'service_category_mismatch');
END;

-- Weekly working windows of a freelancer, in local time, minutes after midnight.
CREATE TABLE IF NOT EXISTS availability (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id   INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    weekday       INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    start_minute  INTEGER NOT NULL CHECK (start_minute BETWEEN 0 AND 1410 AND start_minute % 30 = 0),
    end_minute    INTEGER NOT NULL CHECK (end_minute BETWEEN 30 AND 1440 AND end_minute % 30 = 0),
    CHECK (end_minute > start_minute)
);

CREATE TRIGGER IF NOT EXISTS availability_no_overlap
BEFORE INSERT ON availability
WHEN EXISTS (
    SELECT 1 FROM availability a
    WHERE a.provider_id = NEW.provider_id AND a.weekday = NEW.weekday
      AND a.start_minute < NEW.end_minute AND NEW.start_minute < a.end_minute
)
BEGIN
    SELECT RAISE(ABORT, 'availability_overlaps');
END;

-- A booking is one appointment. Status: pending -> accepted -> completed, or pending/accepted -> rejected/cancelled.
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    provider_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    service_id  INTEGER NOT NULL REFERENCES services (id) ON DELETE RESTRICT,
    starts_at   TEXT NOT NULL,
    ends_at     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'cancelled', 'completed')),
    note        TEXT NOT NULL DEFAULT '' CHECK (length(note) <= 500),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (ends_at > starts_at),
    CHECK (client_id <> provider_id)
);

-- Booking rules enforced by the database, not only by the server.
CREATE TRIGGER IF NOT EXISTS bookings_not_in_past
BEFORE INSERT ON bookings
WHEN NEW.starts_at <= strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
BEGIN
    SELECT RAISE(ABORT, 'booking_in_past');
END;

CREATE TRIGGER IF NOT EXISTS bookings_service_belongs_to_provider
BEFORE INSERT ON bookings
WHEN NOT EXISTS (
    SELECT 1 FROM services s WHERE s.id = NEW.service_id AND s.provider_id = NEW.provider_id AND s.active = 1
)
BEGIN
    SELECT RAISE(ABORT, 'service_not_available');
END;

CREATE TRIGGER IF NOT EXISTS bookings_length_matches_service
BEFORE INSERT ON bookings
WHEN ROUND((julianday(NEW.ends_at) - julianday(NEW.starts_at)) * 1440) <>
     (SELECT duration_minutes FROM services WHERE id = NEW.service_id)
BEGIN
    SELECT RAISE(ABORT, 'booking_length_mismatch');
END;

CREATE TRIGGER IF NOT EXISTS bookings_no_overlap
BEFORE INSERT ON bookings
WHEN NEW.status IN ('pending', 'accepted') AND EXISTS (
    SELECT 1 FROM bookings b
    WHERE b.provider_id = NEW.provider_id AND b.status IN ('pending', 'accepted')
      AND b.starts_at < NEW.ends_at AND NEW.starts_at < b.ends_at
)
BEGIN
    SELECT RAISE(ABORT, 'booking_overlaps');
END;

CREATE INDEX IF NOT EXISTS idx_services_provider ON services (provider_id);
CREATE INDEX IF NOT EXISTS idx_services_category_active ON services (category, active);
CREATE INDEX IF NOT EXISTS idx_availability_provider ON availability (provider_id, weekday);
CREATE INDEX IF NOT EXISTS idx_bookings_provider_starts ON bookings (provider_id, starts_at);
CREATE INDEX IF NOT EXISTS idx_bookings_client ON bookings (client_id);


-- Portfolio: work samples a freelancer shows to clients. Links must be https. Soft delete through active.
CREATE TABLE IF NOT EXISTS portfolio_items (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id       INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title             TEXT NOT NULL CHECK (length(title) BETWEEN 3 AND 100),
    description       TEXT NOT NULL CHECK (length(description) BETWEEN 10 AND 1000),
    image_url         TEXT CHECK (image_url IS NULL OR (length(image_url) <= 500 AND image_url LIKE 'https://%')),
    project_url       TEXT CHECK (project_url IS NULL OR (length(project_url) <= 500 AND project_url LIKE 'https://%')),
    category          TEXT NOT NULL CHECK (category IN ('photography', 'home-maintenance', 'education-training', 'graphic-design', 'web-development', 'video-editing', 'digital-marketing', 'translation-services', 'social-media-management')),
    active            INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_portfolio_provider ON portfolio_items (provider_id, active);
CREATE INDEX IF NOT EXISTS idx_portfolio_category_active ON portfolio_items (category, active);

CREATE TRIGGER IF NOT EXISTS portfolio_category_matches_specialty
BEFORE INSERT ON portfolio_items
WHEN NOT EXISTS (
    SELECT 1 FROM users u WHERE u.id = NEW.provider_id AND u.role = 'freelancer' AND u.specialty = NEW.category
)
BEGIN
    SELECT RAISE(ABORT, 'portfolio_category_mismatch');
END;

-- ===================================================================
-- Financial management (phase 1). Money is always in halalas (1 SAR = 100).
-- Real payments are not active: the only provider is the sandbox.
-- ===================================================================

CREATE TABLE IF NOT EXISTS platform_settings (
    key         TEXT PRIMARY KEY CHECK (key IN ('commission_bps')),
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_by  INTEGER REFERENCES users (id) ON DELETE SET NULL
);

INSERT OR IGNORE INTO platform_settings (key, value) VALUES ('commission_bps', '1000');

-- The sandbox provider's own records (stands in for the provider's dashboard).
CREATE TABLE IF NOT EXISTS sandbox_payments (
    provider_ref   TEXT PRIMARY KEY CHECK (length(provider_ref) BETWEEN 8 AND 80),
    amount_halalas INTEGER NOT NULL CHECK (amount_halalas > 0),
    status         TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'failed')),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS subscription_plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL UNIQUE CHECK (code GLOB '[a-z0-9-]*' AND length(code) BETWEEN 3 AND 40),
    name          TEXT NOT NULL CHECK (length(name) BETWEEN 3 AND 80),
    audience      TEXT NOT NULL CHECK (audience IN ('freelancer', 'client')),
    price_halalas INTEGER NOT NULL CHECK (price_halalas >= 0),
    interval_days INTEGER NOT NULL CHECK (interval_days BETWEEN 1 AND 366),
    active        INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS user_subscriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    plan_id     INTEGER NOT NULL REFERENCES subscription_plans (id) ON DELETE RESTRICT,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'active', 'cancelled', 'expired')),
    starts_at   TEXT,
    ends_at     TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (status <> 'active' OR (starts_at IS NOT NULL AND ends_at IS NOT NULL AND ends_at > starts_at))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_subscription ON user_subscriptions (user_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_user_subscriptions_user ON user_subscriptions (user_id, status);

CREATE TABLE IF NOT EXISTS payouts (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    freelancer_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    amount_halalas INTEGER NOT NULL CHECK (amount_halalas > 0),
    status         TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'paid', 'rejected')),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decided_at     TEXT,
    decided_by     INTEGER REFERENCES users (id) ON DELETE SET NULL,
    CHECK ((status = 'requested' AND decided_at IS NULL) OR (status <> 'requested' AND decided_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_payouts_freelancer ON payouts (freelancer_id, status);

CREATE TABLE IF NOT EXISTS payment_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL CHECK (kind IN ('booking', 'subscription')),
    booking_id      INTEGER REFERENCES bookings (id) ON DELETE RESTRICT,
    subscription_id INTEGER REFERENCES user_subscriptions (id) ON DELETE RESTRICT,
    payer_id        INTEGER NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    payee_id        INTEGER REFERENCES users (id) ON DELETE RESTRICT,
    amount_halalas  INTEGER NOT NULL CHECK (amount_halalas > 0),
    commission_bps  INTEGER NOT NULL CHECK (commission_bps BETWEEN 0 AND 5000),
    currency        TEXT NOT NULL DEFAULT 'SAR' CHECK (currency = 'SAR'),
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'failed', 'refunded')),
    provider        TEXT NOT NULL DEFAULT 'sandbox' CHECK (provider IN ('sandbox')),
    provider_ref    TEXT NOT NULL UNIQUE REFERENCES sandbox_payments (provider_ref) ON DELETE RESTRICT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK ((kind = 'booking' AND booking_id IS NOT NULL AND subscription_id IS NULL AND payee_id IS NOT NULL)
        OR (kind = 'subscription' AND subscription_id IS NOT NULL AND booking_id IS NULL AND payee_id IS NULL))
);
-- At most one open payment per booking (failed payments may be retried; paid or refunded ones block a second charge).
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_payment_per_booking ON payment_transactions (booking_id)
    WHERE booking_id IS NOT NULL AND status IN ('pending', 'paid', 'refunded');
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_subscription_payment ON payment_transactions (subscription_id)
    WHERE subscription_id IS NOT NULL AND status IN ('pending', 'paid');
CREATE INDEX IF NOT EXISTS idx_payment_transactions_status ON payment_transactions (status, created_at);

CREATE TABLE IF NOT EXISTS platform_commissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  INTEGER NOT NULL UNIQUE REFERENCES payment_transactions (id) ON DELETE RESTRICT,
    rate_bps        INTEGER NOT NULL CHECK (rate_bps BETWEEN 0 AND 5000),
    amount_halalas  INTEGER NOT NULL CHECK (amount_halalas >= 0),
    status          TEXT NOT NULL DEFAULT 'accrued' CHECK (status IN ('accrued', 'reversed')),
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS freelancer_earnings (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id         INTEGER NOT NULL UNIQUE REFERENCES payment_transactions (id) ON DELETE RESTRICT,
    freelancer_id          INTEGER NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    gross_halalas          INTEGER NOT NULL CHECK (gross_halalas > 0),
    commission_halalas     INTEGER NOT NULL CHECK (commission_halalas >= 0),
    net_halalas            INTEGER NOT NULL CHECK (net_halalas >= 0),
    status                 TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending', 'awaiting_confirmation', 'available', 'paid_out', 'reversed')),
    payout_id              INTEGER REFERENCES payouts (id) ON DELETE SET NULL,
    provider_eligible_at   TEXT,
    created_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    updated_at             TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (gross_halalas = commission_halalas + net_halalas),
    CHECK (status <> 'available' OR provider_eligible_at IS NOT NULL),
    CHECK (payout_id IS NULL OR status IN ('available', 'paid_out'))
);
CREATE INDEX IF NOT EXISTS idx_earnings_freelancer ON freelancer_earnings (freelancer_id, status);

CREATE TABLE IF NOT EXISTS refunds (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  INTEGER NOT NULL REFERENCES payment_transactions (id) ON DELETE RESTRICT,
    amount_halalas  INTEGER NOT NULL CHECK (amount_halalas > 0),
    reason          TEXT NOT NULL DEFAULT '' CHECK (length(reason) <= 200),
    status          TEXT NOT NULL DEFAULT 'requested' CHECK (status IN ('requested', 'processed', 'rejected')),
    requested_by   INTEGER REFERENCES users (id) ON DELETE SET NULL,
    decided_by      INTEGER REFERENCES users (id) ON DELETE SET NULL,
    provider_ref    TEXT UNIQUE,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    decided_at      TEXT
);
-- Only one open refund request per payment.
CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_refund ON refunds (transaction_id) WHERE status = 'requested';

CREATE TABLE IF NOT EXISTS payment_webhook_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL CHECK (provider IN ('sandbox')),
    event_id        TEXT NOT NULL CHECK (length(event_id) BETWEEN 4 AND 80),
    event_type      TEXT NOT NULL CHECK (length(event_type) <= 60),
    outcome         TEXT NOT NULL CHECK (outcome IN ('processed', 'ignored', 'rejected')),
    payload_sha256  TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    received_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (provider, event_id)
);

CREATE TABLE IF NOT EXISTS financial_audit_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id     INTEGER REFERENCES users (id) ON DELETE SET NULL,
    action       TEXT NOT NULL CHECK (length(action) <= 60),
    entity       TEXT NOT NULL CHECK (length(entity) <= 40),
    entity_id    TEXT NOT NULL CHECK (length(entity_id) <= 40),
    details      TEXT NOT NULL DEFAULT '{}' CHECK (length(details) <= 2000),
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_audit_entity ON financial_audit_logs (entity, entity_id);

-- The audit log is append-only: rows cannot be changed or removed.
CREATE TRIGGER IF NOT EXISTS financial_audit_no_update BEFORE UPDATE ON financial_audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_log_is_append_only');
END;
CREATE TRIGGER IF NOT EXISTS financial_audit_no_delete BEFORE DELETE ON financial_audit_logs
BEGIN
    SELECT RAISE(ABORT, 'audit_log_is_append_only');
END;

-- A refund can never exceed what was paid for the payment.
CREATE TRIGGER IF NOT EXISTS refunds_not_above_payment BEFORE INSERT ON refunds
WHEN NEW.amount_halalas > (SELECT amount_halalas FROM payment_transactions WHERE id = NEW.transaction_id)
BEGIN
    SELECT RAISE(ABORT, 'refund_exceeds_payment');
END;

-- Saved freelancers (wishlist). Only clients may save; the foreign keys keep rows consistent.
CREATE TABLE IF NOT EXISTS wishlist (
  client_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  freelancer_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (client_id, freelancer_id),
  CHECK (client_id <> freelancer_id)
);

-- Reviews: one per completed booking. Only the client of that booking can write it, and only after the
-- freelancer marked the booking complete. Reviews cannot be edited (trigger below).
CREATE TABLE IF NOT EXISTS reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id     INTEGER NOT NULL UNIQUE REFERENCES bookings (id) ON DELETE CASCADE,
    client_id      INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    freelancer_id  INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    rating         INTEGER NOT NULL CHECK (rating BETWEEN 1 AND 5),
    comment        TEXT NOT NULL DEFAULT '' CHECK (length(comment) <= 600),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (client_id <> freelancer_id)
);
CREATE INDEX IF NOT EXISTS idx_reviews_freelancer ON reviews (freelancer_id, created_at);

CREATE TRIGGER IF NOT EXISTS reviews_booking_guard
BEFORE INSERT ON reviews
WHEN NOT EXISTS (
    SELECT 1 FROM bookings b
    WHERE b.id = NEW.booking_id AND b.status = 'completed'
      AND b.client_id = NEW.client_id AND b.provider_id = NEW.freelancer_id
)
BEGIN
    SELECT RAISE(ABORT, 'review_not_allowed');
END;

CREATE TRIGGER IF NOT EXISTS reviews_no_update
BEFORE UPDATE ON reviews
BEGIN
    SELECT RAISE(ABORT, 'reviews_are_final');
END;

-- A client's "I am looking for <category>" signal. Used to limit alerts to one per client and category a day.
CREATE TABLE IF NOT EXISTS category_alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    client_id   INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    category    TEXT NOT NULL CHECK (category IN ('photography', 'home-maintenance', 'education-training', 'graphic-design', 'web-development', 'video-editing', 'digital-marketing', 'translation-services', 'social-media-management')),
    recipients  INTEGER NOT NULL DEFAULT 0 CHECK (recipients >= 0),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_category_alerts_client ON category_alerts (client_id, category, created_at);

-- Outgoing e-mails. Rows stay 'queued' when no SMTP server is configured, so nothing is lost.
CREATE TABLE IF NOT EXISTS email_outbox (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    to_address  TEXT NOT NULL CHECK (length(to_address) BETWEEN 5 AND 254),
    subject     TEXT NOT NULL CHECK (length(subject) <= 200),
    body        TEXT NOT NULL CHECK (length(body) <= 4000),
    status      TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'sent', 'failed')),
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    sent_at     TEXT
);
CREATE INDEX IF NOT EXISTS idx_email_outbox_status ON email_outbox (status, id);

-- E-mail verification. A new account must confirm its e-mail before it can book a service or review a
-- freelancer. Only a hash of the token is stored.
CREATE TABLE IF NOT EXISTS email_verifications (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    token_hash  TEXT NOT NULL UNIQUE,
    expires_at  TEXT NOT NULL,
    used_at     TEXT,
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_email_verifications_user ON email_verifications (user_id, created_at);

-- ---------- direct payment and order confirmations (no payment gateway, no commission) ----------
-- The agreed price is copied from the service when the order is created. Payment is arranged directly
-- between customer and freelancer; the site only records what each side confirms, separately.
CREATE TABLE IF NOT EXISTS booking_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL REFERENCES bookings (id) ON DELETE CASCADE,
    actor_id   INTEGER REFERENCES users (id) ON DELETE SET NULL,
    action     TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
CREATE INDEX IF NOT EXISTS idx_booking_events_booking ON booking_events (booking_id, id);

CREATE TABLE IF NOT EXISTS order_reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    booking_id INTEGER NOT NULL REFERENCES bookings (id) ON DELETE CASCADE,
    reporter_id INTEGER NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    reason     TEXT NOT NULL CHECK (reason IN ('no_show', 'no_payment', 'poor_quality', 'abuse', 'other')),
    details    TEXT NOT NULL DEFAULT '' CHECK (length(details) <= 1000),
    status     TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (booking_id, reporter_id)
);

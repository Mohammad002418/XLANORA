#!/usr/bin/env python3
"""XLANORA local server (standard library only).

- Serves the static site from site/ with security headers.
- Accounts: clients and freelancers sign up, log in and log out (cookie sessions).
- Contact requests: stored in SQLite, linked to the account when signed in.
- Optional email copy of each request when SMTP_HOST is set.

Run:  python3 server/app.py --port 8000
"""

import argparse
import csv
import hashlib
import hmac
import io
import json
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
SITE = (ROOT / "site").resolve()
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"
DEFAULT_DB = Path(__file__).resolve().parent / "data" / "xlanora.db"

MAX_BODY_BYTES = 8 * 1024
RATE_LIMIT_COUNT = 5  # contact requests per IP
AUTH_RATE_LIMIT_COUNT = 10  # register or login attempts per IP
RATE_LIMIT_WINDOW = 600  # seconds

SESSION_COOKIE = "xlanora_session"
SESSION_DAYS = 7
PBKDF2_ITERS = int(os.environ.get("XLANORA_PBKDF2_ITERS", "310000"))
SECURE_COOKIES = os.environ.get("XLANORA_SECURE_COOKIES") == "1"  # set to 1 behind HTTPS
# Set to 1 only when a reverse proxy you control sets X-Forwarded-For. Otherwise the header is ignored.
TRUST_PROXY = os.environ.get("XLANORA_TRUST_PROXY") == "1"
REQUESTS_PAGE = 50
PRUNE_EVERY = 1000  # rate limiter: drop idle IP keys every N calls

# Service slugs. Must match build/content.py SERVICES (checked by tests/test_consistency.py).
SPECIALTIES = frozenset({
    "photography", "home-maintenance", "education-training",
    "graphic-design", "web-development", "video-editing",
    "digital-marketing", "translation-services", "social-media-management",
})
ALLOWED_SERVICES = frozenset({""} | SPECIALTIES | {"unsure"})
ROLES = {"client", "freelancer"}
PASSWORD_MIN, PASSWORD_MAX = 8, 128

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
PHONE_RE = re.compile(r"^[0-9+\-\s()]{0,30}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; img-src 'self' data: https:; media-src 'self' https://*.supabase.co; connect-src 'self' https://*.supabase.co; "
        "form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webp": "image/webp",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".xml": "application/xml; charset=utf-8",
}

import bookings as rules  # noqa: E402  - booking rules, see server/bookings.py
import finance as fin  # noqa: E402  - money rules and provider boundary, see server/finance.py
from finance import FinanceError, csv_safe  # noqa: E402
from finance_store import FinanceStore, halalas_text  # noqa: E402

log = logging.getLogger("xlanora")


MAX_ACTIVE_SERVICES = 3  # a freelancer may publish at most three active services


IMAGE_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per image (avatars and portfolio photos)
VIDEO_MAX_BYTES = 50 * 1024 * 1024  # 50 MB per portfolio video
IMAGE_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
VIDEO_TYPES = {"video/mp4": "mp4", "video/webm": "webm", "video/quicktime": "mov"}
UPLOAD_NAME_RE = re.compile(r"[a-f0-9]{32}\.(jpg|png|webp|mp4|webm|mov)")
UPLOAD_MIME = {
    "jpg": "image/jpeg", "png": "image/png", "webp": "image/webp",
    "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
}
VIDEO_EXTS = {"mp4", "webm", "mov"}


def sniff_image(data):
    """Return (extension, mime) when the bytes really are a JPEG, PNG or WebP image, else None.
    The browser's claimed type is never trusted on its own."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def sniff_video(data):
    """Return (extension, mime) when the bytes really are an MP4, MOV or WebM video, else None."""
    if len(data) >= 12 and data[4:8] == b"ftyp":
        if data[8:12] == b"qt  ":
            return "mov", "video/quicktime"
        return "mp4", "video/mp4"
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return "webm", "video/webm"
    return None


# Payment routes from the old commission system. XLANORA no longer takes money or a commission: customers and
# freelancers pay each other directly. These paths answer 410 so nothing on the old flow is reachable.
RETIRED_PAYMENT_PREFIXES = (
    "/api/payments", "/api/plans", "/api/my/subscription", "/api/my/finance", "/api/my/payouts",
    "/api/admin/refunds", "/api/admin/payouts", "/api/admin/plans", "/api/admin/settings/commission",
    "/api/admin/subscriptions",
)


def is_retired_payment_path(path):
    return path.startswith(RETIRED_PAYMENT_PREFIXES)


class ApiError(Exception):
    def __init__(self, status, errors):
        super().__init__(status)
        self.status = status
        self.payload = {"errors": errors}


class BookingRefused(Exception):
    """The database refused a booking (overlap, past time, wrong length or service)."""


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(data, field):
    """Return the field as a string ('' if missing), or None if it is not a string."""
    value = data.get(field, "")
    if value is None:
        return ""
    return value if isinstance(value, str) else None


def validate_contact(data):
    """Return (clean_values, errors). Same rules as site/assets/js/contact.js."""
    if not isinstance(data, dict):
        return None, {"form": "invalid"}
    errors, clean = {}, {}

    name = _text(data, "name")
    if name is None or CONTROL_RE.search(name) or not (2 <= len(name.strip()) <= 80):
        errors["name"] = "invalid_name"
    else:
        clean["name"] = name.strip()

    email = _text(data, "email")
    if email is None or not (5 <= len(email.strip()) <= 254) or not EMAIL_RE.match(email.strip()):
        errors["email"] = "invalid_email"
    else:
        clean["email"] = email.strip()

    phone = _text(data, "phone")
    if phone is None or CONTROL_RE.search(phone) or not PHONE_RE.match(phone.strip()):
        errors["phone"] = "invalid_phone"
    else:
        clean["phone"] = phone.strip() or None

    service = _text(data, "service")
    if service is None or service not in ALLOWED_SERVICES:
        errors["service"] = "invalid_service"
    else:
        clean["service"] = service

    message = _text(data, "message")
    if message is None or CONTROL_RE.search(message) or not (10 <= len(message.strip()) <= 2000):
        errors["message"] = "invalid_message"
    else:
        clean["message"] = message.strip()

    return clean, errors


def validate_registration(data):
    """Raise ApiError(400) with field errors, or return clean account values."""
    if not isinstance(data, dict):
        raise ApiError(400, {"form": "invalid"})
    errors, clean = {}, {}

    name = _text(data, "full_name")
    if name is None or CONTROL_RE.search(name) or not (2 <= len(name.strip()) <= 80):
        errors["full_name"] = "invalid_name"
    else:
        clean["full_name"] = name.strip()

    email = _text(data, "email")
    email_n = email.strip().lower() if email else ""
    if email is None or not (5 <= len(email_n) <= 254) or not EMAIL_RE.match(email_n):
        errors["email"] = "invalid_email"
    else:
        clean["email"] = email_n

    password = _text(data, "password")
    if password is None or not (PASSWORD_MIN <= len(password) <= PASSWORD_MAX):
        errors["password"] = "invalid_password"
    else:
        clean["password"] = password

    role = _text(data, "role")
    if role not in ROLES:
        errors["role"] = "invalid_role"
    else:
        clean["role"] = role

    specialty = _text(data, "specialty")
    if specialty is None:
        errors["specialty"] = "invalid_specialty"
    elif role == "freelancer":
        if specialty not in SPECIALTIES:
            errors["specialty"] = "invalid_specialty"
        else:
            clean["specialty"] = specialty
    elif role == "client":
        if specialty:
            errors["specialty"] = "not_allowed_for_client"
        clean["specialty"] = None

    if errors:
        raise ApiError(400, errors)
    return clean


def hash_password(password, iterations=PBKDF2_ITERS):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, iterations, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(digest, bytes.fromhex(digest_hex))
    except (ValueError, TypeError):
        return False


# Used when the email is unknown, so login takes the same time either way (no account guessing by timing).
DUMMY_HASH = hash_password("not-a-real-password-xlanora")


def hash_token(raw):
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _portfolio_json(row):
    """A portfolio item for the API: image_url is the uploaded photo if there is one, else the link."""
    item = dict(row)
    name = item.pop("image_file", None)
    item["media_type"] = "image"
    if name and UPLOAD_NAME_RE.fullmatch(name):
        item["image_url"] = "/uploads/" + name
        if name.rsplit(".", 1)[1] in VIDEO_EXTS:
            item["media_type"] = "video"
    return item


def public_user(row):
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "email": row["email"],
        "role": row["role"],
        "specialty": row["specialty"],
        "is_admin": bool(row["is_admin"]) if "is_admin" in row.keys() else False,
        "avatar_url": row["avatar_url"] if "avatar_url" in row.keys() else None,
        "email_verified": bool(row["email_verified_at"]) if "email_verified_at" in row.keys() else False,
        "headline": row["headline"] if "headline" in row.keys() else "",
    }


class RateLimiter:
    """Sliding-window limit per key (client IP). In memory, so it resets on restart."""

    def __init__(self, limit=RATE_LIMIT_COUNT, window=RATE_LIMIT_WINDOW):
        self.limit = limit
        self.window = window
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def allow(self, key, now=None):
        now = time.monotonic() if now is None else now
        with self._lock:
            self._calls += 1
            if self._calls % PRUNE_EVERY == 0:
                self._prune(now)
            hits = self._hits[key]
            while hits and now - hits[0] > self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def _prune(self, now):
        """Forget IPs whose hits have all expired, so memory does not grow without limit."""
        for key in [k for k, hits in self._hits.items() if not hits or now - hits[-1] > self.window]:
            del self._hits[key]


class Store(FinanceStore):
    """SQLite storage. Every query uses parameters; no SQL is built from user input."""

    def __init__(self, db_path):
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.upload_dir = db_path.parent / "uploads"  # uploaded images; never inside the website folder
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.execute("PRAGMA foreign_keys = ON")
            schema = SCHEMA_PATH.read_text(encoding="utf-8")
            self._conn.executescript(schema)
            # Databases created by version 1 lack user_id on contact_messages; add it once.
            cols = [row[1] for row in self._conn.execute("PRAGMA table_info(contact_messages)")]
            if "user_id" not in cols:
                self._conn.execute(
                    "ALTER TABLE contact_messages ADD COLUMN user_id INTEGER REFERENCES users (id) ON DELETE SET NULL"
                )
            self._conn.commit()
            self._migrate_service_list(schema)
            # Created here, after the column exists, so old databases migrate cleanly.
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_messages_user_id ON contact_messages (user_id)")
            self._conn.commit()
            # Admin flag. Set only from the command line (server/manage.py), never through the web API.
            user_cols = [row[1] for row in self._conn.execute("PRAGMA table_info(users)")]
            if "is_admin" not in user_cols:
                self._conn.execute(
                    "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0 CHECK (is_admin IN (0, 1))"
                )
                self._conn.commit()
            # E-mail verification time. Accounts that existed before this change count as verified.
            user_cols = [row[1] for row in self._conn.execute("PRAGMA table_info(users)")]
            if "email_verified_at" not in user_cols:
                self._conn.execute("ALTER TABLE users ADD COLUMN email_verified_at TEXT")
                self._conn.execute("UPDATE users SET email_verified_at = created_at WHERE email_verified_at IS NULL")
                self._conn.commit()
            # Profile photo: the uploaded file's path, or NULL.
            user_cols = [row[1] for row in self._conn.execute("PRAGMA table_info(users)")]
            if "avatar_url" not in user_cols:
                self._conn.execute("ALTER TABLE users ADD COLUMN avatar_url TEXT")
                self._conn.commit()
            # Short public headline shown on a freelancer's profile.
            user_cols = [row[1] for row in self._conn.execute("PRAGMA table_info(users)")]
            if "headline" not in user_cols:
                self._conn.execute("ALTER TABLE users ADD COLUMN headline TEXT NOT NULL DEFAULT ''")
                self._conn.commit()
            # Work-sample photo uploaded from the device: the stored file name, or NULL.
            item_cols = [row[1] for row in self._conn.execute("PRAGMA table_info(portfolio_items)")]
            if "image_file" not in item_cols:
                self._conn.execute("ALTER TABLE portfolio_items ADD COLUMN image_file TEXT")
                self._conn.commit()
            # Direct payment and order confirmations (see schema.sql). Existing orders get no payment data.
            booking_cols = [row[1] for row in self._conn.execute("PRAGMA table_info(bookings)")]
            for col, ddl in [
                ("agreed_price_sar", "INTEGER"),
                ("payment_method", "TEXT CHECK (payment_method IN ('bank_transfer', 'cash', 'other'))"),
                ("payment_method_note", "TEXT NOT NULL DEFAULT '' CHECK (length(payment_method_note) <= 200)"),
                ("payment_currency", "TEXT NOT NULL DEFAULT 'SAR' CHECK (payment_currency IN ('SAR', 'USD'))"),
                ("client_paid_at", "TEXT"),
                ("provider_received_at", "TEXT"),
                ("delivery_confirmed_at", "TEXT"),
            ]:
                if col not in booking_cols:
                    self._conn.execute("ALTER TABLE bookings ADD COLUMN " + col + " " + ddl)
            self._conn.execute(
                "UPDATE bookings SET agreed_price_sar = (SELECT price_sar FROM services WHERE services.id = bookings.service_id) "
                "WHERE agreed_price_sar IS NULL")
            self._conn.commit()

    def _migrate_service_list(self, schema):
        """SQLite cannot change a CHECK constraint, so tables that still list only the
        original three services are rebuilt with the current list. Rows are kept."""
        row = self._conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'users'").fetchone()
        if row is None or "social-media-management" in row[0]:
            return
        self._conn.execute("PRAGMA foreign_keys = OFF")
        # legacy_alter_table keeps the foreign keys in sessions pointing at "users".
        self._conn.execute("PRAGMA legacy_alter_table = ON")
        self._conn.execute("ALTER TABLE users RENAME TO users_old")
        self._conn.execute("ALTER TABLE contact_messages RENAME TO contact_messages_old")
        self._conn.commit()
        self._conn.executescript(schema)  # fresh tables with the current CHECK lists
        self._conn.execute(
            "INSERT INTO users (id, email, full_name, password_hash, role, specialty, created_at) "
            "SELECT id, email, full_name, password_hash, role, specialty, created_at FROM users_old"
        )
        self._conn.execute(
            "INSERT INTO contact_messages (id, user_id, name, email, phone, service, message, ip_hash, created_at) "
            "SELECT id, user_id, name, email, phone, service, message, ip_hash, created_at FROM contact_messages_old"
        )
        self._conn.execute("DROP TABLE users_old")
        self._conn.execute("DROP TABLE contact_messages_old")
        self._conn.commit()
        self._conn.executescript(schema)  # recreate indexes that were dropped with the old tables
        self._conn.execute("PRAGMA legacy_alter_table = OFF")
        self._conn.execute("PRAGMA foreign_keys = ON")

    # --- users and sessions ---
    VERIFY_HOURS = 24
    VERIFY_RESEND_SECONDS = 600

    def create_verification(self, user_id, user_email, user_name):
        """Store a hash of a new one-time token and queue the e-mail. Returns the queued outbox id, or None when
        a link was sent in the last 10 minutes."""
        now = utc_now()
        with self._lock:
            recent = self._conn.execute(
                "SELECT 1 FROM email_verifications WHERE user_id = ? AND created_at > ? LIMIT 1",
                (user_id, iso(now - timedelta(seconds=self.VERIFY_RESEND_SECONDS)))).fetchone()
            if recent:
                return None
            raw = secrets.token_urlsafe(32)
            self._conn.execute(
                "INSERT INTO email_verifications (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)",
                (user_id, hashlib.sha256(raw.encode()).hexdigest(),
                 iso(now + timedelta(hours=self.VERIFY_HOURS)), iso(now)))
            site = os.environ.get("XLANORA_PUBLIC_URL", "").rstrip("/")
            link = f"{site}/en/verify.html?token={raw}"
            subject = "Confirm your XLANORA e-mail"
            body = (f"Hello {user_name},\n\nConfirm your e-mail to book services and leave reviews on XLANORA:\n"
                    f"{link}\n\nThe link works for {self.VERIFY_HOURS} hours. If you did not create an account, ignore this e-mail.\n\n"
                    "--\nXLANORA - contactxlanora@gmail.com\n")
            cur = self._conn.execute("INSERT INTO email_outbox (to_address, subject, body) VALUES (?, ?, ?)",
                                     (user_email, subject, body))
            self._conn.commit()
            return cur.lastrowid

    def verify_email(self, raw_token):
        """Mark the account verified if the token is valid, unused and not expired. Returns True or False."""
        if not isinstance(raw_token, str) or not 20 <= len(raw_token) <= 100:
            return False
        digest = hashlib.sha256(raw_token.encode()).hexdigest()
        now = iso(utc_now())
        with self._lock:
            row = self._conn.execute(
                "SELECT id, user_id FROM email_verifications WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
                (digest, now)).fetchone()
            if row is None:
                return False
            self._conn.execute("UPDATE email_verifications SET used_at = ? WHERE id = ?", (now, row["id"]))
            self._conn.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, ?) WHERE id = ?",
                               (now, row["user_id"]))
            self._conn.commit()
        return True

    def create_user(self, clean, password_hash):
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO users (email, full_name, password_hash, role, specialty) VALUES (?, ?, ?, ?, ?)",
                (clean["email"], clean["full_name"], password_hash, clean["role"], clean.get("specialty")),
            )
            self._conn.commit()
            return cur.lastrowid

    def user_by_email(self, email):
        with self._lock:
            return self._conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    def user_by_id(self, user_id):
        with self._lock:
            return self._conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()

    def create_session(self, user_id):
        raw = secrets.token_urlsafe(32)
        expires = iso(utc_now() + timedelta(days=SESSION_DAYS))
        with self._lock:
            # Expired sessions are removed whenever a new one is made, so the table does not grow forever.
            self._conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (iso(utc_now()),))
            self._conn.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (hash_token(raw), user_id, expires),
            )
            self._conn.commit()
        return raw

    def user_for_token(self, raw):
        if not raw:
            return None
        with self._lock:
            return self._conn.execute(
                "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id "
                "WHERE s.token_hash = ? AND s.expires_at > ?",
                (hash_token(raw), iso(utc_now())),
            ).fetchone()

    def delete_session(self, raw):
        if not raw:
            return
        with self._lock:
            self._conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_token(raw),))
            self._conn.commit()

    # --- contact requests ---
    def insert_contact(self, values, ip_hash, user_id):
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO contact_messages (user_id, name, email, phone, service, message, ip_hash) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, values["name"], values["email"], values.get("phone"), values["service"],
                 values["message"], ip_hash),
            )
            self._conn.commit()
            return cur.lastrowid

    def requests_for(self, user, before=None, limit=REQUESTS_PAGE):
        """Clients see their own requests. Freelancers see requests for their specialty.
        Newest first, one page at a time. Columns are chosen explicitly so ip_hash is never returned."""
        columns = "id, name, email, phone, service, message, created_at"
        params = []
        if user["role"] == "client":
            where, params = "user_id = ?", [user["id"]]
        else:
            where, params = "service = ?", [user["specialty"]]
        if before is not None:
            where += " AND id < ?"
            params.append(before)
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {columns} FROM contact_messages WHERE {where} ORDER BY id DESC LIMIT ?",
                (*params, limit + 1),
            ).fetchall()
        rows = [dict(r) for r in rows]
        next_before = rows[limit - 1]["id"] if len(rows) > limit else None
        return rows[:limit], next_before

    # --- password ---
    def update_password(self, user_id, password_hash, keep_token_hash):
        """Store a new hash and end every other session of this user."""
        with self._lock:
            self._conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (password_hash, user_id))
            self._conn.execute("DELETE FROM sessions WHERE user_id = ? AND token_hash <> ?", (user_id, keep_token_hash))
            self._conn.commit()

    # --- services and availability ---
    def save_image(self, data, ext):
        """Write an already-validated image under a random name. Returns its public path."""
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        name = secrets.token_hex(16) + "." + ext
        target = self.upload_dir / name
        tmp = self.upload_dir / (name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
        return "/uploads/" + name

    def set_avatar(self, user_id, data, ext):
        url = self.save_image(data, ext)
        with self._lock:
            old = self._conn.execute("SELECT avatar_url FROM users WHERE id = ?", (user_id,)).fetchone()
            self._conn.execute("UPDATE users SET avatar_url = ? WHERE id = ?", (url, user_id))
            self._conn.commit()
        previous = old["avatar_url"] if old else None
        if previous and previous.startswith("/uploads/"):
            old_name = previous[len("/uploads/"):]
            if UPLOAD_NAME_RE.fullmatch(old_name):
                try:
                    (self.upload_dir / old_name).unlink()
                except OSError:
                    pass  # already gone: nothing to clean up
        return url

    def list_contacts(self, limit=200):
        """Newest contact messages for the administrator's inbox. The client's IP hash is never sent."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, name, email, phone, service, message, created_at FROM contact_messages "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def create_service(self, provider, clean):
        now = iso(utc_now())
        with self._lock:
            active = self._conn.execute(
                "SELECT COUNT(*) FROM services WHERE provider_id = ? AND active = 1", (provider["id"],)).fetchone()[0]
            if active >= MAX_ACTIVE_SERVICES:
                raise ApiError(409, {"services": "limit_reached"})
            cur = self._conn.execute(
                "INSERT INTO services (provider_id, title, description, price_sar, duration_minutes, category, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (provider["id"], clean["title"], clean["description"], clean["price_sar"],
                 clean["duration_minutes"], provider["specialty"], now, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def update_service(self, provider_id, service_id, clean):
        with self._lock:
            cur = self._conn.execute(
                "UPDATE services SET title = ?, description = ?, price_sar = ?, duration_minutes = ?, updated_at = ? "
                "WHERE id = ? AND provider_id = ? AND active = 1",
                (clean["title"], clean["description"], clean["price_sar"], clean["duration_minutes"],
                 iso(utc_now()), service_id, provider_id),
            )
            self._conn.commit()
            return cur.rowcount

    def deactivate_service(self, provider_id, service_id):
        """Soft delete: existing bookings keep their service; new bookings are refused."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE services SET active = 0, updated_at = ? WHERE id = ? AND provider_id = ? AND active = 1",
                (iso(utc_now()), service_id, provider_id),
            )
            self._conn.commit()
            return cur.rowcount

    def services_of(self, provider_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, description, price_sar, duration_minutes, category FROM services "
                "WHERE provider_id = ? AND active = 1 ORDER BY id DESC", (provider_id,)).fetchall()
        return [dict(r) for r in rows]

    def service_for_booking(self, service_id):
        with self._lock:
            row = self._conn.execute(
                "SELECT s.*, u.full_name AS provider_name, u.email AS provider_email FROM services s "
                "JOIN users u ON u.id = s.provider_id WHERE s.id = ? AND s.active = 1", (service_id,)).fetchone()
        return row

    def search_services(self, category=None, text=None, max_price=None, sort="newest"):
        clauses, params = ["s.active = 1"], []
        if category:
            clauses.append("s.category = ?")
            params.append(category)
        if text:
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(s.title LIKE ? ESCAPE '\\' OR s.description LIKE ? ESCAPE '\\' OR u.full_name LIKE ? ESCAPE '\\')")
            pattern = f"%{escaped}%"
            params += [pattern, pattern, pattern]
        if max_price is not None:
            clauses.append("s.price_sar <= ?")
            params.append(max_price)
        order = {"price_asc": "s.price_sar ASC, s.id DESC", "price_desc": "s.price_sar DESC, s.id DESC",
                 "name": "s.title COLLATE NOCASE ASC, s.id DESC"}.get(sort, "s.id DESC")
        with self._lock:
            rows = self._conn.execute(
                "SELECT s.id, s.title, s.description, s.price_sar, s.duration_minutes, s.category, "
                "u.full_name AS provider_name FROM services s JOIN users u ON u.id = s.provider_id "
                f"WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT 100", params).fetchall()
        return [dict(r) for r in rows]

    def create_portfolio_item(self, provider, clean):
        now = iso(utc_now())
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO portfolio_items (provider_id, title, description, image_url, project_url, category, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (provider["id"], clean["title"], clean["description"], clean["image_url"], clean["project_url"],
                 provider["specialty"], now, now))
            self._conn.commit()
            return cur.lastrowid

    def update_portfolio_item(self, provider_id, item_id, clean):
        with self._lock:
            cur = self._conn.execute(
                "UPDATE portfolio_items SET title = ?, description = ?, image_url = ?, project_url = ?, updated_at = ? "
                "WHERE id = ? AND provider_id = ? AND active = 1",
                (clean["title"], clean["description"], clean["image_url"], clean["project_url"],
                 iso(utc_now()), item_id, provider_id))
            self._conn.commit()
            return cur.rowcount

    def deactivate_portfolio_item(self, provider_id, item_id):
        with self._lock:
            cur = self._conn.execute(
                "UPDATE portfolio_items SET active = 0, updated_at = ? WHERE id = ? AND provider_id = ? AND active = 1",
                (iso(utc_now()), item_id, provider_id))
            self._conn.commit()
            return cur.rowcount

    def set_portfolio_image(self, provider_id, item_id, data, ext):
        """Attach an uploaded photo to one of the freelancer's own items. Returns its public path,
        or None when the item is not theirs (or is inactive). The previous upload is removed."""
        url = self.save_image(data, ext)
        name = url[len("/uploads/"):]
        with self._lock:
            old = self._conn.execute(
                "SELECT image_file FROM portfolio_items WHERE id = ? AND provider_id = ? AND active = 1",
                (item_id, provider_id)).fetchone()
            if old is None:
                (self.upload_dir / name).unlink(missing_ok=True)
                return None
            self._conn.execute(
                "UPDATE portfolio_items SET image_file = ?, updated_at = ? WHERE id = ? AND provider_id = ?",
                (name, iso(utc_now()), item_id, provider_id))
            self._conn.commit()
        previous = old["image_file"]
        if previous and UPLOAD_NAME_RE.fullmatch(previous):
            (self.upload_dir / previous).unlink(missing_ok=True)
        return url

    # --- freelancer directory and profiles ---
    def list_freelancers(self, text=None, category=None):
        clauses, params = ["u.role = 'freelancer'"], []
        if category:
            clauses.append("u.specialty = ?")
            params.append(category)
        if text:
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(u.full_name LIKE ? ESCAPE '\\' OR u.headline LIKE ? ESCAPE '\\')")
            pattern = f"%{escaped}%"
            params += [pattern, pattern]
        with self._lock:
            rows = self._conn.execute(
                "SELECT u.id, u.full_name, u.specialty, u.avatar_url, u.headline, "
                "(SELECT COUNT(*) FROM services s WHERE s.provider_id = u.id AND s.active = 1) AS service_count, "
                "(SELECT MIN(s.price_sar) FROM services s WHERE s.provider_id = u.id AND s.active = 1) AS from_price, "
                "(SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.freelancer_id = u.id) AS rating_avg, "
                "(SELECT COUNT(*) FROM reviews r WHERE r.freelancer_id = u.id) AS rating_count "
                f"FROM users u WHERE {' AND '.join(clauses)} ORDER BY u.full_name COLLATE NOCASE ASC LIMIT 100",
                params).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]

    def freelancer_detail(self, user_id, viewer=None):
        with self._lock:
            row = self._conn.execute(
                "SELECT u.id, u.full_name, u.specialty, u.avatar_url, u.headline, "
                "(SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.freelancer_id = u.id) AS rating_avg, "
                "(SELECT COUNT(*) FROM reviews r WHERE r.freelancer_id = u.id) AS rating_count "
                "FROM users u WHERE u.id = ? AND u.role = 'freelancer'",
                (user_id,)).fetchone()
            if row is None:
                return None
            services = self._conn.execute(
                "SELECT id, title, description, price_sar, duration_minutes, category FROM services "
                "WHERE provider_id = ? AND active = 1 ORDER BY id DESC", (user_id,)).fetchall()
        review_booking = None
        if viewer is not None and viewer["role"] == "client":
            review_booking = self.booking_to_review(viewer["id"], user_id)
        return {"freelancer": {k: row[k] for k in row.keys()},
                "services": [{k: r[k] for k in r.keys()} for r in services],
                "portfolio": self.portfolio_of(user_id),
                "reviews": self.reviews_for(user_id),
                "review_booking_id": review_booking}

    def reviews_for(self, freelancer_id, limit=20):
        with self._lock:
            rows = self._conn.execute(
                "SELECT r.id, r.rating, r.comment, r.created_at, u.full_name AS client_name "
                "FROM reviews r JOIN users u ON u.id = r.client_id "
                "WHERE r.freelancer_id = ? ORDER BY r.created_at DESC, r.id DESC LIMIT ?",
                (freelancer_id, limit)).fetchall()
        reviews = []
        for r in rows:
            parts = (r["client_name"] or "").split()
            short = parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "") if parts else ""
            reviews.append({"id": r["id"], "rating": r["rating"], "comment": r["comment"],
                            "created_at": r["created_at"], "client_name": short})
        return reviews

    def booking_to_review(self, client_id, freelancer_id):
        """The newest completed booking with this freelancer that has no review yet, or None."""
        with self._lock:
            row = self._conn.execute(
                "SELECT b.id FROM bookings b WHERE b.client_id = ? AND b.provider_id = ? AND b.status = 'completed' "
                "AND b.delivery_confirmed_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM reviews r WHERE r.booking_id = b.id) "
                "ORDER BY b.ends_at DESC, b.id DESC LIMIT 1", (client_id, freelancer_id)).fetchone()
        return row["id"] if row else None

    def create_review(self, client_id, booking_id, rating, comment):
        """Returns (review, None) or (None, reason). Reasons: not_found, not_completed, already_reviewed."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id, client_id, provider_id, status FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            if row is None or row["client_id"] != client_id:
                return None, "not_found"
            if row["status"] != "completed":
                return None, "not_completed"
            if row["client_id"] == row["provider_id"]:
                return None, "not_completed"
            confirmed = self._conn.execute(
                "SELECT delivery_confirmed_at FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            if confirmed["delivery_confirmed_at"] is None:
                return None, "delivery_not_confirmed"
            if self._conn.execute("SELECT 1 FROM reviews WHERE booking_id = ?", (booking_id,)).fetchone():
                return None, "already_reviewed"
            now = iso(utc_now())
            try:
                cur = self._conn.execute(
                    "INSERT INTO reviews (booking_id, client_id, freelancer_id, rating, comment, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (booking_id, client_id, row["provider_id"], rating, comment, now))
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.rollback()
                return None, "already_reviewed"
            review_id = cur.lastrowid
        return {"id": review_id, "booking_id": booking_id, "freelancer_id": row["provider_id"],
                "rating": rating, "comment": comment, "created_at": now}, None

    def queue_category_alert(self, client_id, category):
        """Queue one e-mail to each freelancer in the category. Returns (outbox ids, recent_flag).
        A client gets at most one alert per category in 24 hours."""
        since = iso(utc_now() - timedelta(hours=24))
        label = CATEGORY_NAMES[category]
        with self._lock:
            if self._conn.execute(
                    "SELECT 1 FROM category_alerts WHERE client_id = ? AND category = ? AND created_at > ? LIMIT 1",
                    (client_id, category, since)).fetchone():
                return [], True
            freelancers = self._conn.execute(
                "SELECT email FROM users WHERE role = 'freelancer' AND specialty = ?", (category,)).fetchall()
            subject, body = category_alert_message(label)
            ids = []
            try:
                for f in freelancers:
                    cur = self._conn.execute(
                        "INSERT INTO email_outbox (to_address, subject, body) VALUES (?, ?, ?)",
                        (f["email"], subject, body))
                    ids.append(cur.lastrowid)
                self._conn.execute(
                    "INSERT INTO category_alerts (client_id, category, recipients) VALUES (?, ?, ?)",
                    (client_id, category, len(ids)))
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
        return ids, False

    def outbox_rows(self, ids):
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            rows = self._conn.execute(
                f"SELECT id, to_address, subject, body FROM email_outbox WHERE status = 'queued' AND id IN ({placeholders})",
                ids).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]

    def mark_email(self, outbox_id, status):
        with self._lock:
            self._conn.execute("UPDATE email_outbox SET status = ?, sent_at = ? WHERE id = ?",
                               (status, iso(utc_now()), outbox_id))
            self._conn.commit()

    def wishlist_of(self, client_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT u.id, u.full_name, u.specialty, u.avatar_url, u.headline, "
                "(SELECT COUNT(*) FROM services s WHERE s.provider_id = u.id AND s.active = 1) AS service_count, "
                "(SELECT MIN(s.price_sar) FROM services s WHERE s.provider_id = u.id AND s.active = 1) AS from_price, "
                "(SELECT ROUND(AVG(r.rating), 1) FROM reviews r WHERE r.freelancer_id = u.id) AS rating_avg, "
                "(SELECT COUNT(*) FROM reviews r WHERE r.freelancer_id = u.id) AS rating_count "
                "FROM wishlist w JOIN users u ON u.id = w.freelancer_id AND u.role = 'freelancer' "
                "WHERE w.client_id = ? ORDER BY w.created_at DESC, u.id DESC", (client_id,)).fetchall()
        return [{k: r[k] for k in r.keys()} for r in rows]

    def save_freelancer(self, client_id, freelancer_id):
        """True when the freelancer exists and is now saved; False for anyone who is not a freelancer."""
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM users WHERE id = ? AND role = 'freelancer'", (freelancer_id,)).fetchone()
            if row is None:
                return False
            self._conn.execute(
                "INSERT OR IGNORE INTO wishlist (client_id, freelancer_id) VALUES (?, ?)", (client_id, freelancer_id))
            self._conn.commit()
        return True

    def unsave_freelancer(self, client_id, freelancer_id):
        with self._lock:
            self._conn.execute(
                "DELETE FROM wishlist WHERE client_id = ? AND freelancer_id = ?", (client_id, freelancer_id))
            self._conn.commit()

    def update_profile(self, user_id, clean):
        with self._lock:
            self._conn.execute("UPDATE users SET full_name = ?, headline = ? WHERE id = ?",
                               (clean["full_name"], clean["headline"], user_id))
            self._conn.commit()

    def portfolio_of(self, provider_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, title, description, image_url, image_file, project_url, category FROM portfolio_items "
                "WHERE provider_id = ? AND active = 1 ORDER BY id DESC", (provider_id,)).fetchall()
        return [_portfolio_json(r) for r in rows]

    def search_portfolio(self, category=None, text=None, sort="newest"):
        clauses, params = ["p.active = 1"], []
        if category:
            clauses.append("p.category = ?")
            params.append(category)
        if text:
            escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            clauses.append("(p.title LIKE ? ESCAPE '\\' OR p.description LIKE ? ESCAPE '\\' OR u.full_name LIKE ? ESCAPE '\\')")
            pattern = f"%{escaped}%"
            params += [pattern, pattern, pattern]
        order = "p.title COLLATE NOCASE ASC, p.id DESC" if sort == "name" else "p.id DESC"
        with self._lock:
            rows = self._conn.execute(
                "SELECT p.id, p.title, p.description, p.image_url, p.image_file, p.project_url, p.category, "
                "u.full_name AS provider_name FROM portfolio_items p JOIN users u ON u.id = p.provider_id "
                f"WHERE {' AND '.join(clauses)} ORDER BY {order} LIMIT 100", params).fetchall()
        return [_portfolio_json(r) for r in rows]

    def availability_of(self, provider_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT weekday, start_minute AS start, end_minute AS end FROM availability "
                "WHERE provider_id = ? ORDER BY weekday, start_minute", (provider_id,)).fetchall()
        return [dict(r) for r in rows]

    def replace_availability(self, provider_id, windows):
        with self._lock:
            try:
                self._conn.execute("DELETE FROM availability WHERE provider_id = ?", (provider_id,))
                for w in windows:
                    self._conn.execute(
                        "INSERT INTO availability (provider_id, weekday, start_minute, end_minute) VALUES (?, ?, ?, ?)",
                        (provider_id, w["weekday"], w["start"], w["end"]))
                self._conn.commit()
            except sqlite3.IntegrityError:
                self._conn.rollback()
                raise

    def busy_intervals(self, provider_id, day_start, day_end):
        """Pending and accepted bookings that touch a UTC day, as aware datetimes."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT starts_at, ends_at FROM bookings WHERE provider_id = ? AND status IN ('pending', 'accepted') "
                "AND starts_at < ? AND ends_at > ?",
                (provider_id, iso(day_end), iso(day_start))).fetchall()
        return [(rules.parse_utc(r["starts_at"]), rules.parse_utc(r["ends_at"])) for r in rows]

    # --- bookings ---
    def create_booking(self, client_id, service, starts_at, ends_at, note):
        """Insert a booking. The database triggers refuse past times, overlaps and wrong lengths."""
        with self._lock:
            try:
                cur = self._conn.execute(
                    "INSERT INTO bookings (client_id, provider_id, service_id, starts_at, ends_at, status, note, "
                    "agreed_price_sar, created_at, updated_at) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)",
                    (client_id, service["provider_id"], service["id"], iso(starts_at), iso(ends_at), note,
                     service["price_sar"], iso(utc_now()), iso(utc_now())))
                self._conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError as err:
                self._conn.rollback()
                raise BookingRefused(str(err)) from err

    def bookings_for(self, user):
        if user["role"] == "client":
            where, params = "b.client_id = ?", (user["id"],)
        else:
            where, params = "b.provider_id = ?", (user["id"],)
        with self._lock:
            rows = self._conn.execute(
                "SELECT b.id, b.status, b.starts_at, b.ends_at, b.note, b.client_id, b.provider_id, "
                "s.id AS service_id, s.title AS service_title, s.price_sar, s.duration_minutes, "
                "b.agreed_price_sar, b.payment_method, b.payment_method_note, b.payment_currency, "
                "b.client_paid_at, b.provider_received_at, b.delivery_confirmed_at, "
                "pu.full_name AS provider_name, pu.email AS provider_email, "
                "cu.full_name AS client_name, cu.email AS client_email "
                "FROM bookings b JOIN services s ON s.id = b.service_id "
                "JOIN users pu ON pu.id = b.provider_id JOIN users cu ON cu.id = b.client_id "
                f"WHERE {where} ORDER BY b.starts_at DESC, b.id DESC LIMIT 200", params).fetchall()
        out = []
        for r in rows:
            row = dict(r)
            start = rules.parse_utc(row["starts_at"])
            row["local_date"] = (start + rules.TZ_OFFSET).strftime("%Y-%m-%d")
            row["local_time"] = rules.utc_to_local_text(start)
            # Contact details are shared only once the freelancer has accepted. Both emails are always
            # removed from the row; only the other party's email can ever become the 'contact' field.
            shared = row["status"] in ("accepted", "completed")
            provider_email = row.pop("provider_email")
            client_email = row.pop("client_email")
            if user["role"] == "client":
                row.pop("client_name")
                row["contact"] = provider_email if shared else None
            else:
                row.pop("provider_name")
                row["contact"] = client_email if shared else None
            out.append(row)
        return out

    PAYMENT_METHODS = ("bank_transfer", "cash", "other")
    REPORT_REASONS = ("no_show", "no_payment", "poor_quality", "abuse", "other")

    def _log_event(self, booking_id, actor_id, action):
        """Append to the order's activity history. Callers hold the lock and commit."""
        self._conn.execute(
            "INSERT INTO booking_events (booking_id, actor_id, action, created_at) VALUES (?, ?, ?, ?)",
            (booking_id, actor_id, action, iso(utc_now())))

    def _order_for_party(self, booking_id, user):
        """The order row when the user is its customer or its freelancer; otherwise None."""
        row = self._conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        if row is None or user["id"] not in (row["client_id"], row["provider_id"]):
            return None
        return row

    def set_payment_method(self, user, booking_id, method, note, currency="SAR"):
        """Customer picks how the agreed amount will be paid and in which currency (SAR or USD)."""
        if method not in self.PAYMENT_METHODS:
            return "invalid_method"
        if currency not in ("SAR", "USD"):
            return "invalid_currency"
        note = (note or "").strip()
        if method == "other" and not note:
            return "note_required"
        if len(note) > 200:
            return "note_too_long"
        with self._lock:
            row = self._order_for_party(booking_id, user)
            if row is None:
                return "not_found"
            if row["client_id"] != user["id"]:
                return "not_allowed"
            if row["status"] not in ("pending", "accepted"):
                return "not_allowed"
            self._conn.execute(
                "UPDATE bookings SET payment_method = ?, payment_method_note = ?, payment_currency = ?, updated_at = ? "
                "WHERE id = ?",
                (method, note if method == "other" else "", currency, iso(utc_now()), booking_id))
            self._log_event(booking_id, user["id"], "payment_method_" + method)
            self._conn.commit()
        return "ok"

    def confirm_payment(self, user, booking_id):
        """Each side confirms separately: the customer 'I paid', the freelancer 'I received'.
        Nothing is marked paid automatically. Returns a result string."""
        with self._lock:
            row = self._order_for_party(booking_id, user)
            if row is None:
                return "not_found"
            if row["status"] not in ("accepted", "completed"):
                return "not_allowed"
            if row["payment_method"] is None:
                return "no_payment_method"
            now = iso(utc_now())
            if row["client_id"] == user["id"]:
                if row["client_paid_at"] is None:
                    self._conn.execute("UPDATE bookings SET client_paid_at = ? WHERE id = ?", (now, booking_id))
                    self._log_event(booking_id, user["id"], "customer_confirmed_payment")
            else:
                if row["provider_received_at"] is None:
                    self._conn.execute("UPDATE bookings SET provider_received_at = ? WHERE id = ?", (now, booking_id))
                    self._log_event(booking_id, user["id"], "freelancer_confirmed_payment")
            self._conn.commit()
        return "ok"

    def confirm_delivery(self, user, booking_id):
        """Only the customer confirms that the delivered work was received. Returns a result string."""
        with self._lock:
            row = self._order_for_party(booking_id, user)
            if row is None:
                return "not_found"
            if row["client_id"] != user["id"]:
                return "not_allowed"
            if row["status"] != "completed":
                return "not_completed"
            if row["delivery_confirmed_at"] is None:
                self._conn.execute("UPDATE bookings SET delivery_confirmed_at = ? WHERE id = ?",
                                   (iso(utc_now()), booking_id))
                self._log_event(booking_id, user["id"], "customer_confirmed_delivery")
            self._conn.commit()
        return "ok"

    def report_order(self, user, booking_id, reason, details):
        """Either party can report the order. One open report per person per order."""
        if reason not in self.REPORT_REASONS:
            return "invalid_reason"
        details = (details or "").strip()
        if len(details) > 1000:
            return "details_too_long"
        with self._lock:
            row = self._order_for_party(booking_id, user)
            if row is None:
                return "not_found"
            try:
                self._conn.execute(
                    "INSERT INTO order_reports (booking_id, reporter_id, reason, details, created_at) VALUES (?, ?, ?, ?, ?)",
                    (booking_id, user["id"], reason, details, iso(utc_now())))
            except sqlite3.IntegrityError:
                self._conn.rollback()
                return "already_reported"
            self._log_event(booking_id, user["id"], "reported_" + reason)
            self._conn.commit()
        return "ok"

    def order_activity(self, user, booking_id):
        """Activity history, visible only to the two parties. None when the user is not a party."""
        with self._lock:
            row = self._order_for_party(booking_id, user)
            if row is None:
                return None
            rows = self._conn.execute(
                "SELECT e.action, e.created_at, e.actor_id FROM booking_events e WHERE e.booking_id = ? ORDER BY e.id",
                (booking_id,)).fetchall()
        return [{"action": r["action"], "created_at": r["created_at"], "by_you": r["actor_id"] == user["id"]}
                for r in rows]

    def transition_booking(self, booking_id, user, action):
        """accept / reject / complete (freelancer) and cancel (client). Returns the new status or None if not found."""
        now = utc_now()
        rules_by_action = {
            "accept": ("pending", "pending", False),     # from, role, must start after now
            "reject": ("pending", "pending", None),
            "complete": ("accepted", "accepted", True),  # must have ended
            "cancel": ("pending", "accepted", False),
        }
        if action not in rules_by_action:
            return "invalid"
        with self._lock:
            row = self._conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
            if row is None:
                return None
            is_owner = row["client_id"] == user["id"] if action == "cancel" else row["provider_id"] == user["id"]
            if not is_owner:
                return None
            allowed_from = ("pending", "accepted") if action == "cancel" else (rules_by_action[action][0],)
            if row["status"] not in allowed_from:
                return "not_allowed"
            starts, ends = rules.parse_utc(row["starts_at"]), rules.parse_utc(row["ends_at"])
            if action in ("accept", "cancel") and starts <= now:
                return "not_allowed"
            if action == "complete" and ends > now:
                return "not_allowed"
            new_status = {"accept": "accepted", "reject": "rejected", "complete": "completed", "cancel": "cancelled"}[action]
            cur = self._conn.execute(
                "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ? AND status IN (" +
                ",".join("?" * len(allowed_from)) + ")",
                (new_status, iso(now), booking_id, *allowed_from))
            try:
                if cur.rowcount == 1:
                    self._log_event(booking_id, user["id"], "status_" + new_status)
                    self._booking_status_changed(booking_id, new_status, user["id"])
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise
            return new_status if cur.rowcount == 1 else "not_allowed"

    def count_contacts(self):
        with self._lock:
            return self._conn.execute("SELECT COUNT(*) FROM contact_messages").fetchone()[0]

    def close(self):
        with self._lock:
            self._conn.close()


def validate_review(data):
    """Return (clean, errors). A review needs a booking id, a rating from 1 to 5 and an optional comment."""
    if not isinstance(data, dict):
        return None, {"form": "invalid"}
    errors, clean = {}, {}
    booking_id = data.get("booking_id")
    if not isinstance(booking_id, int) or isinstance(booking_id, bool) or booking_id <= 0:
        errors["booking_id"] = "invalid"
    else:
        clean["booking_id"] = booking_id
    rating = data.get("rating")
    if not isinstance(rating, int) or isinstance(rating, bool) or not 1 <= rating <= 5:
        errors["rating"] = "invalid"
    else:
        clean["rating"] = rating
    comment = data.get("comment", "")
    if comment is None:
        comment = ""
    if not isinstance(comment, str) or len(comment) > 600 or CONTROL_RE.search(comment):
        errors["comment"] = "invalid"
    else:
        clean["comment"] = comment.strip()
    return clean, errors


CATEGORY_NAMES = {
    "photography": "Photography", "home-maintenance": "Home Maintenance",
    "education-training": "Education and Training", "graphic-design": "Graphic Design",
    "web-development": "Web Development", "video-editing": "Video Editing",
    "digital-marketing": "Digital Marketing", "translation-services": "Translation Services",
    "social-media-management": "Social Media Management",
}


def category_alert_message(label):
    subject = f"New customer looking for {label} - XLANORA"
    site = os.environ.get("XLANORA_PUBLIC_URL", "").rstrip("/")
    link = f"\nOpen XLANORA: {site}/en/services.html\n" if site else "\n"
    body = (f"Hello,\n\nA customer is looking for {label} services on XLANORA right now.\n"
            "Make sure your profile and services are up to date so the customer can find you."
            f"{link}\n--\nXLANORA - contactxlanora@gmail.com\n")
    return subject, body


def deliver_emails(store, ids):
    """Send queued e-mails over SMTP when it is configured. Rows stay queued when it is not."""
    host = os.environ.get("SMTP_HOST")
    if not host or not ids:
        return

    def send():
        try:
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as smtp:
                smtp.starttls()
                user = os.environ.get("SMTP_USER")
                if user:
                    smtp.login(user, os.environ.get("SMTP_PASSWORD", ""))
                for row in store.outbox_rows(ids):
                    try:
                        msg = EmailMessage()
                        msg["Subject"] = row["subject"]
                        msg["From"] = os.environ.get("SMTP_FROM", "contactxlanora@gmail.com")
                        msg["To"] = row["to_address"]
                        msg.set_content(row["body"])
                        smtp.send_message(msg)
                        store.mark_email(row["id"], "sent")
                    except Exception:  # noqa: BLE001 - one bad address must not stop the rest
                        log.exception("alert e-mail failed")
                        store.mark_email(row["id"], "failed")
        except Exception:  # noqa: BLE001 - delivery problems never reach the request
            log.exception("alert e-mail batch failed")

    threading.Thread(target=send, daemon=True).start()


def notify_by_email(values):
    """Send a copy to the team if SMTP is configured. Never raises into the request."""
    host = os.environ.get("SMTP_HOST")
    to_addr = os.environ.get("CONTACT_TO") or "contactxlanora@gmail.com"  # the official contact address
    if not host or not to_addr:
        return

    def send():
        try:
            msg = EmailMessage()
            msg["Subject"] = f"XLANORA contact: {values['name']}"
            msg["From"] = os.environ.get("SMTP_FROM", to_addr)
            msg["To"] = to_addr
            msg["Reply-To"] = values["email"]
            msg.set_content(
                f"Name: {values['name']}\nEmail: {values['email']}\nPhone: {values.get('phone') or '-'}\n"
                f"Service: {values['service'] or '-'}\n\n{values['message']}\n"
            )
            with smtplib.SMTP(host, int(os.environ.get("SMTP_PORT", "587")), timeout=10) as smtp:
                smtp.starttls()
                user = os.environ.get("SMTP_USER")
                if user:
                    smtp.login(user, os.environ.get("SMTP_PASSWORD", ""))
                smtp.send_message(msg)
        except Exception:  # noqa: BLE001 - email failure must not lose the stored message
            log.exception("contact email failed")

    threading.Thread(target=send, daemon=True).start()


def make_handler(store, limiter, auth_limiter, salt, webhook_secret=""):
    ID_PATH = re.compile(r"^/api/(?:my/services|bookings)/(\d+)(?:/(accept|reject|complete|cancel|pay|payment-method|confirm-payment|confirm-delivery|report))?$")
    ACTIVITY_PATH = re.compile(r"^/api/bookings/(\d+)/activity$")
    PORTFOLIO_PATH = re.compile(r"^/api/my/portfolio/(\d+)$")
    WISHLIST_PATH = re.compile(r"^/api/wishlist/(\d+)$")
    PORTFOLIO_IMAGE_PATH = re.compile(r"^/api/my/portfolio/(\d+)/image$")
    FREELANCER_PATH = re.compile(r"^/api/freelancers/(\d+)$")
    SLOTS_PATH = re.compile(r"^/api/services/(\d+)/slots$")
    PAYMENT_PATH = re.compile(r"^/api/payments/(\d+)$")
    PLAN_PATH = re.compile(r"^/api/admin/plans/(\d+)$")
    ADMIN_ITEM = re.compile(r"^/api/admin/(refunds|payouts|subscriptions)/(\d+)/(approve|reject|paid|cancel)$")

    class Handler(BaseHTTPRequestHandler):
        def version_string(self):
            return "XLANORA"

        def log_message(self, fmt, *args):  # quiet by default, no client IPs in logs
            log.debug("%s", fmt % args)

        def end_headers(self):
            for name, value in SECURITY_HEADERS.items():
                self.send_header(name, value)
            super().end_headers()

        def _client_ip(self):
            """The address used for rate limits and the stored IP hash. X-Forwarded-For is used only when
            XLANORA_TRUST_PROXY=1, and then only the last entry (the one the proxy added)."""
            if TRUST_PROXY:
                forwarded = self.headers.get("X-Forwarded-For", "")
                last = forwarded.split(",")[-1].strip() if forwarded else ""
                if last:
                    return last
            return self.client_address[0]

        def _send(self, status, body, content_type, cache="no-store", cookies=()):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            for cookie in cookies:
                self.send_header("Set-Cookie", cookie)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status, payload, cookies=()):
            self._send(status, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", cookies=cookies)

        def _cookie_flags(self):
            return "; Secure" if SECURE_COOKIES else ""

        def _current_user(self):
            try:
                jar = SimpleCookie(self.headers.get("Cookie", ""))
            except Exception:  # noqa: BLE001 - malformed cookie header means "not signed in"
                return None
            morsel = jar.get(SESSION_COOKIE)
            return store.user_for_token(morsel.value) if morsel else None

        def _require_user(self, role=None):
            user = self._current_user()
            if not user:
                raise ApiError(401, {"form": "not_signed_in"})
            if role and user["role"] != role:
                raise ApiError(403, {"form": "forbidden"})
            return user

        def _session_token(self):
            try:
                jar = SimpleCookie(self.headers.get("Cookie", ""))
            except Exception:  # noqa: BLE001
                return None
            morsel = jar.get(SESSION_COOKIE)
            return morsel.value if morsel else None

        def _read_json(self, allow_empty=False):
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type != "application/json":
                raise ApiError(415, {"form": "unsupported_type"})
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                raise ApiError(400, {"form": "bad_length"})
            if length <= 0:
                if allow_empty:
                    return {}
                raise ApiError(400, {"form": "empty_body"})
            if length > MAX_BODY_BYTES:
                raise ApiError(413, {"form": "too_large"})
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise ApiError(400, {"form": "bad_json"})

        def _query(self):
            return {k: v[-1] for k, v in parse_qs(urlsplit(self.path).query, keep_blank_values=True).items()}

        def do_GET(self):
            if is_retired_payment_path(urlsplit(self.path).path):
                return self._json(410, {"payments": "disabled_direct_payment"})
            path = urlsplit(self.path).path
            try:
                return self._route_get(path)
            except ApiError as err:
                return self._json(err.status, err.payload)
            except FinanceError as err:
                return self._json(err.status, {"errors": {"finance": err.code}})
            except Exception:  # noqa: BLE001 - never drop the connection silently; log and answer
                import traceback
                traceback.print_exc()
                return self._json(500, {"errors": {"server": "internal_error"}})

        def _route_get(self, path):
            if path.startswith("/uploads/"):
                name = path[len("/uploads/"):]
                if not UPLOAD_NAME_RE.fullmatch(name) or not (store.upload_dir / name).is_file():
                    raise ApiError(404, {"error": "not_found"})
                data = (store.upload_dir / name).read_bytes()
                return self._send(200, data, UPLOAD_MIME[name.rsplit(".", 1)[1]])
            if path == "/api/health":
                return self._json(200, {"status": "ok"})
            if path == "/api/me":
                user = self._current_user()
                if not user:
                    return self._json(401, {"errors": {"form": "not_signed_in"}})
                return self._json(200, {"user": public_user(user)})
            if path == "/api/freelancers":
                query = self._query()
                text = (query.get("q") or "").strip()
                category = (query.get("category") or "").strip()
                if len(text) > 80 or (category and category not in SPECIALTIES):
                    raise ApiError(400, {"query": "invalid"})
                found = store.list_freelancers(text=text or None, category=category or None)
                return self._json(200, {"freelancers": found})
            match = FREELANCER_PATH.match(path)
            if match:
                detail = store.freelancer_detail(int(match.group(1)), viewer=self._current_user())
                if detail is None:
                    raise ApiError(404, {"error": "not_found"})
                return self._json(200, detail)
            if path == "/api/requests":
                user = self._require_user()
                query = self._query()
                try:
                    before = int(query["before"]) if query.get("before") else None
                    limit = min(max(int(query.get("limit", REQUESTS_PAGE)), 1), 100)
                except ValueError:
                    raise ApiError(400, {"form": "invalid_paging"})
                rows, next_before = store.requests_for(user, before, limit)
                return self._json(200, {"requests": rows, "next_before": next_before})
            if path == "/api/services":
                return self._services_search()
            match = SLOTS_PATH.match(path)
            if match:
                return self._slots(int(match.group(1)))
            if path == "/api/portfolio":
                return self._portfolio_search()
            if path == "/api/my/portfolio":
                user = self._require_user("freelancer")
                return self._json(200, {"items": store.portfolio_of(user["id"])})
            if path == "/api/wishlist":
                user = self._require_user("client")
                return self._json(200, {"items": store.wishlist_of(user["id"])})
            if path == "/api/my/services":
                user = self._require_user("freelancer")
                return self._json(200, {"services": store.services_of(user["id"])})
            if path == "/api/my/availability":
                user = self._require_user("freelancer")
                return self._json(200, {"windows": store.availability_of(user["id"])})
            if path == "/api/bookings":
                user = self._require_user()
                return self._json(200, {"bookings": store.bookings_for(user)})
            if path == "/api/plans":
                return self._json(200, {"plans": [_plan_json(p) for p in store.list_plans()]})
            if path == "/api/my/subscription":
                user = self._require_user()
                return self._json(200, {"subscription": store.subscription_for(user["id"])})
            if path == "/api/my/finance":
                user = self._require_user("freelancer")
                return self._json(200, {"finance": _freelancer_json(store.freelancer_finance(user["id"]))})
            match = ACTIVITY_PATH.match(path)
            if match:
                user = self._require_user()
                events = store.order_activity(user, int(match.group(1)))
                if events is None:
                    raise ApiError(404, {"error": "not_found"})
                return self._json(200, {"activity": events})
            match = PAYMENT_PATH.match(path)
            if match:
                user = self._require_user()
                view = store.payment_for(user, int(match.group(1)))
                if view is None:
                    raise ApiError(404, {"error": "not_found"})
                return self._json(200, {"payment": _payment_json(view, user["is_admin"])})
            if path.startswith("/api/admin/"):
                return self._admin_get(path)
            return self._static(path)

        def _admin_get(self, path):
            user = self._require_admin()
            query = self._query()
            status = query.get("status") or None
            if status is not None and status not in ("pending", "paid", "failed", "refunded", "requested",
                                                      "processed", "rejected"):
                raise ApiError(400, {"status": "invalid_status"})
            if path == "/api/admin/contacts":
                return self._json(200, {"messages": store.list_contacts()})
            if path == "/api/admin/summary":
                return self._json(200, {"summary": store.finance_summary()})
            if path == "/api/admin/transactions":
                rows = store.admin_transactions(status)
                return self._json(200, {"transactions": [_admin_tx_json(r) for r in rows]})
            if path == "/api/admin/refunds":
                return self._json(200, {"refunds": store.list_refunds(status)})
            if path == "/api/admin/payouts":
                return self._json(200, {"payouts": store.list_payouts(status)})
            if path == "/api/admin/plans":
                return self._json(200, {"plans": [_plan_json(p) for p in store.list_plans(include_inactive=True)]})
            if path == "/api/admin/settings/commission":
                return self._json(200, {"commission_percent": store.commission_rate() / 100})
            if path == "/api/admin/audit":
                return self._json(200, {"audit": store.admin_audit()})
            if path == "/api/admin/subscriptions":
                return self._json(200, {"subscriptions": store.list_subscriptions()})
            if path == "/api/admin/report.csv":
                buf = io.StringIO()
                writer = csv.writer(buf)
                writer.writerow(["id", "kind", "status", "amount_sar", "commission_sar", "net_sar",
                                 "rate_percent", "created_at", "provider_reference"])
                for r in store.report_rows():
                    writer.writerow([csv_safe(v) for v in (
                        r["id"], r["kind"], r["status"], halalas_text(r["amount_halalas"]),
                        halalas_text(r["commission_halalas"]) if r["commission_halalas"] is not None else "",
                        halalas_text(r["net_halalas"]) if r["net_halalas"] is not None else "",
                        r["commission_bps"] / 100, r["created_at"], r["provider_ref"])])
                self._send(200, buf.getvalue().encode("utf-8"), "text/csv; charset=utf-8")
                return
            raise ApiError(404, {"error": "not_found"})

        def _require_admin(self):
            user = self._require_user()
            if not user["is_admin"]:
                raise ApiError(403, {"form": "forbidden"})
            return user

        def _read_media_upload(self, allow_video=False):
            """Raw upload bytes. Images are limited to IMAGE_MAX_BYTES; videos (only when allow_video)
            to VIDEO_MAX_BYTES. The Content-Type must name an allowed type, and the first bytes must
            really be that kind of file. Returns (data, extension)."""
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            is_video = allow_video and ctype in VIDEO_TYPES
            if not is_video and ctype not in IMAGE_TYPES:
                raise ApiError(415, {"image": "unsupported_type"})
            limit = VIDEO_MAX_BYTES if is_video else IMAGE_MAX_BYTES
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                raise ApiError(400, {"image": "bad_length"})
            if length <= 0:
                raise ApiError(400, {"image": "empty"})
            if length > limit:
                self.close_connection = True  # the unread body must not be parsed as the next request
                raise ApiError(413, {"image": "too_large", "limit_mb": limit // (1024 * 1024)})
            data = self.rfile.read(length)
            if len(data) != length:
                raise ApiError(400, {"image": "incomplete"})
            kind = sniff_video(data) if is_video else sniff_image(data)
            if kind is None or kind[1] != ctype:
                raise ApiError(400, {"image": "not_a_video" if is_video else "not_an_image"})
            return data, kind[0]

        def _read_raw_body(self):
            """Bytes of a JSON body, for signature checks. Same size and type rules as _read_json."""
            content_type = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if content_type != "application/json":
                raise ApiError(415, {"form": "unsupported_type"})
            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                raise ApiError(400, {"form": "bad_length"})
            if length <= 0:
                raise ApiError(400, {"form": "empty_body"})
            if length > MAX_BODY_BYTES:
                raise ApiError(413, {"form": "too_large"})
            return self.rfile.read(length)

        def do_POST(self):
            if is_retired_payment_path(urlsplit(self.path).path):
                return self._json(410, {"payments": "disabled_direct_payment"})
            path = urlsplit(self.path).path
            try:
                return self._route_post(path)
            except ApiError as err:
                return self._json(err.status, err.payload)
            except FinanceError as err:
                return self._json(err.status, {"errors": {"finance": err.code}})
            except Exception:  # noqa: BLE001 - never drop the connection silently; log and answer
                import traceback
                traceback.print_exc()
                return self._json(500, {"errors": {"server": "internal_error"}})

        def _route_post(self, path):
            if path == "/api/reviews":
                user = self._require_user("client")
                if not user["email_verified_at"]:
                    raise ApiError(403, {"form": "email_not_verified"})
                clean, errors = validate_review(self._read_json())
                if errors:
                    raise ApiError(400, errors)
                review, reason = store.create_review(user["id"], clean["booking_id"], clean["rating"], clean["comment"])
                if reason == "not_found":
                    raise ApiError(404, {"error": "not_found"})
                if reason:
                    raise ApiError(409, {"error": reason})
                return self._json(201, {"review": review})
            if path == "/api/category-alerts":
                user = self._require_user("client")
                body = self._read_json()
                category = body.get("category") if isinstance(body, dict) else None
                if not isinstance(category, str) or category not in CATEGORY_NAMES:
                    raise ApiError(400, {"category": "invalid"})
                ids, recent = store.queue_category_alert(user["id"], category)
                deliver_emails(store, ids)
                return self._json(202, {"queued": len(ids), "recent": recent,
                                        "delivery": "smtp" if os.environ.get("SMTP_HOST") else "queued"})
            if path == "/api/wishlist":
                user = self._require_user("client")
                body = self._read_json()
                freelancer_id = body.get("freelancer_id") if isinstance(body, dict) else None
                if not isinstance(freelancer_id, int) or isinstance(freelancer_id, bool) or freelancer_id <= 0:
                    raise ApiError(400, {"freelancer_id": "invalid"})
                if not store.save_freelancer(user["id"], freelancer_id):
                    raise ApiError(404, {"error": "not_found"})
                return self._json(201, {"saved": True, "freelancer_id": freelancer_id})
            match = PORTFOLIO_IMAGE_PATH.match(path)
            if match:
                user = self._require_user("freelancer")
                data, ext = self._read_media_upload(allow_video=True)
                url = store.set_portfolio_image(user["id"], int(match.group(1)), data, ext)
                if url is None:
                    raise ApiError(404, {"error": "not_found"})
                return self._json(200, {"image_url": url})
            if path == "/api/me/profile":
                return self._update_profile()
            if path == "/api/me/avatar":
                user = self._require_user()
                data, ext = self._read_media_upload()
                return self._json(200, {"avatar_url": store.set_avatar(user["id"], data, ext)})
            if path == "/api/contact":
                return self._contact()
            if path == "/api/auth/register":
                return self._register()
            if path == "/api/auth/login":
                return self._login()
            if path == "/api/auth/verify":
                return self._verify_email()
            if path == "/api/auth/resend-verification":
                return self._resend_verification()
            if path == "/api/auth/logout":
                return self._logout()
            if path == "/api/auth/password":
                return self._change_password()
            if path == "/api/my/services":
                return self._create_service()
            if path == "/api/my/portfolio":
                return self._create_portfolio()
            if path == "/api/bookings":
                return self._create_booking()
            if path == "/api/payments/webhook/sandbox":
                return self._sandbox_webhook()
            if path == "/api/my/payouts":
                user = self._require_user("freelancer")
                self._read_json(allow_empty=True)
                return self._json(201, {"payout": store.request_payout(user["id"])})
            if path == "/api/my/subscriptions":
                user = self._require_user()
                data = self._read_json()
                plan_id = data.get("plan_id") if isinstance(data, dict) else None
                if isinstance(plan_id, bool) or not isinstance(plan_id, int):
                    raise ApiError(400, {"plan_id": "invalid_plan"})
                result = store.start_subscription(user["id"], plan_id)
                return self._json(201, {"subscription_id": result["subscription_id"],
                                        "payment": _payment_json(result["payment"], False)})
            match = ID_PATH.match(path)
            if match and match.group(1) and match.group(2) and path.startswith("/api/bookings/"):
                return self._booking_action(int(match.group(1)), match.group(2))
            if path == "/api/admin/plans":
                admin = self._require_admin()
                clean, errors = fin.validate_plan(self._read_json(), creating=True)
                if errors:
                    raise ApiError(400, errors)
                return self._json(201, {"id": store.create_plan(admin["id"], clean)})
            match = ADMIN_ITEM.match(path)
            if match:
                return self._admin_action(match.group(1), int(match.group(2)), match.group(3))
            return self._json(404, {"error": "not_found"})

        def _admin_action(self, kind, item_id, action):
            admin = self._require_admin()
            self._read_json(allow_empty=True)  # JSON-only rule for every write; body is not used
            if kind == "refunds" and action in ("approve", "reject"):
                result = store.decide_refund(admin["id"], item_id, approve=action == "approve")
            elif kind == "payouts" and action in ("paid", "reject"):
                result = store.decide_payout(admin["id"], item_id, mark_paid=action == "paid")
            elif kind == "subscriptions" and action == "cancel":
                result = store.cancel_subscription(admin["id"], item_id)
            else:
                raise ApiError(404, {"error": "not_found"})
            if result is None:
                raise ApiError(404, {"error": "not_found"})
            return self._json(200, {"result": result, "id": item_id})

        def _sandbox_webhook(self):
            raw = self._read_raw_body()
            event = fin.SandboxProvider(webhook_secret).verify(
                self.headers.get(fin.TIMESTAMP_HEADER), self.headers.get(fin.SIGNATURE_HEADER), raw)
            return self._json(200, {"outcome": store.apply_webhook(event, raw)})

        def do_PUT(self):
            if is_retired_payment_path(urlsplit(self.path).path):
                return self._json(410, {"payments": "disabled_direct_payment"})
            path = urlsplit(self.path).path
            try:
                if path == "/api/my/availability":
                    return self._save_availability()
                if path == "/api/admin/settings/commission":
                    admin = self._require_admin()
                    rate, errors = fin.validate_commission_percent(self._read_json())
                    if errors:
                        raise ApiError(400, errors)
                    store.set_commission_rate(admin["id"], rate)
                    return self._json(200, {"commission_percent": rate / 100})
                match = PLAN_PATH.match(path)
                if match:
                    admin = self._require_admin()
                    clean, errors = fin.validate_plan(self._read_json(), creating=False)
                    if errors:
                        raise ApiError(400, errors)
                    if store.update_plan(admin["id"], int(match.group(1)), clean) is None:
                        raise ApiError(404, {"error": "not_found"})
                    return self._json(200, {"id": int(match.group(1))})
                match = PORTFOLIO_PATH.match(path)
                if match:
                    return self._update_portfolio(int(match.group(1)))
                match = ID_PATH.match(path)
                if match and match.group(1) and not match.group(2) and path.startswith("/api/my/services/"):
                    return self._update_service(int(match.group(1)))
                return self._json(404, {"error": "not_found"})
            except ApiError as err:
                return self._json(err.status, err.payload)
            except FinanceError as err:
                return self._json(err.status, {"errors": {"finance": err.code}})
            except Exception:  # noqa: BLE001 - never drop the connection silently; log and answer
                import traceback
                traceback.print_exc()
                return self._json(500, {"errors": {"server": "internal_error"}})

        def do_DELETE(self):
            if is_retired_payment_path(urlsplit(self.path).path):
                return self._json(410, {"payments": "disabled_direct_payment"})
            path = urlsplit(self.path).path
            try:
                match = PORTFOLIO_PATH.match(path)
                if match:
                    return self._remove_portfolio(int(match.group(1)))
                match = WISHLIST_PATH.match(path)
                if match:
                    user = self._require_user("client")
                    store.unsave_freelancer(user["id"], int(match.group(1)))
                    return self._json(200, {"saved": False, "freelancer_id": int(match.group(1))})
                match = ID_PATH.match(path)
                if match and match.group(1) and not match.group(2) and path.startswith("/api/my/services/"):
                    return self._deactivate_service(int(match.group(1)))
                return self._json(404, {"error": "not_found"})
            except ApiError as err:
                return self._json(err.status, err.payload)
            except FinanceError as err:
                return self._json(err.status, {"errors": {"finance": err.code}})
            except Exception:  # noqa: BLE001 - never drop the connection silently; log and answer
                import traceback
                traceback.print_exc()
                return self._json(500, {"errors": {"server": "internal_error"}})

        def _static(self, path):
            rel = unquote(path)
            if "\x00" in rel or "\\" in rel:
                return self._not_found()
            if rel.endswith("/"):
                rel += "index.html"
            target = (SITE / rel.lstrip("/")).resolve()
            if not target.is_relative_to(SITE):
                return self._not_found()
            if target.is_dir():
                target = target / "index.html"
            if not target.is_file():
                return self._not_found()
            cache = "no-cache" if target.suffix == ".html" else "public, max-age=86400"
            ctype = CONTENT_TYPES.get(target.suffix.lower(), "application/octet-stream")
            return self._send(200, target.read_bytes(), ctype, cache=cache)

        def _not_found(self):
            return self._send(404, b"Not found", "text/plain; charset=utf-8")

        def _contact(self):
            if not limiter.allow(self._client_ip()):
                raise ApiError(429, {"form": "rate_limited"})
            data = self._read_json()
            # Honeypot: real people never fill this hidden field. Pretend success, store nothing.
            if isinstance(data, dict) and data.get("website"):
                return self._json(201, {"status": "received"})
            clean, errors = validate_contact(data)
            if errors:
                raise ApiError(400, errors)
            user = self._current_user()
            ip_hash = hashlib.sha256((salt + self._client_ip()).encode("utf-8")).hexdigest()
            new_id = store.insert_contact(clean, ip_hash, user["id"] if user else None)
            notify_by_email(clean)
            return self._json(201, {"status": "received", "id": new_id})

        def _register(self):
            if not auth_limiter.allow(self._client_ip()):
                raise ApiError(429, {"form": "rate_limited"})
            clean = validate_registration(self._read_json())
            password = clean.pop("password")
            try:
                user_id = store.create_user(clean, hash_password(password))
            except sqlite3.IntegrityError:
                raise ApiError(409, {"email": "email_taken"})
            token = store.create_session(user_id)
            user = store.user_by_id(user_id)
            outbox_id = store.create_verification(user_id, user["email"], user["full_name"])
            if outbox_id:
                deliver_emails(store, [outbox_id])
            return self._json(201, {"user": public_user(user)}, cookies=[self._set_cookie(token)])

        def _login(self):
            if not auth_limiter.allow(self._client_ip()):
                raise ApiError(429, {"form": "rate_limited"})
            data = self._read_json()
            email = _text(data, "email") if isinstance(data, dict) else None
            password = _text(data, "password") if isinstance(data, dict) else None
            if not email or not password:
                raise ApiError(400, {"form": "invalid_credentials"})
            user = store.user_by_email(email.strip().lower())
            stored = user["password_hash"] if user else DUMMY_HASH
            ok = verify_password(password, stored)
            if not user or not ok:
                raise ApiError(401, {"form": "invalid_credentials"})
            token = store.create_session(user["id"])
            return self._json(200, {"user": public_user(user)}, cookies=[self._set_cookie(token)])

        def _verify_email(self):
            if not auth_limiter.allow(self._client_ip()):
                raise ApiError(429, {"form": "rate_limited"})
            data = self._read_json()
            token = data.get("token") if isinstance(data, dict) else None
            if not store.verify_email(token):
                raise ApiError(400, {"token": "invalid_or_expired"})
            return self._json(200, {"verified": True})

        def _resend_verification(self):
            user = self._require_user()
            self._read_json(allow_empty=True)
            if user["email_verified_at"]:
                return self._json(200, {"verified": True, "queued": 0})
            outbox_id = store.create_verification(user["id"], user["email"], user["full_name"])
            if outbox_id:
                deliver_emails(store, [outbox_id])
            return self._json(202, {"verified": False, "queued": 1 if outbox_id else 0})

        def _logout(self):
            self._read_json(allow_empty=True)  # JSON-only: a cross-site form cannot sign the user out
            store.delete_session(self._session_token())
            clear = f"{SESSION_COOKIE}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{self._cookie_flags()}"
            return self._json(200, {"status": "signed_out"}, cookies=[clear])

        def _change_password(self):
            user = self._require_user()
            if not auth_limiter.allow(self._client_ip()):
                raise ApiError(429, {"form": "rate_limited"})
            data = self._read_json()
            current = _text(data, "current_password") if isinstance(data, dict) else None
            new = _text(data, "new_password") if isinstance(data, dict) else None
            if not current or not verify_password(current, user["password_hash"]):
                raise ApiError(400, {"current_password": "wrong_password"})
            if new is None or not (PASSWORD_MIN <= len(new) <= PASSWORD_MAX):
                raise ApiError(400, {"new_password": "invalid_password"})
            store.update_password(user["id"], hash_password(new), hash_token(self._session_token() or ""))
            return self._json(200, {"status": "password_changed"})

        # --- services ---
        def _services_search(self):
            query = self._query()
            category = query.get("category") or None
            if category is not None and category not in SPECIALTIES:
                raise ApiError(400, {"category": "invalid_category"})
            text = (query.get("q") or "").strip()
            if len(text) > 80 or rules.CONTROL_RE.search(text):
                raise ApiError(400, {"q": "invalid_search"})
            max_price = query.get("max_price")
            if max_price not in (None, ""):
                if not max_price.isdigit() or int(max_price) > 100000:
                    raise ApiError(400, {"max_price": "invalid_price"})
                max_price = int(max_price)
            else:
                max_price = None
            sort = query.get("sort", "newest")
            if sort not in ("newest", "price_asc", "price_desc", "name"):
                raise ApiError(400, {"sort": "invalid_sort"})
            rows = store.search_services(category, text or None, max_price, sort)
            return self._json(200, {"services": rows})

        def _slots(self, service_id):
            service = store.service_for_booking(service_id)
            if service is None:
                raise ApiError(404, {"error": "not_found"})
            now = utc_now()
            date = self._query().get("date", "")
            problem = rules.validate_date(date, now)
            if problem:
                raise ApiError(400, {"date": problem})
            day_start, day_end = rules.day_bounds_utc(date)
            windows = [(w["weekday"], w["start"], w["end"]) for w in store.availability_of(service["provider_id"])]
            busy = store.busy_intervals(service["provider_id"], day_start, day_end)
            slots = rules.free_slots(windows, date, service["duration_minutes"], busy, now)
            return self._json(200, {"date": date, "duration_minutes": service["duration_minutes"], "slots": slots})

        def _update_profile(self):
            user = self._require_user()
            clean, errors = rules.validate_profile(self._read_json())
            if errors:
                raise ApiError(400, errors)
            store.update_profile(user["id"], clean)
            payload = public_user(user)
            payload.update(full_name=clean["full_name"], headline=clean["headline"])
            return self._json(200, {"user": payload})

        def _create_service(self):
            user = self._require_user("freelancer")
            clean, errors = rules.validate_service(self._read_json())
            if errors:
                raise ApiError(400, errors)
            new_id = store.create_service(user, clean)
            return self._json(201, {"status": "created", "id": new_id})

        def _update_service(self, service_id):
            user = self._require_user("freelancer")
            clean, errors = rules.validate_service(self._read_json())
            if errors:
                raise ApiError(400, errors)
            if store.update_service(user["id"], service_id, clean) != 1:
                raise ApiError(404, {"error": "not_found"})
            return self._json(200, {"status": "updated"})

        def _deactivate_service(self, service_id):
            user = self._require_user("freelancer")
            if store.deactivate_service(user["id"], service_id) != 1:
                raise ApiError(404, {"error": "not_found"})
            return self._json(200, {"status": "removed"})

        # --- portfolio ---
        def _portfolio_search(self):
            query = self._query()
            category = query.get("category") or None
            if category is not None and category not in SPECIALTIES:
                raise ApiError(400, {"category": "invalid_category"})
            text = (query.get("q") or "").strip()
            if len(text) > 80 or rules.CONTROL_RE.search(text):
                raise ApiError(400, {"q": "invalid_search"})
            sort = query.get("sort", "newest")
            if sort not in ("newest", "name"):
                raise ApiError(400, {"sort": "invalid_sort"})
            return self._json(200, {"items": store.search_portfolio(category, text or None, sort)})

        def _create_portfolio(self):
            user = self._require_user("freelancer")
            clean, errors = rules.validate_portfolio(self._read_json())
            if errors:
                raise ApiError(400, errors)
            new_id = store.create_portfolio_item(user, clean)
            return self._json(201, {"status": "created", "id": new_id})

        def _update_portfolio(self, item_id):
            user = self._require_user("freelancer")
            clean, errors = rules.validate_portfolio(self._read_json())
            if errors:
                raise ApiError(400, errors)
            if store.update_portfolio_item(user["id"], item_id, clean) != 1:
                raise ApiError(404, {"error": "not_found"})
            return self._json(200, {"status": "updated"})

        def _remove_portfolio(self, item_id):
            user = self._require_user("freelancer")
            if store.deactivate_portfolio_item(user["id"], item_id) != 1:
                raise ApiError(404, {"error": "not_found"})
            return self._json(200, {"status": "removed"})

        def _save_availability(self):
            user = self._require_user("freelancer")
            clean, errors = rules.validate_availability(self._read_json())
            if errors:
                raise ApiError(400, errors)
            try:
                store.replace_availability(user["id"], clean)
            except sqlite3.IntegrityError:
                raise ApiError(400, {"windows": "overlap"})
            return self._json(200, {"status": "saved", "windows": store.availability_of(user["id"])})

        # --- bookings ---
        def _create_booking(self):
            user = self._require_user("client")
            if not user["email_verified_at"]:
                raise ApiError(403, {"form": "email_not_verified"})
            data = self._read_json()
            if not isinstance(data, dict):
                raise ApiError(400, {"form": "invalid"})
            errors = {}
            try:
                service_id = int(data.get("service_id"))
            except (TypeError, ValueError):
                service_id = None
                errors["service_id"] = "invalid_service"
            date = data.get("date") if isinstance(data.get("date"), str) else ""
            time_text = data.get("time") if isinstance(data.get("time"), str) else ""
            note = _text(data, "note")
            if note is None or len(note) > 500 or rules.CONTROL_RE.search(note):
                errors["note"] = "invalid_note"
            now = utc_now()
            problem = rules.validate_date(date, now)
            if problem:
                errors["date"] = problem
            if not rules.TIME_RE.match(time_text):
                errors["time"] = "invalid_time"
            if errors:
                raise ApiError(400, errors)
            service = store.service_for_booking(service_id)
            if service is None:
                raise ApiError(404, {"service_id": "not_found"})
            if service["provider_id"] == user["id"]:
                raise ApiError(400, {"service_id": "own_service"})
            # The slot must be one the server would offer right now.
            day_start, day_end = rules.day_bounds_utc(date)
            windows = [(w["weekday"], w["start"], w["end"]) for w in store.availability_of(service["provider_id"])]
            busy = store.busy_intervals(service["provider_id"], day_start, day_end)
            offered = rules.free_slots(windows, date, service["duration_minutes"], busy, now)
            if time_text not in offered:
                raise ApiError(409, {"slot": "unavailable"})
            starts = rules.local_to_utc(date, time_text)
            ends = starts + timedelta(minutes=service["duration_minutes"])
            try:
                new_id = store.create_booking(user["id"], service, starts, ends, note)
            except BookingRefused as err:
                reason = "overlap" if "booking_overlaps" in str(err) else "unavailable"
                raise ApiError(409, {"slot": reason})
            return self._json(201, {"status": "pending", "id": new_id})

        def _booking_action(self, booking_id, action):
            if action == "pay":
                # The site no longer takes payments or a commission: customer and freelancer pay each other directly.
                self._read_json(allow_empty=True)
                return self._json(410, {"payments": "disabled_direct_payment"})
            if action in ("payment-method", "confirm-payment", "confirm-delivery", "report"):
                return self._order_action(booking_id, action)
            user = self._require_user("client" if action == "cancel" else "freelancer")
            self._read_json(allow_empty=True)  # body is ignored; keeps the JSON-only rule for every write
            result = store.transition_booking(booking_id, user, action)
            if result is None:
                raise ApiError(404, {"error": "not_found"})
            if result in ("not_allowed", "invalid"):
                raise ApiError(409, {"booking": "not_allowed"})
            return self._json(200, {"status": result, "id": booking_id})

        def _order_action(self, booking_id, action):
            """Direct payment, separate payment confirmations, delivery confirmation and reports."""
            if action == "payment-method":
                user = self._require_user("client")
                body = self._read_json()
                result = store.set_payment_method(user, booking_id, str(body.get("method", "")), str(body.get("note", "")),
                                                  str(body.get("currency", "SAR")))
            elif action == "confirm-payment":
                user = self._require_user()
                self._read_json(allow_empty=True)
                result = store.confirm_payment(user, booking_id)
            elif action == "confirm-delivery":
                user = self._require_user("client")
                self._read_json(allow_empty=True)
                result = store.confirm_delivery(user, booking_id)
            else:
                user = self._require_user()
                body = self._read_json()
                result = store.report_order(user, booking_id, str(body.get("reason", "")), str(body.get("details", "")))
            if result == "not_found":
                raise ApiError(404, {"error": "not_found"})
            if result in ("invalid_method", "invalid_currency", "note_required", "note_too_long", "invalid_reason", "details_too_long"):
                raise ApiError(400, {"form": result})
            if result in ("not_allowed", "no_payment_method", "not_completed", "already_reported"):
                raise ApiError(409, {"form": result})
            return self._json(200, {"ok": True, "id": booking_id, "action": action})

        def _set_cookie(self, token):
            return (f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; "
                    f"Max-Age={SESSION_DAYS * 86400}{self._cookie_flags()}")

    return Handler


def _plan_json(plan):
    return {"id": plan["id"], "code": plan["code"], "name": plan["name"], "audience": plan["audience"],
            "price_halalas": plan["price_halalas"], "interval_days": plan["interval_days"],
            "active": bool(plan["active"])}


def _payment_json(view, include_reference):
    out = {"id": view["id"], "kind": view["kind"], "booking_id": view.get("booking_id"),
           "subscription_id": view.get("subscription_id"), "status": view["status"],
           "amount_halalas": view["amount_halalas"], "provider": view.get("provider", "sandbox")}
    if include_reference:
        out["provider_reference"] = view.get("provider_ref")
    return out


def _admin_tx_json(row):
    row = dict(row)
    row["commission_percent"] = row.pop("commission_bps") / 100
    return row


def _freelancer_json(data):
    data = dict(data)
    data["history"] = [dict(h, commission_percent=h.pop("commission_bps") / 100) for h in data["history"]]
    return data


def make_server(host="127.0.0.1", port=8000, db_path=DEFAULT_DB, limiter=None, auth_limiter=None,
                webhook_secret=None):
    store = Store(db_path)
    limiter = limiter or RateLimiter(RATE_LIMIT_COUNT, RATE_LIMIT_WINDOW)
    auth_limiter = auth_limiter or RateLimiter(AUTH_RATE_LIMIT_COUNT, RATE_LIMIT_WINDOW)
    salt = os.environ.get("XLANORA_IP_SALT") or secrets.token_hex(16)
    if webhook_secret is None:
        webhook_secret = os.environ.get("XLANORA_SANDBOX_WEBHOOK_SECRET", "")
    server = ThreadingHTTPServer((host, port), make_handler(store, limiter, auth_limiter, salt, webhook_secret))
    server.store = store
    return server


def main():
    parser = argparse.ArgumentParser(description="Run the XLANORA local server.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", default=os.environ.get("XLANORA_DB", str(DEFAULT_DB)))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    server = make_server(args.host, args.port, args.db)
    log.info("XLANORA running on http://%s:%s (db: %s)", args.host, args.port, args.db)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.store.close()
        server.server_close()


if __name__ == "__main__":
    main()

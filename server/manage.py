#!/usr/bin/env python3
"""Owner command-line tools. Run them on the machine that holds the database.

Administrator access is granted here only. The web API cannot create or promote admins.

  python3 server/manage.py create-admin --email you@example.com --name "Your Name" --generate
  python3 server/manage.py create-admin --email you@example.com --name "Your Name"     (asks for a password)
  python3 server/manage.py promote-admin --email you@example.com
  python3 server/manage.py demote-admin --email you@example.com
  python3 server/manage.py commission-show
  python3 server/manage.py make-webhook-secret
  python3 server/manage.py sandbox-pay REF --url http://127.0.0.1:8000
  python3 server/manage.py sandbox-fail REF --url http://127.0.0.1:8000
  python3 server/manage.py sandbox-eligible REF --url http://127.0.0.1:8000

Passwords are never written to a file: --generate prints one password once, and only its
salted hash is stored. The sandbox commands need XLANORA_SANDBOX_WEBHOOK_SECRET in the
environment, the same value the server was started with.
"""

import argparse
import getpass
import json
import os
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import app as xlanora  # noqa: E402
from finance import SandboxProvider, TIMESTAMP_HEADER, SIGNATURE_HEADER, MIN_SECRET_LENGTH, iso_utc, now_utc  # noqa: E402

ADMIN_MIN_PASSWORD = 12


def _db_path(args):
    return args.db or os.environ.get("XLANORA_DB") or str(xlanora.DEFAULT_DB)


def _connect(args):
    store = xlanora.Store(_db_path(args))  # creates or upgrades the schema, as the server does
    return store


def cmd_create_admin(args):
    email = (args.email or "").strip().lower()
    name = (args.name or "").strip()
    if not xlanora.EMAIL_RE.match(email):
        return _fail("invalid_email")
    if not 2 <= len(name) <= 80:
        return _fail("invalid_name")
    if args.generate:
        password = secrets.token_urlsafe(18)
    else:
        password = getpass.getpass("New admin password: ")
        if password != getpass.getpass("Repeat password: "):
            return _fail("passwords_do_not_match")
    if len(password) < ADMIN_MIN_PASSWORD:
        return _fail("password_too_short_min_12")
    store = _connect(args)
    if store.user_by_email(email) is not None:
        return _fail("email_already_registered_use_promote_admin")
    user_id = store.create_user({"email": email, "full_name": name, "role": "client", "specialty": None},
                                xlanora.hash_password(password))
    with store._lock:
        store._conn.execute("UPDATE users SET is_admin = 1 WHERE id = ?", (user_id,))
        store._audit(None, "admin.created", "user", user_id, {})
        store._conn.commit()
    if args.generate:
        print("Admin account created. This password is shown once and is not stored anywhere in plain text:")
        print(password)
    else:
        print("Admin account created.")
    return 0


def _set_admin(args, value):
    email = (args.email or "").strip().lower()
    store = _connect(args)
    with store._lock:
        row = store._conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            return _fail("user_not_found")
        store._conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (value, row["id"]))
        store._audit(None, "admin.granted" if value else "admin.removed", "user", row["id"], {})
        store._conn.commit()
    print("Admin access " + ("granted." if value else "removed."))
    return 0


def cmd_commission_show(args):
    store = _connect(args)
    print(f"Platform commission: {store.commission_rate() / 100}%")
    return 0


def cmd_make_webhook_secret(args):
    print("Set this in the environment of the server AND of this command. It is not stored by the program:")
    print(secrets.token_hex(32))
    return 0


def _sandbox_event(args, event_type):
    secret = os.environ.get("XLANORA_SANDBOX_WEBHOOK_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        return _fail("XLANORA_SANDBOX_WEBHOOK_SECRET is missing or too short")
    store = _connect(args)
    with store._lock:
        row = store._conn.execute(
            "SELECT provider_ref, amount_halalas FROM sandbox_payments WHERE provider_ref = ?", (args.ref,)).fetchone()
    if row is None:
        return _fail("unknown_reference")
    data = {"provider_ref": row["provider_ref"]}
    if event_type != "earning.eligible":
        data["amount_halalas"] = row["amount_halalas"]
    body = json.dumps({"id": "cli-" + uuid.uuid4().hex, "type": event_type, "data": data}).encode("utf-8")
    timestamp = int(time.time())
    request = urllib.request.Request(
        args.url.rstrip("/") + "/api/payments/webhook/sandbox", data=body, method="POST", headers={
            "Content-Type": "application/json",
            TIMESTAMP_HEADER: str(timestamp),
            SIGNATURE_HEADER: SandboxProvider(secret).sign(timestamp, body),
        })
    try:
        with urllib.request.urlopen(request, timeout=10) as res:
            print(res.status, res.read().decode("utf-8"))
        return 0
    except urllib.error.HTTPError as err:
        print(err.code, err.read().decode("utf-8"))
        return 1


def _fail(code):
    print("Error:", code, file=sys.stderr)
    return 1


def build_parser():
    parser = argparse.ArgumentParser(description="XLANORA owner tools.")
    parser.add_argument("--db", help="database file (default: XLANORA_DB or server/data/xlanora.db)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-admin")
    p.add_argument("--email", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--generate", action="store_true", help="generate a password and print it once")
    p.set_defaults(func=cmd_create_admin)

    for name, value in (("promote-admin", 1), ("demote-admin", 0)):
        p = sub.add_parser(name)
        p.add_argument("--email", required=True)
        p.set_defaults(func=lambda a, v=value: _set_admin(a, v))

    p = sub.add_parser("commission-show")
    p.set_defaults(func=cmd_commission_show)

    p = sub.add_parser("make-webhook-secret")
    p.set_defaults(func=cmd_make_webhook_secret)

    for name, event in (("sandbox-pay", "payment.paid"), ("sandbox-fail", "payment.failed"),
                        ("sandbox-eligible", "earning.eligible")):
        p = sub.add_parser(name)
        p.add_argument("ref", help="sandbox payment reference, e.g. sbx_...")
        p.add_argument("--url", default="http://127.0.0.1:8000")
        p.set_defaults(func=lambda a, e=event: _sandbox_event(a, e))
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    sys.exit(parsed.func(parsed))

"""Money rules and the payment-provider boundary.

Nothing in this module moves money and nothing here touches the database.

* Amounts are integer halalas (1 SAR = 100 halalas). Floats are never used for money.
* Commission is a rate in basis points (1000 = 10%), rounded DOWN, so the freelancer's
  net absorbs any halala remainder. net = gross - commission always holds.
* The only provider is the sandbox. It stands in for a provider dashboard: its records
  live in the sandbox_payments table and its webhooks are signed with a secret taken from
  the environment. A real provider would be a second class with the same methods, and
  would be added only after an approved provider, legal arrangements and written
  authorization. Until then no real money can move through this code.
"""

import hashlib
import hmac
import json
import re
import secrets
import time
from datetime import datetime, timezone

COMMISSION_DEFAULT_BPS = 1000  # 10%, the initial example rate
COMMISSION_MAX_BPS = 5000  # the admin may set 0-50%
MAX_AMOUNT_HALALAS = 50_000 * 100  # one payment may not exceed 50,000 SAR
MIN_SECRET_LENGTH = 32
WEBHOOK_TOLERANCE_SECONDS = 300
SIGNATURE_HEADER = "X-XLANORA-Signature"
TIMESTAMP_HEADER = "X-XLANORA-Timestamp"
PAYMENT_EVENTS = frozenset({"payment.paid", "payment.failed", "earning.eligible"})
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{4,80}$")
PLAN_CODE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
AUDIENCES = frozenset({"freelancer", "client"})

# Allowed status moves. Anything not listed is refused, so a late or repeated event can
# never move money twice or move a settled payment backwards.
PAYMENT_TRANSITIONS = frozenset({("pending", "paid"), ("pending", "failed"), ("paid", "refunded")})
REFUND_TRANSITIONS = frozenset({("requested", "processed"), ("requested", "rejected")})
EARNING_TRANSITIONS = frozenset({
    ("pending", "awaiting_confirmation"),
    ("awaiting_confirmation", "available"),
    ("pending", "reversed"),
    ("awaiting_confirmation", "reversed"),
    ("available", "paid_out"),
})
PAYOUT_TRANSITIONS = frozenset({("requested", "paid"), ("requested", "rejected")})
SUBSCRIPTION_TRANSITIONS = frozenset({
    ("pending", "active"), ("pending", "cancelled"), ("active", "cancelled"), ("active", "expired"),
})


class FinanceError(Exception):
    """A refused financial operation. `code` is a stable machine-readable reason."""

    def __init__(self, code, status=409):
        super().__init__(code)
        self.code = code
        self.status = status


class WebhookError(FinanceError):
    pass


def now_utc():
    return datetime.now(timezone.utc)


def iso_utc(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def sar_to_halalas(price_sar):
    return int(price_sar) * 100


def commission_split(amount_halalas, rate_bps):
    """Return (commission, net) in halalas. Commission rounds down; net takes the remainder."""
    if isinstance(amount_halalas, bool) or not isinstance(amount_halalas, int):
        raise FinanceError("invalid_amount", 400)
    if amount_halalas <= 0 or amount_halalas > MAX_AMOUNT_HALALAS:
        raise FinanceError("invalid_amount", 400)
    if isinstance(rate_bps, bool) or not isinstance(rate_bps, int) or not 0 <= rate_bps <= COMMISSION_MAX_BPS:
        raise FinanceError("invalid_rate", 400)
    commission = amount_halalas * rate_bps // 10_000
    return commission, amount_halalas - commission


def check_transition(table, current, target):
    if (current, target) not in table:
        raise FinanceError("invalid_transition", 409)


def new_provider_reference():
    return "sbx_" + secrets.token_hex(12)


def new_refund_reference():
    return "sbr_" + secrets.token_hex(12)


class SandboxProvider:
    """Signs and verifies sandbox webhooks. Holds the secret; never returns it."""

    name = "sandbox"

    def __init__(self, secret):
        self._secret = secret or ""

    @property
    def enabled(self):
        return len(self._secret) >= MIN_SECRET_LENGTH

    def sign(self, timestamp, body):
        message = f"{int(timestamp)}.".encode("ascii") + body
        return "sha256=" + hmac.new(self._secret.encode("utf-8"), message, hashlib.sha256).hexdigest()

    def verify(self, timestamp_header, signature_header, body, now=None):
        """Check signature and freshness, then return the parsed event. Raises WebhookError."""
        if not self.enabled:
            raise FinanceError("webhooks_disabled", 503)
        if not timestamp_header or not signature_header:
            raise WebhookError("missing_signature", 401)
        try:
            timestamp = int(timestamp_header)
        except ValueError:
            raise WebhookError("bad_timestamp", 401)
        now = int(time.time()) if now is None else int(now)
        if abs(now - timestamp) > WEBHOOK_TOLERANCE_SECONDS:
            raise WebhookError("stale_timestamp", 401)
        if not hmac.compare_digest(self.sign(timestamp, body), signature_header.strip()):
            raise WebhookError("bad_signature", 401)
        return parse_event(body)


def parse_event(body):
    try:
        event = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise WebhookError("bad_json", 400)
    if not isinstance(event, dict):
        raise WebhookError("bad_event", 400)
    event_id, event_type, data = event.get("id"), event.get("type"), event.get("data")
    if not isinstance(event_id, str) or not EVENT_ID_RE.match(event_id):
        raise WebhookError("bad_event_id", 400)
    if event_type not in PAYMENT_EVENTS:
        raise WebhookError("unknown_event_type", 400)
    if not isinstance(data, dict) or not isinstance(data.get("provider_ref"), str):
        raise WebhookError("bad_event_data", 400)
    if event_type != "earning.eligible":
        amount = data.get("amount_halalas")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise WebhookError("bad_event_data", 400)
    return event


def validate_plan(data, creating):
    """Clean a subscription plan written by an administrator. Returns (clean, errors)."""
    errors, clean = {}, {}
    if not isinstance(data, dict):
        return clean, {"form": "invalid"}
    if creating:
        code = data.get("code")
        if not isinstance(code, str) or not PLAN_CODE_RE.match(code):
            errors["code"] = "invalid_code"
        else:
            clean["code"] = code
    name = data.get("name")
    if not isinstance(name, str) or not 3 <= len(name.strip()) <= 80 or CONTROL_RE.search(name):
        errors["name"] = "invalid_name"
    else:
        clean["name"] = name.strip()
    if creating:
        if data.get("audience") not in AUDIENCES:
            errors["audience"] = "invalid_audience"
        else:
            clean["audience"] = data["audience"]
    _int_field(data, "price_sar", 1, 100_000, clean, errors)
    _int_field(data, "interval_days", 1, 366, clean, errors)
    if not creating and "active" in data:
        if not isinstance(data["active"], bool):
            errors["active"] = "invalid_active"
        else:
            clean["active"] = 1 if data["active"] else 0
    return clean, errors


def validate_commission_percent(data):
    """Admin commission setting in whole percent, 0-50. Returns (rate_bps, errors)."""
    if not isinstance(data, dict):
        return None, {"form": "invalid"}
    percent = data.get("percent")
    if isinstance(percent, bool) or not isinstance(percent, int) or not 0 <= percent <= COMMISSION_MAX_BPS // 100:
        return None, {"percent": "invalid_percent"}
    return percent * 100, {}


def _int_field(data, key, low, high, clean, errors):
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        errors[key] = f"invalid_{key}"
    else:
        clean[key] = value


def csv_safe(value):
    """Stop spreadsheet formula injection: text starting with = + - @ or a tab/CR is prefixed."""
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text

"""Booking rules shared by the server and the tests: validation, time handling and free slots.

Times are stored in UTC as 'YYYY-MM-DDTHH:MM:SSZ'. Clients and freelancers work in local time
(XLANORA_TZ_OFFSET_MINUTES, default 180 = Asia/Riyadh, which has no daylight saving).
"""
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

TZ_OFFSET = timedelta(minutes=int(os.environ.get("XLANORA_TZ_OFFSET_MINUTES", "180")))
SLOT_STEP_MIN = 30
MIN_DURATION, MAX_DURATION = 30, 480
BOOKING_HORIZON_DAYS = 60
UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def parse_utc(text):
    return datetime.strptime(text, UTC_FORMAT).replace(tzinfo=timezone.utc)


def format_utc(dt):
    return dt.astimezone(timezone.utc).strftime(UTC_FORMAT)


def local_to_utc(date_str, time_str):
    """'2026-11-20' + '09:30' in local time -> aware UTC datetime."""
    local = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
    return (local - TZ_OFFSET).replace(tzinfo=timezone.utc)


def utc_to_local_text(dt):
    local = dt + TZ_OFFSET
    return local.strftime("%H:%M")


def _text(data, field):
    value = data.get(field, "")
    if value is None:
        return ""
    return value if isinstance(value, str) else None


def _int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def validate_service(data):
    """Return (clean, errors). Category is taken from the freelancer's specialty, not from the form."""
    if not isinstance(data, dict):
        return None, {"form": "invalid"}
    errors, clean = {}, {}

    title = _text(data, "title")
    if title is None or CONTROL_RE.search(title) or not (3 <= len(title.strip()) <= 100):
        errors["title"] = "invalid_title"
    else:
        clean["title"] = title.strip()

    description = _text(data, "description")
    if description is None or CONTROL_RE.search(description) or not (10 <= len(description.strip()) <= 1000):
        errors["description"] = "invalid_description"
    else:
        clean["description"] = description.strip()

    price = _int(data.get("price_sar"))
    if price is None or not (0 <= price <= 100000):
        errors["price_sar"] = "invalid_price"
    else:
        clean["price_sar"] = price

    duration = _int(data.get("duration_minutes"))
    if duration is None or not (MIN_DURATION <= duration <= MAX_DURATION) or duration % SLOT_STEP_MIN:
        errors["duration_minutes"] = "invalid_duration"
    else:
        clean["duration_minutes"] = duration

    return (clean, errors) if not errors else (None, errors)


def validate_availability(data):
    """data = {'windows': [{weekday, start, end}]}; start/end are minutes after local midnight."""
    if not isinstance(data, dict) or not isinstance(data.get("windows"), list):
        return None, {"form": "invalid"}
    windows = data["windows"]
    if len(windows) > 28:
        return None, {"windows": "too_many"}
    clean, seen = [], {}
    for item in windows:
        if not isinstance(item, dict):
            return None, {"windows": "invalid"}
        weekday, start, end = _int(item.get("weekday")), _int(item.get("start")), _int(item.get("end"))
        if weekday is None or not (0 <= weekday <= 6):
            return None, {"windows": "invalid_weekday"}
        if start is None or end is None or not (0 <= start < end <= 1440) or start % SLOT_STEP_MIN or end % SLOT_STEP_MIN:
            return None, {"windows": "invalid_time"}
        for other_start, other_end in seen.get(weekday, []):
            if start < other_end and other_start < end:
                return None, {"windows": "overlap"}
        seen.setdefault(weekday, []).append((start, end))
        clean.append({"weekday": weekday, "start": start, "end": end})
    return clean, {}


def free_slots(windows, local_date, duration_min, busy, now):
    """Start times (local 'HH:MM') that fit in a window on that local date and do not overlap busy intervals.

    windows: [(weekday, start_min, end_min)]; busy: [(start_utc, end_utc)] of pending or accepted bookings;
    now: aware UTC datetime. Slots in the past are skipped.
    """
    weekday = datetime.strptime(local_date, "%Y-%m-%d").weekday()  # Monday = 0, same as our windows
    duration = timedelta(minutes=duration_min)
    out = []
    for win_day, start_min, end_min in sorted(windows):
        if win_day != weekday:
            continue
        for minute in range(start_min, end_min - duration_min + 1, SLOT_STEP_MIN):
            local_start = datetime.strptime(local_date, "%Y-%m-%d") + timedelta(minutes=minute)
            start_utc = (local_start - TZ_OFFSET).replace(tzinfo=timezone.utc)
            end_utc = start_utc + duration
            if start_utc <= now:
                continue
            if any(start_utc < b_end and b_start < end_utc for b_start, b_end in busy):
                continue
            out.append(local_start.strftime("%H:%M"))
    return out


def day_bounds_utc(local_date):
    """UTC start and end of a local calendar day, for finding that day's bookings."""
    start = (datetime.strptime(local_date, "%Y-%m-%d") - TZ_OFFSET).replace(tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def validate_date(value, now):
    """A local date string that is today or later, and within the booking horizon."""
    if not isinstance(value, str) or not DATE_RE.match(value):
        return "invalid_date"
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return "invalid_date"
    today = (now + TZ_OFFSET).replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    if day < today:
        return "date_in_past"
    if day > today + timedelta(days=BOOKING_HORIZON_DAYS):
        return "date_too_far"
    return None


URL_MAX = 500


# An image uploaded through this server: a random 32-hex name and a known extension, nothing else.
UPLOAD_PATH_RE = re.compile(r"/uploads/[a-f0-9]{32}\.(?:jpg|png|webp)")


def _optional_https_url(data, field, errors, clean):
    """Empty is allowed (None). Anything else must be a plain https:// address: no spaces, no credentials."""
    value = _text(data, field)
    if value is None:
        errors[field] = "invalid_url"
        return
    value = value.strip()
    if value == "":
        clean[field] = None
        return
    parts = urlsplit(value)
    if (len(value) > URL_MAX or CONTROL_RE.search(value) or any(c.isspace() for c in value)
            or not value.startswith("https://") or not parts.netloc or parts.username or parts.password):
        errors[field] = "invalid_url"
    else:
        clean[field] = value


def validate_profile(data):
    """Return (clean, errors) for the signed-in user's own name and short headline."""
    if not isinstance(data, dict):
        return None, {"form": "invalid"}
    errors, clean = {}, {}
    name = _text(data, "full_name")
    if name is None or CONTROL_RE.search(name) or not (2 <= len(name.strip()) <= 80):
        errors["full_name"] = "invalid_name"
    else:
        clean["full_name"] = name.strip()
    headline = _text(data, "headline")
    if headline is None or CONTROL_RE.search(headline) or len(headline.strip()) > 160:
        errors["headline"] = "invalid_headline"
    else:
        clean["headline"] = headline.strip()
    return (clean, errors) if not errors else (None, errors)


def validate_portfolio(data):
    """Return (clean, errors) for one portfolio item. The category comes from the freelancer's specialty."""
    if not isinstance(data, dict):
        return None, {"form": "invalid"}
    errors, clean = {}, {}
    title = _text(data, "title")
    if title is None or CONTROL_RE.search(title) or not (3 <= len(title.strip()) <= 100):
        errors["title"] = "invalid_title"
    else:
        clean["title"] = title.strip()
    description = _text(data, "description")
    if description is None or CONTROL_RE.search(description) or not (10 <= len(description.strip()) <= 1000):
        errors["description"] = "invalid_description"
    else:
        clean["description"] = description.strip()
    _optional_https_url(data, "image_url", errors, clean)  # photos from the device use their own endpoint
    _optional_https_url(data, "project_url", errors, clean)
    return (clean, errors) if not errors else (None, errors)

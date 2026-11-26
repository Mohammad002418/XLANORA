"""Financial storage operations, mixed into Store (server/app.py).

Locking rule: public methods take self._lock and commit or roll back themselves.
Methods whose names start with an underscore expect the caller to hold the lock and to
commit. Every multi-table money change runs inside one transaction, so a failure midway
leaves nothing half-written.
"""

import hashlib
import json
import sqlite3
from datetime import timedelta

from finance import (
    COMMISSION_DEFAULT_BPS,
    FinanceError,
    check_transition,
    commission_split,
    iso_utc,
    new_provider_reference,
    new_refund_reference,
    now_utc,
    sar_to_halalas,
    MAX_AMOUNT_HALALAS,
    PAYMENT_TRANSITIONS,
    PAYOUT_TRANSITIONS,
    REFUND_TRANSITIONS,
    SUBSCRIPTION_TRANSITIONS,
)

PAYMENT_STATES = ("pending", "paid", "failed", "refunded")
EARNING_STATES = ("pending", "awaiting_confirmation", "available", "paid_out", "reversed")


def halalas_text(value):
    """Exact SAR text for CSV reports, e.g. 1234 -> '12.34'."""
    value = int(value or 0)
    sign = "-" if value < 0 else ""
    value = abs(value)
    return f"{sign}{value // 100}.{value % 100:02d}"


class FinanceStore:
    # ------------------------------------------------------------------ helpers
    def _audit(self, actor_id, action, entity, entity_id, details=None):
        """Append-only audit row. Ids and amounts only; never card data or secrets."""
        text = json.dumps(details or {}, ensure_ascii=False, sort_keys=True)[:2000]
        self._conn.execute(
            "INSERT INTO financial_audit_logs (actor_id, action, entity, entity_id, details, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (actor_id, action, entity, str(entity_id), text, iso_utc(now_utc())))

    def _commission_bps(self):
        row = self._conn.execute("SELECT value FROM platform_settings WHERE key = 'commission_bps'").fetchone()
        return int(row[0]) if row else COMMISSION_DEFAULT_BPS

    def _expire_subscriptions(self, now_text):
        self._conn.execute(
            "UPDATE user_subscriptions SET status = 'expired', updated_at = ? "
            "WHERE status = 'active' AND ends_at <= ?", (now_text, now_text))

    def _set_sandbox_status(self, provider_ref, status):
        self._conn.execute("UPDATE sandbox_payments SET status = ? WHERE provider_ref = ?", (status, provider_ref))

    # ------------------------------------------------------------------ settings
    def commission_rate(self):
        with self._lock:
            return self._commission_bps()

    def set_commission_rate(self, admin_id, rate_bps):
        with self._lock:
            try:
                old = self._commission_bps()
                self._conn.execute(
                    "UPDATE platform_settings SET value = ?, updated_at = ?, updated_by = ? WHERE key = 'commission_bps'",
                    (str(rate_bps), iso_utc(now_utc()), admin_id))
                self._audit(admin_id, "commission.changed", "settings", "commission_bps",
                            {"from_bps": old, "to_bps": rate_bps})
                self._conn.commit()
                return rate_bps
            except Exception:
                self._conn.rollback()
                raise

    # ------------------------------------------------------------------ payments
    def create_booking_payment(self, client_id, booking_id):
        """Start a sandbox payment for an accepted booking. Returns the payment view or None."""
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT b.id, b.client_id, b.provider_id, b.status, s.price_sar "
                    "FROM bookings b JOIN services s ON s.id = b.service_id WHERE b.id = ?",
                    (booking_id,)).fetchone()
                if row is None or row["client_id"] != client_id:
                    return None
                if row["status"] != "accepted":
                    raise FinanceError("booking_not_accepted", 409)
                amount = sar_to_halalas(row["price_sar"])
                if amount <= 0:
                    raise FinanceError("free_service", 400)
                if amount > MAX_AMOUNT_HALALAS:
                    raise FinanceError("amount_too_large", 400)
                rate = self._commission_bps()
                ref = new_provider_reference()
                now = iso_utc(now_utc())
                self._conn.execute(
                    "INSERT INTO sandbox_payments (provider_ref, amount_halalas, status, created_at) "
                    "VALUES (?, ?, 'pending', ?)", (ref, amount, now))
                cur = self._conn.execute(
                    "INSERT INTO payment_transactions (kind, booking_id, payer_id, payee_id, amount_halalas, "
                    "commission_bps, status, provider, provider_ref, created_at, updated_at) "
                    "VALUES ('booking', ?, ?, ?, ?, ?, 'pending', 'sandbox', ?, ?, ?)",
                    (booking_id, client_id, row["provider_id"], amount, rate, ref, now, now))
                tx_id = cur.lastrowid
                self._audit(client_id, "payment.created", "payment", tx_id,
                            {"booking_id": booking_id, "amount_halalas": amount, "commission_bps": rate})
                self._conn.commit()
                return self._payment_view(tx_id)
            except sqlite3.IntegrityError as err:
                self._conn.rollback()
                raise FinanceError("payment_already_open", 409) from err
            except Exception:
                self._conn.rollback()
                raise

    def _payment_view(self, tx_id):
        row = self._conn.execute(
            "SELECT id, kind, booking_id, subscription_id, payer_id, amount_halalas, status, provider, provider_ref "
            "FROM payment_transactions WHERE id = ?", (tx_id,)).fetchone()
        return dict(row) if row else None

    def payment_for(self, user, tx_id):
        """Payer or administrator only. Reconciles a pending payment with the provider's own record."""
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT * FROM payment_transactions WHERE id = ?", (tx_id,)).fetchone()
                if row is None:
                    return None
                if row["payer_id"] != user["id"] and not user["is_admin"]:
                    return None
                if row["status"] == "pending":
                    provider = self._conn.execute(
                        "SELECT status, amount_halalas FROM sandbox_payments WHERE provider_ref = ?",
                        (row["provider_ref"],)).fetchone()
                    if provider is not None and provider["status"] in ("paid", "failed"):
                        event = {"id": f"reconcile-{row['provider_ref']}-{provider['status']}",
                                 "type": "payment." + provider["status"],
                                 "data": {"provider_ref": row["provider_ref"],
                                          "amount_halalas": provider["amount_halalas"]}}
                        self._apply_event_locked(event)
                        self._conn.commit()
                return self._payment_view(tx_id)
            except Exception:
                self._conn.rollback()
                raise

    def apply_webhook(self, event, body):
        """Apply one verified provider event exactly once. Returns 'processed', 'ignored' or 'duplicate'."""
        with self._lock:
            try:
                seen = self._conn.execute(
                    "SELECT 1 FROM payment_webhook_events WHERE provider = 'sandbox' AND event_id = ?",
                    (event["id"],)).fetchone()
                if seen:
                    return "duplicate"
                outcome = self._apply_event_locked(event)
                self._conn.execute(
                    "INSERT INTO payment_webhook_events (provider, event_id, event_type, outcome, payload_sha256, received_at) "
                    "VALUES ('sandbox', ?, ?, ?, ?, ?)",
                    (event["id"], event["type"], outcome, hashlib.sha256(body).hexdigest(), iso_utc(now_utc())))
                self._conn.commit()
                return outcome
            except Exception:
                self._conn.rollback()
                raise

    def _apply_event_locked(self, event):
        data = event["data"]
        kind = event["type"]
        ref = data["provider_ref"]
        tx = self._conn.execute("SELECT * FROM payment_transactions WHERE provider_ref = ?", (ref,)).fetchone()
        if tx is None:
            raise FinanceError("unknown_payment", 404)
        now = iso_utc(now_utc())

        if kind == "earning.eligible":
            # The provider confirms payout eligibility; only then does an earning become 'available'.
            cur = self._conn.execute(
                "UPDATE freelancer_earnings SET status = 'available', provider_eligible_at = ?, updated_at = ? "
                "WHERE transaction_id = ? AND status = 'awaiting_confirmation'", (now, now, tx["id"]))
            if cur.rowcount == 0:
                return "ignored"
            self._audit(None, "earning.eligible", "payment", tx["id"], {})
            return "processed"

        if data["amount_halalas"] != tx["amount_halalas"]:
            raise FinanceError("amount_mismatch", 400)

        if kind == "payment.paid":
            if tx["status"] in ("paid", "refunded"):
                return "ignored"
            check_transition(PAYMENT_TRANSITIONS, tx["status"], "paid")
            self._set_sandbox_status(ref, "paid")
            if tx["kind"] == "subscription":
                self._settle_subscription(tx, now)
            else:
                self._settle_booking(tx, now)
            return "processed"

        # payment.failed
        if tx["status"] == "failed":
            return "ignored"
        check_transition(PAYMENT_TRANSITIONS, tx["status"], "failed")
        self._conn.execute("UPDATE payment_transactions SET status = 'failed', updated_at = ? WHERE id = ?",
                           (now, tx["id"]))
        self._set_sandbox_status(ref, "failed")
        self._audit(None, "payment.failed", "payment", tx["id"], {})
        return "processed"

    def _settle_booking(self, tx, now):
        booking = self._conn.execute("SELECT status FROM bookings WHERE id = ?", (tx["booking_id"],)).fetchone()
        if booking is None or booking["status"] not in ("accepted", "completed"):
            # Paid after the booking was cancelled. Nothing is credited; the row is kept for a manual refund.
            self._conn.execute("UPDATE payment_transactions SET status = 'failed', updated_at = ? WHERE id = ?",
                               (now, tx["id"]))
            self._audit(None, "payment.paid_for_inactive_booking", "payment", tx["id"],
                        {"booking_id": tx["booking_id"], "needs": "manual_refund"})
            return
        commission, net = commission_split(tx["amount_halalas"], tx["commission_bps"])
        self._conn.execute("UPDATE payment_transactions SET status = 'paid', updated_at = ? WHERE id = ?",
                           (now, tx["id"]))
        self._conn.execute(
            "INSERT INTO platform_commissions (transaction_id, rate_bps, amount_halalas, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'accrued', ?, ?)",
            (tx["id"], tx["commission_bps"], commission, now, now))
        # If the freelancer already marked the job complete, the earning waits for provider confirmation.
        earning_status = "awaiting_confirmation" if booking["status"] == "completed" else "pending"
        self._conn.execute(
            "INSERT INTO freelancer_earnings (transaction_id, freelancer_id, gross_halalas, commission_halalas, "
            "net_halalas, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (tx["id"], tx["payee_id"], tx["amount_halalas"], commission, net, earning_status, now, now))
        self._audit(None, "payment.paid", "payment", tx["id"],
                    {"booking_id": tx["booking_id"], "amount_halalas": tx["amount_halalas"],
                     "commission_halalas": commission, "net_halalas": net})

    def _settle_subscription(self, tx, now):
        sub = self._conn.execute(
            "SELECT us.id, us.status, sp.interval_days FROM user_subscriptions us "
            "JOIN subscription_plans sp ON sp.id = us.plan_id WHERE us.id = ?", (tx["subscription_id"],)).fetchone()
        if sub is None or sub["status"] != "pending":
            self._conn.execute("UPDATE payment_transactions SET status = 'failed', updated_at = ? WHERE id = ?",
                               (now, tx["id"]))
            self._audit(None, "subscription.payment_inactive", "payment", tx["id"], {"needs": "manual_refund"})
            return
        starts = now_utc()
        ends = starts + timedelta(days=sub["interval_days"])
        self._conn.execute(
            "UPDATE user_subscriptions SET status = 'active', starts_at = ?, ends_at = ?, updated_at = ? WHERE id = ?",
            (iso_utc(starts), iso_utc(ends), now, sub["id"]))
        self._conn.execute("UPDATE payment_transactions SET status = 'paid', updated_at = ? WHERE id = ?",
                           (now, tx["id"]))
        self._audit(None, "subscription.activated", "subscription", sub["id"],
                    {"amount_halalas": tx["amount_halalas"], "ends_at": iso_utc(ends)})

    # ------------------------------------------------------------------ booking hooks
    def _booking_status_changed(self, booking_id, new_status, actor_id):
        """Called inside transition_booking's transaction. Caller commits."""
        now = iso_utc(now_utc())
        if new_status == "cancelled":
            rows = self._conn.execute(
                "SELECT id, status, amount_halalas, provider_ref FROM payment_transactions "
                "WHERE booking_id = ? AND status IN ('pending', 'paid')", (booking_id,)).fetchall()
            for row in rows:
                if row["status"] == "pending":
                    # The provider never confirmed it, so nothing was taken: close it.
                    self._conn.execute("UPDATE payment_transactions SET status = 'failed', updated_at = ? WHERE id = ?",
                                       (now, row["id"]))
                    self._set_sandbox_status(row["provider_ref"], "failed")
                    self._audit(actor_id, "payment.closed_on_cancel", "payment", row["id"], {})
                else:
                    self._conn.execute(
                        "INSERT INTO refunds (transaction_id, amount_halalas, reason, status, requested_by, created_at) "
                        "VALUES (?, ?, 'booking_cancelled', 'requested', ?, ?)",
                        (row["id"], row["amount_halalas"], actor_id, now))
                    self._audit(actor_id, "refund.requested", "payment", row["id"],
                                {"booking_id": booking_id, "amount_halalas": row["amount_halalas"]})
        elif new_status == "completed":
            self._conn.execute(
                "UPDATE freelancer_earnings SET status = 'awaiting_confirmation', updated_at = ? "
                "WHERE status = 'pending' AND transaction_id IN "
                "(SELECT id FROM payment_transactions WHERE booking_id = ? AND status = 'paid')",
                (now, booking_id))

    # ------------------------------------------------------------------ refunds
    def list_refunds(self, status=None):
        with self._lock:
            rows = self._conn.execute(
                "SELECT rf.id, rf.transaction_id, rf.amount_halalas, rf.reason, rf.status, rf.created_at, "
                "rf.decided_at, tx.status AS payment_status, tx.booking_id, "
                "payer.full_name AS payer_name, payee.full_name AS payee_name "
                "FROM refunds rf JOIN payment_transactions tx ON tx.id = rf.transaction_id "
                "JOIN users payer ON payer.id = tx.payer_id LEFT JOIN users payee ON payee.id = tx.payee_id "
                "WHERE (? IS NULL OR rf.status = ?) ORDER BY rf.id DESC LIMIT 200", (status, status)).fetchall()
            return [dict(r) for r in rows]

    def decide_refund(self, admin_id, refund_id, approve):
        with self._lock:
            try:
                row = self._conn.execute(
                    "SELECT rf.*, tx.status AS tx_status, tx.amount_halalas AS tx_amount FROM refunds rf "
                    "JOIN payment_transactions tx ON tx.id = rf.transaction_id WHERE rf.id = ?",
                    (refund_id,)).fetchone()
                if row is None:
                    return None
                target = "processed" if approve else "rejected"
                check_transition(REFUND_TRANSITIONS, row["status"], target)
                now = iso_utc(now_utc())
                if not approve:
                    self._conn.execute(
                        "UPDATE refunds SET status = 'rejected', decided_by = ?, decided_at = ? WHERE id = ?",
                        (admin_id, now, refund_id))
                    self._audit(admin_id, "refund.rejected", "refund", refund_id, {})
                    self._conn.commit()
                    return "rejected"
                check_transition(PAYMENT_TRANSITIONS, row["tx_status"], "refunded")
                if row["amount_halalas"] != row["tx_amount"]:
                    raise FinanceError("partial_refund_not_supported", 400)
                released = self._conn.execute(
                    "SELECT 1 FROM freelancer_earnings WHERE transaction_id = ? AND status IN ('available', 'paid_out')",
                    (row["transaction_id"],)).fetchone()
                if released:
                    raise FinanceError("earnings_already_released", 409)
                self._conn.execute(
                    "UPDATE refunds SET status = 'processed', provider_ref = ?, decided_by = ?, decided_at = ? WHERE id = ?",
                    (new_refund_reference(), admin_id, now, refund_id))
                self._conn.execute("UPDATE payment_transactions SET status = 'refunded', updated_at = ? WHERE id = ?",
                                   (now, row["transaction_id"]))
                self._conn.execute(
                    "UPDATE platform_commissions SET status = 'reversed', updated_at = ? WHERE transaction_id = ?",
                    (now, row["transaction_id"]))
                self._conn.execute(
                    "UPDATE freelancer_earnings SET status = 'reversed', updated_at = ? "
                    "WHERE transaction_id = ? AND status IN ('pending', 'awaiting_confirmation')",
                    (now, row["transaction_id"]))
                self._audit(admin_id, "refund.processed", "refund", refund_id,
                            {"transaction_id": row["transaction_id"], "amount_halalas": row["amount_halalas"]})
                self._conn.commit()
                return "processed"
            except Exception:
                self._conn.rollback()
                raise

    # ------------------------------------------------------------------ payouts
    def request_payout(self, freelancer_id):
        with self._lock:
            try:
                rows = self._conn.execute(
                    "SELECT id, net_halalas FROM freelancer_earnings "
                    "WHERE freelancer_id = ? AND status = 'available' AND payout_id IS NULL", (freelancer_id,)).fetchall()
                if not rows:
                    raise FinanceError("nothing_available", 409)
                amount = sum(r["net_halalas"] for r in rows)
                now = iso_utc(now_utc())
                cur = self._conn.execute(
                    "INSERT INTO payouts (freelancer_id, amount_halalas, status, created_at) VALUES (?, ?, 'requested', ?)",
                    (freelancer_id, amount, now))
                payout_id = cur.lastrowid
                ids = [r["id"] for r in rows]
                self._conn.execute(
                    "UPDATE freelancer_earnings SET payout_id = ?, updated_at = ? WHERE id IN (" +
                    ",".join("?" * len(ids)) + ")", (payout_id, now, *ids))
                self._audit(freelancer_id, "payout.requested", "payout", payout_id,
                            {"amount_halalas": amount, "earnings": len(ids)})
                self._conn.commit()
                return {"id": payout_id, "amount_halalas": amount}
            except Exception:
                self._conn.rollback()
                raise

    def decide_payout(self, admin_id, payout_id, mark_paid):
        """Record an administrator's decision. No money is moved by this code."""
        with self._lock:
            try:
                row = self._conn.execute("SELECT * FROM payouts WHERE id = ?", (payout_id,)).fetchone()
                if row is None:
                    return None
                target = "paid" if mark_paid else "rejected"
                check_transition(PAYOUT_TRANSITIONS, row["status"], target)
                now = iso_utc(now_utc())
                self._conn.execute(
                    "UPDATE payouts SET status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
                    (target, now, admin_id, payout_id))
                if mark_paid:
                    self._conn.execute(
                        "UPDATE freelancer_earnings SET status = 'paid_out', updated_at = ? "
                        "WHERE payout_id = ? AND status = 'available'", (now, payout_id))
                else:
                    self._conn.execute(
                        "UPDATE freelancer_earnings SET payout_id = NULL, updated_at = ? "
                        "WHERE payout_id = ? AND status = 'available'", (now, payout_id))
                self._audit(admin_id, "payout." + target, "payout", payout_id, {"amount_halalas": row["amount_halalas"]})
                self._conn.commit()
                return target
            except Exception:
                self._conn.rollback()
                raise

    def list_payouts(self, status=None):
        with self._lock:
            rows = self._conn.execute(
                "SELECT p.id, p.freelancer_id, u.full_name AS freelancer_name, p.amount_halalas, p.status, "
                "p.created_at, p.decided_at FROM payouts p JOIN users u ON u.id = p.freelancer_id "
                "WHERE (? IS NULL OR p.status = ?) ORDER BY p.id DESC LIMIT 200", (status, status)).fetchall()
            return [dict(r) for r in rows]

    # ------------------------------------------------------------------ subscriptions
    def list_plans(self, include_inactive=False):
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, code, name, audience, price_halalas, interval_days, active FROM subscription_plans "
                "WHERE (? = 1 OR active = 1) ORDER BY id", (1 if include_inactive else 0,)).fetchall()
            return [dict(r) for r in rows]

    def create_plan(self, admin_id, clean):
        with self._lock:
            try:
                now = iso_utc(now_utc())
                cur = self._conn.execute(
                    "INSERT INTO subscription_plans (code, name, audience, price_halalas, interval_days, active, created_at) "
                    "VALUES (?, ?, ?, ?, ?, 1, ?)",
                    (clean["code"], clean["name"], clean["audience"], sar_to_halalas(clean["price_sar"]),
                     clean["interval_days"], now))
                self._audit(admin_id, "plan.created", "plan", cur.lastrowid,
                            {"code": clean["code"], "price_halalas": sar_to_halalas(clean["price_sar"])})
                self._conn.commit()
                return cur.lastrowid
            except sqlite3.IntegrityError:
                self._conn.rollback()
                raise FinanceError("plan_code_taken", 409)
            except Exception:
                self._conn.rollback()
                raise

    def update_plan(self, admin_id, plan_id, clean):
        """Price changes apply to subscriptions started after the change; existing payments keep their amount."""
        with self._lock:
            try:
                row = self._conn.execute("SELECT * FROM subscription_plans WHERE id = ?", (plan_id,)).fetchone()
                if row is None:
                    return None
                name = clean.get("name", row["name"])
                price = sar_to_halalas(clean["price_sar"]) if "price_sar" in clean else row["price_halalas"]
                interval = clean.get("interval_days", row["interval_days"])
                active = clean.get("active", row["active"])
                self._conn.execute(
                    "UPDATE subscription_plans SET name = ?, price_halalas = ?, interval_days = ?, active = ? WHERE id = ?",
                    (name, price, interval, active, plan_id))
                self._audit(admin_id, "plan.updated", "plan", plan_id,
                            {"price_halalas": price, "active": active})
                self._conn.commit()
                return True
            except Exception:
                self._conn.rollback()
                raise

    def start_subscription(self, user_id, plan_id):
        with self._lock:
            try:
                plan = self._conn.execute(
                    "SELECT * FROM subscription_plans WHERE id = ? AND active = 1", (plan_id,)).fetchone()
                if plan is None:
                    raise FinanceError("plan_not_found", 404)
                user = self._conn.execute("SELECT role FROM users WHERE id = ?", (user_id,)).fetchone()
                if user is None or user["role"] != plan["audience"]:
                    raise FinanceError("plan_audience_mismatch", 403)
                if plan["price_halalas"] <= 0:
                    raise FinanceError("free_plan", 400)
                open_sub = self._conn.execute(
                    "SELECT 1 FROM user_subscriptions WHERE user_id = ? AND status IN ('pending', 'active')",
                    (user_id,)).fetchone()
                if open_sub:
                    raise FinanceError("subscription_exists", 409)
                now = iso_utc(now_utc())
                ref = new_provider_reference()
                self._conn.execute(
                    "INSERT INTO sandbox_payments (provider_ref, amount_halalas, status, created_at) VALUES (?, ?, 'pending', ?)",
                    (ref, plan["price_halalas"], now))
                sub = self._conn.execute(
                    "INSERT INTO user_subscriptions (user_id, plan_id, status, created_at, updated_at) "
                    "VALUES (?, ?, 'pending', ?, ?)", (user_id, plan_id, now, now))
                cur = self._conn.execute(
                    "INSERT INTO payment_transactions (kind, subscription_id, payer_id, payee_id, amount_halalas, "
                    "commission_bps, status, provider, provider_ref, created_at, updated_at) "
                    "VALUES ('subscription', ?, ?, NULL, ?, 0, 'pending', 'sandbox', ?, ?, ?)",
                    (sub.lastrowid, user_id, plan["price_halalas"], ref, now, now))
                self._audit(user_id, "subscription.started", "subscription", sub.lastrowid,
                            {"plan_id": plan_id, "payment_id": cur.lastrowid})
                self._conn.commit()
                return {"subscription_id": sub.lastrowid, "payment": self._payment_view(cur.lastrowid)}
            except sqlite3.IntegrityError as err:
                self._conn.rollback()
                raise FinanceError("subscription_exists", 409) from err
            except Exception:
                self._conn.rollback()
                raise

    def cancel_subscription(self, admin_id, subscription_id):
        with self._lock:
            try:
                row = self._conn.execute("SELECT status FROM user_subscriptions WHERE id = ?",
                                         (subscription_id,)).fetchone()
                if row is None:
                    return None
                check_transition(SUBSCRIPTION_TRANSITIONS, row["status"], "cancelled")
                self._conn.execute("UPDATE user_subscriptions SET status = 'cancelled', updated_at = ? WHERE id = ?",
                                   (iso_utc(now_utc()), subscription_id))
                self._audit(admin_id, "subscription.cancelled", "subscription", subscription_id, {})
                self._conn.commit()
                return True
            except Exception:
                self._conn.rollback()
                raise

    def list_subscriptions(self):
        with self._lock:
            self._expire_subscriptions(iso_utc(now_utc()))
            self._conn.commit()
            return [dict(r) for r in self._conn.execute(
                "SELECT us.id, us.user_id, u.full_name AS user_name, sp.name AS plan_name, us.status, "
                "us.starts_at, us.ends_at FROM user_subscriptions us JOIN users u ON u.id = us.user_id "
                "JOIN subscription_plans sp ON sp.id = us.plan_id ORDER BY us.id DESC LIMIT 200").fetchall()]

    def subscription_for(self, user_id):
        with self._lock:
            try:
                self._expire_subscriptions(iso_utc(now_utc()))
                self._conn.commit()
                return self._subscription_locked(user_id)
            except Exception:
                self._conn.rollback()
                raise

    def _subscription_locked(self, user_id):
        """Caller holds the lock. Never call the public method from inside a locked section."""
        row = self._conn.execute(
            "SELECT us.id, us.status, us.starts_at, us.ends_at, sp.name, sp.price_halalas, sp.interval_days "
            "FROM user_subscriptions us JOIN subscription_plans sp ON sp.id = us.plan_id "
            "WHERE us.user_id = ? ORDER BY us.id DESC LIMIT 1", (user_id,)).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------ reports
    def freelancer_finance(self, user_id):
        """Only this freelancer's own records. 'available' is set only after provider confirmation."""
        with self._lock:
            self._expire_subscriptions(iso_utc(now_utc()))
            self._conn.commit()
            totals = {s: 0 for s in EARNING_STATES}
            counts = {s: 0 for s in EARNING_STATES}
            gross = commission = 0
            for row in self._conn.execute(
                    "SELECT status, COUNT(*) AS n, COALESCE(SUM(net_halalas), 0) AS net, "
                    "COALESCE(SUM(gross_halalas), 0) AS gross, COALESCE(SUM(commission_halalas), 0) AS commission "
                    "FROM freelancer_earnings WHERE freelancer_id = ? GROUP BY status", (user_id,)):
                totals[row["status"]] = row["net"]
                counts[row["status"]] = row["n"]
                if row["status"] != "reversed":
                    gross += row["gross"]
                    commission += row["commission"]
            reserved = self._conn.execute(
                "SELECT COALESCE(SUM(net_halalas), 0) FROM freelancer_earnings "
                "WHERE freelancer_id = ? AND status = 'available' AND payout_id IS NOT NULL", (user_id,)).fetchone()[0]
            history = [dict(r) for r in self._conn.execute(
                "SELECT fe.id, fe.status, fe.gross_halalas, fe.commission_halalas, fe.net_halalas, fe.payout_id, "
                "fe.provider_eligible_at, fe.created_at, tx.commission_bps, s.title AS service_title, b.starts_at "
                "FROM freelancer_earnings fe JOIN payment_transactions tx ON tx.id = fe.transaction_id "
                "JOIN bookings b ON b.id = tx.booking_id JOIN services s ON s.id = b.service_id "
                "WHERE fe.freelancer_id = ? ORDER BY fe.id DESC LIMIT 100", (user_id,)).fetchall()]
            payouts = [dict(r) for r in self._conn.execute(
                "SELECT id, amount_halalas, status, created_at, decided_at FROM payouts "
                "WHERE freelancer_id = ? ORDER BY id DESC LIMIT 20", (user_id,)).fetchall()]
            return {
                "gross_halalas": gross,
                "commission_halalas": commission,
                "total_net_halalas": totals["pending"] + totals["awaiting_confirmation"]
                                     + totals["available"] + totals["paid_out"],
                "pending_halalas": totals["pending"] + totals["awaiting_confirmation"],
                "available_halalas": totals["available"] - reserved,
                "reserved_halalas": reserved,
                "paid_out_halalas": totals["paid_out"],
                "counts": counts,
                "history": history,
                "payouts": payouts,
                "subscription": self._subscription_locked(user_id),
            }

    def finance_summary(self):
        with self._lock:
            self._expire_subscriptions(iso_utc(now_utc()))
            self._conn.commit()
            by_status = {s: {"count": 0, "amount_halalas": 0} for s in PAYMENT_STATES}
            for row in self._conn.execute(
                    "SELECT status, COUNT(*) AS n, COALESCE(SUM(amount_halalas), 0) AS total "
                    "FROM payment_transactions GROUP BY status"):
                by_status[row["status"]] = {"count": row["n"], "amount_halalas": row["total"]}
            commissions = self._conn.execute(
                "SELECT COALESCE(SUM(amount_halalas), 0) FROM platform_commissions WHERE status = 'accrued'").fetchone()[0]
            subscription_revenue = self._conn.execute(
                "SELECT COALESCE(SUM(amount_halalas), 0) FROM payment_transactions "
                "WHERE kind = 'subscription' AND status = 'paid'").fetchone()[0]
            earnings = {s: 0 for s in EARNING_STATES}
            for row in self._conn.execute(
                    "SELECT status, COALESCE(SUM(net_halalas), 0) AS net FROM freelancer_earnings GROUP BY status"):
                earnings[row["status"]] = row["net"]
            reserved = self._conn.execute(
                "SELECT COALESCE(SUM(net_halalas), 0) FROM freelancer_earnings "
                "WHERE status = 'available' AND payout_id IS NOT NULL").fetchone()[0]
            refunds = {r["status"]: r["n"] for r in self._conn.execute(
                "SELECT status, COUNT(*) AS n FROM refunds GROUP BY status")}
            payouts = {r["status"]: {"count": r["n"], "amount_halalas": r["total"]} for r in self._conn.execute(
                "SELECT status, COUNT(*) AS n, COALESCE(SUM(amount_halalas), 0) AS total FROM payouts GROUP BY status")}
            active_subscriptions = self._conn.execute(
                "SELECT COUNT(*) FROM user_subscriptions WHERE status = 'active'").fetchone()[0]
            return {
                "commission_percent": self._commission_bps() / 100,
                # Money processed through the platform: settled payments plus those since refunded.
                "transaction_volume_halalas": by_status["paid"]["amount_halalas"] + by_status["refunded"]["amount_halalas"],
                "transactions": by_status,
                # Platform's own income only: commissions still standing plus subscription payments.
                "platform_revenue_halalas": commissions + subscription_revenue,
                "platform_commissions_halalas": commissions,
                "subscription_revenue_halalas": subscription_revenue,
                # Freelancers' money held by the platform, which is NOT platform revenue.
                "freelancer_funds": {
                    "pending_halalas": earnings["pending"] + earnings["awaiting_confirmation"],
                    "available_halalas": earnings["available"] - reserved,
                    "reserved_for_payout_halalas": reserved,
                    "paid_out_halalas": earnings["paid_out"],
                },
                "refunds": refunds,
                "payouts": payouts,
                "active_subscriptions": active_subscriptions,
            }

    def admin_transactions(self, status=None, limit=200):
        with self._lock:
            rows = self._conn.execute(
                "SELECT tx.id, tx.kind, tx.status, tx.amount_halalas, tx.commission_bps, tx.created_at, "
                "tx.booking_id, tx.subscription_id, pc.amount_halalas AS commission_halalas, "
                "fe.net_halalas AS net_halalas, payer.full_name AS payer_name, payee.full_name AS payee_name "
                "FROM payment_transactions tx "
                "LEFT JOIN platform_commissions pc ON pc.transaction_id = tx.id "
                "LEFT JOIN freelancer_earnings fe ON fe.transaction_id = tx.id "
                "JOIN users payer ON payer.id = tx.payer_id LEFT JOIN users payee ON payee.id = tx.payee_id "
                "WHERE (? IS NULL OR tx.status = ?) ORDER BY tx.id DESC LIMIT ?",
                (status, status, int(limit))).fetchall()
            return [dict(r) for r in rows]

    def admin_audit(self, limit=100):
        with self._lock:
            return [dict(r) for r in self._conn.execute(
                "SELECT id, actor_id, action, entity, entity_id, details, created_at "
                "FROM financial_audit_logs ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()]

    def report_rows(self):
        """Transactions as plain rows for CSV export. Text is made safe by the caller."""
        with self._lock:
            return [dict(r) for r in self._conn.execute(
                "SELECT tx.id, tx.kind, tx.status, tx.amount_halalas, tx.commission_bps, tx.created_at, "
                "tx.provider_ref, pc.amount_halalas AS commission_halalas, fe.net_halalas AS net_halalas "
                "FROM payment_transactions tx "
                "LEFT JOIN platform_commissions pc ON pc.transaction_id = tx.id "
                "LEFT JOIN freelancer_earnings fe ON fe.transaction_id = tx.id ORDER BY tx.id").fetchall()]

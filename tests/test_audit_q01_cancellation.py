"""Q01: a cancellation Stripe schedules with `cancel_at` shows as scheduled, with its date (audit round, 2026-11-27).

Stripe is the local stub (tests/support/stripe_stub.py); nothing reaches api.stripe.com. Events are signed as
tests/test_pass3_billing_ladder.py signs them.
"""
from __future__ import annotations

import time

import pytest

from app.auth import store as auth_store
from tests.test_pass3_billing_ladder import (  # noqa: F401  (fixtures and helpers are shared)
    ENT, PRO, WHSEC, clean, deliver, event, on, reader, send, stripe, sub)

DAY = 86400


def with_cancel_at(obj, at):
    obj = dict(obj)
    obj["cancel_at"] = at
    return obj


def iso(epoch):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def test_cancel_at_set_and_period_end_flag_false_is_a_scheduled_cancellation(monkeypatch):
    on(monkeypatch)
    _, user = reader("q01a@example.com")
    t = int(time.time())
    end = t + 20 * DAY
    send(event(with_cancel_at(sub(user["id"], [PRO]), end), created=t))
    s = auth_store.subscription(user["id"])
    assert s["plan"] == "pro" and s["cancel_at_period_end"] is False
    assert s["cancels"] is True and s["cancel_at"] == iso(end) and s["ends_on"] == iso(end)


def test_the_older_shape_period_end_flag_gives_the_period_end(monkeypatch):
    on(monkeypatch)
    _, user = reader("q01b@example.com")
    send(event(sub(user["id"], [PRO], cancel=True)))
    s = auth_store.subscription(user["id"])
    assert s["cancels"] is True and s["cancel_at"] is None
    assert s["ends_on"] == s["current_period_end"] and s["plan"] == "pro"


def test_resumption_clears_both_and_the_plan_stays_paid(monkeypatch):
    on(monkeypatch)
    _, user = reader("q01c@example.com")
    t = int(time.time())
    send(event(with_cancel_at(sub(user["id"], [PRO]), t + 20 * DAY), created=t))
    send(event(sub(user["id"], [PRO], cancel=False), created=t + 5))
    s = auth_store.subscription(user["id"])
    assert s["cancels"] is False and s["ends_on"] is None and s["cancel_at"] is None
    assert s["plan"] == "pro"


def test_a_delayed_scheduling_event_after_the_resumption_changes_nothing(monkeypatch):
    on(monkeypatch)
    _, user = reader("q01d@example.com")
    t = int(time.time())
    send(event(sub(user["id"], [PRO], cancel=False), created=t + 10))      # the resumption arrives first
    out = send(event(with_cancel_at(sub(user["id"], [PRO]), t + 20 * DAY), created=t))   # older, delivered late
    assert out["result"] == "stale"
    s = auth_store.subscription(user["id"])
    assert s["cancels"] is False and s["ends_on"] is None and s["plan"] == "pro"


def test_invoice_paid_carries_cancel_at_from_the_subscription_stripe_returns(monkeypatch, stripe):
    on(monkeypatch)
    _, user = reader("q01e@example.com")
    t = int(time.time())
    end = t + 15 * DAY
    send(event(sub(user["id"], [PRO]), created=t))
    stripe.subscriptions["sub_l1"] = with_cancel_at(sub(user["id"], [PRO]), end)
    send(event({"object": "invoice", "id": "in_q01", "customer": "cus_l1", "subscription": "sub_l1"},
               etype="invoice.paid", created=t + 10))
    s = auth_store.subscription(user["id"])
    assert s["cancels"] is True and s["ends_on"] == iso(end)


def test_the_subscription_deleted_at_the_end_leaves_a_free_plan_and_no_scheduled_state(monkeypatch):
    on(monkeypatch)
    _, user = reader("q01f@example.com")
    t = int(time.time())
    end = t + 2 * DAY
    send(event(with_cancel_at(sub(user["id"], [PRO]), end), created=t))
    send(event(with_cancel_at(sub(user["id"], [PRO], status="canceled"), end),
               etype="customer.subscription.deleted", created=t + 3 * DAY))
    s = auth_store.subscription(user["id"])
    assert s["plan"] == "free" and s["cancels"] is False and s["cancel_at"] is None


def test_a_free_plan_never_reports_a_cancellation(monkeypatch):
    _, user = reader("q01g@example.com")
    s = auth_store.subscription(user["id"])
    assert s["plan"] == "free" and s["cancels"] is False and s["ends_on"] is None


def test_migration_28_is_registered_last_and_adds_only_the_column():
    from app import db as accounts_db
    last = accounts_db.MIGRATIONS[-1]
    assert last[0] == 28 and last[1] == "subscription_cancel_at"
    assert last[2] == ["ALTER TABLE subscriptions ADD COLUMN cancel_at TEXT"]
    # applying it on a database at 27, and running migrate() again, is tests/test_pass3_migrations.py


# ---------------------------------------------------------------- the Settings row, under JavaScriptCore

def _ending(tmp_path, plan):
    import json
    from tests.test_frontend_v2_stage0 import V2, _run
    return _run(tmp_path, f"""
      const s = await import('{(V2 / "js/pages/settings.js").as_posix()}');
      print(JSON.stringify(s.endingNote({json.dumps(plan)}, (iso) => iso.slice(0, 10))));
    """)


def test_the_row_for_one_date(tmp_path):
    got = _ending(tmp_path, {"label": "Pro", "cancels": True, "ends_on": "2026-12-20T00:00:00Z",
                             "current_period_end": "2026-12-20T00:00:00Z"})
    assert got == "Cancellation scheduled. Pro stays active through 2026-12-20; it will not renew."


def test_the_row_for_two_dates_adds_paid_through(tmp_path):
    got = _ending(tmp_path, {"label": "Pro", "cancels": True, "ends_on": "2026-12-05T00:00:00Z",
                             "current_period_end": "2026-12-20T00:00:00Z"})
    assert got == ("Cancellation scheduled. Pro stays active through 2026-12-05; it will not renew. "
                   "Paid through 2026-12-20.")


def test_the_row_for_no_cancellation_says_nothing(tmp_path):
    assert _ending(tmp_path, {"label": "Pro", "cancels": False, "ends_on": None,
                              "current_period_end": "2026-12-20T00:00:00Z"}) == ""
    assert _ending(tmp_path, {"label": "Free"}) == ""


def test_settings_prints_the_note_from_the_plan():
    from tests.test_frontend_v2_stage0 import V2
    src = (V2 / "js/pages/settings.js").read_text()
    assert "endingNote(plan)" in src and "plan.cancel_at_period_end &&" not in src

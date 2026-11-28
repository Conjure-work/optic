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
    last = [m for m in accounts_db.MIGRATIONS if m[0] == 28][0]
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


# ------------------------------------------------- backfill: a cancellation scheduled before cancel_at was recorded

from app import billing, db  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_retry_clock(stripe):
    billing._backfill_tried.clear()
    stripe.subscriptions.clear()          # the stub's reset() keeps subscriptions between tests
    yield
    billing._backfill_tried.clear()


def legacy(monkeypatch, email, stripe_sub, *, flag=False):
    """A paid row as it stood before this code: linked, entitled, cancel_at unrecorded, never synced."""
    on(monkeypatch)
    c, user = reader(email)
    t = int(time.time())
    send(event(sub(user["id"], [PRO]), created=t))
    db.execute("UPDATE subscriptions SET cancel_at = NULL, cancel_at_period_end = ?, cancel_synced_at = NULL "
               "WHERE user_id = ?", (1 if flag else 0, user["id"]))
    return c, user, t


def counted(monkeypatch):
    calls = []
    real = billing._stripe

    def spy(method, path, *a, **k):
        if "/subscriptions/" in path:           # the price lookups status() makes for its labels are not the subject
            calls.append((method, path))
        return real(method, path, *a, **k)
    monkeypatch.setattr(billing, "_stripe", spy)
    return calls


def test_a_cancellation_scheduled_before_the_deploy_appears_on_the_first_status_read(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01h@example.com", None)
    end = t + 27 * DAY
    stripe.subscriptions["sub_l1"] = with_cancel_at(sub(user["id"], [PRO]), end)
    assert auth_store.subscription(user["id"])["cancels"] is False            # as the customer saw it
    out = c.get("/api/billing/status").json()["subscription"]
    assert out["cancels"] is True and out["cancel_at"] == iso(end) and out["ends_on"] == iso(end)
    assert out["plan"] == "pro"


def test_the_account_state_read_also_backfills(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01i@example.com", None)
    stripe.subscriptions["sub_l1"] = with_cancel_at(sub(user["id"], [PRO]), t + 9 * DAY)
    me = c.get("/api/auth/me").json()
    assert me["subscription"]["cancels"] is True and me["subscription"]["ends_on"] == iso(t + 9 * DAY)


def test_one_retrieval_per_subscription_across_reads(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01j@example.com", None)
    stripe.subscriptions["sub_l1"] = with_cancel_at(sub(user["id"], [PRO]), t + 5 * DAY)
    calls = counted(monkeypatch)
    c.get("/api/billing/status")
    c.get("/api/billing/status")
    c.get("/api/auth/me")
    assert calls == [("GET", "/subscriptions/sub_l1")]


def test_a_subscription_with_no_cancellation_is_still_read_once_and_stays_uncancelled(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01k@example.com", None)
    stripe.subscriptions["sub_l1"] = sub(user["id"], [PRO])
    calls = counted(monkeypatch)
    c.get("/api/billing/status")
    out = c.get("/api/billing/status").json()["subscription"]
    assert len(calls) == 1 and out["cancels"] is False and out["plan"] == "pro"


def test_a_stripe_failure_leaves_the_row_does_not_raise_and_retries_after_ten_minutes(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01l@example.com", None)      # nothing in the stub: Stripe answers 404
    calls = counted(monkeypatch)
    before = db.row("SELECT * FROM subscriptions WHERE user_id = ?", (user["id"],))
    r = c.get("/api/billing/status")
    assert r.status_code == 200 and r.json()["subscription"]["cancels"] is False
    c.get("/api/billing/status")
    assert len(calls) == 1                                           # not again inside ten minutes
    after = db.row("SELECT * FROM subscriptions WHERE user_id = ?", (user["id"],))
    assert after == before and after["cancel_synced_at"] is None
    stripe.subscriptions["sub_l1"] = with_cancel_at(sub(user["id"], [PRO]), t + 4 * DAY)
    sid = "sub_l1"
    billing._backfill_tried[sid] -= billing._BACKFILL_RETRY_SECONDS + 1     # ten minutes later
    assert c.get("/api/billing/status").json()["subscription"]["ends_on"] == iso(t + 4 * DAY)
    assert len(calls) == 2


def test_a_stripe_timeout_does_not_raise(monkeypatch):
    c, user, t = legacy(monkeypatch, "q01m@example.com", None)
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("down")
    monkeypatch.setattr(requests, "request", boom)
    assert billing.backfill_cancellation(user["id"]) is False
    assert c.get("/api/billing/status").status_code == 200


def test_billing_off_or_no_key_makes_no_call(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01n@example.com", None)
    stripe.subscriptions["sub_l1"] = with_cancel_at(sub(user["id"], [PRO]), t + 5 * DAY)
    calls = counted(monkeypatch)
    monkeypatch.delenv("STRIPE_SECRET_KEY")
    c.get("/api/billing/status"); c.get("/api/auth/me")
    assert calls == [] and auth_store.subscription(user["id"])["cancels"] is False
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_ladder")
    monkeypatch.delenv("STRIPE_PRICE_ID_PRO")                       # off: no price configured
    monkeypatch.delenv("STRIPE_PRICE_ID_ENTERPRISE")
    c.get("/api/billing/status")
    assert calls == []


def test_a_row_the_webhook_already_wrote_is_not_retrieved(monkeypatch, stripe):
    on(monkeypatch)
    c, user = reader("q01o@example.com")
    send(event(with_cancel_at(sub(user["id"], [PRO]), int(time.time()) + 6 * DAY)))
    calls = counted(monkeypatch)
    c.get("/api/billing/status")
    assert calls == []


def test_a_guest_and_a_free_account_make_no_call(monkeypatch, stripe):
    on(monkeypatch)
    calls = counted(monkeypatch)
    from fastapi.testclient import TestClient
    from app import main
    TestClient(main.app).get("/api/billing/status")
    c, _ = reader("q01p@example.com")
    c.get("/api/billing/status")
    assert calls == []


def test_the_period_end_fallback_through_the_backfill(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01q@example.com", None)
    stripe.subscriptions["sub_l1"] = sub(user["id"], [PRO], cancel=True)    # cancel_at_period_end, no cancel_at
    out = c.get("/api/billing/status").json()["subscription"]
    assert out["cancels"] is True and out["cancel_at"] is None
    assert out["ends_on"] == out["current_period_end"] and out["cancel_at_period_end"] is True


def test_the_backfill_and_the_webhook_write_identical_rows(monkeypatch, stripe):
    cols = ("plan", "status", "provider_status", "cancel_at", "cancel_at_period_end", "current_period_end",
            "provider_subscription_id", "provider_customer_id")
    end = int(time.time()) + 12 * DAY
    obj = with_cancel_at(sub("PLACEHOLDER", [PRO]), end)
    on(monkeypatch)
    _, a = reader("q01r@example.com")
    _, b = reader("q01s@example.com")
    t = int(time.time())
    # the webhook path
    send(event(with_cancel_at(sub(a["id"], [PRO]), end), created=t))
    # the backfill path: link, then retrieve (a different subscription id so the two rows can coexist)
    send(event(sub(b["id"], [PRO], sid="sub_l2"), created=t - 100))
    db.execute("UPDATE subscriptions SET cancel_at = NULL, cancel_synced_at = NULL WHERE user_id = ?", (b["id"],))
    stripe.subscriptions["sub_l2"] = with_cancel_at(sub(b["id"], [PRO], sid="sub_l2"), end)
    assert billing.backfill_cancellation(b["id"]) is True
    ra = db.row("SELECT * FROM subscriptions WHERE user_id = ?", (a["id"],))
    rb = db.row("SELECT * FROM subscriptions WHERE user_id = ?", (b["id"],))
    for k in cols:
        if k == "provider_subscription_id":
            continue
        assert ra[k] == rb[k], k
    assert ra["cancel_at"] == iso(end) and rb["cancel_synced_at"]
    assert rb["last_event_at"] == t - 100                      # the backfill does not move the event clock


def test_a_resumption_after_a_backfilled_cancellation_still_clears_it(monkeypatch, stripe):
    c, user, t = legacy(monkeypatch, "q01t@example.com", None)
    stripe.subscriptions["sub_l1"] = with_cancel_at(sub(user["id"], [PRO]), t + 8 * DAY)
    c.get("/api/billing/status")
    send(event(sub(user["id"], [PRO], cancel=False), created=t + 60))
    assert auth_store.subscription(user["id"])["cancels"] is False


# ----------------------------------------------- the date is Stripe's calendar day (UTC), not the viewer's

def _day(tmp_path, iso_):
    import json
    from tests.test_frontend_v2_stage0 import V2, _run
    return _run(tmp_path, f"""
      const s = await import('{(V2 / "js/pages/settings.js").as_posix()}');
      print(JSON.stringify([s.dayOf({json.dumps(iso_)}),
        s.endingNote({{label: 'Pro', cancels: true, ends_on: {json.dumps(iso_)}, current_period_end: {json.dumps(iso_)}}})]));
    """)


def test_the_ending_date_is_the_utc_day_stripe_names(tmp_path):
    # 04:48 UTC is the evening before in New York; the suite runs under TZ=America/New_York
    day, note = _day(tmp_path, "2026-12-25T04:48:09Z")
    assert day == "Dec 25, 2026"
    assert note == "Cancellation scheduled. Pro stays active through Dec 25, 2026; it will not renew."


def test_a_late_utc_time_does_not_roll_forward_either(tmp_path):
    assert _day(tmp_path, "2026-12-25T23:59:59Z")[0] == "Dec 25, 2026"


def test_every_billing_date_on_the_plan_section_goes_through_the_utc_formatter():
    from tests.test_frontend_v2_stage0 import V2
    src = (V2 / "js/pages/settings.js").read_text()
    assert "timeZone: 'UTC'" in src and "prefs.stamp(iso).split" not in src
    plan = src.split('id="pl-h"')[1].split("</section>")[0]
    assert "short(" not in plan and "prefs.stamp" not in plan         # no other date is formatted in the viewer's zone
    note = src.split("export function endingNote")[1].split("\n}\n")[0]
    assert note.count("fmt(") == 2 and "toLocale" not in note

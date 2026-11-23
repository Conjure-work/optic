"""Round three billing (2026-11-23): the plan ladder from variables, entitlement from the price Stripe bills, the
legal gate on Checkout, caps by plan in both billing states, and Stripe down at the route.

Stripe is tests/support/stripe_stub.py on a local port (STRIPE_API_BASE), which records every request; nothing here
reaches api.stripe.com. Webhooks are signed with a test secret exactly as Stripe signs them.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import billing, health_extra, legal_text
from app.auth import store as auth_store
from tests.support.stripe_stub import StripeStub
from tests.test_billing import deliver, reader

WHSEC = "whsec_test_ladder"
PRO, ENT = "price_test_pro_ladder", "price_test_ent_ladder"
BILLING_VARS = ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID", "STRIPE_PRICE_ID_PRO",
                "STRIPE_PRICE_ID_ENTERPRISE", "BILLING_LIVE_APPROVED", "BILLING_PRICE_LABEL",
                "BILLING_PRICE_LABEL_PRO", "BILLING_PRICE_LABEL_ENTERPRISE", "BILLING_TEST_IGNORE_LEGAL_PLACEHOLDER",
                "BILLING_PLAN_LABEL_PRO", "BILLING_PLAN_LABEL_ENTERPRISE")


@pytest.fixture(scope="module")
def stripe():
    s = StripeStub().start()
    yield s
    s.stop()


@pytest.fixture(autouse=True)
def clean(accounts, monkeypatch, stripe, tmp_path):
    for n in BILLING_VARS:
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv("STRIPE_API_BASE", stripe.url)
    monkeypatch.setenv("STRIPE_TIMEOUT_SECONDS", "1")
    stripe.reset()
    stripe.hold = 3.0
    stripe.prices.update({PRO: {"id": PRO, "unit_amount": 2000, "currency": "usd", "recurring": {"interval": "month"}},
                          ENT: {"id": ENT, "unit_amount": 9900, "currency": "usd",
                                "recurring": {"interval": "month"}}})
    billing._PRICE.update({"id": None, "at": 0.0, "label": None})
    billing._PRICES.clear()
    legal = tmp_path / "legal"
    legal.mkdir()
    for doc in ("terms", "privacy"):
        (legal / (doc + ".md")).write_text("# Fixture {}\n\nFixture text, not legal text.\n".format(doc))
    monkeypatch.setenv("LEGAL_TEXT_DIR", str(legal))
    return accounts


def on(monkeypatch, *, enterprise=True, key="sk_test_ladder"):
    monkeypatch.setenv("STRIPE_SECRET_KEY", key)
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", PRO)
    if enterprise:
        monkeypatch.setenv("STRIPE_PRICE_ID_ENTERPRISE", ENT)


def placeholder(monkeypatch, tmp_path):
    d = tmp_path / "ph"
    d.mkdir()
    for doc in ("terms", "privacy"):
        (d / (doc + ".md")).write_text("<!-- {} -->\nBeing prepared.\n".format(legal_text.MARKER))
    monkeypatch.setenv("LEGAL_TEXT_DIR", str(d))


def sub(uid, prices, status="active", sid="sub_l1", meta_plan=None, cancel=False):
    meta = {"user_id": uid}
    if meta_plan:
        meta["plan"] = meta_plan
    return {"object": "subscription", "id": sid, "customer": "cus_l1", "status": status, "metadata": meta,
            "cancel_at_period_end": cancel,
            "items": {"data": [{"price": {"id": p}, "current_period_end": int(time.time()) + 86400 * 30}
                               for p in prices]}}


def event(obj, etype="customer.subscription.updated", created=None):
    return {"id": "evt_l_{}".format(time.time_ns()), "type": etype, "livemode": False,
            "created": created or int(time.time()), "data": {"object": obj}}


def send(ev):
    r = deliver(ev, secret=WHSEC)
    assert r.status_code == 200, r.text
    return r.json()


# ------------------------------------------------------------------ the ladder from variables


def test_nothing_set_is_off_with_nothing_to_show_and_no_names_to_a_reader():
    st = billing.status()
    assert st["available"] is False and "plans" not in st
    assert billing.anything_set() is False
    assert billing.health()["state"] == "off" and billing.health()["plans"] == 0
    assert billing.health_operator()["missing"] == []          # nothing configured: no list to read


def test_the_ladder_is_the_three_plans_in_store_with_their_caps(monkeypatch):
    on(monkeypatch)
    plans = billing.status()["plans"]
    assert [p["plan"] for p in plans] == ["free", "pro", "enterprise"]
    for p in plans:
        want = {k: v for k, v in auth_store.PLANS[p["plan"]].items() if k != "label"}
        assert p["limits"] == want and p["label"] == auth_store.PLANS[p["plan"]]["label"]
    assert plans[1]["price_label"] == "$20 a month" and plans[2]["price_label"] == "$99 a month"


def test_a_plan_without_a_price_is_not_on_sale(monkeypatch):
    on(monkeypatch, enterprise=False)
    assert [p["plan"] for p in billing.status()["plans"]] == ["free", "pro"]


def test_the_old_single_price_variable_is_still_the_pro_price(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_ladder")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    monkeypatch.setenv("STRIPE_PRICE_ID", PRO)
    assert billing.price_id("pro") == PRO and billing.status()["available"] is True
    monkeypatch.setenv("STRIPE_PRICE_ID_PRO", "price_other")
    assert billing.price_id("pro") == "price_other"            # the new name wins when both are set


def test_plan_and_price_labels_are_configuration(monkeypatch):
    on(monkeypatch)
    monkeypatch.setenv("BILLING_PLAN_LABEL_ENTERPRISE", "Desk")
    monkeypatch.setenv("BILLING_PRICE_LABEL_ENTERPRISE", "$80 a month, billed yearly")
    ent = billing.status()["plans"][2]
    assert ent["label"] == "Desk" and ent["price_label"] == "$80 a month, billed yearly"


@pytest.mark.parametrize("unset", ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "prices"])
def test_a_partial_set_reads_as_off_and_names_what_is_missing(monkeypatch, unset):
    on(monkeypatch)
    if unset == "prices":
        monkeypatch.delenv("STRIPE_PRICE_ID_PRO")
        monkeypatch.delenv("STRIPE_PRICE_ID_ENTERPRISE")
        name = "STRIPE_PRICE_ID_PRO"
    else:
        monkeypatch.delenv(unset)
        name = unset
    assert billing.status()["available"] is False
    assert billing.health()["state"] == "off"
    assert billing.health_operator()["missing"] == [name]


def test_the_live_key_refusal_is_unchanged(monkeypatch):
    on(monkeypatch, key="rk_live_ladder")
    assert billing.status()["available"] is False
    monkeypatch.setenv("BILLING_LIVE_APPROVED", "true")
    assert billing.status()["available"] is True and billing.status()["mode"] == "live"


def test_health_reports_the_mode_publicly_and_the_missing_names_to_the_owner_only(monkeypatch):
    on(monkeypatch)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET")
    body = TestClient(main.app).get("/api/health").json()
    assert body["modes"]["billing"]["state"] == "off"
    assert "billing_setup" not in body["modes"]                      # names are the owner's to read
    assert health_extra.snapshot(operator=True)["billing_setup"]["missing"] == ["STRIPE_WEBHOOK_SECRET"]


# ------------------------------------------------------------------ caps (amendment A6)


def test_caps_are_per_stored_plan_while_billing_is_off_exactly_as_before(monkeypatch):
    c, user = reader("off-caps@example.com")
    assert billing.health()["caps"].startswith("per stored plan, as before round three")
    assert auth_store.subscription(user["id"])["limits"]["ai_calls_per_day"] == 3
    auth_store.set_plan(user["id"], "enterprise")                     # the owner's grant, as on the copy
    assert auth_store.subscription(user["id"])["limits"]["ai_calls_per_day"] == 4000


def test_caps_follow_the_plan_stripe_bills_while_billing_is_on(monkeypatch):
    on(monkeypatch)
    c, user = reader("on-caps@example.com")
    assert billing.health()["caps"] == "per plan, derived from Stripe's prices"
    send(event(sub(user["id"], [ENT])))
    s = auth_store.subscription(user["id"])
    assert s["plan"] == "enterprise" and s["limits"]["brokerage_connections"] == 10
    send(event(sub(user["id"], [PRO]), created=int(time.time()) + 5))
    s = auth_store.subscription(user["id"])
    assert s["plan"] == "pro" and s["limits"]["ai_calls_per_day"] == 15 and s["limits"]["brokerage_connections"] == 3
    from app.brokerage import service
    assert service.entitlement(auth_store.get_user(user["id"]))["max_connections"] == 3


# ------------------------------------------------------------------ billing truth


def test_the_price_decides_the_plan_never_the_metadata(monkeypatch):
    on(monkeypatch)
    _, user = reader("truth@example.com")
    assert send(event(sub(user["id"], [PRO], meta_plan="enterprise")))["result"] == "pro"
    assert auth_store.subscription(user["id"])["plan"] == "pro"


def test_the_highest_plan_among_the_items_wins_and_a_foreign_price_grants_nothing(monkeypatch):
    on(monkeypatch)
    _, user = reader("items@example.com")
    assert billing.plan_of(sub(user["id"], [PRO, ENT])) == "enterprise"
    assert send(event(sub(user["id"], ["price_someone_elses"])))["result"] == "free"


def test_a_portal_change_cancel_at_period_end_and_resume_move_the_plan(monkeypatch):
    on(monkeypatch)
    _, user = reader("portal@example.com")
    t = int(time.time())
    send(event(sub(user["id"], [PRO]), created=t))
    send(event(sub(user["id"], [ENT]), created=t + 1))                    # upgraded in the portal
    assert auth_store.subscription(user["id"])["plan"] == "enterprise"
    send(event(sub(user["id"], [ENT], cancel=True), created=t + 2))       # cancel at period end: still entitled
    s = auth_store.subscription(user["id"])
    assert s["plan"] == "enterprise" and s["cancel_at_period_end"] is True
    send(event(sub(user["id"], [ENT], cancel=False), created=t + 3))      # resumed
    assert auth_store.subscription(user["id"])["cancel_at_period_end"] is False
    send(event(sub(user["id"], [PRO]), created=t + 4))                    # downgraded in the portal
    assert auth_store.subscription(user["id"])["plan"] == "pro"
    send(event(sub(user["id"], [PRO], status="canceled"), etype="customer.subscription.deleted", created=t + 5))
    assert auth_store.subscription(user["id"])["plan"] == "free"


def test_invoice_paid_reads_the_subscription_from_stripe_and_derives_the_plan_again(monkeypatch, stripe):
    on(monkeypatch)
    _, user = reader("invoice@example.com")
    t = int(time.time())
    send(event(sub(user["id"], [PRO]), created=t))
    stripe.subscriptions["sub_l1"] = sub(user["id"], [ENT])               # a change whose event was missed
    out = send(event({"object": "invoice", "id": "in_1", "customer": "cus_l1", "subscription": "sub_l1"},
                     etype="invoice.paid", created=t + 10))
    assert out["result"] == "enterprise"
    assert auth_store.subscription(user["id"])["plan"] == "enterprise"
    assert any(r["method"] == "GET" and r["path"].endswith("/subscriptions/sub_l1") for r in stripe.requests)


def test_invoice_paid_with_stripe_down_is_not_acknowledged_so_stripe_retries(monkeypatch, stripe):
    on(monkeypatch)
    _, user = reader("invoice-down@example.com")
    send(event(sub(user["id"], [PRO])))
    stripe.mode = "error"
    ev = event({"object": "invoice", "id": "in_2", "subscription": "sub_l1", "customer": "cus_l1"},
               etype="invoice.paid", created=int(time.time()) + 10)
    assert deliver(ev, secret=WHSEC).status_code == 500
    stripe.mode = "ok"
    stripe.subscriptions["sub_l1"] = sub(user["id"], [PRO])
    assert deliver(ev, secret=WHSEC).status_code == 200                   # the same event id, processed on retry


def test_a_duplicate_event_is_applied_once(monkeypatch):
    on(monkeypatch)
    _, user = reader("dup@example.com")
    ev = event(sub(user["id"], [PRO]))
    send(ev)
    assert deliver(ev, secret=WHSEC).json().get("duplicate") is True


# ------------------------------------------------------------------ Checkout and the portal


def test_checkout_sells_the_plan_asked_for_at_its_own_price(monkeypatch, stripe):
    on(monkeypatch)
    c, user = reader("buy-ent@example.com")
    r = c.post("/api/billing/checkout", json={"plan": "enterprise"})
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.com/")
    made = [x for x in stripe.requests if x["path"].endswith("/checkout/sessions")][-1]
    assert made["form"]["line_items[0][price]"] == ENT and made["form"]["client_reference_id"] == user["id"]
    assert made["authorized"] and "enterprise" in made["idempotency_key"]
    assert auth_store.subscription(user["id"])["plan"] == "free"           # the browser never grants a plan


def test_checkout_with_no_plan_named_buys_pro_and_an_unknown_plan_is_refused(monkeypatch, stripe):
    on(monkeypatch, enterprise=False)
    c, _ = reader("buy-pro@example.com")
    assert c.post("/api/billing/checkout").status_code == 200
    made = [x for x in stripe.requests if x["path"].endswith("/checkout/sessions")][-1]
    assert made["form"]["line_items[0][price]"] == PRO
    assert c.post("/api/billing/checkout", json={"plan": "enterprise"}).status_code == 400   # no price set
    assert c.post("/api/billing/checkout", json={"plan": "platinum"}).status_code == 400


def test_checkout_is_refused_to_a_reader_already_on_a_paid_plan(monkeypatch):
    on(monkeypatch)
    c, user = reader("already@example.com")
    auth_store.set_plan(user["id"], "enterprise")
    r = c.post("/api/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 409 and "Enterprise" in r.json()["detail"]


def test_checkout_and_portal_refuse_no_user_and_a_missing_csrf_and_the_portal_another_readers_account(monkeypatch):
    on(monkeypatch)
    anon = TestClient(main.app)
    assert anon.post("/api/billing/checkout").status_code == 401           # no user
    assert anon.post("/api/billing/portal").status_code == 401
    c, _ = reader("nocsrf@example.com")
    del c.headers["X-Optic-CSRF"]
    assert c.post("/api/billing/checkout").status_code == 403              # a cookie alone is not the reader
    assert c.post("/api/billing/portal").status_code == 403
    # wrong user: a reader with no billing account of their own cannot reach anyone else's portal
    other, other_user = reader("other@example.com")
    _, payer = reader("payer2@example.com")
    send(event(sub(payer["id"], [PRO])))
    assert other.post("/api/billing/portal").status_code == 404


def test_the_portal_opens_for_a_reader_with_a_billing_account(monkeypatch, stripe):
    on(monkeypatch)
    c, user = reader("portal-open@example.com")
    send(event(sub(user["id"], [PRO])))
    r = c.post("/api/billing/portal")
    assert r.status_code == 200 and r.json()["url"].startswith("https://billing.stripe.com/")
    made = [x for x in stripe.requests if x["path"].endswith("/billing_portal/sessions")][-1]
    assert made["form"]["customer"] == "cus_l1"


@pytest.mark.parametrize("mode,code", [("timeout", 503), ("error", 502)])
def test_stripe_down_at_checkout_says_so_and_writes_nothing(monkeypatch, stripe, mode, code):
    on(monkeypatch)
    c, user = reader("down-{}@example.com".format(mode))
    stripe.mode = mode
    r = c.post("/api/billing/checkout", json={"plan": "pro"})
    assert r.status_code == code
    assert "payment provider" in r.json()["detail"]
    assert auth_store.subscription(user["id"])["plan"] == "free"
    assert billing._sub_row(user["id"]).get("provider_customer_id") is None


@pytest.mark.parametrize("mode,code", [("timeout", 503), ("error", 502)])
def test_stripe_down_at_the_portal_says_so(monkeypatch, stripe, mode, code):
    on(monkeypatch)
    c, user = reader("pdown-{}@example.com".format(mode))
    send(event(sub(user["id"], [PRO])))
    stripe.mode = mode
    assert c.post("/api/billing/portal").status_code == code


def test_stripe_down_leaves_the_price_unnamed_rather_than_guessed(monkeypatch, stripe):
    on(monkeypatch)
    stripe.mode = "error"
    assert [p["price_label"] for p in billing.status()["plans"]] == [None, None, None]


def test_the_suite_never_points_at_the_real_host(stripe):
    assert billing._api() == stripe.url and "stripe.com" not in billing._api()


# ------------------------------------------------------------------ the legal gate (card D)


def test_checkout_is_refused_with_the_pages_sentence_while_the_terms_are_the_placeholder(monkeypatch, tmp_path, stripe):
    on(monkeypatch)
    placeholder(monkeypatch, tmp_path)
    st = billing.status()
    assert st["available"] is True and st["checkout_open"] is False
    assert st["checkout_refusal"] == legal_text.CHECKOUT_REFUSAL
    c, _ = reader("legal-gate@example.com")
    r = c.post("/api/billing/checkout", json={"plan": "pro"})
    assert r.status_code == 503 and r.json()["detail"] == legal_text.CHECKOUT_REFUSAL
    assert not [x for x in stripe.requests if x["path"].endswith("/checkout/sessions")]


def test_the_copys_switch_opens_checkout_on_a_test_key_only(monkeypatch, tmp_path):
    on(monkeypatch)
    placeholder(monkeypatch, tmp_path)
    monkeypatch.setenv("BILLING_TEST_IGNORE_LEGAL_PLACEHOLDER", "true")
    assert billing.status()["checkout_open"] is True
    assert billing.health_operator()["legal_override"] is True
    on(monkeypatch, key="rk_live_ladder")
    monkeypatch.setenv("BILLING_LIVE_APPROVED", "true")
    assert billing.status()["checkout_open"] is False                    # a live key ignores it

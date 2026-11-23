"""Round three billing, legal pages and alert emails in a real browser (2026-11-23).

What is real: the app in a subprocess, its database, Chromium, the clicks, the signed webhook. What is not: Stripe is
tests/support/stripe_stub.py on a local port (STRIPE_API_BASE), which records what Optic asked for; the hosted Checkout
page is never opened (the browser's navigation to checkout.stripe.com is caught and answered with a blank page, and
the address is asserted). The proof against Stripe's real test mode is the evaluation copy's gauntlet, not this file.
The "counsel" legal files here are fixtures that say so; no legal text is written.
"""
from __future__ import annotations

import atexit
import json
import re
import sqlite3
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import DESKTOP, PHONE, open_page
from tests.support.stripe_stub import StripeStub
from tests.test_billing import signed

ROOT = Path(__file__).resolve().parents[2]
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
WHSEC = "whsec_e2e_fixture"
PRO, ENT = "price_e2e_pro", "price_e2e_enterprise"

STRIPE = StripeStub().start()
atexit.register(STRIPE.stop)
STRIPE.prices.update({PRO: {"id": PRO, "unit_amount": 2000, "currency": "usd", "recurring": {"interval": "month"}},
                      ENT: {"id": ENT, "unit_amount": 9900, "currency": "usd", "recurring": {"interval": "month"}}})
FINAL = Path(tempfile.mkdtemp(prefix="optic-legal-fixture-"))
for _doc in ("terms", "privacy"):
    (FINAL / (_doc + ".md")).write_text("# {} (fixture)\n\nA fixture paragraph, not legal text.\n\n- a fixture item\n"
                                        .format(_doc.title()))

ON = {"STRIPE_SECRET_KEY": "sk_test_e2e_fixture", "STRIPE_WEBHOOK_SECRET": WHSEC, "STRIPE_PRICE_ID_PRO": PRO,
      "STRIPE_PRICE_ID_ENTERPRISE": ENT, "STRIPE_API_BASE": STRIPE.url, "STRIPE_TIMEOUT_SECONDS": "3"}
BILLING_ON_FINAL = dict(ON, LEGAL_TEXT_DIR=str(FINAL))
BILLING_ON_PLACEHOLDER = dict(ON)                                   # the repository's own placeholder files
ALERTS_ON = {"ALERT_DELIVERY_READERS": "1"}

# "Upgrade" alone is an analyst's rating change on Analyst actions, so the plan wording is matched as a phrase
PAYWALL = re.compile(r"Choose (Pro|Enterprise)|Upgrade (to|for)\b|Resume with Pro|Plans are not on sale|Linking is part of the paid plan|"
                     r"\$\d+ a month|Manage billing|Test mode", re.I)


def _axe(page):
    from axe_playwright_python.sync_playwright import Axe
    result = Axe().run(page, options={"runOnly": {"type": "tag", "values": TAGS}})
    return [{"id": v["id"], "impact": v["impact"], "nodes": [n["target"] for n in v["nodes"]][:4]}
            for v in result.response.get("violations", [])]


def _routes():
    """Every v2 address, enumerated from the source (nav.js slugs and router.js's own), never a hand-kept list."""
    nav = (ROOT / "static" / "v2" / "js" / "nav.js").read_text()
    router = (ROOT / "static" / "v2" / "js" / "core" / "router.js").read_text()
    slugs = set(re.findall(r"slug: '([a-z0-9-]+)'", nav)) | set(re.findall(r"SLUG_VIEW\.([a-z]+) =", router))
    tabs = ["", "financials", "chart", "options", "earnings", "news", "investing"]
    return ["#/"] + ["#/" + s for s in sorted(slugs)] + ["#/AAPL/" + t if t else "#/AAPL" for t in tabs]


def _settings(page, server):
    page.goto(server["base"] + "/#/settings", wait_until="domcontentloaded")
    page.wait_for_selector("[data-v2-account].avatar", timeout=30000)
    page.wait_for_selector("#pl-h", timeout=30000)
    page.wait_for_function("() => !document.body.innerText.includes('Checking plans...')", timeout=30000)


def test_with_nothing_set_no_route_shows_a_plan_a_price_or_a_paywall(chrome, server):
    """A signed-in reader walks every v2 address with no billing variable set."""
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    seen = {}
    try:
        for route in _routes():
            page.goto(server["base"] + "/" + route, wait_until="domcontentloaded")
            page.wait_for_selector("#main", timeout=30000)
            page.wait_for_timeout(700)
            text = page.inner_text("body")
            hit = PAYWALL.search(text)
            if hit or page.query_selector("[data-v2-plans], [data-v2-billing], [data-v2-bill]"):
                seen[route] = hit.group(0) if hit else "a billing control"
        assert len(_routes()) >= 25
        assert seen == {}, seen
        assert page.errors == [], page.errors
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [BILLING_ON_FINAL], indirect=True)
def test_the_ladder_checkout_and_the_webhook_move_the_reader_to_the_plan(chrome, server):
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    went = []
    ctx.route(re.compile(r"https://(checkout|billing)\.stripe\.com/.*"),
              lambda route: (went.append(route.request.url), route.fulfill(status=200, body="<title>stub</title>")))
    STRIPE.reset()
    try:
        _settings(page, server)
        page.wait_for_selector("[data-v2-plans]")
        plans = page.inner_text("[data-v2-plans]")
        assert "Pro" in plans and "Enterprise" in plans and "$20 a month" in plans and "$99 a month" in plans
        assert "15 assistant messages a day" in plans and "10 brokerage connections" in plans
        page.click("[data-v2-plan='enterprise']")
        page.wait_for_url(re.compile(r"https://checkout\.stripe\.com/c/pay/cs_test_stub_\d+"), timeout=15000)
        made = [r for r in STRIPE.requests if r["path"].endswith("/checkout/sessions")]
        assert made and made[-1]["form"]["line_items[0][price]"] == ENT
        with sqlite3.connect(str(server["db"])) as c:
            uid = c.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
            assert c.execute("SELECT plan FROM subscriptions WHERE user_id = ?", (uid,)).fetchone()[0] == "free"
        assert made[-1]["form"]["client_reference_id"] == uid
        # Stripe's signed webhook is the only thing that grants the plan
        ev = {"id": "evt_e2e_{}".format(time.time_ns()), "type": "customer.subscription.created", "livemode": False,
              "created": int(time.time()),
              "data": {"object": {"object": "subscription", "id": "sub_e2e", "customer": "cus_e2e", "status": "active",
                                  "metadata": {"user_id": uid}, "cancel_at_period_end": False,
                                  "items": {"data": [{"price": {"id": ENT},
                                                      "current_period_end": int(time.time()) + 86400 * 30}]}}}}
        body, headers = signed(ev, secret=WHSEC)
        req = urllib.request.Request(server["base"] + "/api/billing/webhook", data=body, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            assert json.loads(r.read())["result"] == "enterprise"
        page.goto(server["base"] + "/?billing=success#/settings", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-plans]", timeout=30000)
        section = page.inner_text("section[aria-labelledby='pl-h']")
        assert "Enterprise" in section and "Your plan" in section and "Manage billing" in section
        assert not page.query_selector("[data-v2-plan]")                 # no second Checkout for a paying reader
        page.click("[data-v2-billing='portal']")
        page.wait_for_url(re.compile(r"https://billing\.stripe\.com/p/session/stub_\d+"), timeout=15000)
        portal = [r for r in STRIPE.requests if r["path"].endswith("/billing_portal/sessions")]
        assert portal and portal[-1]["form"]["customer"] == "cus_e2e"
        assert page.errors == [], page.errors
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [BILLING_ON_PLACEHOLDER], indirect=True)
def test_while_the_terms_are_the_placeholder_settings_says_so_and_offers_no_checkout(chrome, server):
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    try:
        _settings(page, server)
        page.wait_for_selector("[data-v2-plans-refusal]")
        assert "being prepared with counsel" in page.inner_text("[data-v2-plans-refusal]")
        assert not page.query_selector("[data-v2-plan]")
        page.goto(server["base"] + "/#/terms", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-legal='placeholder']", timeout=30000)
        assert "being prepared with counsel" in page.inner_text("[data-v2-legal='placeholder']")
        assert page.query_selector(".legal-doc h2")                       # the published draft is still readable
        assert page.errors == [], page.errors
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [BILLING_ON_FINAL], indirect=True)
def test_counsels_text_renders_on_both_pages(chrome, server):
    ctx, page = open_page(chrome, server, level="advanced")
    try:
        for doc in ("terms", "privacy"):
            page.goto(server["base"] + "/#/" + doc, wait_until="domcontentloaded")
            page.wait_for_selector("[data-v2-legal='counsel']", timeout=30000)
            text = page.inner_text("[data-v2-legal='counsel']")
            assert "{} (fixture)".format(doc.title()) in text and "a fixture item" in text
            assert not page.query_selector("[data-v2-legal='placeholder']")
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [dict(BILLING_ON_FINAL, **ALERTS_ON)], indirect=True)
def test_a_reader_turns_their_alert_emails_on_and_off_from_settings_by_keyboard(chrome, server):
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    try:
        _settings(page, server)
        page.wait_for_selector("[data-v2-alert-mail]", timeout=30000)
        btn = page.locator("[data-v2-alert-mail]")
        assert btn.get_attribute("aria-pressed") == "false"
        btn.focus()
        page.keyboard.press("Enter")
        page.wait_for_selector("[data-v2-alert-mail][aria-pressed='true']")
        assert page.evaluate("document.activeElement && document.activeElement.hasAttribute('data-v2-alert-mail')")
        with sqlite3.connect(str(server["db"])) as c:
            row = c.execute("SELECT p.alert_email FROM user_preferences p JOIN users u ON u.id = p.user_id "
                            "WHERE u.email = ?", (email,)).fetchone()
        assert row[0] == 1
        page.keyboard.press("Enter")
        page.wait_for_selector("[data-v2-alert-mail][aria-pressed='false']")
    finally:
        ctx.close()


def test_with_the_switch_off_settings_offers_no_alert_emails(chrome, server):
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    try:
        _settings(page, server)
        page.wait_for_timeout(500)
        assert not page.query_selector("[data-v2-alert-mail]")
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [dict(BILLING_ON_FINAL, **ALERTS_ON)], indirect=True)
@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_settings_with_the_ladder_and_alert_emails_has_no_axe_violation(chrome, server, viewport):
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar, viewport=viewport)
    try:
        _settings(page, server)
        page.wait_for_selector("[data-v2-plans]")
        page.wait_for_selector("[data-v2-alert-mail]")
        assert _axe(page) == []
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [BILLING_ON_PLACEHOLDER], indirect=True)
@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_settings_with_the_refusal_and_the_placeholder_pages_have_no_axe_violation(chrome, server, viewport):
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar, viewport=viewport)
    try:
        _settings(page, server)
        page.wait_for_selector("[data-v2-plans-refusal]")
        assert _axe(page) == []
        for doc in ("terms", "privacy"):
            page.goto(server["base"] + "/#/" + doc, wait_until="domcontentloaded")
            page.wait_for_selector("[data-v2-legal='placeholder']", timeout=30000)
            assert _axe(page) == [], doc
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"), doc
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [BILLING_ON_FINAL], indirect=True)
@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_counsels_pages_have_no_axe_violation(chrome, server, viewport):
    ctx, page = open_page(chrome, server, level="advanced", viewport=viewport)
    try:
        for doc in ("terms", "privacy"):
            page.goto(server["base"] + "/#/" + doc, wait_until="domcontentloaded")
            page.wait_for_selector("[data-v2-legal='counsel']", timeout=30000)
            assert _axe(page) == [], doc
    finally:
        ctx.close()

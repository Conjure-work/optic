"""Audit round (2026-11-27), Package C in a real browser: F06 the level's sentence, Q01 a scheduled cancellation, Q02
the owner's two question figures.

What is real: the app in a subprocess, its database, Chromium, the clicks and the signed webhooks. What is not: Stripe
is tests/support/stripe_stub.py on a local port (no live or test-mode call); Anthropic is not reached.
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

from tests.e2e.conftest import PASSWORD, make_account
from tests.e2e.test_pass1_journeys import home, open_page
from tests.support.stripe_stub import StripeStub
from tests.test_billing import signed

WHSEC = "whsec_e2e_audit_c"
PRO = "price_e2e_audit_pro"
OWNER = "owner-audit-c@example.com"
DAY = 86400

STRIPE = StripeStub().start()
atexit.register(STRIPE.stop)
STRIPE.prices.update({PRO: {"id": PRO, "unit_amount": 2000, "currency": "usd", "recurring": {"interval": "month"}}})
FINAL = Path(tempfile.mkdtemp(prefix="optic-legal-fixture-audit-c-"))
for _doc in ("terms", "privacy"):
    (FINAL / (_doc + ".md")).write_text("# {} (fixture)\n\nA fixture paragraph, not legal text.\n".format(_doc.title()))
BILLING_ON = {"STRIPE_SECRET_KEY": "sk_test_e2e_audit_c", "STRIPE_WEBHOOK_SECRET": WHSEC, "STRIPE_PRICE_ID_PRO": PRO,
              "STRIPE_API_BASE": STRIPE.url, "STRIPE_TIMEOUT_SECONDS": "3", "LEGAL_TEXT_DIR": str(FINAL)}


def _norm(text):
    return re.sub(r"\s+", " ", text).strip()


# ----------------------------------------------------------------------------- F06

def _shot(page, selector, path):
    """The element's picture by its box, so a page that redraws under it does not fail the capture."""
    box = page.locator(selector).first.bounding_box()
    sx, sy = page.evaluate("[window.scrollX, window.scrollY]")
    page.screenshot(path=str(path), full_page=True, clip={"x": box["x"] + sx, "y": box["y"] + sy,
                                                          "width": max(box["width"], 1), "height": max(box["height"], 1)})


def test_homes_level_control_and_settings_say_the_same_thing_and_the_level_is_kept(chrome, server, tmp_path):
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="beginner", cookies=jar)
    try:
        home(page, server)
        home_says = _norm(page.get_attribute("[data-v2-lc] .lc-i", "title"))
        _shot(page, "[data-v2-lc]", tmp_path / "f06-home-control.png")
        page.click("[data-v2-level='advanced']")
        page.wait_for_selector("[data-v2-level='advanced'][aria-pressed='true']")
        page.goto(server["base"] + "/#/settings", wait_until="domcontentloaded")
        page.wait_for_selector("#hm-h", timeout=30000)
        section = _norm(page.inner_text("section[aria-labelledby='hm-h']"))
        _shot(page, "section[aria-labelledby='hm-h']", tmp_path / "f06-settings-section.png")
        # both say: the words, and how much the screen shows; and that no figure, caveat or disclosure changes
        assert "words" in home_says and "how much each screen shows" in home_says
        assert "never a figure, a caveat or a disclosure" in home_says.lower()
        assert "worded for this level" in section and "also sets how much the screen shows" in section
        assert "never changes a figure, a source, a caveat or a disclosure" in section.lower()
        assert "does not change what a page shows" not in section
        # the slider shows the level chosen on Home, and a reload keeps it
        page.wait_for_selector("#set-lvl-in")
        assert page.input_value("#set-lvl-in") == "3"
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#set-lvl-in", timeout=30000)
        assert page.input_value("#set-lvl-in") == "3"
        assert (tmp_path / "f06-home-control.png").stat().st_size > 0 and (tmp_path / "f06-settings-section.png").stat().st_size > 0
        assert page.errors == [], page.errors
    finally:
        ctx.close()


# ----------------------------------------------------------------------------- Q01

def _post_sub(server, uid, created, cancel_at=None, cancel_flag=False, end=None):
    obj = {"object": "subscription", "id": "sub_e2e_audit", "customer": "cus_e2e_audit", "status": "active",
           "metadata": {"user_id": uid}, "cancel_at_period_end": cancel_flag, "cancel_at": cancel_at,
           "items": {"data": [{"price": {"id": PRO}, "current_period_end": end}]}}
    ev = {"id": "evt_e2e_audit_{}".format(time.time_ns()), "type": "customer.subscription.updated", "livemode": False,
          "created": created, "data": {"object": obj}}
    body, headers = signed(ev, secret=WHSEC)
    req = urllib.request.Request(server["base"] + "/api/billing/webhook", data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["result"]


def _settings(page, server):
    page.goto("about:blank")                       # a hash-only change would not reload, and the page would keep the old plan
    page.goto(server["base"] + "/#/settings", wait_until="domcontentloaded")
    page.wait_for_selector("[data-v2-account].avatar", timeout=30000)
    page.wait_for_selector("#pl-h", timeout=30000)
    page.wait_for_function("() => !document.body.innerText.includes('Checking plans...')", timeout=30000)
    return _norm(page.inner_text("section[aria-labelledby='pl-h']"))


@pytest.mark.parametrize("server", [BILLING_ON], indirect=True)
def test_a_scheduled_cancellation_shows_its_date_and_a_resumption_clears_it(chrome, server):
    email, jar = make_account(server)
    with sqlite3.connect(str(server["db"])) as c:
        uid = c.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()[0]
    t = int(time.time())
    period_end = t + 30 * DAY
    cancel_at = t + 12 * DAY
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    try:
        assert _post_sub(server, uid, t, end=period_end) == "pro"
        before = _settings(page, server)
        assert "Pro" in before and "Cancellation scheduled" not in before and "will not renew" not in before
        # Stripe's way of scheduling it from the portal: cancel_at set, cancel_at_period_end false
        assert _post_sub(server, uid, t + 5, cancel_at=cancel_at, end=period_end) == "pro"
        scheduled = _settings(page, server)
        when = time.strftime("%b %-d", time.gmtime(cancel_at))
        assert "Cancellation scheduled" in scheduled and "will not renew" in scheduled, scheduled
        assert when in scheduled, (when, scheduled)
        assert "Paid through" in scheduled                    # twelve days short of the period end: two dates
        assert "Manage billing" in scheduled and "Pro" in scheduled
        # resumed in the portal: both cleared, the plan is still the paid one
        assert _post_sub(server, uid, t + 10, end=period_end) == "pro"
        after = _settings(page, server)
        assert "Cancellation scheduled" not in after and "will not renew" not in after and "Paid through" not in after
        assert "Pro" in after and "Manage billing" in after
        assert page.errors == [], page.errors
    finally:
        ctx.close()


# ----------------------------------------------------------------------------- Q02

@pytest.mark.parametrize("server", [{"ADMIN_EMAILS": OWNER}], indirect=True)
def test_the_owner_page_reconciles_the_headline_with_the_table_and_defines_a_question_twice(chrome, server):
    body = json.dumps({"first_name": "Site", "last_name": "Owner", "email": OWNER, "password": PASSWORD,
                       "confirm_password": PASSWORD}).encode()
    req = urllib.request.Request(server["base"] + "/api/auth/register", data=body,
                                 headers={"Content-Type": "application/json", "X-Forwarded-For": "198.51.100.201"})
    with urllib.request.urlopen(req, timeout=15) as r:
        cookies = r.headers.get_all("Set-Cookie") or []
    _, reader_jar = make_account(server)
    jar = [{"name": raw.partition("=")[0].strip(), "value": raw.partition("=")[2].split(";", 1)[0], "url": server["base"]}
           for raw in cookies]
    now = time.time()
    with sqlite3.connect(str(server["db"])) as c:
        c.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (OWNER,))
        uid = c.execute("SELECT id FROM users WHERE email != ? LIMIT 1", (OWNER,)).fetchone()[0]
        owner_id = c.execute("SELECT id FROM users WHERE email = ?", (OWNER,)).fetchone()[0]
        at = lambda secs: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - secs))      # noqa: E731
        for kind, secs, who in (("chat", 3600, uid), ("earnings_brief", 2 * DAY, uid), ("scan", 10 * DAY, uid),
                                ("investigation", 20 * DAY, None), ("portfolio", 3 * DAY, uid), ("chat", 60, owner_id)):
            c.execute("INSERT INTO milo_questions (at, user_id, kind) VALUES (?,?,?)", (at(secs), who, kind))
        # one of them has a usage event, as the chat route writes; the headline must not depend on that
        c.execute("INSERT INTO usage_event (occurred_at, actor_kind, actor_ref, user_id, event, symbol, source_screen, level) "
                  "VALUES (?,?,?,?,?,?,?,?)", (at(3600), "signed_in", uid, uid, "milo_question", None, None, None))
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    try:
        page.goto(server["base"] + "/#/metrics", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-q-total]", timeout=30000)
        page.wait_for_selector("[data-v2-signals]", timeout=30000)
        row = lambda sel: [_norm(x) for x in page.eval_on_selector_all(sel + " td", "els => els.map(e => e.textContent)")]   # noqa: E731
        headline = row("[data-v2-signals] tbody tr:nth-child(3)")          # Asked Milo a question: today, 7, 30, all
        assert _norm(page.inner_text("[data-v2-signals] tbody tr:nth-child(3) th")) == "Asked Milo a question"
        total = row("[data-v2-q-total]")                                   # All questions: 7, 30, all
        assert headline[1] == total[0] == "3" and headline[2] == total[1] == "5", (headline, total)
        defs = [_norm(x) for x in page.eval_on_selector_all("[data-v2-q-definition]", "els => els.map(e => e.textContent)")]
        assert len(defs) == 2 and defs[0] == defs[1] and defs[0].startswith("A question to Milo is one request"), defs
        assert "Readers who asked counts chat and deep research before" in page.inner_text("#main")
        assert page.errors == [], page.errors
    finally:
        ctx.close()

"""The phone bar's Lists tab with unread alerts passes axe at 390.

Found on the evaluation copy (2026-11-23): once a reader had unread alerts, the tab's name ("Lists. 3 unread alerts")
did not contain the count it shows, and axe-core 4.14 reported label-content-name-mismatch on every screen at phone
width. The hits are seeded in the journey's own database; nothing reaches a feed."""

from __future__ import annotations

import sqlite3
import uuid

from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import PHONE, open_page
from tests.e2e.test_pass3_investor_journeys import _axe, _quiz_done, _user_id


def _unread_hits(server, email, n=3):
    uid = _user_id(server, email)
    with sqlite3.connect(str(server["db"])) as c:
        wid = str(uuid.uuid4())
        c.execute("INSERT INTO watches (id,user_id,symbol,kind,params,active,created_at,updated_at) "
                  "VALUES (?,?,?,?,?,1,'2026-11-23T00:00:00Z','2026-11-23T00:00:00Z')", (wid, uid, "AAPL", "price_below", '{"level": 100000}'))
        for i in range(n):
            c.execute("INSERT INTO watch_hits (id,user_id,watch_id,symbol,kind,title,created_at,seen,dedupe_key) "
                      "VALUES (?,?,?,?,?,?,?,0,?)", (str(uuid.uuid4()), uid, wid, "AAPL", "price_below", "AAPL: Price falls below",
                                                     "2026-11-23T20:0%d:00Z" % i, "k%d" % i))


def test_the_phone_bars_lists_tab_names_its_unread_count_and_passes_axe(chrome, server):
    email, jar = make_account(server)
    _quiz_done(server, email)
    _unread_hits(server, email)
    ctx, page = open_page(chrome, server, level="beginner", viewport=PHONE, cookies=jar)
    try:
        page.goto(server["base"] + "/#/settings", wait_until="domcontentloaded")
        page.wait_for_selector(".tabbar [data-v2-tab='lists'] .tab-n", timeout=30000)
        tab = page.locator(".tabbar [data-v2-tab='lists']")
        shown = tab.locator(".tab-n").inner_text().strip()
        name = page.evaluate("() => { const t = document.querySelector(\".tabbar [data-v2-tab='lists']\"); return [t.getAttribute('aria-label'), (t.querySelector('.tab-said') || {}).textContent]; }")
        assert name[0] is None and "unread" in (name[1] or ""), (name, shown)
        violations = [v for v in _axe(page) if v["id"] == "label-content-name-mismatch"]
        assert violations == [], violations
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()

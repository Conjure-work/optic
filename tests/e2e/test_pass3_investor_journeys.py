"""Round three's Investor mode in a real browser (Pass 3, 2026-11-23): Watchlist and alerts in one place, Portfolio with
one meaning, the Markets calendar, the first visit at Beginner, the owner report, the sign-up questions, the saved line
beside the layout form, and the accessibility items (axe at WCAG 2.1 A and AA, desktop and phone, and the keyboard).

Market answers the pages need come from labelled fixtures at the page's own API boundary, as in the Pass 1 and Pass 2
journeys; every account is made by the journey itself; preconditions are seeded through the API or the database."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import uuid

import pytest

from tests.e2e.conftest import PASSWORD, make_account
from tests.e2e.test_pass1_journeys import DESKTOP, PHONE, home, open_page, pressed
from tests.e2e.visual_fixtures import _json, route_company, route_home

TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
OWNER = "owner-e2e@example.com"


def _axe(page):
    from axe_playwright_python.sync_playwright import Axe
    result = Axe().run(page, options={"runOnly": {"type": "tag", "values": TAGS}})
    return [{"id": v["id"], "impact": v["impact"], "nodes": [n["target"] for n in v["nodes"]][:4]} for v in result.response.get("violations", [])]


def _db(server, sql, args=()):
    with sqlite3.connect(str(server["db"])) as c:
        c.row_factory = sqlite3.Row
        cur = c.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]


def _user_id(server, email):
    return _db(server, "SELECT id FROM users WHERE email = ?", (email,))[0]["id"]


def _quiz_done(server, email):
    """Mark the sign-up questions as answered, so a journey about something else is not offered them."""
    uid = _user_id(server, email)
    with sqlite3.connect(str(server["db"])) as c:
        c.execute("INSERT INTO user_preferences (user_id, updated_at) VALUES (?, '2026-11-23T00:00:00Z') ON CONFLICT(user_id) DO NOTHING", (uid,))
        c.execute("UPDATE user_preferences SET level_quiz = ? WHERE user_id = ?",
                  (json.dumps({"shown": True, "suggested": None, "outcome": "skipped", "at": "2026-11-23"}), uid))


def _list_with(server, email, *symbols):
    uid = _user_id(server, email)
    now = "2026-11-23T00:00:00Z"
    with sqlite3.connect(str(server["db"])) as c:
        row = c.execute("SELECT id FROM watchlists WHERE user_id = ?", (uid,)).fetchone()
        if row:
            wid = row[0]
        else:
            wid = str(uuid.uuid4())
            c.execute("INSERT INTO watchlists (id,user_id,name,position,created_at,updated_at,owner_id) VALUES (?,?,?,?,?,?,?)",
                      (wid, uid, "Watchlist", 0, now, now, uid))
        for i, s in enumerate(symbols):
            c.execute("INSERT OR IGNORE INTO watchlist_items (id,watchlist_id,symbol,position,created_at) VALUES (?,?,?,?,?)",
                      (str(uuid.uuid4()), wid, s, i, now))


def _watch(server, email, symbol):
    uid = _user_id(server, email)
    now = "2026-11-23T00:00:00Z"
    with sqlite3.connect(str(server["db"])) as c:
        c.execute("INSERT INTO watches (id,user_id,symbol,kind,params,active,created_at,updated_at) VALUES (?,?,?,?,?,1,?,?)",
                  (str(uuid.uuid4()), uid, symbol, "price_above", json.dumps({"level": 500.0}), now, now))


BOOK = {"alerts": [{"id": 1, "ticker": "AAPL", "title": "Opened a balanced position (test data)", "kind": "open", "kind_label": "Position opened",
                    "created_at": "2026-11-23T15:00:00Z", "seen": 0, "payload": {}, "urgency": "normal"}],
        "kinds": {"open": {"label": "Position opened"}}, "unseen": None,
        "delivery": {"enabled": False, "blockers": [], "note": "These alerts are shown in Optic; email delivery is not set up for readers."}}


def route_book(page):
    page.route(re.compile(r".*/api/alerts(\?.*)?$"), lambda r: _json(r, BOOK) if r.request.method == "GET" else r.fallback())


# ------------------------------------------------------------------ 1. watchlists and alerts in one place

def test_watchlist_rows_carry_each_names_alerts_of_every_kind_and_alerts_is_a_view_of_watchlist(chrome, server):
    email, jar = make_account(server)
    _quiz_done(server, email)
    _list_with(server, email, "AAPL", "MSFT")
    _watch(server, email, "AAPL")
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    route_home(page)
    route_book(page)
    try:
        page.goto(server["base"] + "/#/watchlist", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-wl-alerts='AAPL']", timeout=20000)
        words = page.inner_text("[data-v2-wl-alerts='AAPL']")
        assert "1 alert" in words and "1 from Optic's book" in words, words
        assert page.locator("[data-v2-wl-alerts='MSFT']").count() == 0
        # the row's accessible name is its own words (axe label-content-name-mismatch), so the alerts are in it
        label = page.evaluate("() => document.querySelector(\"[data-v2-company='AAPL']\").innerText")
        assert "1 from Optic's book" in label and "Open the detail" in page.inner_text("[data-v2-company='AAPL'] .sr"), label
        # #/alerts lands on the Alerts view of the same place, headed Watchlist, with all three kinds gathered
        page.goto(server["base"] + "/#/alerts", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-all-list]", timeout=20000)
        assert page.inner_text("h1").startswith("Watchlist")
        tabs = page.eval_on_selector_all(".tabs a", "els => els.map(e => e.textContent.trim())")
        assert tabs == ["Watchlist", "Alerts"]
        kinds = page.eval_on_selector_all("[data-v2-all-item]", "els => els.map(e => e.dataset.v2AllItem)")
        assert "yours" in kinds and "optic" in kinds, kinds
        page.click("[data-v2-all-kind='optic']")
        page.wait_for_function("() => [...document.querySelectorAll('[data-v2-all-item]')].every(e => e.dataset.v2AllItem === 'optic')")
        # the three stores are untouched: the watch is still the one row, the book was only read
        assert len(_db(server, "SELECT * FROM watches")) == 1
        assert not page.errors
    finally:
        ctx.close()


def test_a_guests_lists_stay_in_the_browser(chrome, server):
    ctx, page = open_page(chrome, server, level="beginner")
    route_home(page)
    try:
        page.goto(server["base"] + "/#/watchlist", wait_until="domcontentloaded")
        page.fill("[data-v2-wl-add]", "MSFT")
        page.press("[data-v2-wl-add]", "Enter")
        page.wait_for_function("() => (localStorage.getItem('optic.watchlists.v1') || '').includes('MSFT')", timeout=15000)
        assert _db(server, "SELECT * FROM watchlist_items") == []
        page.goto(server["base"] + "/#/alerts", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-all-list], #h-all", timeout=15000)
        assert not page.errors
    finally:
        ctx.close()


# ------------------------------------------------------------------ 2. Portfolio with one meaning

PAPER = {"open": [{"id": "p1", "ticker": "AAPL", "qty": 10, "entry_price": 200, "instrument": "shares", "direction": "long", "entry_at": "2026-11-20T15:00:00Z"},
                  {"id": "p2", "ticker": "MSFT", "qty": 5, "entry_price": 400, "instrument": "shares", "direction": "long", "entry_at": "2026-11-20T15:00:00Z"}], "closed": []}
RISK = {"available": True, "diversification_ratio": 1.21, "effective_positions": 1.8, "names": 2, "gross_exposure": 4000,
        "verdict": "Test data: two names that move much like one."}


def test_portfolio_is_the_readers_book_first_and_the_diversification_follows_the_book_in_view(chrome, server):
    ctx, page = open_page(chrome, server, level="beginner", store={"optic.paper.v1": json.dumps(PAPER)})
    asked = []
    def risk(route):
        asked.append((route.request.method, route.request.url, route.request.post_data))
        _json(route, dict(RISK, names=2 if route.request.method == "POST" else 7))
    page.route(re.compile(r".*/api/portfolio-risk.*"), risk)
    try:
        page.goto(server["base"] + "/#/portfolio", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-pf-div='paper']", timeout=20000)
        line = page.inner_text("[data-v2-pf-line]")
        assert line.startswith("Your book: your Paper Desk, 2 open") and "Optic's model portfolios are below" in line, line
        heads = page.eval_on_selector_all("#main h2", "els => els.map(e => e.textContent.trim())")
        assert heads.index("Your Paper Desk") < heads.index("Optic's model portfolios"), heads
        assert page.locator("a[href='#/retirement']").count() >= 1
        assert asked[0][0] == "POST" and json.loads(asked[0][2])["positions"][0]["ticker"] == "AAPL"
        page.click("[data-v2-pf-book='balanced']")
        page.wait_for_selector("[data-v2-pf-div='balanced']", timeout=20000)
        assert any(m == "GET" and "book=balanced" in u for m, u, _ in asked)
        assert "of 7 held" in page.inner_text("[data-v2-pf-div='balanced']")
        assert page.inner_text("h1").startswith("Portfolio")
        rail = page.eval_on_selector_all(".rail-nav a.rail-row", "els => els.map(e => e.textContent.trim())")
        assert "Portfolio" in rail and "Positions" not in rail
        assert not page.errors
    finally:
        ctx.close()


def test_a_linked_brokerage_comes_first_and_the_paper_desk_stays_beside_it(chrome, server):
    email, jar = make_account(server)
    _quiz_done(server, email)
    ctx, page = open_page(chrome, server, level="beginner", cookies=jar, store={"optic.paper.v1": json.dumps(PAPER)})
    page.route(re.compile(r".*/api/brokerage/portfolio(\?.*)?$"), lambda r: _json(r, {"available": True, "holdings": [
        {"symbol": "VOO", "quantity": 3, "price": 500.0, "kind": "equity"}, {"symbol": "AAPL", "quantity": 4, "price": 230.0, "kind": "equity"}]}))
    page.route(re.compile(r".*/api/portfolio-risk.*"), lambda r: _json(r, RISK))
    try:
        page.goto(server["base"] + "/#/portfolio", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-pf-div='brokerage']", timeout=20000)
        heads = page.eval_on_selector_all("#main h2", "els => els.map(e => e.textContent.trim())")
        assert heads.index("Your brokerage") < heads.index("Your Paper Desk") < heads.index("Optic's model portfolios"), heads
        # a guest's Paper Desk on this browser is not the account's until the reader brings it in (core/device.js)
        assert page.inner_text("[data-v2-pf-line]").startswith("Your books: your linked brokerage, then your Paper Desk")
        assert not page.errors
    finally:
        ctx.close()


@pytest.mark.parametrize("server", [{"OPTIC_SEPARATE_ALERTS_AND_MODELS": "on"}], indirect=True)
def test_the_setting_restores_the_old_separate_pages(chrome, server):
    ctx, page = open_page(chrome, server, level="beginner")
    try:
        page.goto(server["base"] + "/#/portfolio", wait_until="domcontentloaded")
        page.wait_for_selector("details.whose", timeout=20000)   # Optic's model books, as before round three
        assert page.locator("[data-v2-pf-line]").count() == 0
        page.goto(server["base"] + "/#/alerts", wait_until="domcontentloaded")
        page.wait_for_selector("#al-body", timeout=15000)
        page.wait_for_function("() => document.querySelector('h1') && document.querySelector('h1').textContent.startsWith('Alerts')")
        assert not page.errors
    finally:
        ctx.close()


# ------------------------------------------------------------------ 3. the Markets calendar

CAL = {"days": [
    {"date": "2026-11-25", "weekday": "Wednesday", "status": "open", "opens": "2026-11-25T09:30:00-05:00", "closes": "2026-11-25T16:00:00-05:00"},
    {"date": "2026-11-26", "weekday": "Thursday", "status": "holiday", "name": "Thanksgiving Day", "note": "US stock markets are closed for Thanksgiving Day."},
    {"date": "2026-11-27", "weekday": "Friday", "status": "early_close", "name": "the day after Thanksgiving", "opens": "2026-11-27T09:30:00-05:00", "closes": "2026-11-27T13:00:00-05:00"},
    {"date": "2026-11-28", "weekday": "Saturday", "status": "weekend"}],
    "futures_note": "Futures holidays are not modelled here: the CME's own holiday hours differ from the stock exchanges', so this calendar covers US stock trading only.",
    "time_zone_of_record": "America/New_York",
    "releases": {"available": True, "events": [{"title": "Consumer Price Index (test data)", "at": "2026-12-10T08:30:00-05:00", "impact": "high"}]}}


def test_the_calendar_shows_a_holiday_and_a_half_day_in_the_readers_time_zone(chrome, server):
    ctx, page = open_page(chrome, server, level="beginner", store={"optic.timezone": "Europe/London"})
    page.route(re.compile(r".*/api/markets/calendar.*"), lambda r: _json(r, CAL))
    page.route(re.compile(r".*/api/earnings-week.*"), lambda r: _json(r, {"available": True, "week_label": "Week of Nov 23 (test data)", "total": 1,
                                                                            "days": [{"date": "2026-11-24", "day": "Tue", "day_number": 24, "count": 1, "rows": [{"ticker": "DELL"}]}]}))
    try:
        page.goto(server["base"] + "/#/calendar", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-cal-sessions]", timeout=20000)
        rows = page.eval_on_selector_all("[data-v2-cal-sessions] tbody tr", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())")
        assert any("Closed, Thanksgiving Day" in r for r in rows), rows
        assert any("Early close: 2:30 pm to 6:00 pm (the day after Thanksgiving)" in r for r in rows), rows
        assert any("Open 2:30 pm to 9:00 pm" in r for r in rows), rows
        assert "Futures holidays are not modelled" in page.inner_text("[data-v2-cal-futures]")
        assert "Consumer Price Index" in page.inner_text("[data-v2-cal-releases]")
        assert "DELL" in page.inner_text("[data-v2-cal-earnings]")
        assert page.locator("a[href='#/read']").count() >= 1
        assert not page.errors
    finally:
        ctx.close()


# ------------------------------------------------------------------ 4. the first visit at Beginner

@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_a_first_visit_lands_on_home_at_beginner_with_the_band_and_the_card(chrome, server, viewport):
    ctx, page = open_page(chrome, server, viewport=viewport, onboarded=False)
    try:
        home(page, server)
        assert pressed(page) == "beginner"
        page.wait_for_selector("#ws-new")                       # the onboarding band, "New to Optic? Three ways to start"
        assert page.evaluate("() => localStorage.getItem('optic.knowledge.v1')") in (None, "beginner")
        assert not page.errors
    finally:
        ctx.close()


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_a_signed_in_reader_keeps_the_accounts_level_on_a_new_browser(chrome, server, viewport):
    email, jar = make_account(server)
    _quiz_done(server, email)
    with sqlite3.connect(str(server["db"])) as c:
        c.execute("UPDATE user_preferences SET knowledge_level = 'advanced' WHERE user_id = ?", (_user_id(server, email),))
    ctx, page = open_page(chrome, server, viewport=viewport, cookies=jar)
    try:
        home(page, server)
        page.wait_for_selector("[data-v2-account].avatar")
        page.wait_for_function("() => document.querySelector(\"[data-v2-lc] [aria-pressed='true']\").dataset.v2Level === 'advanced'", timeout=15000)
        assert not page.errors
    finally:
        ctx.close()


# ------------------------------------------------------------------ 5. the owner report

def _register(server, email):
    import urllib.request
    body = json.dumps({"first_name": "Site", "last_name": "Owner", "email": email, "password": PASSWORD, "confirm_password": PASSWORD}).encode()
    req = urllib.request.Request(server["base"] + "/api/auth/register", data=body, headers={"Content-Type": "application/json", "X-Forwarded-For": "198.51.100.200"})
    with urllib.request.urlopen(req, timeout=15) as r:
        cookies = r.headers.get_all("Set-Cookie") or []
    with sqlite3.connect(str(server["db"])) as c:
        c.execute("UPDATE users SET email_verified = 1 WHERE email = ?", (email,))
    return [{"name": raw.partition("=")[0].strip(), "value": raw.partition("=")[2].split(";", 1)[0], "url": server["base"]} for raw in cookies]


@pytest.mark.parametrize("server", [{"ADMIN_EMAILS": OWNER}], indirect=True)
def test_the_owner_report_reads_counts_by_week_and_names_the_group_it_read(chrome, server):
    jar = _register(server, OWNER)
    _quiz_done(server, OWNER)
    now = time.time()
    rows = []
    for i in range(700):   # about the evaluation copy's size
        at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - i * 3600))
        ev = ("visit", "home_stock_open", "milo_question")[i % 3]
        rows.append((at, "visitor", "v-%032d" % (i % 40), None, ev, "AAPL" if ev == "home_stock_open" else None, ("home", "overview", "financials")[i % 3], ("beginner", "intermediate", "advanced")[i % 3]))
    with sqlite3.connect(str(server["db"])) as c:
        c.executemany("INSERT INTO usage_event (occurred_at, actor_kind, actor_ref, user_id, event, symbol, source_screen, level) VALUES (?,?,?,?,?,?,?,?)", rows)
    ctx, page = open_page(chrome, server, level="advanced", cookies=jar)
    try:
        t = time.perf_counter()
        with page.expect_response(lambda r: "/api/admin/owner-report" in r.url, timeout=20000) as got:
            page.goto(server["base"] + "/#/owner-report", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-or-signals]", timeout=20000)
        took = time.perf_counter() - t
        assert got.value.status == 200 and took < 2.0, took
        cells = page.eval_on_selector_all("[data-v2-or-signals] tbody tr", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())")
        assert any(c.startswith("Opened a stock from Home") for c in cells), cells
        assert page.locator("[data-v2-or-levels] tbody tr").count() == 3
        assert page.locator("[data-v2-or-weeks] tbody tr").count() == 12
        text = page.inner_text("#main")
        assert "%" not in text, "counts only, never a percentage"
        assert page.get_attribute("[data-v2-or-group]", "data-v2-or-group") == "everyone"
        # the group in the address is read, said, and today every count is everyone's
        page.goto(server["base"] + "/#/owner-report?owner_kind=org&owner_id=team-1", wait_until="domcontentloaded")
        page.wait_for_selector("text=Reading one group is not built yet", timeout=20000)
        for vp in (DESKTOP, PHONE):
            page.set_viewport_size(vp)
            page.wait_for_load_state("networkidle")
            violations = _axe(page)
            assert violations == [], json.dumps(violations, indent=1)
        # the Metrics page lists the modes /api/health reports
        page.goto(server["base"] + "/#/metrics", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-mode='investor_pages']", timeout=20000)
        assert "one place, two views" in page.inner_text("[data-v2-mode='investor_pages']")
        assert not page.errors
    finally:
        ctx.close()


def test_the_owner_report_is_refused_to_a_reader_who_is_not_the_owner(chrome, server):
    email, jar = make_account(server)
    _quiz_done(server, email)
    ctx, page = open_page(chrome, server, level="beginner", cookies=jar)
    try:
        page.goto(server["base"] + "/#/owner-report", wait_until="domcontentloaded")
        page.wait_for_selector("text=This is for the owner of this site", timeout=15000)
        assert page.locator("[data-v2-or-signals]").count() == 0
    finally:
        ctx.close()


# ------------------------------------------------------------------ 6. the sign-up questions

def _sign_up_through_the_form(page, server, email):
    page.goto(server["base"] + "/#/signin?mode=up", wait_until="domcontentloaded")
    page.wait_for_selector("[data-v2-auth='up']")
    page.fill("[data-v2-auth='up'] input[name=first_name]", "New")
    page.fill("[data-v2-auth='up'] input[name=last_name]", "Reader")
    page.fill("[data-v2-auth='up'] input[name=email]", email)
    page.fill("[data-v2-auth='up'] input[name=password]", PASSWORD)
    page.fill("[data-v2-auth='up'] input[name=confirm]", PASSWORD)
    page.click("[data-v2-auth='up'] button[type=submit]")


def test_the_sign_up_form_leads_to_the_questions_and_accepting_writes_only_the_level(chrome, server):
    email = "quiz{}@example.com".format(int(time.time() * 1000) % 10 ** 9)
    ctx, page = open_page(chrome, server)      # no level chosen on this browser, so none is sent to the new account
    try:
        _sign_up_through_the_form(page, server, email)
        page.wait_for_selector("[data-v2-lq-form]", timeout=20000)
        assert page.url.split("#", 1)[1].startswith("/welcome")
        qs = page.locator(".lq-q").count()
        assert 5 <= qs <= 8
        # Skip is as large as Continue
        c = page.locator("[data-v2-lq-form] button[type=submit]").bounding_box()
        s = page.locator("[data-v2-lq-skip]").bounding_box()
        assert abs(c["width"] - s["width"]) <= 1 and abs(c["height"] - s["height"]) <= 1, (c, s)
        # the keyboard: answer every question with the arrow keys, then Continue
        page.focus(".lq-q input[type=radio]")
        for i in range(qs):
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowDown")
            if i < qs - 1:
                page.keyboard.press("Tab")
        page.focus("[data-v2-lq-form] button[type=submit]")
        page.keyboard.press("Enter")
        page.wait_for_selector("[data-v2-lq-why]", timeout=15000)
        suggested = page.get_attribute("[data-v2-lq-result]", "data-v2-lq-result")
        assert suggested in ("beginner", "intermediate", "advanced")
        assert page.evaluate("() => document.activeElement && document.activeElement.id") == "lq-sug"
        uid = _user_id(server, email)
        assert _db(server, "SELECT knowledge_level FROM user_preferences WHERE user_id = ?", (uid,))[0]["knowledge_level"] is None
        page.focus("[data-v2-lq-accept]")
        page.keyboard.press("Enter")
        page.wait_for_function("() => !location.hash.startsWith('#/welcome')", timeout=15000)
        row = _db(server, "SELECT knowledge_level, level_quiz FROM user_preferences WHERE user_id = ?", (uid,))[0]
        assert row["knowledge_level"] == suggested and json.loads(row["level_quiz"])["outcome"] == "accepted"
        # no answer is in any table
        with sqlite3.connect(str(server["db"])) as cdb:
            tables = [r[0] for r in cdb.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            dump = json.dumps([[list(map(str, r)) for r in cdb.execute('SELECT * FROM "{}"'.format(t))] for t in tables])
        for word in ('"1_5"', '"sheets"', '"indicators"', "One to five years", "Planning and tracking trades", "Spreadsheets or a stock screener",
                     "Indicators, volume and patterns", "Fast answers with the figures"):
            assert word not in dump, word
        # and the level stays changeable on Home
        home(page, server)
        other = "advanced" if suggested != "advanced" else "beginner"
        page.click(f"[data-v2-lc] [data-v2-level='{other}']")
        page.wait_for_function(f"() => document.querySelector('[data-v2-level-now]').dataset.v2LevelNow === '{other}'")
        assert not page.errors
    finally:
        ctx.close()


def test_an_account_made_another_way_is_offered_the_questions_once_on_a_band(chrome, server):
    """Google, Apple and passkey accounts never see the sign-up form (refinement A4): their first signed-in visit offers
    the questions on a band above the page. The account here is made through the API, which is that same state."""
    email, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="beginner", cookies=jar)
    try:
        home(page, server)
        page.wait_for_selector("[data-v2-lq-offer]", timeout=15000)
        assert page.locator("[data-v2-lq-answer]").bounding_box()["height"] == page.locator("[data-v2-lq-dismiss]").bounding_box()["height"]
        page.click("[data-v2-lq-dismiss]")
        page.wait_for_selector("[data-v2-lq-offer]", state="detached")
        page.reload(wait_until="domcontentloaded")
        home(page, server)
        page.wait_for_timeout(500)
        assert page.locator("[data-v2-lq-offer]").count() == 0, "offered once"
        assert json.loads(_db(server, "SELECT level_quiz FROM user_preferences WHERE user_id = ?", (_user_id(server, email),))[0]["level_quiz"])["outcome"] == "skipped"
        assert not page.errors
    finally:
        ctx.close()


# ------------------------------------------------------------------ 7. the saved line beside the layout form

def test_a_saved_layout_says_so_beside_the_form_until_the_next_change(chrome, server):
    email, jar = make_account(server)
    _quiz_done(server, email)
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar)
    try:
        home(page, server)
        page.wait_for_selector("[data-v2-account].avatar")
        page.click("[data-ws-edit]")
        page.wait_for_selector("#ws-named-name")
        page.fill("#ws-named-name", "Morning check")
        page.click("[data-ws-named] button[type=submit]")
        page.wait_for_function("() => (document.querySelector('[data-ws-named-said]') || {}).textContent === 'Saved: Morning check is on your account.'", timeout=15000)
        page.type("#ws-named-name", "x")
        page.wait_for_function("() => document.querySelector('[data-ws-named-said]').textContent === ''")
        assert not page.errors
    finally:
        ctx.close()


# ------------------------------------------------------------------ 8. accessibility: the changed screens at both widths

REVISIONS = {"available": True, "note": "Test data.", "analysts_up_30d": 3, "analysts_down_30d": 1, "caveat": "Invented for a browser test.",
             "rows": [{"label": lbl, "current": 1.9 + i / 10, "chg_30d_pct": 1.2, "chg_90d_pct": -0.4, "analysts_up_30d": 3, "analysts_down_30d": 1}
                      for i, lbl in enumerate(["Current quarter", "Next quarter", "Current year", "Next year"])]}


def _signed_in_page(chrome, server, viewport):
    email, jar = make_account(server)
    _quiz_done(server, email)
    _list_with(server, email, "AAPL")
    return open_page(chrome, server, level="beginner", viewport=viewport, cookies=jar)


SCREENS = {
    "watchlist": ("/#/watchlist", "[data-v2-wl-alerts='AAPL'], .wl-rows"),
    "alerts": ("/#/alerts", "[data-v2-all-list]"),
    "portfolio": ("/#/portfolio", "[data-v2-pf-div]"),
    "calendar": ("/#/calendar", "[data-v2-cal-sessions]"),
    "welcome": ("/#/welcome", "[data-v2-lq-form]"),
}


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
@pytest.mark.parametrize("screen", sorted(SCREENS))
def test_the_changed_screens_have_no_axe_violation(chrome, server, viewport, screen):
    ctx, page = _signed_in_page(chrome, server, viewport)
    route_home(page)
    route_book(page)
    page.route(re.compile(r".*/api/markets/calendar.*"), lambda r: _json(r, CAL))
    page.route(re.compile(r".*/api/earnings-week.*"), lambda r: _json(r, {"available": True, "week_label": "Test week", "total": 0, "days": []}))
    page.route(re.compile(r".*/api/portfolio-risk.*"), lambda r: _json(r, RISK))
    try:
        if screen == "portfolio":
            page.add_init_script("localStorage.setItem('optic.paper.v1', %s)" % json.dumps(json.dumps(PAPER)))
        path, sel = SCREENS[screen]
        page.goto(server["base"] + path, wait_until="domcontentloaded")
        page.wait_for_selector(sel, timeout=20000)
        page.wait_for_load_state("networkidle")
        violations = _axe(page)
        assert violations == [], json.dumps(violations, indent=1)
        assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), "no sideways scroll"
        assert not page.errors
    finally:
        ctx.close()


def test_the_earnings_revisions_table_is_a_named_keyboard_stop_at_phone_width(chrome, server):
    from tests.e2e.visual_fixtures import earnings_payload
    ctx, page = open_page(chrome, server, level="advanced", viewport=PHONE)
    route_company(page)
    page.route(re.compile(r".*/api/earnings/AAPL(\?.*)?$"), lambda r: _json(r, dict(earnings_payload(), revisions=REVISIONS)))
    try:
        page.goto(server["base"] + "/#/AAPL/earnings", wait_until="domcontentloaded")
        page.wait_for_selector("#rv-h", timeout=20000)
        box = page.locator("#rv-h ~ .tscroll").first
        assert box.get_attribute("tabindex") == "0" and box.get_attribute("aria-label") == "Estimate revisions by period, table"
        assert page.locator("#rv-h ~ .tscroll caption").count() == 1
        box.focus()
        assert page.evaluate("() => document.activeElement.getAttribute('aria-label')") == "Estimate revisions by period, table"
        page.keyboard.press("ArrowRight")
        page.wait_for_load_state("networkidle")
        violations = _axe(page)
        assert violations == [], json.dumps(violations, indent=1)
        assert not page.errors
    finally:
        ctx.close()


def test_the_failure_toast_meets_aa_contrast_in_the_dark_theme(chrome, server):
    ctx, page = open_page(chrome, server, level="beginner", store={"optic.theme": "charcoal"})
    try:
        home(page, server)
        got = page.evaluate("""async () => {
          const el = document.createElement('div'); el.className = 'toast show'; el.dataset.kind = 'bad'; el.textContent = 'Test'; document.body.appendChild(el);
          const cs = getComputedStyle(el); const c = document.createElement('canvas').getContext('2d');
          const hex = (v) => { c.fillStyle = '#000'; c.fillStyle = v; return c.fillStyle; };
          const out = { bg: hex(cs.backgroundColor), fg: hex(cs.color), theme: document.documentElement.dataset.theme || '' }; el.remove(); return out; }""")
        def lum(hx):
            r, g, b = [int(hx[i:i + 2], 16) / 255 for i in (1, 3, 5)]
            f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
        a, b = sorted([lum(got["bg"]), lum(got["fg"])], reverse=True)
        assert got["theme"] == "charcoal" and (a + 0.05) / (b + 0.05) >= 4.5, got
    finally:
        ctx.close()


def test_the_financials_table_boxes_have_distinct_names(chrome, server):
    from tests.e2e.test_pass2_axe import route_financials
    from tests.e2e.test_pass2_milo_view import PERIOD_KEY
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, store={PERIOD_KEY: "quarter"})
    route_financials(page)
    try:
        page.goto(server["base"] + "/#/AAPL/financials", wait_until="domcontentloaded")
        page.wait_for_selector("#fin-congress .tscroll table tbody tr", timeout=20000)
        page.wait_for_load_state("networkidle")
        page.evaluate("() => document.querySelectorAll('details').forEach((d) => { d.open = true; })")
        page.wait_for_timeout(300)
        names = page.eval_on_selector_all(".tscroll[role=region]", "els => els.map(e => e.getAttribute('aria-label'))")
        assert names and len(names) == len(set(names)), names
        assert not any(n == "View data, table" for n in names), names
    finally:
        ctx.close()

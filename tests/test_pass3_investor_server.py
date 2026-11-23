"""Round three's Investor mode, server side (Pass 3, 2026-11-23; app/investor.py, app/investor_routes.py).

The market calendar's sessions (a holiday, a half day, a weekend), the owner report (its three refusals, its counts,
the group filter that today admits only everyone, and that it never shows a percentage or a rate), the sign-up
questions (offered once on every sign-up path, the answers never stored, the level written only on accept), the owner
shape on new watchlists and saved research, the Paper Desk's diversification route, and the setting that shows the old
separate pages again."""
from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import db, investor, usage
from app.auth import admin, config, linking, store

client = TestClient(main.app)
GOOD = "tungsten-carbide-9"
OWNER = "owner@example.com"


@pytest.fixture(autouse=True)
def fresh(accounts, monkeypatch):
    client.cookies.clear()
    usage.reset_limits()
    monkeypatch.delenv(admin.ENV_NAME, raising=False)
    monkeypatch.delenv(investor.SEPARATE_SETTING, raising=False)
    yield accounts
    client.cookies.clear()


def register(email):
    r = client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": email,
                                                "password": GOOD, "confirm_password": GOOD})
    assert r.status_code == 200, r.text
    return client.cookies.get(config.CSRF_COOKIE)


def owner_csrf(monkeypatch):
    monkeypatch.setenv(admin.ENV_NAME, OWNER)
    csrf = register(OWNER)
    store.mark_verified(store.get_user_by_email(OWNER)["id"])
    return csrf


# ------------------------------------------------------------------ the market calendar

def test_the_calendar_marks_thanksgiving_closed_and_the_day_after_a_one_oclock_close():
    days = {d["date"]: d for d in investor.session_days(date(2026, 11, 25), 5)}
    assert days["2026-11-25"]["status"] == "open" and days["2026-11-25"]["closes"].startswith("2026-11-25T16:00")
    assert days["2026-11-26"]["status"] == "holiday" and days["2026-11-26"]["name"] == "Thanksgiving Day"
    assert "closed" in days["2026-11-26"]["note"]
    half = days["2026-11-27"]
    assert half["status"] == "early_close" and half["closes"].startswith("2026-11-27T13:00")
    assert half["opens"].startswith("2026-11-27T09:30") and half["closes"].endswith("-05:00")
    assert days["2026-11-28"]["status"] == "weekend" and days["2026-11-29"]["status"] == "weekend"


def test_the_calendar_marks_christmas_eve_short_and_christmas_closed():
    days = {d["date"]: d for d in investor.session_days(date(2026, 12, 24), 2)}
    assert days["2026-12-24"]["status"] == "early_close"
    assert days["2026-12-25"]["status"] == "holiday" and days["2026-12-25"]["name"] == "Christmas Day"


def test_the_calendar_route_is_open_and_states_the_futures_limit(monkeypatch):
    from app import events
    monkeypatch.setattr(events, "upcoming", lambda *a, **k: {"events": [{"title": "CPI (test data)", "at": "2026-12-10T13:30:00Z"}]})
    r = client.get("/api/markets/calendar?days=10")
    assert r.status_code == 200
    d = r.json()
    assert len(d["days"]) == 10 and d["time_zone_of_record"] == "America/New_York"
    assert "Futures holidays are not modelled" in d["futures_note"]
    assert d["releases"] == {"available": True, "events": [{"title": "CPI (test data)", "at": "2026-12-10T13:30:00Z"}]}


def test_the_calendar_says_so_when_the_release_calendar_cannot_be_read(monkeypatch):
    from app import events
    def down(*a, **k):
        raise TimeoutError("refused")
    monkeypatch.setattr(events, "upcoming", down)
    d = client.get("/api/markets/calendar").json()
    assert d["releases"]["available"] is False and d["releases"]["reason"] and len(d["days"]) == 14


# ------------------------------------------------------------------ the owner report: three legs and the owner

def test_no_user_is_refused_the_owner_report(monkeypatch):
    monkeypatch.setenv(admin.ENV_NAME, OWNER)
    assert client.get("/api/admin/owner-report").status_code == 401


def test_the_wrong_user_is_refused_the_owner_report(monkeypatch):
    monkeypatch.setenv(admin.ENV_NAME, OWNER)
    csrf = register("stranger@example.com")
    store.mark_verified(store.get_user_by_email("stranger@example.com")["id"])
    assert client.get("/api/admin/owner-report", headers={"X-Optic-CSRF": csrf}).status_code == 403


def test_the_wrong_role_an_unverified_owner_address_is_refused_the_owner_report(monkeypatch):
    monkeypatch.setenv(admin.ENV_NAME, OWNER)
    csrf = register(OWNER)
    assert client.get("/api/admin/owner-report", headers={"X-Optic-CSRF": csrf}).status_code == 403


def _seed_events(now):
    a, b = ("visitor", "v-" + "a" * 32, None), ("visitor", "v-" + "b" * 32, None)
    usage.record("visit", a, source_screen="home", level="beginner", now=now - timedelta(days=10))
    usage.record("visit", a, source_screen="home", level="beginner", now=now - timedelta(days=5))
    usage.record("visit", b, source_screen="overview", level="advanced", now=now - timedelta(days=9))
    usage.record("home_stock_open", a, symbol="AAPL", source_screen="home", level="beginner", now=now)
    usage.record("home_stock_open", b, symbol="AAPL", source_screen="home", level="advanced", now=now)
    usage.record("home_stock_open", a, symbol="MSFT", source_screen="home", level="beginner", now=now)
    usage.record("milo_question", a, source_screen="financials", level="intermediate", now=now - timedelta(days=2))


def test_the_owner_reads_counts_per_week_and_over_thirty_days(monkeypatch):
    now = datetime.now(timezone.utc)
    _seed_events(now)
    csrf = owner_csrf(monkeypatch)
    r = client.get("/api/admin/owner-report", headers={"X-Optic-CSRF": csrf})
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    m = d["last_30_days"]
    assert m["signals"]["home_stock_open"] == {"events": 3, "readers": 2}
    assert m["signals"]["milo_question"] == {"events": 1, "readers": 1}
    assert m["signals"]["visit"]["readers"] == 2
    assert m["symbols"][0] == {"symbol": "AAPL", "opens": 2}
    assert {x["level"] for x in m["levels"]} >= {"beginner", "advanced", "intermediate"}
    assert {"screen": "financials", "event": "milo_question", "events": 1} in m["screens"]
    assert m["came_back"] == {"readers": 1, "had_a_full_week": 2}
    assert len(d["weeks"]) == 12 and sum(w["signals"]["home_stock_open"]["events"] for w in d["weeks"]) == 3
    assert "v-aaaa" not in r.text                                   # counts only: no reader id leaves the server


def test_the_owner_report_never_shows_a_percentage_or_a_rate(monkeypatch):
    """Counts and per-week series only (refinement A8): on a handful of readers a percentage reads as more than it is."""
    _seed_events(datetime.now(timezone.utc))
    csrf = owner_csrf(monkeypatch)
    body = client.get("/api/admin/owner-report", headers={"X-Optic-CSRF": csrf}).json()
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    assert not [k for k in keys(body) if re.search(r"pct|percent|(^|_)rate|ratio|share", k) and k != "generated_at"]
    assert "%" not in json.dumps({k: v for k, v in body.items() if k != "what_is_counted"})
    page = open("static/v2/js/pages/reports.js").read()
    block = page[page.index("/* ---------------- the owner report"):page.index("/* ---------------- end of the owner report")]
    assert "%" not in block and "pct" not in block and not re.search(r"\brate\b|percent", block.lower())


def test_the_owners_own_accounts_are_left_out_of_the_report(monkeypatch):
    csrf = owner_csrf(monkeypatch)
    owner = store.get_user_by_email(OWNER)
    usage.record("home_stock_open", ("signed_in", owner["id"], owner["id"]), symbol="AAPL")
    d = client.get("/api/admin/owner-report", headers={"X-Optic-CSRF": csrf}).json()
    assert d["last_30_days"]["signals"]["home_stock_open"]["events"] == 0 and d["owners_left_out"] == 1


def test_the_group_filter_is_accepted_and_today_reads_everyone(monkeypatch):
    """The organization round reads one group with this filter; today any group is accepted, named as not applied,
    and the counts are everyone's (contract)."""
    _seed_events(datetime.now(timezone.utc))
    csrf = owner_csrf(monkeypatch)
    h = {"X-Optic-CSRF": csrf}
    every = client.get("/api/admin/owner-report", headers=h).json()
    org = client.get("/api/admin/owner-report?owner_kind=org&owner_id=team-1", headers=h).json()
    user = client.get("/api/admin/owner-report?owner_kind=user&owner_id=x", headers=h).json()
    named = client.get("/api/admin/owner-report?owner_kind=everyone", headers=h).json()
    for d in (org, user, named):
        assert d["group"]["applied"] == "everyone"
        assert d["last_30_days"] == every["last_30_days"] and d["weeks"] == every["weeks"]
    assert org["group"]["asked"] == {"kind": "org", "id": "team-1"} and org["group"]["note"]
    assert every["group"]["note"] is None
    assert client.get("/api/admin/owner-report?owner_kind=team", headers=h).status_code == 400


def test_the_owner_report_answers_in_under_two_seconds_on_fifty_thousand_rows(monkeypatch):
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(50000):
        at = (now - timedelta(minutes=i * 2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ev = ("visit", "home_stock_open", "milo_question")[i % 3]
        rows.append((at, "visitor", "v-%032d" % (i % 900), None, ev, "AAPL" if ev == "home_stock_open" else None,
                     "home", ("beginner", "intermediate", "advanced")[i % 3]))
    with db.cursor(write=True) as c:
        c.executemany("INSERT INTO usage_event (occurred_at, actor_kind, actor_ref, user_id, event, symbol, source_screen,"
                      " level) VALUES (?,?,?,?,?,?,?,?)", rows)
    csrf = owner_csrf(monkeypatch)
    t = time.perf_counter()
    r = client.get("/api/admin/owner-report", headers={"X-Optic-CSRF": csrf})
    took = time.perf_counter() - t
    assert r.status_code == 200 and took < 2.0, took


# ------------------------------------------------------------------ the sign-up questions

def test_the_questions_are_five_to_eight_each_optional_and_each_suggests_a_level():
    qs = investor.public_questions()
    assert 5 <= len(qs) <= 8
    assert investor.suggest({}) == {"suggested": None, "why": None, "answered": 0}
    low = investor.suggest({q["id"]: q["choices"][0]["id"] for q in qs})
    high = investor.suggest({q["id"]: q["choices"][-1]["id"] for q in qs})
    assert low["suggested"] == "beginner" and high["suggested"] == "advanced"
    one = investor.suggest({"charts": "trends"})
    assert one["suggested"] == "intermediate" and one["answered"] == 1
    for lvl in ("beginner", "intermediate", "advanced"):
        assert investor.WHY[lvl].count(".") == 1                      # one sentence of why


def test_questions_need_a_reader():
    assert client.get("/api/account/level-questions").status_code == 401
    assert client.post("/api/account/level-questions/decide", json={"outcome": "skipped"}).status_code in (401, 403)


def _everything_in_every_table():
    with sqlite3.connect(db.DB_PATH) as c:
        names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return "\n".join(json.dumps([list(map(str, row)) for row in c.execute('SELECT * FROM "{}"'.format(n))])
                         for n in names)


def test_answers_are_never_stored_and_accept_writes_the_level(monkeypatch):
    csrf = register("reader@example.com")
    h = {"X-Optic-CSRF": csrf}
    got = client.get("/api/account/level-questions").json()
    assert got["offer"] is True and len(got["questions"]) == 6
    assert client.post("/api/account/level-questions/shown", headers=h).status_code == 200
    answers = {q["id"]: q["choices"][-1]["id"] for q in got["questions"]}
    s = client.post("/api/account/level-questions/suggest", headers=h, json={"answers": answers}).json()
    assert s["suggested"] == "advanced"
    uid = store.get_user_by_email("reader@example.com")["id"]
    assert store.preferences(uid)["knowledge_level"] is None          # nothing written before the reader accepts
    d = client.post("/api/account/level-questions/decide", headers=h,
                    json={"outcome": "accepted", "suggested": s["suggested"]}).json()
    assert d["knowledge_level"] == "advanced" and d["level_quiz"]["outcome"] == "accepted"
    everything = _everything_in_every_table()
    for answer in answers.values():
        assert '"{}"'.format(answer) not in everything, answer          # no answer id in any table
    for q in investor.QUESTIONS:
        for _cid, label, _s in q["choices"]:
            assert label not in everything
    assert client.get("/api/account/level-questions").json()["offer"] is False


def test_skip_writes_only_that_the_questions_were_skipped():
    csrf = register("skipper@example.com")
    uid = store.get_user_by_email("skipper@example.com")["id"]
    before = store.preferences(uid)["knowledge_level"]
    d = client.post("/api/account/level-questions/decide", headers={"X-Optic-CSRF": csrf},
                    json={"outcome": "skipped"}).json()
    assert d["level_quiz"]["outcome"] == "skipped" and d["knowledge_level"] == before
    assert client.get("/api/account/level-questions").json()["offer"] is False


def test_the_level_stays_changeable_after_the_questions():
    csrf = register("change@example.com")
    h = {"X-Optic-CSRF": csrf}
    client.post("/api/account/level-questions/decide", headers=h, json={"outcome": "accepted", "suggested": "beginner"})
    r = client.patch("/api/auth/preferences", headers=h, json={"knowledge_level": "advanced"})
    assert r.status_code == 200 and r.json()["preferences"]["knowledge_level"] == "advanced"


# the four sign-up paths (refinement A4): the questions are offered on the first signed-in visit of any new account

def test_offered_after_a_password_sign_up():
    register("pw@example.com")
    assert client.get("/api/account/level-questions").json()["offer"] is True


@pytest.mark.parametrize("provider", ["google", "apple"])
def test_offered_after_a_google_or_apple_sign_up(provider, monkeypatch):
    """Through the real callback with the code exchange stubbed (as tests/test_auth_providers.py does)."""
    from app.auth import oauth
    monkeypatch.setattr(config, "GOOGLE_CLIENT_ID", "client-id.apps.googleusercontent.com")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setattr(oauth, "complete", lambda p, code, nonce, verifier, apple_user=None: {
        "provider": provider, "subject": provider + "-sub", "email": provider + "@example.com", "email_verified": True,
        "private_relay": False, "first_name": "New", "last_name": "Reader", "avatar_url": None})
    if provider == "apple":
        # Apple needs a paid developer membership configured; the account it creates is what is tested, through linking
        outcome = linking.resolve(oauth.complete("apple", "c", "n", "v"))
        user = outcome.get("user") or store.get_user_by_email("apple@example.com")
        assert user and investor.offer_questions(user["id"]) is True
        return
    client.get("/api/auth/google/start", follow_redirects=False)
    state = db.rows("SELECT state FROM oauth_states")[0]["state"]
    reply = client.get("/api/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False)
    assert "auth=ok" in reply.headers["location"]
    assert client.get("/api/account/level-questions").json()["offer"] is True


def test_offered_after_a_first_passkey_sign_in():
    from webauthn_fixtures import SoftAuthenticator
    csrf = register("pk@example.com")
    options = client.post("/api/auth/passkeys/register/options", headers={"X-Optic-CSRF": csrf}).json()["options"]
    device = SoftAuthenticator(rp_id=config.rp_id())
    assert client.post("/api/auth/passkeys/register/verify", headers={"X-Optic-CSRF": csrf},
                       json={"credential": device.register(options["challenge"], "http://localhost:8000")}).status_code == 200
    client.cookies.clear()
    options = client.post("/api/auth/passkeys/login/options").json()["options"]
    signed = client.post("/api/auth/passkeys/login/verify",
                         json={"credential": device.authenticate(options["challenge"], "http://localhost:8000")})
    assert signed.status_code == 200
    assert client.get("/api/account/level-questions").json()["offer"] is True


# ------------------------------------------------------------------ the owner shape on new rows

def test_new_watchlists_and_saved_research_carry_their_owner():
    csrf = register("owner-shape@example.com")
    uid = store.get_user_by_email("owner-shape@example.com")["id"]
    h = {"X-Optic-CSRF": csrf}
    assert client.post("/api/watchlists", headers=h, json={"name": "Second"}).status_code == 200
    client.post("/api/saved-research", headers=h, json={"title": "A note", "content": "text", "symbol": "AAPL"})
    lists = db.rows("SELECT owner_kind, owner_id, user_id FROM watchlists")
    assert lists and all(r["owner_kind"] == "user" and r["owner_id"] == uid for r in lists)
    research = db.rows("SELECT owner_kind, owner_id FROM saved_research")
    assert all(r["owner_kind"] == "user" and r["owner_id"] == uid for r in research)
    # behaviour unchanged: the lists read back as before
    names = [w["name"] for w in client.get("/api/watchlists").json()["watchlists"]]
    assert "Second" in names


# ------------------------------------------------------------------ the Paper Desk's diversification

def test_paper_positions_are_checked_before_any_market_call(monkeypatch):
    seen = {}
    from app.analytics import portfolio_risk
    monkeypatch.setattr(portfolio_risk, "build", lambda provider, positions: seen.setdefault("p", positions) and {"available": True, "names": len(positions)})
    r = client.post("/api/portfolio-risk/positions", json={"positions": [
        {"ticker": "aapl", "qty": 10, "entry_price": 200}, {"ticker": "", "qty": 1, "entry_price": 1},
        {"ticker": "MSFT", "qty": -3, "entry_price": 400}, {"symbol": "nvda", "qty": "2", "entry_price": "100", "direction": "short"}]})
    assert r.status_code == 200 and r.json()["names"] == 2
    assert [p["ticker"] for p in seen["p"]] == ["AAPL", "NVDA"] and seen["p"][1]["direction"] == "short"
    assert client.post("/api/portfolio-risk/positions", json={"positions": []}).json()["available"] is False


# ------------------------------------------------------------------ the setting for the old separate pages

def test_the_separate_pages_setting_is_off_by_default_and_named_on_health(monkeypatch):
    assert investor.separate_pages() is False
    modes = client.get("/api/health").json()["modes"]["investor_pages"]
    assert modes == {"watchlist_and_alerts": "one place, two views", "portfolio": "the reader's own books first",
                     "setting": "OPTIC_SEPARATE_ALERTS_AND_MODELS"}
    monkeypatch.setenv(investor.SEPARATE_SETTING, "on")
    assert investor.separate_pages() is True
    modes = client.get("/api/health").json()["modes"]["investor_pages"]
    assert modes["watchlist_and_alerts"] == "separate pages" and modes["portfolio"] == "Optic's model books"

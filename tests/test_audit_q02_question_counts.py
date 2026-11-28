"""Q02: the owner's two Milo question figures are one definition (audit round, 2026-11-27).

The headline "Asked Milo a question" (app/usage.py signals) and the table "Questions to Milo by where they were
asked" (app/metrics.py overview) read the same `milo_questions` rows through `metrics.question_totals`; one write path,
`main._count_question`, writes the row and the usage event together. Controlled events only; no provider is reached.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from starlette.requests import Request

import app.main as main
from app import db, metrics, usage
from app.auth import admin, store

ROOT = Path(__file__).resolve().parent.parent
OWNER = "owner@example.com"
V = "v-" + "d" * 32
KINDS = ("chat", "research", "earnings_brief", "scan", "investigation", "portfolio")


@pytest.fixture(autouse=True)
def fresh(accounts, monkeypatch):
    monkeypatch.delenv("OPTIC_USAGE_CAPTURE", raising=False)
    monkeypatch.setenv(admin.ENV_NAME, OWNER)
    usage.reset_limits()
    yield accounts


def make_user(email):
    now = db.utcnow()
    uid = db.new_id()
    db.execute("INSERT INTO users (id, email, first_name, created_at, updated_at) VALUES (?,?,?,?,?)",
               (uid, email, "A", now, now))
    return {"id": uid, "email": email}


def request_for(visitor=None):
    headers = [(b"x-optic-visitor", visitor.encode())] if visitor else []
    return Request({"type": "http", "method": "POST", "path": "/api/chat", "headers": headers, "query_string": b""})


def count(monkeypatch, who, kind, payload=None, visitor=None):
    monkeypatch.setattr(main.auth_deps, "current_user", lambda request: who)
    main._count_question(request_for(visitor), kind, payload)


def at(now, **delta):
    return (now - timedelta(**delta)).strftime("%Y-%m-%dT%H:%M:%SZ")


def raw_question(when, uid, kind="chat"):
    db.execute("INSERT INTO milo_questions (at, user_id, kind) VALUES (?, ?, ?)", (when, uid, kind))


def event_count():
    return db.row("SELECT COUNT(*) AS n FROM usage_event WHERE event = 'milo_question'")["n"]


def question_count():
    return db.row("SELECT COUNT(*) AS n FROM milo_questions")["n"]


def test_the_headline_and_the_table_agree_across_all_six_kinds(monkeypatch):
    reader, owner = make_user("reader@example.com"), make_user(OWNER)
    for kind in KINDS:
        count(monkeypatch, reader, kind, visitor=V)
    count(monkeypatch, owner, "chat")                      # the owner's own: left out of both
    count(monkeypatch, None, "scan")                       # a guest with no visitor id: counted in both
    now = datetime.now(timezone.utc)
    sig, over = usage.signals(now), metrics.overview(now)
    total = over["questions"]["total"]
    for window, key in (("week", "last_7_days"), ("month", "last_30_days"), ("today", "today")):
        assert sig["windows"][window]["milo_question"]["events"] == total[key] == 7, window
    assert over["questions"]["owner_questions_left_out"] == 1
    assert sorted(k["kind"] for k in over["questions"]["by_kind"]) == sorted(KINDS)
    assert {k["label"] for k in over["questions"]["by_kind"]} >= {"Investigation steps", "Earnings briefs"}


def test_every_call_writes_exactly_one_row_and_one_event_and_a_repeat_adds_one_more(monkeypatch):
    reader = make_user("reader@example.com")
    for i, kind in enumerate(KINDS, start=1):
        count(monkeypatch, reader, kind)
        assert question_count() == i and event_count() == i, kind
    count(monkeypatch, reader, "chat")                     # no deduplication: one row per request
    assert question_count() == 7 and event_count() == 7


def test_the_payload_gives_the_event_its_screen_symbol_and_level(monkeypatch):
    reader = make_user("reader@example.com")
    count(monkeypatch, reader, "chat", {"mode": "advanced", "context": {"focus": {"ticker": "AAPL", "view": "overview"}}})
    row = db.row("SELECT * FROM usage_event WHERE event = 'milo_question'")
    assert (row["symbol"], row["source_screen"], row["level"]) == ("AAPL", "overview", "advanced")
    count(monkeypatch, reader, "scan")                     # no payload: an event with no symbol or screen
    rows = db.rows("SELECT * FROM usage_event WHERE event = 'milo_question' ORDER BY id")
    assert (rows[1]["symbol"], rows[1]["source_screen"], rows[1]["level"]) == (None, None, None)


def test_window_edges_fall_on_the_same_side_in_both_figures():
    now = datetime.now(timezone.utc).replace(microsecond=0)
    reader = make_user("reader@example.com")
    for delta in (dict(days=6, hours=23), dict(days=7, hours=1), dict(days=29, hours=23), dict(days=30, hours=1)):
        raw_question(at(now, **delta), reader["id"])
        usage.record("milo_question", ("signed_in", reader["id"], reader["id"]), now=now - timedelta(**delta))
    sig, over = usage.signals(now), metrics.overview(now)
    t = over["questions"]["total"]
    assert t["last_7_days"] == sig["windows"]["week"]["milo_question"]["events"] == 1
    assert t["last_30_days"] == sig["windows"]["month"]["milo_question"]["events"] == 3
    assert over["questions"]["by_kind"][0]["last_7_days"] == 1 and over["questions"]["by_kind"][0]["last_30_days"] == 3


def test_with_capture_off_the_headline_still_equals_the_table(monkeypatch):
    monkeypatch.setenv("OPTIC_USAGE_CAPTURE", "off")
    reader = make_user("reader@example.com")
    count(monkeypatch, reader, "chat")
    count(monkeypatch, reader, "portfolio")
    now = datetime.now(timezone.utc)
    sig, over = usage.signals(now), metrics.overview(now)
    assert event_count() == 0 and question_count() == 2
    assert sig["windows"]["week"]["milo_question"]["events"] == over["questions"]["total"]["last_7_days"] == 2


def test_the_reader_count_now_covers_every_kind(monkeypatch):
    a, b = make_user("a@example.com"), make_user("b@example.com")
    count(monkeypatch, a, "earnings_brief")
    count(monkeypatch, b, "investigation")
    sig = usage.signals(datetime.now(timezone.utc))
    assert sig["windows"]["week"]["milo_question"] == {"events": 2, "readers": 2}
    assert sig["readers_all_kinds_from"] == usage.READERS_ALL_KINDS_FROM == "2026-11-27"


def test_the_definition_is_in_both_payloads_and_is_the_same_object():
    now = datetime.now(timezone.utc)
    assert usage.signals(now)["definition"] is metrics.QUESTION_DEFINITION
    assert metrics.overview(now)["questions"]["definition"] is metrics.QUESTION_DEFINITION
    assert metrics.QUESTION_DEFINITION == (
        "A question to Milo is one request that passed the allowance, through chat, deep research, an earnings brief, "
        "a scan request, an investigation step or a portfolio briefing. Your own are left out.")
    assert "\u2014" not in metrics.QUESTION_DEFINITION and "\u2013" not in metrics.QUESTION_DEFINITION


def test_each_of_the_six_routes_calls_the_one_write_path_once():
    src = (ROOT / "app/main.py").read_text()
    for kind in KINDS:
        assert len(re.findall(r'_count_question\(request, "{}"[,)]'.format(kind), src)) == 1, kind
    assert "_usage_milo" not in src
    assert '_count_question(request, "chat", payload)' in src and '_count_question(request, "research", payload)' in src

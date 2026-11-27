"""Q02: the real chat route writes exactly one milo_questions row and one milo_question event per request (the
other kinds' call sites are asserted in tests/test_audit_q02_question_counts.py). Provider: the recording stub."""
from __future__ import annotations

from app import db
from tests.test_pass1_milo_route import (  # noqa: F401  (fixtures and helpers are shared)
    ask, overview_context, provider, signed_in, stub)


def test_one_chat_question_is_one_row_and_one_event(stub):
    csrf = signed_in()
    r, _ = ask("Why is Apple moving today?", overview_context(), mode="intermediate", csrf=csrf)
    assert r.status_code == 200
    rows = db.rows("SELECT kind FROM milo_questions")
    assert [x["kind"] for x in rows] == ["chat"]
    assert db.row("SELECT COUNT(*) AS n FROM usage_event WHERE event = 'milo_question'")["n"] == 1
    ask("And Microsoft?", overview_context("MSFT"), mode="intermediate", csrf=csrf)
    assert db.row("SELECT COUNT(*) AS n FROM milo_questions")["n"] == 2
    assert db.row("SELECT COUNT(*) AS n FROM usage_event WHERE event = 'milo_question'")["n"] == 2

"""Audit F04 (2026-11-27), in a real browser: Milo's final answer after the grounding check.

From AAPL Financials the reader asks the question the audit asked. The recording stub plays a scripted draft (a table
of dollar figures that are not in the page's data) and then a scripted rewrite. The finished bubble has no table
fragment, no empty table and no lead-in with nothing after it; the note counts the statements removed; and after a
reload the conversation is reopened from Milo's history with the same text and the same note. A second journey
scripts a rewrite that is still unsupported and asserts the server's limit answer, final and reopened.
"""
from __future__ import annotations

import re

import pytest

from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import DESKTOP, open_page
from tests.e2e.test_pass2_milo_view import PERIOD_KEY, route_statements

QUESTION = ("What were Apple's operating cash flow, capital spending and free cash flow in Q4 FY2026, and how did they "
            "compare with the previous four quarters? Show a table.")

# every dollar figure here is absent from the page's data (the fixture's cash flow is 32, 3 and 29 billion)
DRAFT = ("**Free cash flow strengthened in Q4.** Apple's operating cash flow was $91.2 billion.\n\n"
         "Here are the figures:\n\n"
         "| Quarter | Operating cash flow | Capex | Free cash flow |\n|---|---|---|---|\n"
         "| Q4 FY2026 | $91.2 billion | $12.4 billion | $78.8 billion |\n"
         "| Q3 FY2026 | $88.0 billion | $11.9 billion | $76.1 billion |\n\n"
         "**What stands out**\n\nCash conversion held up.\n\n→ What drove the change?")
REWRITE = ("The page carries Apple's quarterly cash flow, but not at the precision this answer first gave, so those "
           "figures are left out.\n\nCash conversion held up across the quarters shown.\n\n→ What drove the change?")
STILL_BAD = "Free cash flow was $78.8 billion in Q4.\n\n→ What drove the change?"


def _ask_and_wait(page, server, stub):
    held = []
    route_statements(page, held)
    page.goto(server["base"] + "/#/AAPL/financials", wait_until="domcontentloaded")
    page.wait_for_selector("[data-v2-account].avatar")
    page.click(".topbar-milo")
    page.wait_for_selector("#milo-q")
    page.fill("#milo-q", QUESTION)
    page.press("#milo-q", "Enter")
    page.wait_for_selector(".milo-amended", timeout=60000)
    page.wait_for_function("() => { const s = document.querySelector('[data-v2-milo-stop]'); return !s || s.hidden; }", timeout=30000)


def _answer(page):
    return page.evaluate("""() => { const log = document.querySelector('.milo-log');
      return { text: log.innerText, tables: log.querySelectorAll('table').length, emptyTables: [...log.querySelectorAll('table')].filter(t => !t.querySelector('tbody tr')).length,
               note: (log.querySelector('.milo-amended') || {}).textContent || '' }; }""")


def _no_fragments(got):
    assert "|---" not in got["text"] and "|" not in got["text"]
    assert got["emptyTables"] == 0
    for para in re.split(r"\n\s*\n", got["text"]):
        assert not para.strip().endswith(":") or para.strip() == got["text"].strip(), "a lead-in with nothing after it: " + para


def _reopen(page):
    page.click("[data-v2-milo-history]")
    page.wait_for_selector("[data-v2-milo-open]")
    page.click("[data-v2-milo-open]")
    page.wait_for_selector(".milo-amended")


def test_the_audit_question_gives_a_whole_answer_final_and_reopened(chrome, server, stub):
    stub.reset("script")
    stub.script = [DRAFT, REWRITE]
    _, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar, store={PERIOD_KEY: "quarter"})
    try:
        _ask_and_wait(page, server, stub)
        got = _answer(page)
        assert "Cash conversion held up across the quarters shown." in got["text"]
        assert "$91.2" not in got["text"] and "$78.8" not in got["text"]
        _no_fragments(got)
        assert "Milo removed 3 statements" in got["note"] and "rewrote the answer from the figures that remain" in got["note"], got["note"]
        assert len(stub.messages()) == 2, "the draft and one rewrite"
        # the rewrite's request carries no tool use and what was removed
        rewrite = stub.messages()[1]["body"]
        assert rewrite.get("tool_choice") == {"type": "none"} and "$91.2 billion" in str(rewrite["messages"][-1]["content"])
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-q")
        _reopen(page)
        again = _answer(page)
        assert again["note"] == got["note"]
        assert "Cash conversion held up across the quarters shown." in again["text"]
        _no_fragments(again)
        assert not page.errors
    finally:
        ctx.close()


def test_a_rewrite_that_is_still_unsupported_gives_the_limit_answer_final_and_reopened(chrome, server, stub):
    stub.reset("script")
    stub.script = [DRAFT, STILL_BAD]
    _, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar, store={PERIOD_KEY: "quarter"})
    try:
        _ask_and_wait(page, server, stub)
        got = _answer(page)
        assert "does not carry some of the figures this question asks for" in got["text"]
        assert "$78.8" not in got["text"] and "$91.2" not in got["text"]
        _no_fragments(got)
        assert "Milo removed 3 statements" in got["note"] and "says above what it could not support" in got["note"], got["note"]
        assert len(stub.messages()) == 2
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-q")
        _reopen(page)
        again = _answer(page)
        assert again["note"] == got["note"] and "does not carry some of the figures" in again["text"]
        _no_fragments(again)
        assert not page.errors
    finally:
        ctx.close()

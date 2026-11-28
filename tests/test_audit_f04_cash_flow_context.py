"""Audit F04 follow-up, round two (2026-11-27): the live retest on the evaluation copy. The real model made no
get_cash_flow call for the customer's question on Financials and answered in one round from CONTEXT, where the
quarterly lines were raw arrays (capital expenditure negative, no capital spending figure), so 12 statements were
removed. These tests drive the route's own context path with no scripted tool call: the server puts the cash flow
block in CONTEXT on Financials and for a cash flow question, and an answer quoting it grounds with nothing removed."""
import json

import pytest

from app import ai, ai_policy as P
from tests.milo_eval import cases as C
from tests.milo_eval import harness as H

QUESTION = "What were AAPL's Q4 operating cash flow, capex and free cash flow?"
GOOD = ("In Q4 FY26 operating cash flow was $28.1 billion, capital spending was $2.2 billion and free cash flow was "
        "$25.9 billion. The four quarters of FY26 add up to the fiscal year's operating cash flow, so each figure is "
        "one fiscal quarter alone.")
TABLE = ("| Quarter | Operating cash flow | Capital spending | Free cash flow |\n|---|---|---|---|\n"
         "| Q4 FY26 | $28.1 billion | $2.2 billion | $25.9 billion |\n| Q3 FY26 | $27.9 billion | $3.5 billion | $24.4 billion |")


def _case(question=QUESTION, view="financials", world=None):
    return {"id": "CF-1", "question": question, "context": C.page(view, "AAPL"), "history": [], "web": False,
            "world": world or {}, "user": None, "mode": None}


def _sent(case):
    out = H.assemble(case)
    assert out["status"] == 200
    return out, json.dumps(out["kwargs"]["messages"], default=str)


def test_the_financials_screen_puts_the_quarterly_cash_figures_in_context():
    out, text = _sent(_case())
    cf = out["context"]["cash_flow"]
    assert cf["status"] == "ok" and cf["currency"] == "USD"
    q4 = cf["quarters"][0]
    assert (q4["period"], q4["operating_cash_flow"], q4["capital_expenditure"], q4["capital_spending"],
            q4["free_cash_flow"]) == ("Q4 FY26", 28101000000.0, -2218000000.0, 2218000000.0, 25883000000.0)
    assert cf["basis"]["said"].startswith("The four quarters of FY26 add up")
    assert 'cash_flow' in text and "28101000000" in text, "the block reaches the model's turn, not only the route"


@pytest.mark.parametrize("answer", [GOOD, TABLE, "Capex was -$2.2B in Q4 FY26."])
def test_an_answer_quoting_the_context_figures_survives_grounding_with_nothing_removed(answer):
    _, text = _sent(_case())
    g = P.ground(answer, text, [])
    assert g["removed"] == 0 and g["text"] == answer and P.integrity(g["text"]) == []


def test_without_the_context_figures_the_same_answer_is_taken_out():
    # the negative control: the same question on a screen that is not Financials and does not ask about cash flow
    out, text = _sent(_case(question="How is AAPL trading?", view="overview"))
    assert "cash_flow" not in out["context"]
    g = P.ground(GOOD, text, [])
    assert g["removed"] >= 1


def test_a_cash_flow_question_on_another_screen_also_gets_the_block():
    out, _ = _sent(_case(view="overview"))
    assert out["context"]["cash_flow"]["quarters"][0]["period"] == "Q4 FY26"


def test_a_fund_with_no_statements_gets_no_block_and_the_answer_still_goes_out():
    case = _case(question="What was SPY's free cash flow last quarter?", view="financials")
    case["context"] = C.page("financials", "SPY")
    out, _ = _sent(case)
    assert "cash_flow" not in out["context"]


def test_a_browser_sent_cash_flow_block_is_dropped():
    case = _case(question="How is AAPL trading?", view="overview")
    case["context"] = dict(case["context"], cash_flow={"status": "ok", "quarters": [{"free_cash_flow": 9e12}]})
    out, text = _sent(case)
    assert "cash_flow" not in out["context"] and "9000000000000" not in text


def test_the_prompt_tells_milo_to_use_the_block_or_call_the_tool_never_memory():
    sp = " ".join(ai.SYSTEM_PROMPT.split())
    assert "when CONTEXT has `cash_flow`, answer from it" in sp
    assert "call get_cash_flow before you write a word of the answer" in sp
    assert "Never write a cash flow, capex or free cash flow figure from memory" in sp
    assert "cash_flow" in ai._ORDER_BASE


def test_the_financials_screen_alone_is_enough_the_question_need_not_name_cash_flow():
    out, _ = _sent(_case(question="How have AAPL's quarters looked lately?", view="financials"))
    assert out["context"]["cash_flow"]["quarters"][0]["period"] == "Q4 FY26"

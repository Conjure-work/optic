"""Audit F04 follow-up (2026-11-27): Milo can look up quarterly cash flow. `get_cash_flow` returns operating cash flow,
capital expenditure and free cash flow by fiscal quarter and year from the statements the Financials page already
reads; a negative amount written with a minus sign before the dollar sign can be grounded. No network, no live model:
the provider is a function over fixed statements and Anthropic is the scripted stand-in in tests/pass3_milo_fakes.py."""
import asyncio
import json

import pytest

from app import ai, ai_policy as P, milo_data, milo_tools
from tests import pass3_milo_fakes as F
from tests.fixtures.audit_financials import raw_financials
from tests.fixtures.milo_cash_flow import aapl_raw

USD = lambda t: {"financial_currency": "USD"}                      # noqa: E731


def _cash(raw=None):
    return lambda ticker: milo_data.cash_flow(lambda t: (raw if raw is not None else aapl_raw()), USD, ticker)


def _run(toolbox, name="get_cash_flow", args=None):
    return asyncio.run(toolbox.run(name, args or {"ticker": "AAPL"}))


def _box(raw=None):
    return milo_tools.Toolbox(runners={"get_cash_flow": _cash(raw)})


# -------------------------------------------------------------------------------------------------- the lookup
def test_the_lookup_returns_each_quarter_with_its_period_units_and_basis():
    r = milo_data.cash_flow(lambda t: aapl_raw(), USD, "AAPL")
    assert r["status"] == "ok" and r["currency"] == "USD" and r["ticker"] == "AAPL"
    assert r["quarters"][0] == {"period": "Q4 FY26", "period_end": "2026-09-26", "operating_cash_flow": 28101000000.0,
                                "capital_expenditure": -2218000000.0, "capital_spending": 2218000000.0,
                                "free_cash_flow": 25883000000.0}
    assert "unavailable" not in r["quarters"][0] and "note" not in r["quarters"][0]
    assert [q["period"] for q in r["quarters"]] == ["Q4 FY26", "Q3 FY26", "Q2 FY26", "Q1 FY26", "Q4 FY25"]
    b = r["basis"]
    assert b["basis"] == "discrete" and b["fiscal_year"] == "FY26" and b["fiscal_year_end"] == "2026-09-26"
    assert b["quarters_sum_operating_cash_flow"] == b["fiscal_year_operating_cash_flow"] == 109855000000.0
    assert b["said"] == ("The four quarters of FY26 add up to the fiscal year's operating cash flow, so each figure is "
                         "one fiscal quarter alone.")
    assert r["as_of"] == "2026-09-26" and r["fiscal_years"][0]["period"] == "FY26"
    assert r["fiscal_years"][0]["capital_spending"] == 11691000000.0


def test_the_currency_is_the_reporting_currency_and_defaults_to_usd():
    def boom(t):
        raise RuntimeError("quote feed down")
    assert milo_data.cash_flow(lambda t: aapl_raw(), lambda t: {"financial_currency": "jpy"}, "X")["currency"] == "JPY"
    assert milo_data.cash_flow(lambda t: aapl_raw(), boom, "X")["currency"] == "USD"
    assert milo_data.cash_flow(lambda t: aapl_raw(), lambda t: {}, "X")["currency"] == "USD"


def test_the_quarter_count_is_capped():
    r = milo_data.cash_flow(lambda t: aapl_raw(), USD, "AAPL", quarters=2, years=1)
    assert [q["period"] for q in r["quarters"]] == ["Q4 FY26", "Q3 FY26"] and len(r["fiscal_years"]) == 1


def test_a_quarter_that_does_not_reconcile_is_null_and_named():
    r = milo_data.cash_flow(lambda t: raw_financials("not_reconciling"), USD, "AAPL")
    row = r["quarters"][1]
    assert row["free_cash_flow"] is None and row["unavailable"] == ["free_cash_flow"]
    assert row["note"] == ("Free cash flow is unavailable for this quarter: operating cash flow, capital expenditure "
                           "and free cash flow do not reconcile on the feed.")
    assert row["operating_cash_flow"] == 28.0 and row["capital_expenditure"] == -3.0
    assert "unavailable" not in r["quarters"][0]


def test_a_year_to_date_quarter_with_nothing_before_it_is_null_with_its_reason():
    r = milo_data.cash_flow(lambda t: raw_financials("year_to_date"), USD, "AAPL")
    assert r["basis"]["basis"] == "year_to_date" and "year to date" in r["basis"]["said"]
    row = next(q for q in r["quarters"] if q["period"] == "Q4 FY24")
    assert [row[k] for k in ("operating_cash_flow", "capital_expenditure", "capital_spending", "free_cash_flow")] == [None] * 4
    assert row["unavailable"] == ["operating_cash_flow", "capital_expenditure", "free_cash_flow"]
    assert row["note"] == ("Unavailable for this quarter: the statements give it year to date and the quarter before it "
                           "is not on hand to take it from.")


def test_quarters_that_cannot_be_checked_say_so():
    r = milo_data.cash_flow(lambda t: raw_financials("unchecked"), USD, "AAPL")
    assert r["basis"]["basis"] == "unchecked" and r["basis"]["quarters_sum_operating_cash_flow"] is None
    assert r["basis"]["said"].startswith("As Yahoo Finance reports each quarter;")


def test_a_feed_with_no_quarterly_statement_says_so_and_keeps_the_years():
    r = milo_data.cash_flow(lambda t: raw_financials("none"), USD, "AAPL")
    assert r["status"] == "ok" and r["quarters"] == [] and r["quarterly_available"] is False
    assert r["quarterly_note"] == "The feed carries no quarterly cash flow statement for AAPL. Fiscal-year figures only."
    assert r["missing"] == ["quarterly cash flow statement"] and "basis" not in r and r["fiscal_years"]
    content, is_error, _ = _run(_box(raw_financials("none")))
    assert not is_error and json.loads(content)["meta"]["partial"] is True


def test_no_statements_at_all_is_unavailable_with_no_figures():
    r = milo_data.cash_flow(lambda t: {}, USD, "SPY")
    assert r["status"] == "unavailable"
    assert r["error"] == "Yahoo Finance returned no financial statements for SPY. Funds and indexes have none."
    assert not any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in r.values())
    content, is_error, _ = _run(milo_tools.Toolbox(runners={"get_cash_flow": _cash({})}), args={"ticker": "SPY"})
    assert is_error is True and json.loads(content)["meta"]["unavailable"] is True


def test_statements_with_no_cash_flow_lines_are_unavailable():
    raw = raw_financials("none")
    raw.pop("cashflow_annual")
    r = milo_data.cash_flow(lambda t: raw, USD, "AAPL")
    assert r["status"] == "unavailable" and r["error"] == "The statements Yahoo Finance carries for AAPL have no cash flow lines."


def test_a_provider_that_raises_is_unavailable_through_the_toolbox():
    def boom(t):
        raise ConnectionError("Yahoo is down")
    box = milo_tools.Toolbox(runners={"get_cash_flow": lambda ticker: milo_data.cash_flow(boom, USD, ticker)})
    content, is_error, _ = _run(box)
    assert is_error is True and json.loads(content)["meta"]["unavailable"] is True


# -------------------------------------------------------------------------------------------------- the tool
def test_the_tool_is_offered_described_and_carries_its_units():
    assert "get_cash_flow" in milo_tools.TOOL_NAMES and "get_cash_flow" in milo_tools.MARKET_TOOLS
    assert "get_cash_flow" in milo_tools.allowed_for("financials")
    assert "get_cash_flow" not in milo_tools.allowed_for("settings")
    assert "currency" in " ".join(milo_tools.UNITS["get_cash_flow"].keys()) + " ".join(milo_tools.UNITS["get_cash_flow"].values())
    assert milo_tools.status_words("get_cash_flow", {"ticker": "AAPL"}) == "Reading AAPL's cash flow"
    assert milo_tools.Record("get_cash_flow", {"ticker": "AAPL"}, True, "ok", 0.1).data_type() == "cash flow by quarter and year"
    sp = " ".join(ai.SYSTEM_PROMPT.split())
    assert "get_cash_flow" in sp and "unavailable for that quarter" in sp
    specs = {s["name"]: s for s in milo_tools.SPECS}
    assert specs["get_financials"]["description"].endswith(" For cash flow, call get_cash_flow.")
    assert "Call it" in specs["get_cash_flow"]["description"]
    assert milo_tools.validate("get_cash_flow", {"ticker": "aapl"}) == {"ticker": "AAPL"}
    for bad in ({"ticker": "AAPL", "user_id": "x"}, {"ticker": "DROP TABLE"}, {}):
        with pytest.raises(milo_tools.InvalidInput):
            milo_tools.validate("get_cash_flow", bad)


# -------------------------------------------------------------------------------------------------- grounding
def _content():
    return _run(_box())[0]


def _ground(answer):
    return P.ground(answer, "", [({"tool": "get_cash_flow", "label": "AAPL cash flow by quarter and year"}, _content())])


TABLE = ("| Quarter | Operating cash flow | Capital expenditure | Free cash flow |\n|---|---|---|---|\n"
         "| Q4 FY26 | $28.1B | -$2.2B | $25.9B |\n| Q3 FY26 | $27.9B | -$3.5B | $24.4B |\n"
         "| Q2 FY26 | $24.0B | -$3.1B | $20.9B |\n| Q1 FY26 | $29.9B | -$2.9B | $27.0B |")


@pytest.mark.parametrize("answer", [
    "Operating cash flow was $28.1 billion, capital spending was $2.2 billion and free cash flow was $25.9 billion in Q4 FY26.",
    "Capex was -$2.2B.",
    "Capex was −$2.2B.",
    TABLE,
])
def test_the_quarterly_figures_survive_grounding(answer):
    g = _ground(answer)
    assert g["removed"] == 0 and g["text"] == answer and P.integrity(g["text"]) == []
    assert g["cited"] and {c["tool"] for c in g["cited"]} == {"get_cash_flow"}


def test_a_figure_the_lookup_does_not_hold_is_still_removed():
    g = _ground("Operating cash flow was $31.4 billion in Q4 FY26.")
    assert g["removed"] == 1


def test_a_minus_sign_before_the_dollar_is_read_as_negative():
    def vals(t):
        return [v for f in P.figures_in(t) for v in f["values"]]
    assert 2.2e9 in vals("-$2.2B") and -2.2e9 in vals("-$2.2B")
    assert 2.2e9 in vals("−$2.2B") and -2.2e9 in vals("−$2.2B")
    assert vals("$2.2B") == [2.2e9]
    assert vals("up $2.2B") == [2.2e9]


# -------------------------------------------------------------------------------------------------- the stream
QUESTION = "What were AAPL's Q4 operating cash flow, capex and free cash flow?"
CTX = {"focus": {"ticker": "AAPL", "view": "financials"}}
GOOD = ("In Q4 FY26 operating cash flow was $28.1 billion, capital spending was $2.2 billion and free cash flow was "
        "$25.9 billion. The four quarters of FY26 add up to the fiscal year's operating cash flow, so each figure is "
        "one fiscal quarter alone.")


def _go(monkeypatch, rounds, box):
    sent = F.install(monkeypatch, rounds)
    events = F.run(QUESTION, toolbox=box, context=CTX)
    return sent, events, [d for k, d in events if k == "amend"], [d for k, d in events if k == "done"][-1]


def test_the_customers_question_gets_a_whole_answer_with_the_figures(monkeypatch):
    sent, events, amend, done = _go(monkeypatch, [F.tool_round("get_cash_flow", {"ticker": "AAPL"}), F.text_round(GOOD)], _box())
    assert len(sent) == 2 and amend == []
    assert "checking the figures" not in [d.get("state") for k, d in events if k == "status"]
    assert {c["figure"] for c in done["cited"]} >= {"$28.1 billion", "$2.2 billion", "$25.9 billion"}
    assert {c["tool"] for c in done["cited"]} == {"get_cash_flow"}
    assert "Read AAPL cash flow by quarter and year" in [d["text"] for k, d in events if k == "step"]
    assert "get_cash_flow" in [t["name"] for t in sent[0]["tools"]]


def test_a_quarter_marked_unavailable_is_said_not_filled(monkeypatch):
    raw = raw_financials("not_reconciling")
    said = "In Q3 FY25 operating cash flow was $28 and capital spending was $3. Free cash flow is unavailable for that quarter. "
    sent, _, amend, done = _go(monkeypatch, [F.tool_round("get_cash_flow", {"ticker": "AAPL"}), F.text_round(said)], _box(raw))
    assert len(sent) == 2 and amend == []
    invented = said.replace("Free cash flow is unavailable for that quarter.", "Free cash flow was $17.3.")
    sent, _, amend, _ = _go(monkeypatch, [F.tool_round("get_cash_flow", {"ticker": "AAPL"}), F.text_round(invented),
                                          F.text_round("Free cash flow is unavailable for that quarter. ")], _box(raw))
    assert len(amend) == 1 and "unsupported_figure" in amend[0]["rules"] and "$17.3" not in amend[0]["text"]


def test_without_the_lookup_the_same_answer_is_taken_out(monkeypatch):
    box = milo_tools.Toolbox(runners={"get_quote": lambda ticker: {"status": "ok", "price": 199.04}})
    sent, _, amend, _ = _go(monkeypatch, [F.tool_round("get_cash_flow", {"ticker": "AAPL"}), F.text_round(GOOD),
                                          F.text_round("Optic has no cash flow figures for that quarter here. ")], box)
    assert len(amend) == 1 and "unsupported_figure" in amend[0]["rules"] and amend[0]["removed"] >= 1

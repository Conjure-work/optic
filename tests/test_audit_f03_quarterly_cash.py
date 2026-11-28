"""F03 (audit 2026-11-27): quarterly cash flow says what a quarter is, checks it against the year, and drops what does
not reconcile. Fixed fixtures in tests/fixtures/audit_financials.py; invented numbers."""
from __future__ import annotations

import copy

from app.analytics import fundamentals
from tests.fixtures import audit_financials as fx
from tests.test_frontend_v2_stage0 import V2, _run


def test_annual_cash_flow_is_unchanged_and_the_bridge_holds():
    f = fx.financials("discrete")
    a = f["annual"]
    assert a["operating_cash_flow"] == [120.0, 110.0] and a["capital_expenditure"] == [-12.0, -11.0] and a["free_cash_flow"] == [108.0, 99.0]
    for i in range(2):
        assert a["free_cash_flow"][i] == a["operating_cash_flow"][i] + a["capital_expenditure"][i]


def test_four_quarters_that_add_to_the_year_are_discrete_and_untouched():
    f = fx.financials("discrete")
    b = f["quarterly_cash_basis"]
    assert b["basis"] == "discrete" and b["fiscal_year"] == "2025-09-30" and b["sum"] == 120.0 and b["annual"] == 120.0
    assert b["fcf_unavailable"] == []
    assert f["quarterly_cash"]["operating_cash_flow"] == fx.OCF
    assert f["quarterly_cash"]["capital_expenditure"] == fx.CAPEX
    assert f["quarterly_cash"]["free_cash_flow"] == fx.FCF
    assert f["quarterly_cash_reported"]["operating_cash_flow"] == fx.OCF


def test_year_to_date_quarters_are_converted_to_the_quarter_alone():
    f = fx.financials("year_to_date")
    b = f["quarterly_cash_basis"]
    assert b["basis"] == "year_to_date" and b["annual"] == 120.0 and b["sum"] == 292.0
    q = f["quarterly_cash"]
    # hand worked: Q1 as given, then each year-to-date figure less the one before it
    assert q["operating_cash_flow"][:4] == [36.0, 28.0, 24.0, 32.0]
    assert q["capital_expenditure"][:4] == [-3.0, -3.0, -3.0, -3.0]
    assert q["free_cash_flow"][:4] == [33.0, 25.0, 21.0, 29.0]
    # FY24 Q4 has no third quarter on hand to take it from: None, never the year to date passed off as a quarter
    assert q["operating_cash_flow"][4] is None and q["capital_expenditure"][4] is None and q["free_cash_flow"][4] is None
    assert f["quarterly_cash_reported"]["operating_cash_flow"] == [120.0, 84.0, 56.0, 32.0, 110.0], "the provider's own, kept"
    assert 4 in b["fcf_unavailable"]


def test_no_complete_fiscal_year_is_unchecked_and_returned_as_given():
    f = fx.financials("unchecked")
    b = f["quarterly_cash_basis"]
    assert b["basis"] == "unchecked" and b["fiscal_year"] is None and b["sum"] is None
    assert f["quarterly_cash"]["operating_cash_flow"] == [28.0, 24.0, 32.0, 29.0, 27.0]
    assert f["quarterly_cash"]["free_cash_flow"] == [25.0, 21.0, 29.0, 27.0, 25.0]


def test_a_quarter_whose_free_cash_flow_does_not_reconcile_has_none():
    f = fx.financials("not_reconciling")
    q = f["quarterly_cash"]
    assert q["free_cash_flow"][1] is None and f["quarterly_cash_basis"]["fcf_unavailable"] == [1]
    assert q["free_cash_flow"][0] == 33.0 and q["free_cash_flow"][2] == 21.0
    assert q["operating_cash_flow"] == fx.OCF, "only free cash flow is dropped"


def test_a_missing_input_leaves_free_cash_flow_out_not_zero():
    raw = copy.deepcopy(fx.raw_financials("discrete"))
    raw["cashflow_quarterly"]["rows"]["Capital Expenditure"][2] = None
    f = fundamentals.analyse_financials(raw)
    assert f["quarterly_cash"]["free_cash_flow"][2] is None and 2 in f["quarterly_cash_basis"]["fcf_unavailable"]


def test_no_quarterly_statement_means_no_lines():
    f = fx.financials("none")
    assert all(v is None for v in f["quarterly_cash"].values())
    assert f["quarterly_cash_basis"]["basis"] == "unchecked" and f["quarterly_cash_basis"]["fcf_unavailable"] == []


def test_the_registry_reason_is_true_and_the_figure_stays_not_reported():
    from app import figures
    fin = {"available": True, "annual_periods": ["2025-12-31"], "quarterly_periods": [],
           "annual": {"revenue": [3.81e12], "net_income": [1.70e12], "operating_cash_flow": [2.27e12],
                      "capital_expenditure": [-1.28e12]},
           "quarterly": {}, "balance_sheet": {"total_debt": 1.0e12, "cash_and_short_term": 3.06e12}}
    b = figures.resolve("TSM", {"price": 300.0, "forward_eps": 14.0, "forward_pe": 17.3, "quote_type": "EQUITY",
                                "currency": "USD", "financial_currency": "TWD"},
                        sec=(None, None, "no US-GAAP filings"), financials=fin)
    f = b["figures"]["free_cash_flow_ttm"]
    assert f["status"] == "not_reported" and f["value"] is None
    assert "Twelve-month cash flow is not added up from the provider's quarterly statements here; the fiscal-year figure is the one given." in str(f)
    assert "carries no quarterly cash flow" not in str(b)


def _caption(tmp_path, kind, extra=""):
    f = fx.financials(kind)
    import json
    return _run(tmp_path, f"""
      const FIN = await import('{(V2 / "js/pages/financials.js").as_posix()}');
      const f = {json.dumps(f)};
      {extra}
      const t = {{ company: {{ financials: f }} }};
      const V = FIN.periodView(f, 'quarter', t), Y = FIN.periodView(f, 'year', t);
      print(JSON.stringify({{ cap: FIN.qcashCaption(f, V, Y) }}));
    """)["cap"]


def test_each_basis_puts_its_sentence_in_the_caption(tmp_path):
    base = "Each bar is one fiscal quarter alone, three months, not the year to date. Free cash flow is operating cash flow less capital spending, which is shown as cash out."
    d = _caption(tmp_path, "discrete")
    assert d.startswith("Quarters, US dollars. " + base) and "The four quarters of" in d and "add up to the fiscal-year total." in d
    y = _caption(tmp_path, "year_to_date")
    assert "The statements give these year to date; each quarter here is that figure less the quarter before it in the same fiscal year." in y
    u = _caption(tmp_path, "unchecked")
    assert "As Yahoo Finance reports each quarter; there are not four quarters of one fiscal year on hand" in u
    n = _caption(tmp_path, "not_reconciling")
    assert "Free cash flow is left out for" in n and "because the three figures do not reconcile there." in n
    older = _caption(tmp_path, "discrete", "delete f.quarterly_cash_basis;")
    assert "As Yahoo Finance reports each quarter" in older, "an older cached payload has no basis field"


def test_the_stale_notice_is_only_in_the_no_quarterly_data_branch():
    src = (V2 / "js" / "pages" / "financials.js").read_text()
    assert src.count("carry no quarterly cash flow") == 1
    line = [l for l in src.split("\n") if "carry no quarterly cash flow" in l][0]
    assert "hasQcf ?" in line and "Quarters are in Cash flow by quarter, below." in line and "for ${sym}" in line
    assert "Yahoo carries no quarterly cash flow" not in src and "yearly only here" not in src


def test_view_data_in_quarters_has_the_three_cash_rows():
    src = (V2 / "js" / "pages" / "financials.js").read_text()
    assert "QROWS = [['Operating cash flow', 'operating_cash_flow'], ['Capital expenditure', 'capital_expenditure'], ['Free cash flow', 'free_cash_flow', true]]" in src
    assert "'Unavailable'" in src and "V.q && hasQcf ? QROWS.map" in src

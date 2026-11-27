"""Fixed financial and insider fixtures for the 2026-11 audit round (F03 quarterly cash flow, F01 insider summaries).

Every number here is invented for a test, in a company shaped like AAPL (fiscal year ends 30 September). Nothing here
is market data. The provider's statement shape is the one `app/providers/yf.py` hands `analyse_financials`: periods
newest first, rows by the statement's own names.
"""
from __future__ import annotations

import copy

FY_END = "2025-09-30"
YEARS = ["2025-09-30", "2024-09-30"]
# the four quarters of the fiscal year to 2025-09-30, then the last quarter of the one before
QUARTERS = ["2025-09-30", "2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30"]

# Each quarter alone, newest first. The fourth quarter of FY24 is not part of a complete fiscal year here.
OCF = [36.0, 28.0, 24.0, 32.0, 29.0]
CAPEX = [-3.0, -3.0, -3.0, -3.0, -2.0]
FCF = [33.0, 25.0, 21.0, 29.0, 27.0]
ANNUAL = {"Operating Cash Flow": [120.0, 110.0], "Capital Expenditure": [-12.0, -11.0], "Free Cash Flow": [108.0, 99.0]}


def _stmt(periods, rows):
    return {"periods": list(periods), "rows": {k: list(v) for k, v in rows.items()}}


def raw_financials(kind="discrete"):
    """`kind`: discrete, year_to_date, unchecked, not_reconciling, none (no quarterly cash flow statement at all)."""
    quarters = list(QUARTERS)
    ocf, capex, fcf = list(OCF), list(CAPEX), list(FCF)
    if kind == "year_to_date":
        # first fiscal quarter as given, then the running total for the year; FY24's Q4 is a year-to-date figure with
        # no third quarter before it on hand
        ocf, capex, fcf = [120.0, 84.0, 56.0, 32.0, 110.0], [-12.0, -9.0, -6.0, -3.0, -11.0], [108.0, 75.0, 50.0, 29.0, 99.0]
    elif kind == "unchecked":
        quarters = ["2025-06-30", "2025-03-31", "2024-12-31", "2024-09-30", "2024-06-30"]
        ocf, capex, fcf = [28.0, 24.0, 32.0, 29.0, 27.0], [-3.0, -3.0, -3.0, -2.0, -2.0], [25.0, 21.0, 29.0, 27.0, 25.0]
    elif kind == "not_reconciling":
        fcf[1] = 40.0                      # 28 less 3 is 25, not 40
    n = len(quarters)
    out = {
        "income_annual": _stmt(YEARS, {"Total Revenue": [400.0, 380.0], "Net Income": [100.0, 90.0]}),
        "income_quarterly": _stmt(quarters, {"Total Revenue": [100.0] * n, "Net Income": [25.0] * n}),
        "balance_annual": _stmt(YEARS, {"Cash And Cash Equivalents": [30.0, 29.0], "Total Debt": [100.0, 105.0]}),
        "cashflow_annual": _stmt(YEARS, ANNUAL),
    }
    if kind != "none":
        out["cashflow_quarterly"] = _stmt(quarters, {"Operating Cash Flow": ocf, "Capital Expenditure": capex, "Free Cash Flow": fcf})
    return out


def financials(kind="discrete"):
    from app.analytics import fundamentals
    return fundamentals.analyse_financials(copy.deepcopy(raw_financials(kind)))


def ticker_payload_with(kind="discrete", sym="AAPL"):
    """The `/api/ticker/<sym>` payload a browser journey serves, carrying the statements for `kind`."""
    from tests.e2e.fixtures import ticker_payload
    p = ticker_payload(sym)
    p["company"]["financials"] = financials(kind)
    return p

"""An AAPL-shaped statement set for the get_cash_flow tests (audit 2026-11-27, F04 follow-up).

Only the fourth quarter of FY26 is a real figure from the feed: operating cash flow 28,101,000,000, capital
expenditure -2,218,000,000 and free cash flow 25,883,000,000. Every other number here is invented for a test, chosen
so that the four quarters of FY26 add up to the year. The provider's shape is the one `app/providers/yf.py` hands
`analyse_financials`: periods newest first, rows by the statement's own names, whole amounts.
"""
from __future__ import annotations

YEARS = ["2026-09-26", "2025-09-27"]
QUARTERS = ["2026-09-26", "2026-06-27", "2026-03-28", "2025-12-27", "2025-09-27"]

OCF = [28101e6, 27867e6, 23952e6, 29935e6, 29000e6]
CAPEX = [-2218e6, -3462e6, -3071e6, -2940e6, -2500e6]
FCF = [25883e6, 24405e6, 20881e6, 26995e6, 26500e6]
ANNUAL = {"Operating Cash Flow": [109855e6, 108000e6], "Capital Expenditure": [-11691e6, -9500e6],
          "Free Cash Flow": [98164e6, 98500e6]}


def _stmt(periods, rows):
    return {"periods": list(periods), "rows": {k: list(v) for k, v in rows.items()}}


def aapl_raw():
    n = len(QUARTERS)
    return {
        "income_annual": _stmt(YEARS, {"Total Revenue": [400e9, 380e9], "Net Income": [100e9, 90e9]}),
        "income_quarterly": _stmt(QUARTERS, {"Total Revenue": [100e9] * n, "Net Income": [25e9] * n}),
        "balance_annual": _stmt(YEARS, {"Cash And Cash Equivalents": [30e9, 29e9], "Total Debt": [100e9, 105e9]}),
        "cashflow_annual": _stmt(YEARS, ANNUAL),
        "cashflow_quarterly": _stmt(QUARTERS, {"Operating Cash Flow": OCF, "Capital Expenditure": CAPEX,
                                                "Free Cash Flow": FCF}),
    }

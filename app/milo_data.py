"""Milo's data tools for facts the terminal already reads but Milo could not ask for (2026-10-25; brought into
the post-demo overhaul by hand in Phase 08, 2026-10-29, from the milo-upgrade branch's app/milo_data.py at 55721f6).

What Milo could not look up before this: which ticker a company name is, a symbol's price history over a
window, the SEC filings list, and the revenue and EPS a company filed in XBRL. Each was already fetched by
Optic for a page (the symbol directory for search, Yahoo daily bars for the charts, EDGAR for Financials
and the Overview), so each tool here is the same integration called with typed, validated input
(`app/milo_tools.py`), and none adds a provider.

Every calculation is code: a window's change, its high and low, the largest drawdown and realised
volatility are computed here from the closes, never left to the model. A result says what it is in
units and where it came from; `milo_tools.describe` adds the freshness flags (delayed, stale, partial,
unavailable) to every tool's answer, these included.

Nothing here reads a reader's data. The reader-specific tools (watchlists, linked portfolio) stay in
`app/main.py`, bound to the session's own user when the toolbox is built.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

# Calendar span of each window, as yfinance names its periods.
PERIODS = {"1m": "1mo", "3m": "3mo", "6m": "6mo", "1y": "1y", "2y": "2y", "5y": "5y", "ytd": "ytd"}
# ...and in days, to keep bars from before the window out of its figures (_in_window)
SPAN_DAYS = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "2y": 731, "5y": 1827}
SLACK_DAYS = 7
INTERVALS = {"daily": "1d", "weekly": "1wk"}
TRADING_DAYS = {"1d": 252, "1wk": 52}
BARS_SHOWN = 40
SYMBOL_DIRECTORY = ("Nasdaq Trader symbol directory (nasdaqlisted and otherlisted files, refreshed daily) plus "
                    "Optic's own index, rate, currency, commodity and crypto list")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _r(x: Optional[float], nd: int = 4) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else round(float(x), nd)


# ------------------------------------------------------------------------------------- company lookup

def lookup_company(search: Callable[..., Dict[str, Any]], query: str) -> Dict[str, Any]:
    """Symbols matching a company name, ticker or alias, ranked as the terminal's search box ranks them."""
    found = search(query, limit=8)
    rows = [{k: r.get(k) for k in ("symbol", "name", "kind", "etf", "match") if r.get(k) is not None}
            for r in (found.get("results") or [])]
    if not found.get("available"):
        return {"status": "unavailable", "source": SYMBOL_DIRECTORY,
                "error": found.get("reason") or "The symbol directory could not be read."}
    out: Dict[str, Any] = {"status": "ok" if rows else "not_found", "source": SYMBOL_DIRECTORY,
                           "query": query, "matches": rows,
                           "note": ("`match` says how each was found: symbol (exact), alias (a name people use), "
                                    "prefix, name, word or contains. Pick the exact or alias match when there is "
                                    "one, and ask the reader when two companies fit equally.")}
    if found.get("stale"):
        out["stale"] = True
        out["stale_note"] = "Today's directory could not be refreshed; an earlier copy answered."
    if not rows:
        out["error"] = "No listed symbol matches {!r}.".format(query)
    return out


# ------------------------------------------------------------------------------------- price history

def history_stats(closes: List[float], dates: List[str], per_year: int) -> Dict[str, Any]:
    """Change, range, drawdown and realised volatility over the closes given, oldest first. Pure."""
    pairs = [(d, float(c)) for d, c in zip(dates, closes) if c is not None and not math.isnan(float(c))]
    if len(pairs) < 2:
        return {"bars": len(pairs)}
    first_d, first = pairs[0]
    last_d, last = pairs[-1]
    hi_d, hi = max(pairs, key=lambda p: p[1])
    lo_d, lo = min(pairs, key=lambda p: p[1])
    peak, peak_d, worst, worst_from, worst_to = pairs[0][1], pairs[0][0], 0.0, None, None
    for d, c in pairs:
        if c > peak:
            peak, peak_d = c, d
        dd = c / peak - 1.0
        if dd < worst:
            worst, worst_from, worst_to = dd, peak_d, d
    rets = [math.log(b[1] / a[1]) for a, b in zip(pairs, pairs[1:]) if a[1] > 0 and b[1] > 0]
    vol = None
    if len(rets) >= 2:
        mean = sum(rets) / len(rets)
        var = sum((x - mean) ** 2 for x in rets) / (len(rets) - 1)
        vol = math.sqrt(var) * math.sqrt(per_year)
    return {
        "bars": len(pairs),
        "first": {"date": first_d, "close": _r(first)},
        "last": {"date": last_d, "close": _r(last)},
        "change": _r(last - first),
        "change_pct": _r((last / first - 1.0) * 100.0, 2) if first else None,
        "high_close": {"date": hi_d, "close": _r(hi)},
        "low_close": {"date": lo_d, "close": _r(lo)},
        "max_drawdown_pct": _r(worst * 100.0, 2),
        "max_drawdown_from": worst_from,
        "max_drawdown_to": worst_to,
        "realised_vol_annualised_pct": _r(vol * 100.0, 2) if vol is not None else None,
    }


def _in_window(df: Any, period: str) -> Any:
    """The bars inside the window asked for. A frame that starts more than a week before it (a cached or stand-in
    frame for a longer window) is cut to the window, so a "3m" figure is never a year's; Yahoo's own frames count
    from today rather than from the last bar, start inside that week, and are used as they came."""
    last = df.index[-1]
    if period == "ytd":
        start = last.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = last - timedelta(days=SPAN_DAYS[period])
    if df.index[0] >= start - timedelta(days=SLACK_DAYS):
        return df
    return df[df.index >= start]


def price_history(history: Callable[..., Any], quote: Callable[[str], Dict[str, Any]], ticker: str,
                  period: str, interval: str) -> Dict[str, Any]:
    """Daily or weekly bars over a named window, with the window's statistics computed from the closes."""
    ivl = INTERVALS[interval]
    df = history(ticker, period=PERIODS[period], interval=ivl)
    if df is None or len(df) == 0:
        return {"status": "not_found", "error": "No {} price history for {}.".format(interval, ticker)}
    whole = len(df)
    since = (getattr(df, "attrs", None) or {}).get("stand_in_since")
    df = _in_window(df, period)
    dates = [d.strftime("%Y-%m-%d") for d in df.index]
    closes = [float(x) for x in df["Close"].tolist()]
    stats = history_stats(closes, dates, TRADING_DAYS[ivl])
    bars = []
    for d, (_, row) in zip(dates[-BARS_SHOWN:], df.tail(BARS_SHOWN).iterrows()):
        vol = _r(row.get("Volume"), 0)
        bars.append({"date": d, "open": _r(row.get("Open")), "high": _r(row.get("High")),
                     "low": _r(row.get("Low")), "close": _r(row.get("Close")),
                     "volume": int(vol) if vol is not None else None})
    try:
        q = quote(ticker) or {}
    except Exception:                                                # noqa: BLE001 - the currency is a label
        q = {}
    body = {
        "status": "ok",
        "source": "Yahoo Finance {} bars (closes not adjusted for dividends; splits are)".format(interval),
        "ticker": ticker, "period": period, "interval": interval,
        "currency": q.get("currency"),
        "as_of": dates[-1],
        "window": stats,
        "recent_bars": bars,
        "bars_note": ("The last {} bars of {}; the window's figures use every bar.".format(len(bars), len(dates))
                      if len(dates) > len(bars) else "Every bar in the window.")
                     + ("" if whole == len(dates) else
                        " {} earlier bars the feed sent were outside the window and left out.".format(whole - len(dates))),
        "method": ("change_pct is the last close against the first close in the window; max_drawdown_pct is the "
                   "largest fall from a running high close to a later close; realised volatility is the "
                   "standard deviation of log returns between bars, annualised (x sqrt({}))."
                   .format(TRADING_DAYS[ivl])),
    }
    if since:
        # the feed did not answer and the last bars read stood in: said, with when (Phase 09, S02)
        body.update(stale=True, stale_note="The feed did not answer just now; these are the bars Optic last read, at {}.".format(since))
    return body


# ------------------------------------------------------------------------------------- SEC filings

def filings(recent: Callable[..., Dict[str, Any]], ticker: str, limit: int) -> Dict[str, Any]:
    """The company's recent notable SEC filings, newest first, with links to the documents."""
    out = recent(ticker, limit=limit)
    rows = [{k: f.get(k) for k in ("form", "filed", "what", "items", "url") if f.get(k)}
            for f in (out.get("filings") or [])]
    base = {"source": "SEC EDGAR submissions (the company's own filing index)", "ticker": ticker,
            "company": out.get("company"), "cik": out.get("cik"), "filings": rows,
            "as_of": rows[0]["filed"] if rows and rows[0].get("filed") else None}
    if out.get("available") is not True:
        if rows:
            return dict(base, status="ok", stale=True, stale_note=out.get("reason"))
        return dict(base, status="unavailable", error=out.get("reason") or "EDGAR filings are unavailable.")
    if not rows:
        return dict(base, status="not_found", error="No notable filings found for {}.".format(ticker))
    return dict(base, status="ok", note="Only the forms Optic lists as notable (annual and quarterly reports, "
                                        "current reports, proxies and similar), not every filing.")


# ------------------------------------------------------------------------------------- reported financials

def financials(sec_history: Callable[..., Dict[str, Any]], ticker: str, quarters: int = 12) -> Dict[str, Any]:
    """Quarterly revenue and diluted EPS as filed in XBRL, with trailing twelve months and year on year."""
    out = sec_history(ticker)
    if out.get("available") is not True:
        return {"status": "unavailable", "source": "SEC EDGAR XBRL company facts",
                "error": out.get("reason") or "No XBRL history."}

    def last(rows: Any) -> List[Any]:
        return list(rows or [])[-quarters:]
    rev, eps = last(out.get("revenue_quarters")), last(out.get("eps_quarters"))
    newest = [r.get("period_end") for r in (rev[-1:] + eps[-1:]) if isinstance(r, dict) and r.get("period_end")]
    body: Dict[str, Any] = {
        "status": "ok", "source": "SEC EDGAR XBRL company facts (as filed; fourth quarters derived from annual "
                                  "less three quarters where only the annual was filed)",
        "ticker": ticker, "cik": out.get("cik"),
        "revenue_quarters": rev, "revenue_ttm": last(out.get("revenue_ttm")),
        "revenue_yoy": last(out.get("revenue_yoy")),
        "eps_diluted_quarters": eps, "eps_ttm": last(out.get("eps_ttm")),
        "counts": out.get("counts"), "notes": out.get("notes") or [],
        "fields": ("period_end is the quarter's last day; available_from is when the figure first became public; "
                   "derived marks a fourth quarter computed as the year less three quarters."),
        "as_of": max(newest) if newest else None,
    }
    if out.get("stale"):
        body["stale"] = True
        body["stale_note"] = "EDGAR could not be reached; an earlier copy of the filed figures answered."
    if out.get("cache_age_days") is not None:
        body["cache_age_days"] = out.get("cache_age_days")
    return body


# ------------------------------------------------------------------------------------- cash flow

CASH_SOURCE = ("The company's cash flow statements as Yahoo Finance carries them; each quarter checked against the "
               "fiscal year by Optic")
CASH_FIELDS = ("Every money field is a whole amount in `currency`, not thousands or millions. Each quarter is one "
               "fiscal quarter alone, three months, not the year to date. capital_expenditure is negative (cash out); "
               "capital_spending is the same amount as a positive number. free_cash_flow is operating_cash_flow plus "
               "capital_expenditure and is not a GAAP line. A null field is unavailable for that period: say so, "
               "never work it out.")
_CASH_LINES = ("operating_cash_flow", "capital_expenditure", "free_cash_flow")


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v


def _cash_at(lines: Any, i: int) -> Any:
    seq = lines or []
    v = seq[i] if i < len(seq) else None
    return float(v) if _is_number(v) else None


def _cash_row(period: Any, end: Any, values: Dict[str, Any]) -> Dict[str, Any]:
    capex = values["capital_expenditure"]
    # capital_spending is the same amount with the sign turned. Prose says "capital spending of $2.2 billion", a
    # positive figure, and grounding reads that as +2.2e9; the evidence holds -2218000000 for capital_expenditure,
    # so without this twin the figure could not be supported (measured, audit 2026-11-27 F04).
    return {"period": period or end, "period_end": end, "operating_cash_flow": values["operating_cash_flow"],
            "capital_expenditure": capex, "capital_spending": abs(capex) if capex is not None else None,
            "free_cash_flow": values["free_cash_flow"]}


def cash_flow(statements: Callable[..., Dict[str, Any]], quote: Callable[..., Dict[str, Any]], ticker: str,
              quarters: int = 8, years: int = 4) -> Dict[str, Any]:
    """Operating cash flow, capital expenditure and free cash flow by fiscal quarter and fiscal year (audit
    2026-11-27, F04 follow-up). Nothing is recomputed here: the quarters are `quarterly_cash` from
    `fundamentals.analyse_financials`, already one quarter alone and already null where free cash flow does not
    reconcile, and the basis is `quarterly_cash_basis`. A provider exception is left to Toolbox.run."""
    from .analytics import fundamentals
    fin = fundamentals.analyse_financials(statements(ticker))
    if fin.get("available") is not True:
        return {"status": "unavailable", "source": CASH_SOURCE, "ticker": ticker,
                "error": "Yahoo Finance returned no financial statements for {}. Funds and indexes have none.".format(ticker)}
    try:
        currency = str((quote(ticker) or {}).get("financial_currency") or "USD").upper()
    except Exception:
        currency = "USD"

    annual = fin.get("annual") or {}
    a_periods = list(fin.get("annual_periods") or [])
    a_fiscal = list(fin.get("annual_fiscal") or [])
    fiscal_years = []
    for i, end in enumerate(a_periods[:years]):
        vals = {k: _cash_at(annual.get(k), i) for k in _CASH_LINES}
        if any(v is not None for v in vals.values()):
            fiscal_years.append(_cash_row(a_fiscal[i] if i < len(a_fiscal) else None, end, vals))

    qc = fin.get("quarterly_cash") or {}
    q_periods = list(fin.get("quarterly_periods") or [])
    q_fiscal = list(fin.get("quarterly_fiscal") or [])
    basis = fin.get("quarterly_cash_basis") or {}
    has_quarters = any(_cash_at(qc.get("operating_cash_flow"), i) is not None for i in range(len(q_periods)))
    if not has_quarters and not fiscal_years:
        return {"status": "unavailable", "source": CASH_SOURCE, "ticker": ticker,
                "error": "The statements Yahoo Finance carries for {} have no cash flow lines.".format(ticker)}

    body: Dict[str, Any] = {"status": "ok", "source": CASH_SOURCE, "ticker": ticker, "currency": currency}
    if not has_quarters:
        body.update({"as_of": fiscal_years[0]["period_end"], "quarters": [], "quarterly_available": False,
                     "missing": ["quarterly cash flow statement"],
                     "quarterly_note": "The feed carries no quarterly cash flow statement for {}. Fiscal-year figures "
                                       "only.".format(ticker),
                     "fiscal_years": fiscal_years, "fields": CASH_FIELDS})
        return body

    gone = set(basis.get("fcf_unavailable") or [])
    rows: List[Any] = []
    for i, end in enumerate(q_periods[:quarters]):
        vals = {k: _cash_at(qc.get(k), i) for k in _CASH_LINES}
        row = _cash_row(q_fiscal[i] if i < len(q_fiscal) else None, end, vals)
        # an all-null row outside the run of figures is dropped, unless the server has a reason to give for it (a
        # year-to-date quarter with no quarter before it): that quarter is one the reader may ask about
        row["_has"] = any(v is not None for v in vals.values())
        row["_why"] = False
        missing = [k for k in _CASH_LINES if vals[k] is None]
        if missing:
            row["unavailable"] = missing
            # the year-to-date reason is the more specific one, so it comes before the reconciliation note
            if basis.get("basis") == "year_to_date" and vals["operating_cash_flow"] is None:
                row["note"] = ("Unavailable for this quarter: the statements give it year to date and the quarter "
                               "before it is not on hand to take it from.")
                row["_why"] = True
            elif i in gone:
                row["note"] = ("Free cash flow is unavailable for this quarter: operating cash flow, capital "
                               "expenditure and free cash flow do not reconcile on the feed.")
            else:
                row["note"] = "The feed has no figure for this quarter."
        rows.append(row)
    kept = [j for j, r in enumerate(rows) if r["_has"]]
    first, last = (kept[0], kept[-1]) if kept else (0, -1)
    rows = [r for j, r in enumerate(rows) if first <= j <= last or r["_why"]]
    for r in rows:
        r.pop("_has")
        r.pop("_why")

    fy_date = basis.get("fiscal_year")
    fy_label = a_fiscal[a_periods.index(fy_date)] if fy_date in a_periods and a_periods.index(fy_date) < len(a_fiscal) else None
    kind = basis.get("basis")
    if kind == "discrete":
        said = ("The four quarters of {} add up to the fiscal year's operating cash flow, so each figure is one "
                "fiscal quarter alone.".format(fy_label or "the fiscal year"))
    elif kind == "year_to_date":
        said = ("The statements give these year to date; each quarter here is that figure less the quarter before "
                "it in the same fiscal year.")
    else:
        said = ("As Yahoo Finance reports each quarter; there are not four quarters of one fiscal year on hand to "
                "check them against the year's total.")
    with_numbers = [r["period_end"] for r in rows if any(r[k] is not None for k in _CASH_LINES)]
    body.update({
        "as_of": max(with_numbers) if with_numbers else (fiscal_years[0]["period_end"] if fiscal_years else None),
        "quarters": rows,
        "basis": {"basis": kind, "fiscal_year": fy_label, "fiscal_year_end": fy_date,
                  "quarters_sum_operating_cash_flow": basis.get("sum"),
                  "fiscal_year_operating_cash_flow": basis.get("annual"), "said": said},
        "fiscal_years": fiscal_years, "fields": CASH_FIELDS})
    return body


# ------------------------------------------------------------------------------------- wiring

def runners(provider: Any, yf_provider: Any) -> Dict[str, Callable[..., Dict[str, Any]]]:
    """The runners for app/main.py's toolbox, bound to the server's providers. Imports are late so this
    module stays importable without the network stack (tests)."""
    from . import universe as universe_mod
    from .analytics import filings as filings_mod
    from .analytics import sec_facts as sec_facts_mod
    return {
        "lookup_company": lambda query: lookup_company(universe_mod.search_with_status, query),
        "get_price_history": lambda ticker, period, interval: price_history(
            yf_provider.history, provider.quote, ticker, period, interval),
        "get_filings": lambda ticker, limit: filings(filings_mod.recent, ticker, limit),
        "get_financials": lambda ticker: financials(sec_facts_mod.history, ticker),
        "get_cash_flow": lambda ticker: cash_flow(yf_provider.financials, provider.quote, ticker),
    }

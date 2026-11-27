"""A deterministic stand-in for yfinance, for the memory soak. Test only.

Every symbol gets its own data, seeded by the symbol, so a symbol always gets the same figures and a new symbol gets
new ones. The shapes are those yfinance returns (tz-aware daily and intraday bars, the six statements, an options chain
of about twenty expiries by a hundred strikes, insider rows, holders, news, estimates), at the sizes a large company
has, so what the app's provider code keeps in its caches is the weight it keeps with the real feed. The app's own
provider code, caches and analytics run for real on top of it.

Limit: curl_cffi's own network path is not exercised, because nothing is fetched.
"""
from __future__ import annotations

import zlib
from collections import namedtuple
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List

import numpy as np
import pandas as pd

NY = "America/New_York"
Chain = namedtuple("Chain", "calls puts underlying")
_PERIOD_DAYS = {"1d": 1, "5d": 5, "1mo": 31, "3mo": 93, "6mo": 186, "1y": 366, "2y": 731, "5y": 1830, "10y": 3660,
                "ytd": 330, "max": 7300}
_MINUTES = {"1m": 1, "2m": 2, "5m": 5, "15m": 15, "30m": 30, "60m": 60, "90m": 90, "1h": 60}


def _rng(symbol: str, salt: str = "") -> np.random.RandomState:
    return np.random.RandomState(zlib.crc32((symbol.upper() + salt).encode()) & 0xFFFFFFFF)


def _base_price(symbol: str) -> float:
    return 20.0 + (zlib.crc32(symbol.upper().encode()) % 48000) / 100.0


def _business_days(n: int, end: date) -> List[date]:
    out: List[date] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def _bars(symbol: str, index: pd.DatetimeIndex, step_vol: float, salt: str = "") -> pd.DataFrame:
    r = _rng(symbol, salt)
    n = len(index)
    close = _base_price(symbol) * np.exp(np.cumsum(r.normal(0.0003, step_vol, n)))
    open_ = close * (1 + r.normal(0, step_vol / 3, n))
    high = np.maximum(open_, close) * (1 + np.abs(r.normal(0, step_vol / 2, n)))
    low = np.minimum(open_, close) * (1 - np.abs(r.normal(0, step_vol / 2, n)))
    vol = r.randint(500_000, 90_000_000, n).astype("int64")
    return pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Adj Close": close,
                         "Volume": vol, "Dividends": 0.0, "Stock Splits": 0.0}, index=index)


def history(symbol: str, period: str = "2y", interval: str = "1d", start=None, end=None, prepost=False, **_kw) -> pd.DataFrame:
    today = datetime.now(timezone.utc).date()
    if interval in _MINUTES:
        days = min(_PERIOD_DAYS.get(period, 5), 60)
        per_day = 390 // _MINUTES[interval]
        stamps: List[pd.Timestamp] = []
        for d in _business_days(max(days * 5 // 7, 1), today):
            open_ = pd.Timestamp(d.isoformat() + " 09:30", tz=NY)
            stamps.extend(open_ + pd.Timedelta(minutes=_MINUTES[interval] * i) for i in range(per_day))
        return _bars(symbol, pd.DatetimeIndex(stamps), 0.0008, "i" + interval)
    if start is not None:
        days = max((date.fromisoformat(str(end)[:10]) - date.fromisoformat(str(start)[:10])).days, 1) if end else 366
    else:
        days = _PERIOD_DAYS.get(period, 731)
    sessions = max(days * 5 // 7, 1)
    index = pd.DatetimeIndex([pd.Timestamp(d.isoformat(), tz=NY) for d in _business_days(sessions, today)])
    if interval == "1wk":
        index = index[::5]
    elif interval == "1mo":
        index = index[::21]
    return _bars(symbol, index, 0.014, "d" + interval)


def download(tickers, period="1y", interval="1d", group_by="ticker", **_kw) -> pd.DataFrame:
    names = tickers if isinstance(tickers, (list, tuple)) else str(tickers).replace(",", " ").split()
    frames = {s: history(s, period, interval) for s in names}
    if len(names) == 1:
        return frames[names[0]]
    return pd.concat(frames, axis=1)


def _info(symbol: str) -> Dict[str, Any]:
    r = _rng(symbol, "info")
    px = _base_price(symbol)
    shares = float(r.randint(50, 8000)) * 1e6
    info: Dict[str, Any] = {
        "symbol": symbol, "shortName": symbol.title() + " Inc.", "longName": symbol.title() + " Incorporated",
        "quoteType": "EQUITY", "exchange": "NMS", "fullExchangeName": "NasdaqGS", "currency": "USD",
        "financialCurrency": "USD", "exchangeTimezoneName": NY, "sector": "Technology",
        "industry": "Software - Infrastructure", "country": "United States", "city": "Cupertino",
        "website": "https://example.invalid/" + symbol.lower(), "fullTimeEmployees": int(r.randint(500, 200000)),
        "longBusinessSummary": ("Synthetic business description for " + symbol + ". ") * 30,
        "regularMarketPrice": px, "regularMarketPreviousClose": px * 0.99, "previousClose": px * 0.99,
        "regularMarketOpen": px * 0.995, "open": px * 0.995, "regularMarketDayHigh": px * 1.01,
        "regularMarketDayLow": px * 0.98, "regularMarketChange": px * 0.01, "regularMarketChangePercent": 1.0,
        "regularMarketVolume": int(r.randint(1_000_000, 80_000_000)), "regularMarketTime": int(datetime.now(timezone.utc).timestamp()),
        "fiftyTwoWeekHigh": px * 1.3, "fiftyTwoWeekLow": px * 0.7, "marketCap": px * shares, "sharesOutstanding": shares,
        "floatShares": shares * 0.9, "beta": 1.2, "trailingPE": 28.0, "forwardPE": 24.0, "trailingEps": px / 28.0,
        "forwardEps": px / 24.0, "pegRatio": 1.8, "priceToBook": 9.0, "profitMargins": 0.24, "revenueGrowth": 0.08,
        "earningsGrowth": 0.11, "dividendRate": 1.0, "dividendYield": 0.005, "marketState": "REGULAR",
        "hasPrePostMarketData": True, "exchangeDataDelayedBy": 0, "recommendationKey": "buy",
        "targetMeanPrice": px * 1.12, "shortPercentOfFloat": 0.012, "sharesShort": shares * 0.01,
        "sharesShortPriorMonth": shares * 0.011, "shortRatio": 1.4, "dateShortInterest": 1_700_000_000,
        "morningStarOverallRating": 4, "morningStarRiskRating": 3, "trailingPegRatio": 1.7,
    }
    for i in range(60):
        info["extraField%02d" % i] = float(r.normal())
    return info


_LABELS_INCOME = ["Total Revenue", "Cost Of Revenue", "Gross Profit", "Operating Expense", "Operating Income",
                  "Net Income", "Diluted EPS", "Basic EPS", "EBITDA", "EBIT", "Interest Expense", "Tax Provision",
                  "Research And Development", "Selling General And Administration", "Diluted Average Shares"]
_LABELS_BALANCE = ["Total Assets", "Total Liabilities Net Minority Interest", "Stockholders Equity", "Cash And Cash Equivalents",
                   "Total Debt", "Current Assets", "Current Liabilities", "Inventory", "Accounts Receivable",
                   "Long Term Debt", "Ordinary Shares Number", "Working Capital", "Retained Earnings"]
_LABELS_CASH = ["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow", "Financing Cash Flow",
                "Investing Cash Flow", "Repurchase Of Capital Stock", "Cash Dividends Paid", "Depreciation And Amortization",
                "Stock Based Compensation", "Change In Working Capital"]


def _statement(symbol: str, labels: List[str], periods: int, quarterly: bool, salt: str) -> pd.DataFrame:
    r = _rng(symbol, salt)
    today = datetime.now(timezone.utc).date()
    step = 91 if quarterly else 365
    cols = [pd.Timestamp(today - timedelta(days=step * i + 20)) for i in range(periods)]
    scale = _base_price(symbol) * 1e7
    data = {c: (r.normal(1.0, 0.3, len(labels)) * scale * (1 + np.arange(len(labels)))).tolist() for c in cols}
    return pd.DataFrame(data, index=labels)


class _Data:
    """yfinance's `_data` object, for the two reads the provider makes through it."""

    def __init__(self, symbol: str):
        self.symbol = symbol

    def get_raw_json(self, url: str, params=None, timeout=10):
        syms = str((params or {}).get("symbols") or self.symbol).split(",")
        rows = [dict(_info(s), symbol=s) for s in syms]
        return {"quoteResponse": {"result": rows}}

    def get(self, url: str, **_kw):
        class R:
            text = ("<html><table><thead><tr><th>Symbol</th><th>Company</th><th>Earnings Date</th><th>EPS Estimate</th>"
                    "<th>Reported EPS</th><th>Surprise (%)</th></tr></thead><tbody>" + "".join(
                        "<tr><td>X</td><td>X</td><td>%s</td><td>1.1</td><td>1.2</td><td>9.0</td></tr>" % when
                        for when in ("January 29, 2026 at 4 PM EST", "October 30, 2025 at 4 PM EDT",
                                     "July 31, 2025 at 4 PM EDT", "May 01, 2025 at 4 PM EDT"))
                    + "</tbody></table></html>")
        return R()


class Ticker:
    def __init__(self, symbol: str, *a, **kw):
        self.ticker = str(symbol).upper()
        self._data = _Data(self.ticker)
        self._expiries = None

    # prices
    def history(self, *a, **kw) -> pd.DataFrame:
        period = kw.get("period") or (a[0] if a else "1mo")
        return history(self.ticker, period, kw.get("interval", "1d"), kw.get("start"), kw.get("end"))

    @property
    def history_metadata(self) -> Dict[str, Any]:
        return {"currentTradingPeriod": {"regular": {"start": 1, "end": 2, "gmtoffset": -18000, "timezone": "EST"}},
                "exchangeTimezoneName": NY}

    @property
    def fast_info(self) -> Dict[str, Any]:
        px = _base_price(self.ticker)
        return {"lastPrice": px, "regularMarketPreviousClose": px * 0.99, "previousClose": px * 0.99}

    @property
    def info(self) -> Dict[str, Any]:
        return _info(self.ticker)

    @property
    def calendar(self) -> Dict[str, Any]:
        d = datetime.now(timezone.utc).date() + timedelta(days=20)
        return {"Earnings Date": [d], "Earnings High": 2.0, "Earnings Low": 1.0, "Earnings Average": 1.5,
                "Revenue High": 1e10, "Revenue Low": 9e9, "Revenue Average": 9.5e9}

    # options
    @property
    def options(self):
        if self._expiries is None:
            today = datetime.now(timezone.utc).date()
            self._expiries = tuple((today + timedelta(days=7 * i + 2)).isoformat() for i in range(20))
        return self._expiries

    def option_chain(self, date_=None, *a, **kw) -> Chain:
        r = _rng(self.ticker, "chain" + str(date_))
        px = _base_price(self.ticker)
        strikes = np.round(px * np.linspace(0.6, 1.4, 100), 2)

        def side(kind: str) -> pd.DataFrame:
            n = len(strikes)
            last = np.abs(r.normal(5, 3, n))
            return pd.DataFrame({
                "contractSymbol": ["%s%s%s%08d" % (self.ticker, str(date_)[2:].replace("-", ""), kind, int(k * 1000)) for k in strikes],
                "lastTradeDate": [pd.Timestamp.now(tz="UTC")] * n, "strike": strikes, "lastPrice": last,
                "bid": last * 0.98, "ask": last * 1.02, "change": r.normal(0, 0.2, n), "percentChange": r.normal(0, 3, n),
                "volume": r.randint(0, 5000, n).astype(float), "openInterest": r.randint(0, 20000, n).astype(float),
                "impliedVolatility": np.abs(r.normal(0.35, 0.08, n)), "inTheMoney": strikes < px if kind == "C" else strikes > px,
                "contractSize": "REGULAR", "currency": "USD"})
        return Chain(side("C"), side("P"), {"symbol": self.ticker})

    # statements
    @property
    def income_stmt(self): return _statement(self.ticker, _LABELS_INCOME, 4, False, "is")
    @property
    def quarterly_income_stmt(self): return _statement(self.ticker, _LABELS_INCOME, 5, True, "qis")
    @property
    def balance_sheet(self): return _statement(self.ticker, _LABELS_BALANCE, 4, False, "bs")
    @property
    def quarterly_balance_sheet(self): return _statement(self.ticker, _LABELS_BALANCE, 5, True, "qbs")
    @property
    def cashflow(self): return _statement(self.ticker, _LABELS_CASH, 4, False, "cf")
    @property
    def quarterly_cashflow(self): return _statement(self.ticker, _LABELS_CASH, 5, True, "qcf")

    @property
    def splits(self) -> pd.Series:
        return pd.Series([4.0], index=pd.DatetimeIndex([pd.Timestamp("2020-08-31", tz=NY)]))

    @property
    def dividends(self) -> pd.Series:
        idx = pd.DatetimeIndex([pd.Timestamp(d.isoformat(), tz=NY) for d in _business_days(60, datetime.now(timezone.utc).date())][::5])
        return pd.Series(0.25, index=idx)

    # people and holders
    @property
    def insider_purchases(self) -> pd.DataFrame:
        return pd.DataFrame({"Insider Purchases Last 6m": ["Purchases", "Sales", "Net Shares Purchased (Sold)"],
                             "Shares": [1000.0, 90000.0, -89000.0], "Trans": [2.0, 14.0, None]})

    @property
    def insider_transactions(self) -> pd.DataFrame:
        r = _rng(self.ticker, "ins")
        n = 120
        days = r.randint(0, 700, n)
        today = datetime.now(timezone.utc).date()
        return pd.DataFrame({
            "Shares": r.randint(100, 100000, n).astype(float), "URL": [""] * n,
            "Text": ["Sale at price %.2f per share." % (r.rand() * 100) if i % 3 else "Purchase at price 10.00 per share" for i in range(n)],
            "Insider": ["Insider %d" % (i % 9) for i in range(n)], "Position": ["Officer"] * n,
            "Transaction": [""] * n, "Start Date": [pd.Timestamp(today - timedelta(days=int(d))) for d in days],
            "Ownership": ["D"] * n, "Value": r.rand(n) * 1e7})

    @property
    def major_holders(self) -> pd.DataFrame:
        return pd.DataFrame({"Value": [0.02, 0.6, 0.61, 3500]},
                            index=["insidersPercentHeld", "institutionsPercentHeld", "institutionsFloatPercentHeld", "institutionsCount"])

    @property
    def institutional_holders(self) -> pd.DataFrame:
        n = 10
        return pd.DataFrame({"Date Reported": [pd.Timestamp("2026-09-30")] * n, "Holder": ["Holder %d" % i for i in range(n)],
                             "pctHeld": np.linspace(0.08, 0.01, n), "Shares": np.linspace(9e8, 1e8, n),
                             "Value": np.linspace(2e11, 2e10, n), "pctChange": np.linspace(-0.02, 0.03, n)})

    # estimates and ratings
    def _est(self, rows, cols) -> pd.DataFrame:
        return pd.DataFrame(np.full((len(rows), len(cols)), 1.5), index=rows, columns=cols)

    @property
    def eps_trend(self): return self._est(["0q", "+1q", "0y", "+1y"], ["current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo"])
    @property
    def eps_revisions(self): return self._est(["0q", "+1q", "0y", "+1y"], ["upLast7days", "upLast30days", "downLast7days", "downLast30days"])
    @property
    def growth_estimates(self): return self._est(["0q", "+1q", "0y", "+1y", "LTG"], ["stock", "industry", "sector", "index"])
    @property
    def earnings_estimate(self): return self._est(["0q", "+1q", "0y", "+1y"], ["avg", "low", "high", "yearAgoEps", "numberOfAnalysts", "growth"])
    @property
    def revenue_estimate(self): return self._est(["0q", "+1q", "0y", "+1y"], ["avg", "low", "high", "yearAgoRevenue", "numberOfAnalysts", "growth"])
    @property
    def analyst_price_targets(self): return {"current": _base_price(self.ticker), "high": 300.0, "low": 100.0, "mean": 200.0, "median": 205.0}

    @property
    def recommendations(self) -> pd.DataFrame:
        return pd.DataFrame({"period": ["0m", "-1m", "-2m", "-3m"], "strongBuy": [10] * 4, "buy": [20] * 4, "hold": [8] * 4,
                             "sell": [1] * 4, "strongSell": [0] * 4})

    @property
    def upgrades_downgrades(self) -> pd.DataFrame:
        n = 400
        idx = pd.DatetimeIndex([pd.Timestamp(d.isoformat(), tz="UTC") for d in _business_days(n, datetime.now(timezone.utc).date())])
        return pd.DataFrame({"Firm": ["Firm %d" % (i % 30) for i in range(n)], "ToGrade": ["Buy"] * n, "FromGrade": ["Hold"] * n,
                             "Action": ["up"] * n, "priceTargetAction": ["Raises"] * n,
                             "currentPriceTarget": np.linspace(100, 250, n), "priorPriceTarget": np.linspace(90, 240, n)}, index=idx)

    @property
    def earnings_dates(self) -> pd.DataFrame:
        idx = pd.DatetimeIndex([pd.Timestamp("2026-01-29 16:00", tz=NY) - pd.Timedelta(days=91 * i) for i in range(12)], name="Earnings Date")
        return pd.DataFrame({"EPS Estimate": 1.1, "Reported EPS": 1.2, "Surprise(%)": 9.0}, index=idx)

    @property
    def news(self) -> List[Dict[str, Any]]:
        r = _rng(self.ticker, "news")
        now = datetime.now(timezone.utc)
        return [{"id": "%s-%d" % (self.ticker, i), "content": {
            "id": "%s-%d" % (self.ticker, i), "contentType": "STORY",
            "title": "%s story %d: %s" % (self.ticker, i, "headline words " * int(r.randint(3, 9))),
            "summary": "Summary text for the story. " * 12, "pubDate": (now - timedelta(hours=i * 5)).isoformat(),
            "provider": {"displayName": "Synthetic Wire"}, "canonicalUrl": {"url": "https://example.invalid/%s/%d" % (self.ticker, i)}}}
            for i in range(14)]


class Search:
    def __init__(self, query, *a, **kw):
        self.query = str(query).upper()

    @property
    def news(self) -> List[Dict[str, Any]]:
        now = datetime.now(timezone.utc)
        return [{"uuid": "%s-s%d" % (self.query, i), "title": "%s search story %d" % (self.query, i), "publisher": "Synthetic Wire",
                 "link": "https://example.invalid/s/%s/%d" % (self.query, i), "providerPublishTime": int((now - timedelta(hours=i)).timestamp()),
                 "type": "STORY", "relatedTickers": [self.query]} for i in range(10)]

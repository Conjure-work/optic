"""Shared helpers for round three's chart journeys (Pass 3, 2026-11-23): the chart page drawn from fixtures.

Every bar here is invented (the fixtures in tests/e2e/fixtures.py and the daily history below), labelled as test data;
the feeds are refused at the closed port, so nothing live is read."""
from __future__ import annotations

import datetime as dt
import json
import math
import re

from tests.e2e.fixtures import QUOTES, route_intraday, route_price_history
from tests.e2e.test_pass1_journeys import DESKTOP, open_page

LISTED = {"AAPL": "1980-12-12"}


def daily_payload(sym, n=400, start="2025-01-02"):
    """Daily bars from `start`, shaped as /api/daily-bars answers, with its history block. Invented values."""
    base = QUOTES.get(sym, {"price": 100.0})["price"]
    d, dates = dt.date.fromisoformat(start), []
    while len(dates) < n:
        if d.weekday() < 5:
            dates.append(d.isoformat())
        d += dt.timedelta(days=1)
    close = [round(base * (0.7 + 0.3 * i / (n - 1)) + 4 * math.sin(i / 7.0), 2) for i in range(n)]
    opens = [close[0]] + close[:-1]
    listed = LISTED.get(sym)
    later = bool(listed and dates[0] > listed)
    from app.chart_routes import history_limit
    sentence = history_limit(sym, dates, listed=listed)["sentence"]
    return {"available": True, "ticker": sym, "dates": dates, "open": opens, "close": close,
            "high": [round(max(o, c) + 1, 2) for o, c in zip(opens, close)], "low": [round(min(o, c) - 1, 2) for o, c in zip(opens, close)],
            "volume": [2_000_000] * n, "bars": n,
            "history": {"first_bar": dates[0], "listed": listed, "later_than_listing": later, "adjusted": "split", "sentence": sentence}}


def route_daily(page, asked=None):
    def daily(route):
        sym = route.request.url.split("/api/daily-bars/", 1)[1].split("?", 1)[0].upper()
        if asked is not None:
            asked.append(sym)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(daily_payload(sym)))
    page.route(re.compile(r".*/api/daily-bars/[A-Za-z0-9.^=-]+(\?.*)?$"), daily)


def route_intraday_any(page):
    """Hourly bars for any symbol (the fixtures' own for the symbols they know)."""
    from tests.e2e.fixtures import intraday_payload
    route_intraday(page)

    def intraday(route):
        sym = route.request.url.split("/api/intraday/", 1)[1].split("?", 1)[0].upper()
        if sym in QUOTES:
            return route.fallback()
        p = intraday_payload("AAPL")
        p["symbol"] = sym
        route.fulfill(status=200, content_type="application/json", body=json.dumps(p))
    page.route(re.compile(r".*/api/intraday/[A-Za-z0-9.^=-]+(\?.*)?$"), intraday)


def full_ticker(sym):
    """The fixtures' ticker payload with open, high, low and volume beside its closes, as the daily chart reads them."""
    from tests.e2e.fixtures import ticker_payload
    p = ticker_payload(sym)
    ps = p["technicals"]["price_series"]
    c = ps["close"]
    ps["open"] = [c[0]] + c[:-1]
    ps["high"] = [round(max(o, x) + 1, 2) for o, x in zip(ps["open"], c)]
    ps["low"] = [round(min(o, x) - 1, 2) for o, x in zip(ps["open"], c)]
    ps["volume"] = [1_500_000] * len(c)
    return p


def route_full_ticker(page, extra=None):
    def ticker(route):
        sym = route.request.url.split("/api/ticker/", 1)[1].split("?", 1)[0].upper()
        if sym not in QUOTES:
            return route.fallback()
        p = full_ticker(sym)
        if extra:
            extra(p)
        route.fulfill(status=200, content_type="application/json", body=json.dumps(p))
    page.route(re.compile(r".*/api/ticker/[A-Za-z0-9.^=-]+(\?.*)?$"), ticker)


def chart_page(chrome, server, *, viewport=DESKTOP, store=None, cookies=None, sym="AAPL", level="advanced"):
    ctx, page = open_page(chrome, server, level=level, viewport=viewport, cookies=cookies, store=store)
    route_price_history(page)
    route_full_ticker(page)
    route_intraday_any(page)
    route_daily(page)
    page.goto(server["base"] + "/#/{}/chart".format(sym), wait_until="domcontentloaded")
    page.wait_for_selector("#ch-body .pc-svg", timeout=30000)
    return ctx, page


def drawing_count(page, scope):
    """How many drawings a chart draws: one .dr shape or more per drawing; an hline is exactly one line."""
    return page.eval_on_selector_all(scope + " .pc-svg line.dr", "els => els.length")


def axe(page):
    from axe_playwright_python.sync_playwright import Axe
    result = Axe().run(page, options={"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]}})
    return [{"id": v["id"], "impact": v["impact"], "nodes": [n["target"] for n in v["nodes"]][:4]} for v in result.response.get("violations", [])]

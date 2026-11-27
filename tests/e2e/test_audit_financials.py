"""Audit round 2026-11-27 (F03, F01) in a real browser: AAPL Financials, Overview and Home with fixed statements.

The statements are invented (tests/fixtures/audit_financials.py), served at the page's own /api/ticker boundary."""
from __future__ import annotations

import json
import re

from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import DESKTOP, open_page
from tests.fixtures import audit_financials as fx

PERIOD_KEY = "optic.v2.financials.period.v1"


def serve(page, payload):
    def ticker(route):
        if "/api/ticker/AAPL" not in route.request.url:
            return route.fallback()
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))
    page.route(re.compile(r".*/api/ticker/[A-Za-z0-9.^=-]+(\?.*)?$"), ticker)


def _financials(chrome, server, stub, payload, store=None):
    stub.reset("ok")
    _, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar, store=store or {})
    serve(page, payload)
    return ctx, page


def _quarters(chrome, server, stub, kind):
    ctx, page = _financials(chrome, server, stub, fx.ticker_payload_with(kind), {PERIOD_KEY: "quarter"})
    page.goto(server["base"] + "/#/AAPL/financials", wait_until="domcontentloaded")
    page.wait_for_selector("#fin-statements .fv-grid", timeout=30000)
    return ctx, page


def _view_data(page):
    page.locator("#fin-statements details.fv-data summary").click()
    return page.locator("#fin-statements details.fv-data table").inner_text()


def test_discrete_quarters_are_labelled_and_listed_with_their_periods(chrome, server, stub):
    ctx, page = _quarters(chrome, server, stub, "discrete")
    try:
        page.wait_for_selector("#main .chart-slot[data-chart='qcash'] svg")
        main = page.locator("#main").inner_text()
        assert "carry no quarterly cash flow" not in main
        assert "Quarters are in Cash flow by quarter, below." in main
        fig = page.locator("#main figure[data-v2-metric]", has=page.locator("h3", has_text=re.compile(r"^Cash flow by quarter$"))).inner_text()
        assert "Each bar is one fiscal quarter alone, three months, not the year to date." in fig
        assert "which is shown as cash out." in fig and "add up to the fiscal-year total." in fig
        table = _view_data(page)
        for row in ("Operating cash flow", "Capital expenditure", "Free cash flow"):
            assert row in table
        assert "Sep 30, 2025" in table and "$36" in table, table
        assert not page.errors
    finally:
        ctx.close()


def test_year_to_date_quarters_show_the_converted_values_and_say_so(chrome, server, stub):
    ctx, page = _quarters(chrome, server, stub, "year_to_date")
    try:
        page.wait_for_selector("#main .chart-slot[data-chart='qcash'] svg")
        fig = page.locator("#main figure[data-v2-metric]", has=page.locator("h3", has_text=re.compile(r"^Cash flow by quarter$"))).inner_text()
        assert "The statements give these year to date; each quarter here is that figure less the quarter before it in the same fiscal year." in fig
        table = _view_data(page)
        ocf = [l for l in table.split("\n") if l.startswith("Operating cash flow")][0]
        assert ocf.split("\t")[1:5] == ["$36", "$28", "$24", "$32"], ocf
        assert "Unavailable" in table, "the quarter with no predecessor on hand"
        assert not page.errors
    finally:
        ctx.close()


def test_without_quarterly_cash_flow_the_true_sentence_shows_and_no_quarterly_chart(chrome, server, stub):
    ctx, page = _quarters(chrome, server, stub, "none")
    try:
        main = page.locator("#main").inner_text()
        assert "The statements Optic reads carry no quarterly cash flow for AAPL." in main
        assert page.locator("#main .chart-slot[data-chart='qcash']").count() == 0
        assert not page.errors
    finally:
        ctx.close()

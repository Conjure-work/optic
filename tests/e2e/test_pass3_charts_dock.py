"""Round three in a real browser (Pass 3, 2026-11-23): the Charting dock. The side widgets stack as an accordion, one
open at a time unless pinned; with none open the chart takes the full width; the tool rail stays; Options opens inside
the dock with its readings, chain, builder, gamma and flow; Ask Milo stays in the top navigation. The chain and the
priced position come from fixtures (invented values, labelled as test data)."""
from __future__ import annotations

import json
import re

from tests.e2e.charts3 import axe, chart_page
from tests.e2e.test_pass1_journeys import DESKTOP, PHONE


def chain_payload(side, expiry="2026-12-18"):
    """A chain at one expiry, shaped as /api/options/{T}/research answers. Invented values."""
    rows = []
    for k, strike in enumerate(range(230, 271, 5)):
        d = round(0.92 - k * 0.1, 2) if side == "call" else round(-0.08 - k * 0.1, 2)
        rows.append({"strike": strike, "type": side, "expiry": expiry, "mid": round(3 + abs(d) * 10, 2), "delta": d,
                     "open_interest": 1000 + k * 50, "liquidity": {"grade": "tradable"}})
    return {"available": True, "expiry": expiry, "table": {"rows": rows}, "listed_expiries": [{"expiry": expiry, "dte": 25}]}


ANALYZED = {"entry": {"mid": 640.0}, "max_profit": 1860.0, "max_loss": -640.0, "breakevens_at_expiry": [251.4], "spot": 248.21}


def route_options(page, posted):
    def research(route):
        side = "put" if "side=put" in route.request.url else "call"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(chain_payload(side)))

    def analyze(route):
        posted.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=200, content_type="application/json", body=json.dumps(ANALYZED))
    page.route(re.compile(r".*/api/options/AAPL/research\?.*"), research)
    page.route(re.compile(r".*/api/options/AAPL/analyze$"), analyze)


def open_dock(chrome, server, viewport=DESKTOP):
    ctx, page = chart_page(chrome, server, viewport=viewport)
    posted = []
    route_options(page, posted)
    return ctx, page, posted


def open_ids(page):
    return page.eval_on_selector_all("#ch-side .chw", "els => els.map(e => e.dataset.chwPanel)")


def test_the_dock_opens_one_widget_at_a_time_holds_pinned_ones_and_gives_the_chart_the_width_when_empty(chrome, server):
    ctx, page, _ = open_dock(chrome, server)
    try:
        full = page.locator("#ch-body").bounding_box()["width"]
        assert page.is_hidden("#ch-side"), "nothing open to start"
        assert page.locator(".ch-draw[role='toolbar']").is_visible(), "the tool rail stays"
        page.click("[data-chw='news']")
        page.wait_for_selector("#chw-news")
        narrower = page.locator("#ch-body").bounding_box()["width"]
        assert narrower < full - 200, (full, narrower)
        page.click("[data-chw='levels']")
        page.wait_for_selector("#chw-levels")
        assert open_ids(page) == ["levels"], "one open at a time: News closed when Levels opened"
        page.click("[data-chw-pin='levels']")
        assert page.get_attribute("[data-chw-pin='levels']", "aria-pressed") == "true"
        page.click("[data-chw='stats']")
        page.wait_for_selector("#chw-stats")
        assert open_ids(page) == ["levels", "stats"], "a pinned widget stays open beside the next"
        page.click("[data-chw='news']")
        page.wait_for_selector("#chw-news")
        assert open_ids(page) == ["news", "levels"], "the unpinned one closed, the pinned one held"
        kept = json.loads(page.evaluate("() => localStorage.getItem('optic.v2.chart.v1')"))
        assert kept["pinned"] == ["levels"] and sorted(kept["dock"]) == ["levels", "news"]
        page.click("[data-chw-close='news']")
        page.click("[data-chw-close='levels']")
        page.wait_for_function("() => document.querySelector('#ch-side').hidden")
        page.wait_for_function(f"() => document.querySelector('#ch-body').getBoundingClientRect().width > {narrower + 200}")
        assert page.locator(".topbar-milo, [data-v2-topbar-milo], .topbar [data-v2-milo]").count() >= 1, "Ask Milo in the top navigation"
        assert page.locator(".ch-draw[role='toolbar']").is_visible()
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_options_open_inside_the_dock_with_readings_chain_builder_gamma_and_flow(chrome, server):
    ctx, page, posted = open_dock(chrome, server)
    try:
        page.click("[data-chw='options']")
        page.wait_for_selector("#chw-options [data-chw-optview]")
        views = page.eval_on_selector_all("#chw-options [data-chw-optview]", "els => els.map(e => e.textContent.trim())")
        assert views == ["Readings", "Chain", "Builder", "Gamma", "Flow"]
        assert page.get_attribute("#chw-options [data-chw-optview='readings']", "aria-pressed") == "true"
        page.click("#chw-options [data-chw-optview='chain']")
        page.wait_for_selector("#chw-options table caption:has-text('AAPL calls expiring 2026-12-18')")
        assert page.locator("#chw-options tbody tr").count() == 9
        page.click("#chw-options [data-chw-optside='put']")
        page.wait_for_selector("#chw-options table caption:has-text('AAPL puts')")
        page.click("#chw-options [data-chw-optview='builder']")
        page.click("#chw-options [data-chw-opttpl='bull_call']")
        page.wait_for_selector("#chw-options dt:has-text('Entry at the mid')", timeout=15000)
        body = page.inner_text("#chw-options")
        assert "$640.00 paid" in body and "$1,860.00" in body and "251.40" in body, body
        assert posted and [l["side"] for l in posted[0]["legs"]] == ["long", "short"], "a long call and a short call above it"
        assert posted[0]["legs"][0]["strike"] < posted[0]["legs"][1]["strike"]
        for v in ("gamma", "flow", "readings"):
            page.click(f"#chw-options [data-chw-optview='{v}']")
            page.wait_for_selector(f"#chw-options [data-chw-optview='{v}'][aria-pressed='true']")
        assert page.locator("#chw-options a[href='#/AAPL/options']").count() >= 1, "the full Options tab one link away"
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_the_dock_works_from_the_keyboard(chrome, server):
    ctx, page, _ = open_dock(chrome, server)
    try:
        page.focus("[data-chw='watchlist']")
        page.keyboard.press("ArrowDown")
        assert page.evaluate("() => document.activeElement.dataset.chw") == "alerts", "arrows move along the rail"
        page.keyboard.press("Enter")
        page.wait_for_selector("#chw-alerts")
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Space")
        page.wait_for_selector("#chw-news")
        assert open_ids(page) == ["news"]
        page.focus("[data-chw-pin='news']")
        page.keyboard.press("Enter")
        assert page.get_attribute("[data-chw-pin='news']", "aria-pressed") == "true"
        assert page.evaluate("() => document.activeElement.dataset.chwPin") == "news", "the focus stays on the pin"
        page.focus("[data-chw='levels']")
        page.keyboard.press("Enter")
        page.wait_for_selector("#chw-levels")
        assert sorted(open_ids(page)) == ["levels", "news"]
    finally:
        ctx.close()


def test_axe_finds_no_violation_with_the_dock_and_options_open(chrome, server):
    for viewport in (DESKTOP, PHONE):
        ctx, page, _ = open_dock(chrome, server, viewport)
        try:
            page.click("[data-chw='options']")
            page.wait_for_selector("#chw-options [data-chw-optview]")
            page.click("#chw-options [data-chw-optview='chain']")
            page.wait_for_selector("#chw-options table")
            page.wait_for_timeout(600)
            assert axe(page) == [], viewport
            assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), "no sideways scroll"
        finally:
            ctx.close()

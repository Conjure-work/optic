"""Round three in a real browser (Pass 3, 2026-11-23): the three trading layouts on Home's panel grid (Charts and
Technicals, Options and Derivatives, Portfolio), opened by name and from the rail's Research labels, with link groups and
the account's saved layouts working on them; the company grid as its own tab on the stock page; the holdings donut and
the sector treemap, each with its text alternative. The feeds are refused; the map and the book are fixtures (invented
values, labelled as test data)."""
from __future__ import annotations

import json
import re

import pytest

from tests.e2e.charts3 import axe
from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import DESKTOP, PHONE, open_page
from tests.e2e.test_pass2_axe import route_financials

PRESETS = {
    "technicals": ("Charts and Technicals", ["quote", "setup", "plan", "expression", "watch", "tearn"]),
    "derivatives": ("Options and Derivatives", ["quote", "vol", "contracts", "expression", "gex", "oflow"]),
    "positions": ("Portfolio", ["bookmix", "plans", "listsetups", "alerts", "watch"]),
}
BOOK = {"open": [{"id": "p1", "ticker": "AAPL", "instrument": "shares", "direction": "long", "qty": 10, "entry_price": 240},
                 {"id": "p2", "ticker": "MSFT", "instrument": "shares", "direction": "long", "qty": 4, "entry_price": 500},
                 {"id": "p3", "ticker": "NVDA", "instrument": "shares", "direction": "long", "qty": 5, "entry_price": 180}], "closed": []}


def stockmap_payload():
    names = [("XLK", "Technology", 9.1e9, 1.2), ("XLF", "Financials", 3.2e9, -0.4), ("XLV", "Health Care", 2.1e9, 0.3),
             ("XLY", "Consumer Discretionary", 1.9e9, -1.1), ("XLE", "Energy", 1.5e9, 0.8)]
    layout, x = [], 0.0
    total = sum(n[2] for n in names)
    for sym, name, dv, chg in names:
        w = 100 * dv / total
        layout.append({"symbol": sym, "name": name, "x": x, "y": 0, "w": w, "h": 100, "values": {"dollar_volume": dv, "chg_1d": chg}})
        x += w
    return {"template": {"id": "sector-today", "label": "Sectors today", "size": "dollar_volume", "color": "chg_1d"},
            "layout": layout, "rows": [{"symbol": l["symbol"], "name": l["name"], "values": l["values"]} for l in layout],
            "dropped": [], "colour_domain": {"min": -1.1, "max": 1.2}}


def route_stockmap(page):
    page.route(re.compile(r".*/api/stockmap\?.*"), lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps(stockmap_payload())))


def open_preset(page, server, preset, sym="AAPL"):
    page.goto(server["base"] + f"/#/?preset={preset}&symbol={sym}", wait_until="domcontentloaded")
    page.wait_for_selector("[data-ws-panel]:not([hidden])")
    return page


def shown(page):
    return page.eval_on_selector_all("[data-ws-panel]:not([hidden])", "els => els.map(e => e.dataset.wsPanel)")


@pytest.mark.parametrize("preset", list(PRESETS))
def test_each_trading_layout_opens_by_name_with_its_panels_and_link_groups(chrome, server, preset):
    label, panels = PRESETS[preset]
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, store={"optic.paper.v1": json.dumps(BOOK)})
    try:
        open_preset(page, server, preset)
        page.wait_for_selector(f"[data-ws-preset='{preset}'][aria-selected='true']")
        assert page.inner_text(f"[data-ws-preset='{preset}']").strip() == label
        got = shown(page)
        for p in panels:
            assert p in got, (p, got)
        if preset != "positions":
            # the linked panels follow the ticker the rail named, and a new one typed in the box above them
            page.wait_for_function("() => (document.querySelector(\"[data-ws-panel='quote'] [data-ws-sym]\") || {}).textContent.includes('AAPL')", timeout=20000)
            page.fill("#ws-link", "MSFT")
            page.press("#ws-link", "Enter")
            page.wait_for_function("() => (document.querySelector(\"[data-ws-panel='quote'] [data-ws-sym]\") || {}).textContent.includes('MSFT')", timeout=20000)
            linked = [p for p in panels if p in ("setup", "plan", "expression", "tearn", "vol", "contracts", "gex", "oflow")]
            for p in linked:
                assert "MSFT" in page.inner_text(f"[data-ws-panel='{p}'] [data-ws-sym]"), p
            # the chart moved to Gold keeps its ticker when Blue changes
            page.click("[data-ws-grp='quote']")
            page.wait_for_selector("[data-ws-grp='quote'].is-gold")
            page.fill("#ws-link", "NVDA")
            page.press("#ws-link", "Enter")
            page.wait_for_function(f"() => (document.querySelector(\"[data-ws-panel='{linked[-1]}'] [data-ws-sym]\") || {{}}).textContent.includes('NVDA')", timeout=20000)
            assert "MSFT" in page.inner_text("[data-ws-panel='quote'] [data-ws-sym]"), "Gold kept its own ticker"
        else:
            donut = page.locator("[data-ws-panel='bookmix'] svg.dn[role='img']")
            donut.wait_for(timeout=20000)
            words = donut.get_attribute("aria-label")
            assert "AAPL" in words and "MSFT" in words and "%" in words, words
            assert page.locator("[data-ws-panel='bookmix'] .dn-key li").count() == 3, "every share written beside it"
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_the_rails_research_labels_open_the_trading_layouts_on_the_company(chrome, server):
    ctx, page = open_page(chrome, server, level="beginner", viewport=DESKTOP)
    try:
        page.goto(server["base"] + "/#/AAPL", wait_until="domcontentloaded")
        page.wait_for_selector(".rail a:has-text('Charts & Technicals')")
        assert page.get_attribute(".rail a:has-text('Charts & Technicals')", "href") == "#/?preset=technicals&symbol=AAPL"
        assert page.get_attribute(".rail a:has-text('Options & Derivatives')", "href") == "#/?preset=derivatives&symbol=AAPL"
        page.click(".rail a:has-text('Options & Derivatives')")
        page.wait_for_selector("[data-ws-panel='contracts']")
        # shown whole at Beginner: the rail opened it by name
        got = shown(page)
        assert all(p in got for p in PRESETS["derivatives"][1]), got
        page.wait_for_function("() => (document.querySelector(\"[data-ws-panel='quote'] [data-ws-sym]\") || {}).textContent.includes('AAPL')", timeout=20000)
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_a_trading_layout_saved_on_the_account_opens_in_another_browser(chrome, server):
    _, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar)
    try:
        open_preset(page, server, "technicals")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click("[data-ws-edit]")
        page.wait_for_selector("#ws-named-name")
        page.fill("#ws-named-name", "My charts")
        with page.expect_response(lambda r: "/api/layouts/" in r.url and r.request.method == "PUT", timeout=15000) as put:
            page.click("[data-ws-named] button[type=submit]")
        assert put.value.status == 200, put.value.text()
        sent = json.loads(put.value.request.post_data)["layout"]["panels"]
        assert [p["id"] for p in sent if not p["hidden"]][:4] == ["quote", "setup", "plan", "expression"]
    finally:
        ctx.close()
    ctx2, page2 = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar)
    try:
        page2.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page2.wait_for_selector("[data-v2-account].avatar")
        page2.click("[data-ws-edit]")
        page2.wait_for_selector("text=Saved layouts (1)", timeout=15000)
        page2.click("text=Saved layouts (1)")
        page2.click("[data-ws-open-named='My charts']")
        page2.wait_for_selector("text=My charts is open as My Desk")
        assert "setup" in shown(page2) and "expression" in shown(page2)
    finally:
        ctx2.close()


def test_the_company_grid_is_its_own_tab_on_the_stock_page(chrome, server):
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP)
    try:
        page.goto(server["base"] + "/#/AAPL", wait_until="domcontentloaded")
        tab = page.locator("nav.tabs[data-v2-dtabs='AAPL'] a:has-text('Panels')")
        tab.wait_for(timeout=20000)
        assert tab.get_attribute("href") == "#/AAPL/workspace"
        tab.click()
        page.wait_for_selector(".ws-stock [data-ws-panel='quote']")
        assert page.get_attribute("nav.tabs[data-v2-dtabs='AAPL'] a:has-text('Panels')", "aria-current") == "page"
        assert page.locator(".ws-stock nav.tabs a:has-text('Chart')").count() == 1, "the company's other tabs one press away"
        assert not page.errors, page.errors
    finally:
        ctx.close()


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_the_sector_treemap_on_financials_has_its_text_alternative_and_no_axe_violation(chrome, server, viewport):
    ctx, page = open_page(chrome, server, level="advanced", viewport=viewport)
    route_financials(page)
    route_stockmap(page)
    try:
        page.goto(server["base"] + "/#/AAPL/financials", wait_until="domcontentloaded")
        svg = page.locator("#fin-sectors svg.smap[role='img']")
        svg.wait_for(timeout=30000)
        words = svg.get_attribute("aria-label")
        assert "Technology +1.20%" in words and "full table follows" in words, words
        assert page.locator("#fin-sectors table tbody tr").count() == 5
        assert "money traded through the sector's fund a day" in page.inner_text("#fin-sectors"), "what the tiles are sized by, said"
        page.wait_for_timeout(800)
        assert axe(page) == [], viewport
        assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        assert not page.errors, page.errors
    finally:
        ctx.close()


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
def test_axe_finds_no_violation_on_the_three_trading_layouts(chrome, server, viewport):
    ctx, page = open_page(chrome, server, level="advanced", viewport=viewport, store={"optic.paper.v1": json.dumps(BOOK)})
    try:
        for preset in PRESETS:
            open_preset(page, server, preset)
            page.wait_for_timeout(1500)
            assert axe(page) == [], (preset, viewport)
            assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), preset
        assert not page.errors, page.errors
    finally:
        ctx.close()

"""Round three in a real browser (Pass 3, 2026-11-23): one, two or four charts on the chart page, each with its own
ticker, bar size and range; the favourite bar sizes kept on the account and, signed out, in the browser; a drawing on
one chart redrawn on every other chart of that ticker within one frame; and a phone shown one or two charts, stacked.
Route-level checks are in tests/test_pass3_charts_routes.py; the pure parts in tests/test_pass3_charts_modules.py."""
from __future__ import annotations

import json
import sqlite3

from tests.e2e.charts3 import axe, chart_page, drawing_count
from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import DESKTOP, PHONE

LAYOUT_KEY = "optic.v2.chart.layout.v1"
INTERVALS_KEY = "optic.v2.chart.intervals.v1"


def slots(page):
    return page.eval_on_selector_all("[data-chg-slot]", "els => els.map(e => [e.dataset.chgSlot, e.dataset.chgSym])")


def wait_slot_drawn(page, i):
    page.wait_for_selector(f"[data-chg-slot='{i}'] .pc-svg", timeout=30000)


def test_one_two_and_four_charts_each_with_its_own_ticker_bar_size_and_range(chrome, server):
    ctx, page = chart_page(chrome, server)
    try:
        assert page.get_attribute("[data-v2-ch-count='1']", "aria-pressed") == "true"
        assert slots(page) == [], "one chart to start"
        page.click("[data-v2-ch-count='2']")
        wait_slot_drawn(page, 1)
        assert slots(page) == [["1", "SPY"]]
        page.click("[data-v2-ch-count='4']")
        for i in (1, 2, 3):
            wait_slot_drawn(page, i)
        assert [s[1] for s in slots(page)] == ["SPY", "QQQ", "IWM"]
        # chart 3 its own ticker, chart 2 its own bar size, chart 4 its own range
        page.fill("[data-chg-slot='2'] input[name='s']", "MSFT")
        page.press("[data-chg-slot='2'] input[name='s']", "Enter")
        page.wait_for_selector("[data-chg-slot='2'][data-chg-sym='MSFT'] .pc-svg", timeout=30000)
        page.select_option("[data-v2-chg-iv='1']", "60")
        page.wait_for_selector("[data-chg-slot='1'] .pc-svg", timeout=30000)
        page.select_option("[data-v2-chg-range='3']", "1Y")
        page.wait_for_selector("[data-chg-slot='3'] .pc-svg", timeout=30000)
        kept = json.loads(page.evaluate(f"() => localStorage.getItem('{LAYOUT_KEY}')"))
        assert kept["count"] == 4
        assert kept["slots"][0]["symbol"] == "AAPL" and kept["slots"][0]["interval"] == "60", "the page's own chart is the first"
        assert kept["slots"][1] == {"symbol": "SPY", "interval": "60", "range": "6M"}
        assert kept["slots"][2]["symbol"] == "MSFT" and kept["slots"][3]["range"] == "1Y"
        # each plot says what it is drawing
        assert "MSFT" in page.get_attribute("[data-chg-slot='2'] .pc-svg", "aria-label")
        # kept across a reload
        page.reload(wait_until="domcontentloaded")
        for i in (1, 2, 3):
            wait_slot_drawn(page, i)
        assert [s[1] for s in slots(page)] == ["SPY", "MSFT", "IWM"]
        page.click("[data-v2-ch-count='1']")
        page.wait_for_function("() => !document.querySelector('[data-chg-slot]')")
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_a_drawing_on_one_chart_is_redrawn_on_every_chart_of_that_ticker_within_one_frame(chrome, server):
    layout = {"count": 4, "slots": [{"symbol": "AAPL", "interval": "60", "range": "6M"}, {"symbol": "AAPL", "interval": "daily", "range": "6M"},
                                    {"symbol": "MSFT", "interval": "daily", "range": "6M"}, {"symbol": "AAPL", "interval": "60", "range": "6M"}]}
    ctx, page = chart_page(chrome, server, store={LAYOUT_KEY: json.dumps(layout)})
    try:
        for i in (1, 2, 3):
            wait_slot_drawn(page, i)
        assert drawing_count(page, "#ch-body") == 0 and drawing_count(page, "[data-chg-slot='1']") == 0
        page.click("[data-v2-tool='hline']")
        box = page.locator("#ch-body .pc-svg").bounding_box()
        # every chart redraws on its next animation frame (ui/pricechart.js redraw), the one drawn on as well; the copies
        # are handed the drawing in the same task as its commit, so all of them draw it on that same frame. Read at the
        # first frame after the click: a copy that waited longer would not be there yet.
        page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.35)
        counts = page.evaluate("""() => new Promise((ok) => requestAnimationFrame(() => { const n = (s) => document.querySelectorAll(s + ' .pc-svg line.dr').length;
            ok([n('#ch-body'), n("[data-chg-slot='1']"), n("[data-chg-slot='2']"), n("[data-chg-slot='3']")]); }))""")
        assert counts[0] == 1, counts
        assert counts[1] == 1 and counts[3] == 1, ("both other AAPL charts in the same frame", counts)
        assert counts[2] == 0, "the MSFT chart keeps its own drawings"
        # and the drawing is AAPL's, kept per ticker in the browser
        kept = json.loads(page.evaluate("() => localStorage.getItem('optic.chart.drawings.v2')"))
        assert len(kept["AAPL"]) == 1 and "MSFT" not in kept
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_favourite_bar_sizes_signed_out_stay_in_the_browser(chrome, server):
    ctx, page = chart_page(chrome, server)
    try:
        favs = page.eval_on_selector_all("#ch-favrow [data-v2-ch-fav]", "els => els.map(e => e.textContent.trim())")
        assert favs == ["5m", "1h", "1D"], "the default row"
        page.click("[data-ch-menu='favs'] > summary")
        page.check("[data-v2-ch-favset='15m']")
        page.uncheck("[data-v2-ch-favset='5m']")
        page.wait_for_function("() => [...document.querySelectorAll('#ch-favrow [data-v2-ch-fav]')].map(e => e.textContent.trim()).join() === '15m,1h,1D'")
        assert json.loads(page.evaluate(f"() => localStorage.getItem('{INTERVALS_KEY}')")) == ["15m", "1h", "1d"]
        # a favourite sets the chart's bar size
        page.click("#ch-favrow [data-v2-ch-fav='daily']")
        page.wait_for_function("() => document.querySelector('[data-v2-ch-iv]').value === 'daily'")
        assert page.get_attribute("#ch-favrow [data-v2-ch-fav='daily']", "aria-pressed") == "true"
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#ch-favrow [data-v2-ch-fav='15']")
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_favourite_bar_sizes_follow_the_account_to_another_browser(chrome, server):
    email, jar = make_account(server)
    ctx, page = chart_page(chrome, server, cookies=jar)
    try:
        page.wait_for_selector("[data-v2-account].avatar")
        page.click("[data-ch-menu='favs'] > summary")
        with page.expect_response(lambda r: r.url.endswith("/api/chart/intervals") and r.request.method == "PUT", timeout=15000) as put:
            page.check("[data-v2-ch-favset='4h']")
        assert put.value.status == 200
    finally:
        ctx.close()
    with sqlite3.connect(str(server["db"])) as c:
        stored = c.execute("SELECT p.favourite_intervals FROM user_preferences p JOIN users u ON u.id = p.user_id WHERE u.email = ?", (email,)).fetchone()[0]
    assert json.loads(stored) == ["5m", "1h", "4h", "1d"]
    # a second browser with none of its own takes the account's
    ctx2, page2 = chart_page(chrome, server, cookies=jar)
    try:
        page2.wait_for_selector("#ch-favrow [data-v2-ch-fav='240']", timeout=15000)
        assert json.loads(page2.evaluate(f"() => localStorage.getItem('{INTERVALS_KEY}')")) == ["5m", "1h", "4h", "1d"]
    finally:
        ctx2.close()


def test_a_saved_chart_layout_opens_from_the_account(chrome, server):
    _, jar = make_account(server)
    ctx, page = chart_page(chrome, server, cookies=jar)
    try:
        page.wait_for_selector("[data-v2-account].avatar")
        page.click("[data-v2-ch-count='2']")
        wait_slot_drawn(page, 1)
        page.click("[data-ch-menu='layouts'] > summary")
        page.fill("[data-v2-ch-laysave] input[name='n']", "Pair")
        with page.expect_response(lambda r: "/api/chart/layouts/Pair" in r.url and r.request.method == "PUT", timeout=15000) as put:
            page.click("[data-v2-ch-laysave] button[type='submit']")
        assert put.value.status == 200
        page.wait_for_selector("[data-v2-ch-layopen='Pair']")
    finally:
        ctx.close()
    ctx2, page2 = chart_page(chrome, server, cookies=jar)
    try:
        page2.wait_for_selector("[data-v2-account].avatar")
        assert page2.eval_on_selector_all("[data-chg-slot]", "els => els.length") == 0, "a fresh browser opens on one chart"
        page2.click("[data-ch-menu='layouts'] > summary")
        page2.click("[data-v2-ch-layopen='Pair']", timeout=15000)
        wait_slot_drawn(page2, 1)
        assert page2.get_attribute("[data-v2-ch-count='2']", "aria-pressed") == "true"
        assert not page2.errors, page2.errors
    finally:
        ctx2.close()


def test_a_phone_shows_one_or_two_charts_stacked_and_says_so_for_a_saved_four(chrome, server):
    four = {"count": 4, "slots": [{"symbol": s, "interval": "daily", "range": "6M"} for s in ("AAPL", "MSFT", "SPY", "QQQ")]}
    ctx, page = chart_page(chrome, server, viewport=PHONE, store={LAYOUT_KEY: json.dumps(four)})
    try:
        wait_slot_drawn(page, 1)
        assert page.eval_on_selector_all("[data-v2-ch-count]", "els => els.map(e => e.dataset.v2ChCount)") == ["1", "2"]
        assert page.get_attribute("[data-v2-ch-count='2']", "aria-pressed") == "true"
        assert [s[1] for s in slots(page)] == ["MSFT"], "the first two charts, the page's own and one more"
        note = page.inner_text("#ch-gridnote")
        assert "This layout has 4 charts; a screen this narrow shows the first two, stacked." in note
        main = page.locator("#ch-body").bounding_box()
        other = page.locator("[data-chg-slot='1']").bounding_box()
        assert other["y"] >= main["y"] + main["height"] - 1, "stacked, the second under the first"
        assert other["width"] <= 390 and page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), "no sideways scroll"
        # the saved four is kept for a wider window
        assert json.loads(page.evaluate(f"() => localStorage.getItem('{LAYOUT_KEY}')"))["count"] == 4
        assert not page.errors, page.errors
    finally:
        ctx.close()


def test_the_layout_control_and_the_favourites_work_from_the_keyboard(chrome, server):
    ctx, page = chart_page(chrome, server)
    try:
        page.focus("[data-v2-ch-count='1']")
        page.keyboard.press("Tab")
        assert page.evaluate("() => document.activeElement.dataset.v2ChCount") == "2"
        page.keyboard.press("Enter")
        wait_slot_drawn(page, 1)
        assert page.evaluate("() => document.activeElement.dataset.v2ChCount") == "2", "the focus stays on the control"
        page.keyboard.press("Tab")
        page.keyboard.press("Space")
        page.wait_for_selector("[data-v2-ch-count='4'][aria-pressed='true']")
        # a favourite by the keyboard on the second chart
        page.focus("[data-chg-slot='1'] [data-v2-ch-fav='60']")
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.querySelector(\"[data-v2-chg-iv='1']\").value === '60'")
        assert page.evaluate("() => document.activeElement.dataset.v2ChFav") == "60"
    finally:
        ctx.close()


def test_axe_finds_no_violation_with_four_charts_at_desktop_and_two_on_a_phone(chrome, server):
    four = {"count": 4, "slots": [{"symbol": s, "interval": "daily", "range": "6M"} for s in ("AAPL", "MSFT", "SPY", "QQQ")]}
    for viewport, n in ((DESKTOP, 3), (PHONE, 1)):
        ctx, page = chart_page(chrome, server, viewport=viewport, store={LAYOUT_KEY: json.dumps(four)})
        try:
            for i in range(1, n + 1):
                wait_slot_drawn(page, i)
            page.wait_for_timeout(800)
            assert axe(page) == [], viewport
            assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), "no sideways scroll"
        finally:
            ctx.close()

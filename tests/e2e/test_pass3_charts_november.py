"""Round three in a real browser (Pass 3, 2026-11-23): the chart changes from the owner's November review. Fibonacci
labels on the right with 0.5 and 0.618; the animated draw on the two line graphs (Line and Area), and none under reduced
motion; All reaching the whole daily history with the free feed's limit said under the chart. Bars and levels are
fixtures (invented values, labelled as test data)."""
from __future__ import annotations

import json
import re

from tests.e2e.charts3 import chart_page, route_daily, route_full_ticker

VIEW = "optic.v2.chart.v1"


def add_fib(p):
    closes = p["technicals"]["price_series"]["close"]
    hi, lo = max(closes[-126:]), min(closes[-126:])
    p["technicals"]["fibonacci"] = {"levels": [{"ratio": r, "label": "{:.1f}%".format(r * 100), "price": round(hi - (hi - lo) * r, 2),
                                                "is_golden": r in (0.5, 0.618)} for r in (0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0)]}


def with_fib(page):
    route_full_ticker(page, add_fib)


def test_fibonacci_labels_sit_on_the_right_with_half_and_the_golden_ratio(chrome, server):
    view = {"interval": "daily", "range": "6M", "overlays": {"fib": True}}
    ctx, page = chart_page(chrome, server, store={VIEW: json.dumps(view)})
    try:
        with_fib(page)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#ch-body .pc-svg text.lv-t.fib", timeout=30000)
        labels = page.eval_on_selector_all("#ch-body .pc-svg text.lv-t.fib", """els => els.map(e => ({ t: e.textContent, anchor: e.getAttribute('text-anchor'),
            x: e.getBBox().x + e.getBBox().width, w: e.ownerSVGElement.getBBox().width, gold: e.classList.contains('fib-gold') }))""")
        texts = [l["t"] for l in labels]
        assert any(t.startswith("0.5 ") for t in texts) and any(t.startswith("0.618 ") for t in texts), texts
        assert all(l["anchor"] == "end" for l in labels), "anchored at the right edge"
        plot_w = page.evaluate("() => document.querySelector('#ch-body .pc-svg').getBoundingClientRect().width")
        assert all(l["x"] > plot_w * 0.6 for l in labels), labels
        assert {l["t"].split(" ")[0] for l in labels if l["gold"]} == {"0.5", "0.618"}, "the golden pair set heavier"
        assert not any("%" in t for t in texts), "ratios, not percents"
        assert not page.errors, page.errors
    finally:
        ctx.close()


# Every animation started on the price line is counted as it starts (Element.animate), so a draw-on that finished
# before the check is still seen.
COUNT = """(() => { window.__plineAnims = 0; const a = Element.prototype.animate;
  Element.prototype.animate = function (...x) { if (this.classList && this.classList.contains('pline')) window.__plineAnims++; return a.apply(this, x); }; })();"""


def _seed(view):
    return "(() => { try { if (sessionStorage.getItem('e2e.v')) return; sessionStorage.setItem('e2e.v', '1'); localStorage.setItem('optic.v2.onboard.v1', 'done'); localStorage.setItem('optic.knowledge.v1', 'advanced'); localStorage.setItem('optic.knowledge.asked.v1', '1'); localStorage.setItem('%s', %s); } catch (e) {} })();" % (VIEW, json.dumps(json.dumps(view)))


def _open(chrome, server, view, reduced):
    from tests.e2e.charts3 import route_intraday_any
    from tests.e2e.fixtures import route_fixtures, route_price_history
    ctx = chrome.new_context(viewport={"width": 1440, "height": 900}, reduced_motion="reduce" if reduced else "no-preference")
    ctx.add_init_script(_seed(view))
    ctx.add_init_script(COUNT)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    route_fixtures(page)
    route_price_history(page)
    route_full_ticker(page)
    route_intraday_any(page)
    route_daily(page)
    page.goto(server["base"] + "/#/AAPL/chart", wait_until="domcontentloaded")
    page.wait_for_selector("#ch-body .pc-svg .pline", timeout=30000)
    return ctx, page, errors


def test_the_line_and_area_charts_draw_themselves_in_and_hold_still_under_reduced_motion(chrome, server):
    for style in ("line", "area"):
        view = {"interval": "daily", "range": "6M", "style": style}
        ctx, page, errors = _open(chrome, server, view, reduced=False)
        try:
            assert page.evaluate("() => window.__plineAnims") >= 1, ("the line traces itself in", style)
            assert not errors, errors
        finally:
            ctx.close()
        ctx, page, errors = _open(chrome, server, view, reduced=True)
        try:
            page.wait_for_timeout(300)
            assert page.evaluate("() => window.__plineAnims") == 0, ("still under reduced motion", style)
            assert not errors, errors
        finally:
            ctx.close()


def test_all_reaches_the_whole_daily_history_and_says_the_free_feeds_limit(chrome, server):
    view = {"interval": "daily", "range": "6M"}
    ctx, page = chart_page(chrome, server, store={VIEW: json.dumps(view)})
    try:
        asked = []
        page.on("request", lambda r: asked.append(r.url) if "/api/daily-bars/" in r.url else None)
        page.click("[data-v2-ch-range='All']")
        page.wait_for_function("() => /history here starts on/.test(document.querySelector('#ch-note').textContent)", timeout=30000)
        assert any("/api/daily-bars/AAPL" in u for u in asked), "All asks for the whole history"
        note = page.inner_text("#ch-note")
        # the page writes the server's dates as the reader reads them (core/format.js clean)
        assert "AAPL's history here starts on Jan 2, 2025" in note, note
        assert "AAPL listed on Dec 12, 1980, so the bars before Jan 2, 2025 are not in the free feed." in note, note
        assert "split-adjusted" in note
        assert "since the listing" not in note.lower(), "never claims more history than it drew"
        assert not page.errors, page.errors
    finally:
        ctx.close()

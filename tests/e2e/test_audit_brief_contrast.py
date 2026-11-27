"""Audit round, 2026-11-27: the earnings brief's headings (F08) and the saved toast's contrast, in a real browser.

F08: the brief arrives as paragraphs in which a heading is its own paragraph ("## The setup"). Finished (the POST), kept
(the GET when the page opens again) and printed, the headings are h3 elements and no paragraph starts with "#".

Contrast: a real action that shows the shared toast (Watch on a stock page: "AAPL added to ...", with an Undo button),
read at rest in each theme, text and button against the toast's own background, with opacity 1. The four figures are
printed; run with -s to see them.
"""
from __future__ import annotations

import json
import re

import pytest

from tests.e2e.test_pass1_journeys import DESKTOP, open_page, stock
from tests.e2e.test_pass3_investor_journeys import REVISIONS
from tests.e2e.visual_fixtures import _json, earnings_payload, route_company

PARAS = ["## The setup", "Reports in 12 days.", "### The track record ###", "Eight beats from eight.\n## Risks\nA fall is possible.", "##"]
BRIEF = {"available": True, "written": True, "can_write": False, "stance": "two-sided", "headline": "Beats every quarter, fades anyway",
         "paragraphs": PARAS, "generated_at": "2026-11-27T12:00:00Z", "written_by": "model", "method": "Test method.", "disclaimer": "Test disclaimer."}
UNWRITTEN = {"available": False, "written": False, "can_write": True, "reason": "No brief has been written for this report yet."}

SCAN = """() => {
  const sec = document.querySelector('#br-h').closest('section');
  return { heads: [...sec.querySelectorAll('h3.t-label')].map((e) => ({ text: e.textContent, shown: !!(e.offsetWidth || e.offsetHeight) })),
           paras: [...sec.querySelectorAll('p')].map((e) => e.textContent.trim()), body: sec.textContent };
}"""


def _route_brief(page, get_body):
    def brief(route):
        if route.request.method == "POST":
            return _json(route, BRIEF)
        _json(route, get_body())
    page.route(re.compile(r".*/api/earnings/AAPL/brief(\?.*)?$"), brief)
    page.route(re.compile(r".*/api/earnings/AAPL(\?.*)?$"), lambda r: _json(r, dict(earnings_payload(), revisions=REVISIONS)))


def _check(page):
    got = page.evaluate(SCAN)
    assert [h["text"] for h in got["heads"]] == ["The setup", "The track record", "Risks"], got
    assert all(h["shown"] for h in got["heads"]), got
    assert not [p for p in got["paras"] if p.startswith("#")], got
    assert "##" not in got["body"], got


def test_the_brief_headings_are_headings_when_finished_kept_and_printed(chrome, server):
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP)
    route_company(page)
    state = {"kept": UNWRITTEN}
    _route_brief(page, lambda: state["kept"])
    try:
        page.goto(server["base"] + "/#/AAPL/earnings", wait_until="domcontentloaded")
        page.get_by_role("button", name="Write the pre-earnings brief").click()
        page.wait_for_selector("section:has(#br-h) h3.t-label", timeout=20000)
        _check(page)                                    # finished
        state["kept"] = BRIEF
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("section:has(#br-h) h3.t-label", timeout=20000)
        _check(page)                                    # kept, read back when the page opens
        page.emulate_media(media="print")
        _check(page)                                    # printed
        assert not page.errors
    finally:
        ctx.close()


def _lum(rgb):
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = [x / 255 for x in rgb[:3]]
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def _ratio(fg, bg):
    a, b = sorted([_lum(fg), _lum(bg)], reverse=True)
    return (a + 0.05) / (b + 0.05)


READ = r"""() => {
  const el = document.querySelector('.toast.show'), b = el.querySelector('.toast-act');
  const rgb = (v) => { const m = /rgba?\(([^)]+)\)/.exec(v); const p = m ? m[1].split(',').map(Number) : []; return p.length === 4 && p[3] === 0 ? 'transparent' : p.slice(0, 3); };
  const cs = getComputedStyle(el), bs = b && getComputedStyle(b);
  return { text: el.textContent, theme: document.documentElement.dataset.theme,
           fg: rgb(cs.color), bg: rgb(cs.backgroundColor), opacity: Number(cs.opacity),
           act: b ? { fg: rgb(bs.color), bg: rgb(bs.backgroundColor), opacity: Number(bs.opacity), border: bs.borderTopColor } : null };
}"""


@pytest.mark.parametrize("theme,scheme,expect", [("light", "light", "ivory"), ("dark", "dark", "charcoal"), ("system", "dark", "charcoal")])
def test_the_saved_toast_and_its_button_read_at_aa_contrast_at_rest(chrome, server, theme, scheme, expect):
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, store={"optic.theme": theme})
    page.emulate_media(color_scheme=scheme)
    route_company(page)
    try:
        stock(page, server, "AAPL")
        page.locator("[data-v2-watch='AAPL']").first.click()
        page.wait_for_selector(".toast.show .toast-act", timeout=10000)
        page.wait_for_timeout(600)                      # the toast's own transition (--d) has finished
        got = page.evaluate(READ)
        assert got["theme"] == expect and "added to" in got["text"], got
        text_ratio = _ratio(got["fg"], got["bg"])
        # the button is transparent over the toast, so its text is read against the toast's background
        btn_ratio = _ratio(got["act"]["fg"], got["bg"])
        print(f"\ntoast contrast [{theme}/{scheme}]: text {text_ratio:.2f}:1, button {btn_ratio:.2f}:1, "
              f"opacity {got['opacity']}/{got['act']['opacity']}, bg {got['bg']}, fg {got['fg']}")
        assert got["opacity"] == 1 and got["act"]["opacity"] == 1, got
        assert got["act"]["bg"] == "transparent", got
        assert text_ratio >= 4.5 and btn_ratio >= 4.5, (text_ratio, btn_ratio, got)
    finally:
        ctx.close()

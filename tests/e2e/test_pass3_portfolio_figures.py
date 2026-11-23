"""Round three, carried item 1 on the Portfolio page: the holdings donut for a reader with no linked brokerage and the
sector treemap, each with its text alternative, and axe clean at both widths with both drawn.

The book is the Paper Desk kept in the browser; the sector map and the diversification read are labelled fixtures at
the page's own API boundary (the feeds are refused in the suite)."""

from __future__ import annotations

import json
import re

from tests.e2e.test_pass1_journeys import DESKTOP, PHONE, open_page
from tests.e2e.test_pass3_charts_presets import route_stockmap
from tests.e2e.test_pass3_investor_journeys import PAPER, RISK, _axe
from tests.e2e.visual_fixtures import _json


def _open(chrome, server, size):
    ctx, page = open_page(chrome, server, level="beginner", store={"optic.paper.v1": json.dumps(PAPER)}, viewport=size)
    page.route(re.compile(r".*/api/portfolio-risk.*"), lambda r: _json(r, RISK))
    route_stockmap(page)
    page.goto(server["base"] + "/#/portfolio", wait_until="domcontentloaded")
    page.wait_for_selector("[data-v2-donut]", timeout=20000)
    page.wait_for_selector("[data-v2-treemap] svg.smap", timeout=20000)
    return ctx, page


def test_the_portfolio_page_draws_the_paper_desk_donut_and_the_sector_treemap_with_text(chrome, server):
    ctx, page = _open(chrome, server, DESKTOP)
    try:
        donut = page.locator("[data-v2-donut]")
        assert "Your Paper Desk by value" in donut.inner_text()
        label = page.get_attribute("[data-v2-donut] svg.dn", "aria-label")
        assert label and "AAPL" in label and "%" in label, label
        legend = page.eval_on_selector_all("[data-v2-donut] .dn-key li", "els => els.map(e => e.textContent.trim())")
        assert len(legend) >= 2, legend
        tm = page.locator("[data-v2-treemap]")
        assert page.get_attribute("[data-v2-treemap] svg.smap", "aria-label").startswith("Sector funds sized by")
        assert tm.locator("table").count() == 1, "the treemap's table alternative"
        heads = page.eval_on_selector_all("#main h2", "els => els.map(e => e.textContent.trim())")
        assert heads.index("Your Paper Desk") < heads.index("Optic's model portfolios"), heads
        assert not page.errors
    finally:
        ctx.close()


def test_the_portfolio_figures_have_no_axe_violation_at_both_widths(chrome, server):
    for size in (DESKTOP, PHONE):
        ctx, page = _open(chrome, server, size)
        try:
            violations = _axe(page)
            assert violations == [], (size, violations)
            width = page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert width <= 0, (size, "no sideways scroll", width)
        finally:
            ctx.close()

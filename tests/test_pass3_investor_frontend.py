"""Round three's Investor mode, the front end's own logic run in JavaScriptCore and its contracts read as text (the
project's pattern, CLAUDE.md): the three kinds of alert in one shape, the reader's books in order, the calendar's
session lines in the reader's zone, the first visit at Beginner, the owner report's counts-only rule, the separate-pages
setting, the saved line, and the three accessibility items. The journeys are tests/e2e/test_pass3_investor_journeys.py."""
from __future__ import annotations

import re

from tests.test_frontend_v2_stage0 import V2, _run

JS = V2 / "js"


def test_the_three_kinds_of_alert_are_drawn_one_way_and_counted_per_name(tmp_path):
    got = _run(tmp_path, f"""
      const m = await import('{(JS / "core/allalerts.js").as_posix()}');
      const items = m.normalise({{
        watches: [{{ id: 'w1', symbol: 'aapl', condition: 'Price rises above $250', active: true }}, {{ id: 'w2', symbol: 'MSFT', active: false }}],
        hits: [{{ id: 'h1', symbol: 'AAPL', title: 'AAPL crossed $250', created_at: '2026-11-23T15:00:00Z' }}],
        book: [{{ id: 1, ticker: 'NVDA', title: 'Opened a position', created_at: '2026-11-22T15:00:00Z' }}],
        brokerage: [{{ id: 'b1', symbol: 'AAPL', title: 'AAPL is 40% of the account', created_at: '2026-11-21T15:00:00Z' }}],
      }});
      const by = m.bySymbol(items, '2026-11-23');
      print(JSON.stringify({{ kinds: items.map((x) => x.kind), keys: Object.keys(items[0]).sort(), by, first: m.ordered(items).map((x) => x.id) }}));
    """)
    assert got["kinds"] == ["yours", "yours", "yours", "optic", "brokerage"]
    assert got["keys"] == ["active", "at", "fired", "id", "kind", "symbol", "title"], "one shape for all three"
    assert got["by"]["AAPL"] == {"yours": 1, "optic": 0, "brokerage": 1, "fired": 1}
    assert got["by"]["MSFT"] == {"yours": 0, "optic": 0, "brokerage": 0, "fired": 0}, "a paused alert is not counted"
    assert got["by"]["NVDA"]["optic"] == 1
    assert got["first"][:3] == ["h:h1", "o:1", "b:b1"], "fired first, newest first; standing conditions last"


def test_the_readers_books_come_first_brokerage_then_the_paper_desk(tmp_path):
    got = _run(tmp_path, f"""
      const m = await import('{(JS / "pages/portfolio.js").as_posix()}');
      print(JSON.stringify({{ linked: m.readerBooks({{ brokerageLinked: true, paperCount: 2 }}), none: m.readerBooks({{ brokerageLinked: false, paperCount: 0 }}),
        pos: m.asPositions([{{ symbol: 'VOO', quantity: 3, price: 500 }}], 'brokerage') }}));
    """)
    assert got["linked"]["books"] == ["brokerage", "paper"]
    assert got["linked"]["line"].startswith("Your books: your linked brokerage, then your Paper Desk (2 open)")
    assert got["none"]["books"] == ["paper"] and "No brokerage is linked" in got["none"]["line"]
    for b in (got["linked"], got["none"]):
        assert "Optic's model portfolios are below, and they are Optic's, not yours." in b["line"]
    assert got["pos"] == [{"ticker": "VOO", "qty": 3, "entry_price": 500, "instrument": "shares"}]


def test_the_calendar_says_each_session_in_the_readers_zone(tmp_path):
    got = _run(tmp_path, f"""
      const m = await import('{(JS / "pages/calendar.js").as_posix()}');
      const half = {{ status: 'early_close', name: 'the day after Thanksgiving', opens: '2026-11-27T09:30:00-05:00', closes: '2026-11-27T13:00:00-05:00' }};
      print(JSON.stringify({{ ny: m.sessionLine(half, 'America/New_York'), la: m.sessionLine(half, 'America/Los_Angeles'),
        hol: m.sessionLine({{ status: 'holiday', name: 'Thanksgiving Day' }}, 'UTC'), wk: m.sessionLine({{ status: 'weekend' }}, 'UTC') }}));
    """)
    assert got["ny"] == "Early close: 9:30 am to 1:00 pm (the day after Thanksgiving)"
    assert got["la"] == "Early close: 6:30 am to 10:00 am (the day after Thanksgiving)"
    assert got["hol"] == "Closed, Thanksgiving Day" and got["wk"] == "Closed, weekend"


def test_the_navigation_names_portfolio_the_model_books_and_the_calendar():
    nav = (JS / "nav.js").read_text()
    assert "{ id: 'portfolio', label: 'Portfolio'" in nav
    assert "{ view: 'portfolio', label: 'Your books', slug: 'portfolio', v2: true }" in nav
    assert "{ view: 'tracker', label: 'Optic’s model portfolios', slug: 'models', v2: true }" in nav
    assert "{ view: 'calendar', label: 'Calendar', slug: 'calendar', v2: true }" in nav
    assert "{ view: 'ownerreport', label: 'Owner report', slug: 'owner-report', v2: true }" in nav
    app = (JS / "app.js").read_text()
    assert "portfolio: P.portfolio, calendar: P.calendar, welcome: P.levelquiz" in app


def test_the_separate_pages_setting_is_read_from_health_and_restores_both_pages():
    flag = (JS / "core/investorpages.js").read_text()
    assert "investor_pages" in flag and "'separate pages'" in flag and "known = false" in flag, "unknown reads as one place"
    pf = (JS / "pages/portfolio.js").read_text()
    assert "if (await separate())" in pf and "import('./tracker.js')" in pf
    al = (JS / "pages/alerts.js").read_text()
    assert "sep ? 'Alerts' : 'Watchlist'" in al


def test_the_owner_report_page_draws_counts_only():
    src = (JS / "pages/reports.js").read_text()
    block = src[src.index("/* ---------------- the owner report"):src.index("/* ---------------- end of the owner report")]
    assert "%" not in block and "pct" not in block
    assert "['owner_kind', 'owner_id'].forEach" in src, "the group in the address is passed to the server"
    assert "modesBlock()" in src and "Object.keys(m)" in src, "the Metrics page lists whatever modes are registered"


def test_a_first_visit_is_at_beginner_on_both_sides():
    assert "const DEFAULT_MODE = 'beginner';" in (JS / "core/prefs.js").read_text()
    from app import knowledge
    assert knowledge.DEFAULT_MODE == "beginner"


def test_the_sign_up_form_leads_to_the_questions_and_every_sign_in_may_offer_them():
    si = (JS / "pages/signin.js").read_text()
    assert "p.next = `#/welcome?next=${encodeURIComponent(p.next || '#/')}`;" in si
    app = (JS / "app.js").read_text()
    assert "if (store.signedIn()) P.levelquiz().then((m) => m.offer())" in app
    lq = (JS / "pages/levelquiz.js").read_text()
    assert "data-v2-lq-skip" in lq and "data-v2-lq-continue" in lq and "lq-btn" in lq
    css = (V2 / "css" / "pages.css").read_text()
    assert ".lq-btn { min-width: 9.5rem; min-height: 44px;" in css, "Skip and Continue are one size"
    assert "drawer" not in lq and 'role="dialog"' not in lq and "aria-modal" not in lq, "no modal: the questions are a page and a band"


def test_the_saved_line_sits_beside_the_layout_form_until_the_next_change():
    ws = (JS / "pages/workspace.js").read_text()
    assert '<p class="ws-named-said" role="status" data-ws-named-said>${namedSaid}</p></form>' in ws
    assert "namedSaid = r.replaced ? `Saved: ${r.name} is updated on your account.` : `Saved: ${r.name} is on your account.`;" in ws
    assert "if (namedSaid) { namedSaid = '';" in ws


def test_the_source_lines_read_as_sentences(tmp_path):
    src = (JS / "pages/financials.js").read_text()
    assert "Source: ${sourceText(s)}" in src
    line = src[src.index("export const sourceText"):src.index("\n", src.index("export const sourceText"))]
    got = _run(tmp_path, f"const sourceText = {line.split('=', 1)[1].strip().rstrip(';')}; print(JSON.stringify([sourceText(\"the company's 10-Q\"), sourceText('The company')]));")
    assert got == ["The company's 10-Q", "The company"]


def test_the_three_accessibility_items():
    earn = (JS / "pages/earnings.js").read_text()
    rv = earn[earn.index("function revisions(sym)"):earn.index("// A growth table")]
    assert 'tabindex="0" role="region" aria-label="Estimate revisions by period, table"' in rv and "<caption" in rv
    tok = (V2 / "css" / "tokens.css").read_text()
    assert "--c-toast-bad: #8e2b1b;" in tok
    assert '.toast[data-kind="bad"] { background: var(--c-toast-bad); color: var(--c-on-scene); }' in (V2 / "css" / "pages.css").read_text()
    align = (JS / "ui/align.js").read_text()
    assert "function distinct(root)" in align and "distinct(root);" in align and "[head, sum].filter(Boolean).join(': ')" in align


def test_toast_failure_kind_contrast_is_aa_against_its_text():
    def lum(h):
        r, g, b = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
    tok = (V2 / "css" / "tokens.css").read_text()
    bad = re.search(r"--c-toast-bad: (#[0-9a-f]{6})", tok).group(1)
    on = re.search(r"--c-on-scene: (#[0-9a-f]{6})", tok).group(1)
    a, b = sorted([lum(bad), lum(on)], reverse=True)
    assert (a + 0.05) / (b + 0.05) >= 4.5

"""F01 class (audit 2026-11-27) in a real browser: the full insider history on AAPL Financials for each state the
server can answer with. The history route is stubbed at the page's own boundary with invented payloads; the ticker
payload is the audit fixture."""
from __future__ import annotations

import json
import re

import pytest

from tests.e2e.test_audit_financials import _financials
from tests.fixtures import audit_financials as fx

SINCE = "2021-11-29"
TAIL = "Awards, option exercises, tax withholding and gifts are not trades and are left out."


def _sale(day):
    return {"insider": "A. INSIDER", "position": "Director", "date": day, "shares": 100.0, "value": 12500.0, "action": "sale",
            "source": "yahoo", "detail": "Sale"}


def _history(state, rows=(), **cov):
    return {"ticker": "AAPL", "years": 5, "since": SINCE, "rows": list(rows),
            "coverage": dict({"state": state, "covered_to": "2026-11-28", "covered_from": None, "yahoo_rows": 0, "sec_rows": 0,
                              "sec_unread": 0, "complete": state == "complete", "none": False}, **cov)}


def _open(chrome, server, stub, payloads):
    """`payloads` is served one per request, the last repeated; returns the context, page and the request count."""
    ctx, page = _financials(chrome, server, stub, fx.ticker_payload_with("discrete"))
    seen = []

    def history(route):
        seen.append(route.request.url)
        body = payloads[min(len(seen), len(payloads)) - 1]
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))
    page.route(re.compile(r".*/api/insiders/AAPL/history.*"), history)
    page.goto(server["base"] + "/#/AAPL/financials", wait_until="domcontentloaded")
    page.wait_for_selector("#fin-ih p", timeout=30000)
    return ctx, page, seen


def _text(page):
    return page.locator("#fin-ih").inner_text()


def test_an_unavailable_history_says_so_and_draws_no_table_or_none_sentence(chrome, server, stub):
    ctx, page, _ = _open(chrome, server, stub, [_history("unavailable", why="sec_unreachable")])
    try:
        page.wait_for_function("() => document.querySelector('#fin-ih').innerText.includes('unavailable right now')")
        t = _text(page)
        assert "Insider trades from Nov 29, 2021 to Nov 28, 2026 are unavailable right now. That is not the same as no activity." in t
        assert "The SEC's filing list could not be reached this time, so the period is not covered." in t
        assert "No open-market purchases" not in t and "Complete for the period" not in t
        assert page.locator("#fin-ih table").count() == 0 and page.locator("#fin-ih [data-fin-ih]").count() == 3
        assert not page.errors
    finally:
        ctx.close()


def test_a_partial_history_keeps_its_rows_and_names_the_dates_it_covers(chrome, server, stub):
    ctx, page, _ = _open(chrome, server, stub, [_history("partial", [_sale("2026-09-01")], covered_from="2024-11-28", yahoo_rows=1,
                                                         why="sec_unreachable")])
    try:
        page.wait_for_function("() => document.querySelector('#fin-ih').innerText.includes('is partial')")
        t = _text(page)
        assert "0 open-market purchases and 1 sale found so far. This list is partial: it covers Nov 28, 2024 to Nov 28, 2026, not the full period from Nov 29, 2021." in t
        assert page.locator("#fin-ih table tbody tr").count() == 1
        assert "The SEC's filing list could not be reached this time, so trades before Nov 28, 2024 are not shown." in t
        assert "Complete for the period" not in t
        assert not page.errors
    finally:
        ctx.close()


def test_a_complete_and_empty_history_says_every_filing_was_read(chrome, server, stub):
    ctx, page, _ = _open(chrome, server, stub, [_history("complete", none=True, sec_filings=4, listed=True, yahoo_rows=0, sec_rows=0)])
    try:
        page.wait_for_function("() => document.querySelector('#fin-ih').innerText.includes('Every Form 4')")
        t = _text(page)
        assert "No open-market purchases or sales by insiders from Nov 29, 2021 to Nov 28, 2026. Every Form 4 filed in the period was read." in t
        assert "Complete for the period." in t and TAIL in t
        assert not page.errors
    finally:
        ctx.close()


def test_a_first_visit_reads_then_settles_on_what_the_second_answer_says(chrome, server, stub):
    """Reading is polled (a pending SEC list too, not only unread filings) and never settles on "none"."""
    ctx, page, seen = _open(chrome, server, stub, [_history("reading", list_pending=True, listed=False),
                                                   _history("unavailable", why="sec_unreachable")])
    try:
        first = _text(page)
        assert 'Insider trades since Nov 29, 2021 are still being read. Nothing is shown as "none" until the read finishes.' in first
        assert "The SEC's list of Form 4 filings is being read; this table fills in as it is." in first
        assert page.locator("#fin-ih p.asof[role='status']").count() == 1
        assert "No open-market purchases" not in first
        # the page asks again on its own timer; make the wait short rather than wait fifteen seconds
        page.wait_for_function("() => document.querySelector('#fin-ih').innerText.includes('unavailable right now')", timeout=40000)
        assert len(seen) >= 2 and "No open-market purchases" not in _text(page)
        assert not page.errors
    finally:
        ctx.close()

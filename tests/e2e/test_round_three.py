"""Round three of Pass 3's gauntlet (CON-58, 2026-11-25): the four defects of the operator's provisional verdict, each
in a real browser against the real server.

- D1: Milo's strip control says what Milo really is, whoever opened or closed it (the top bar's Ask Milo, the strip,
  the panel's own close).
- D2: the server keeps answering while a scheduled market-data batch runs on a small, slow machine
  (tests/support/small_machine), and a stance ask that failed is asked again and corrects the panel.
- D3: the rail entry that opened a trading layout on Home is the current one, and Home is not.
"""
from __future__ import annotations

import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import DESKTOP, PHONE, open_page

ROOT = Path(__file__).resolve().parents[2]
KEPT = "As kept: a conservative investor's reading"


def _signed_in(chrome, server, viewport=DESKTOP):
    _, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", viewport=viewport, cookies=jar)
    return ctx, page, jar


def _strip(page):
    return page.evaluate("""() => { const t = document.querySelector('[data-v2-milo-strip-toggle]');
      const s = document.querySelector('[data-v2-milo-strip]');
      return { label: t.textContent.trim(), expanded: t.getAttribute('aria-expanded'), state: s.dataset.state,
               open: !!document.querySelector('.drawer-milo.is-open'), focused: document.activeElement === t }; }""")


# ------------------------------------------------------------------------------------------------------------ D1

def test_the_strip_follows_milo_opened_from_the_top_bar_then_collapses_it(chrome, server):
    ctx, page, _ = _signed_in(chrome, server)
    try:
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.wait_for_selector("[data-v2-milo-strip-toggle]")
        assert _strip(page)["label"] == "Open Milo" and _strip(page)["expanded"] == "false"
        # opened from the top bar's Ask Milo: the strip says so at once
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-q")
        page.wait_for_function("() => document.querySelector('[data-v2-milo-strip-toggle]').getAttribute('aria-expanded') === 'true'", timeout=5000)
        s = _strip(page)
        assert (s["label"], s["expanded"], s["state"], s["open"]) == ("Collapse Milo", "true", "open", True), s
        # the strip's control, pressed: Milo collapses, the control says Open Milo and keeps the focus
        page.click("[data-v2-milo-strip-toggle]")
        page.wait_for_function("() => !document.querySelector('.drawer-milo.is-open')", timeout=5000)
        s = _strip(page)
        assert (s["label"], s["expanded"], s["state"], s["focused"]) == ("Open Milo", "false", "strip", True), s
        # and opens it again from the keyboard
        page.keyboard.press("Enter")
        page.wait_for_selector(".drawer-milo.is-open #milo-q")
        s = _strip(page)
        assert (s["label"], s["expanded"]) == ("Collapse Milo", "true"), s
        # closed by the panel's own close button: the strip says Open Milo again
        page.click(".drawer-milo [data-v2-close]")
        page.wait_for_function("() => document.querySelector('[data-v2-milo-strip-toggle]').getAttribute('aria-expanded') === 'false'", timeout=5000)
        assert _strip(page)["label"] == "Open Milo"
        # opened from the top bar once more, then the strip collapses it in one press (the defect: it needed two)
        page.click(".topbar-milo")
        page.wait_for_selector(".drawer-milo.is-open #milo-q")
        page.click("[data-v2-milo-strip-toggle]")
        page.wait_for_function("() => !document.querySelector('.drawer-milo.is-open')", timeout=5000)
        assert _strip(page)["label"] == "Open Milo"
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


def test_the_strip_follows_milo_across_a_page_change(chrome, server):
    ctx, page, _ = _signed_in(chrome, server)
    try:
        page.goto(server["base"] + "/#/AAPL", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click(".topbar-milo")
        page.wait_for_selector(".drawer-milo.is-open #milo-q")
        page.evaluate("() => { location.hash = '#/AAPL/financials'; }")
        page.wait_for_function("() => document.querySelector('[data-v2-milo-strip]').dataset.v2MiloScreen === 'financials'", timeout=20000)
        s = _strip(page)
        assert (s["label"], s["expanded"], s["open"]) == ("Collapse Milo", "true", True), s
    finally:
        ctx.close()


# ------------------------------------------------------------------------------------------------------------ D2

def _keep_stoic(page):
    csrf = next(c["value"] for c in page.context.cookies() if c["name"].lower().endswith("csrf"))
    status = page.evaluate("async (t) => (await fetch('/api/milo/stance', { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Optic-CSRF': t }, body: JSON.stringify({ stance: 'stoic' }) })).status", csrf)
    assert status == 200


def test_a_failed_stance_ask_is_asked_again_and_corrects_the_panel(chrome, server):
    """syncStance ran once per page and never again after a failure, so a panel opened then kept the default stance."""
    ctx, page, jar = _signed_in(chrome, server)
    try:
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        _keep_stoic(page)
    finally:
        ctx.close()
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar)
    refused = []

    def refuse_twice(route):
        if route.request.method == "GET" and len(refused) < 2:
            refused.append(time.monotonic())
            route.abort("connectionreset")
        else:
            route.continue_()
    page.route("**/api/milo/stance", refuse_twice)
    try:
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-stance-once")
        page.wait_for_function("k => (document.querySelector('#milo-stance-once option') || {}).textContent === k", arg=KEPT, timeout=20000)
        assert len(refused) == 2, "the first two asks were refused and a third was made"
    finally:
        ctx.close()


MARK = Path(tempfile.mkdtemp(prefix="optic-small-machine-")) / "job-downloads"
SMALL = {"PYTHONPATH": os.pathsep.join([str(ROOT / "tests" / "support" / "small_machine"), str(ROOT)]),
         "SMALL_MACHINE_CPUS": "2", "SMALL_MACHINE_JOB_SECONDS_PER_NAME": "0.25", "SMALL_MACHINE_MARK": str(MARK)}


LOCK_READERS = ["MSFT", "NVDA", "AMZN", "META", "TSLA", "AVGO", "COST", "PEP"]


def _job_names():
    if not MARK.exists():
        return 0
    return sum(int(line.split()[1]) for line in MARK.read_text().splitlines() if line.strip())


def _get(url, timeout):
    t0 = time.monotonic()
    with urllib.request.urlopen(url, timeout=timeout) as r:
        r.read()
        return r.status, time.monotonic() - t0


@pytest.mark.parametrize("server", [SMALL], indirect=True)
def test_the_server_keeps_answering_while_a_scheduled_batch_runs_on_a_small_machine(chrome, server):
    """The stall CI found (e2e-4, 2026-11-24): on a two-CPU runner a scheduled batch held the provider lock for about
    26 s, the readers' legs filled the loop's six default threads, the browser's six connections were all held by them,
    and the Milo panel opened then showed the default stance. Here the server runs as that machine (two CPUs, a job's
    batch download 0.25 s a name) and the journey opens Milo while a job's batch is downloading."""
    ctx, page, jar = _signed_in(chrome, server)
    try:
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        _keep_stoic(page)
        # the ranking's batch is under way: Home's movers start it in the jobs' lane, about a hundred names, as on CI
        # (the warm-up's smaller batches count too); proceed once 60 names' worth of job downloads have started
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline and _job_names() < 60:
            time.sleep(0.2)
        assert _job_names() >= 60, "the scheduled batch did not start within 90 s ({} names)".format(_job_names())
        # readers that need the provider lock, eight at once, each a company's setup detail (one batch download each):
        # on a two-CPU machine they were enough to fill the loop's six default threads while the batch held the lock
        held = []

        def reader(sym):
            try:
                held.append(_get(server["base"] + "/api/setups/{}/detail?preset=trend_pullback".format(sym), 90))
            except urllib.error.HTTPError as exc:                 # no history behind the closed port: a 404, answered
                held.append((exc.code, None))
            except Exception as exc:                              # noqa: BLE001 - recorded, judged below
                held.append((None, repr(exc)))
        readers = [threading.Thread(target=reader, args=(s,), daemon=True) for s in LOCK_READERS]
        for t in readers:
            t.start()
        time.sleep(1.0)
        # from outside, while they wait: a route with no thread, and routes through the readers' pool that need no
        # provider (the account's stance, the research archive)
        for path in ("/api/personas", "/api/research-book", "/api/delays"):
            status, took = _get(server["base"] + path, 30)
            print("STALL_PROBE {} {} {:.2f}s, job names {}".format(path, status, took, _job_names()))
            assert status == 200 and took < 2.0, "{} took {:.1f}s while the batch ran".format(path, took)
        # and in a browser: Milo opened now shows the stance kept on the account
        ctx2, page2 = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar)
        try:
            t0 = time.monotonic()
            page2.goto(server["base"] + "/#/", wait_until="domcontentloaded")
            page2.wait_for_selector("[data-v2-account].avatar", timeout=15000)
            page2.click(".topbar-milo")
            page2.wait_for_function("k => (document.querySelector('#milo-stance-once option') || {}).textContent === k", arg=KEPT, timeout=15000)
            print("STALL_PROBE stance shown after {:.1f}s".format(time.monotonic() - t0))
            assert not page2.errors, page2.errors[:3]
        finally:
            ctx2.close()
        for t in readers:
            t.join(90)
        assert len(held) == len(LOCK_READERS) and all(h[0] in (200, 404) for h in held), held
    finally:
        ctx.close()


# ------------------------------------------------------------------------------------------------------------ D3

def _current(page, scope=".rail"):
    return page.evaluate("s => [...document.querySelectorAll(s + ' [aria-current=\"page\"]')].map(a => a.textContent.trim())", scope)


@pytest.mark.parametrize("label,preset", [("Charts & Technicals", "technicals"), ("Options & Derivatives", "derivatives")])
def test_the_rail_entry_that_opened_a_trading_layout_is_current_and_home_is_not(chrome, server, label, preset):
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP)
    try:
        page.goto(server["base"] + "/#/AAPL", wait_until="domcontentloaded")
        # the company page drawn first (its rail marks Company Overview), so the press is on a settled page
        page.wait_for_function("() => [...document.querySelectorAll('.rail [aria-current=\"page\"]')].map(a => a.textContent.trim()).includes('Company Overview')", timeout=45000)
        page.click(".rail a:has-text('{}')".format(label))
        page.wait_for_function("p => location.hash.startsWith('#/?preset=' + p)", arg=preset)
        page.wait_for_selector("[data-ws-preset='{}'][aria-selected='true']".format(preset), timeout=45000)
        page.wait_for_function("l => [...document.querySelectorAll('.rail [aria-current=\"page\"]')].map(a => a.textContent.trim()).includes(l)", arg=label, timeout=15000)
        assert _current(page) == [label], _current(page)
        assert page.locator(".rail .rail-group").first.evaluate("g => g.classList.contains('is-in')")
        # Home, pressed in the rail, is Home again
        page.click(".rail a.rail-row:has-text('Home')")
        page.wait_for_function("() => location.hash === '#/'")
        page.wait_for_function("() => [...document.querySelectorAll('.rail [aria-current=\"page\"]')].map(a => a.textContent.trim()).join() === 'Home'", timeout=30000)
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


def test_the_phone_bar_marks_research_not_home_on_a_trading_layout(chrome, server):
    ctx, page = open_page(chrome, server, level="advanced", viewport=PHONE)
    try:
        page.goto(server["base"] + "/#/?preset=technicals&symbol=AAPL", wait_until="domcontentloaded")
        page.wait_for_selector(".tabbar [data-v2-tab]")
        on = page.evaluate("() => [...document.querySelectorAll('.tabbar [aria-current=\"page\"]')].map(a => a.dataset.v2Tab || a.textContent.trim())")
        assert on == ["security"], on
    finally:
        ctx.close()


# ------------------------------------------------------------------ the stock page's reads while it redraws

def test_the_stock_pages_primary_is_read_whole_while_the_overview_redraws(chrome, server):
    """test_stock_page_at_advanced read no primary button once in a fresh-clone run on 7550291 (1 in 36 repeats on the
    Mac). The Milo bar is drawn by the same render as the header and was on screen throughout; the read was the
    fault: page.eval_on_selector_all queries in one call and evaluates in a second, and the Overview redraws itself as
    each piece of data arrives. Here the Overview is made to repaint every few milliseconds (the level, from another
    tab, as a storage event) and the read is taken 300 times: the two-step read is wrong some of the time and the
    suite's helper, one evaluate after the bar's own visibility, never."""
    from tests.e2e.test_pass1_journeys import primaries, stock
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP)
    try:
        page.add_init_script("""window.__draws = 0; new MutationObserver((ms) => { if (ms.some(m => m.target.classList && m.target.classList.contains('page-view'))) window.__draws++; }).observe(document, { subtree: true, childList: true });""")
        stock(page, server)
        page.evaluate("""() => { window.__stop = false; const tick = () => { if (window.__stop) return;
          window.dispatchEvent(new StorageEvent('storage', { key: 'optic.knowledge.v1', newValue: 'advanced' })); setTimeout(tick, 2); }; tick(); }""")
        two_step = "els => els.filter(e => e.offsetParent !== null).map(e => e.matches('[data-v2-mp-ask]') ? 'milo bar' : (e.textContent || '').trim())"
        d0 = page.evaluate("() => window.__draws")
        helper_wrong = sum(1 for _ in range(300) if primaries(page) != ["milo bar"])
        two_wrong = sum(1 for _ in range(300) if page.eval_on_selector_all("#main .btn-primary", two_step) != ["milo bar"])
        redraws = page.evaluate("() => window.__draws") - d0
        page.evaluate("() => { window.__stop = true; }")
        assert redraws > 50, "the Overview did not repaint during the reads ({})".format(redraws)
        assert helper_wrong == 0, "the suite's read was wrong {} of 300 times".format(helper_wrong)
        print("two-step read wrong {} of 300 during {} redraws".format(two_wrong, redraws))
    finally:
        ctx.close()

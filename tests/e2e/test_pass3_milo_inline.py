"""Round three, Milo in a real browser (flow 12 c to e, carried items 2 and 3).

Milo on every screen: a walk of every route in v2's route table (read from app.js, not a hand list) finds the strip
with its one offer naming what is on that screen. The offer asks with the screen's figures and the chart in view; the
strip opens Milo beside the page and collapses it back. The steps arrive before the answer (the recording stub asks
for a lookup and holds the answer back), the stance is named on the answer and can be picked for one answer from the
keyboard or kept on the account, an off-topic question is declined in one sentence with no model call, and Investing
and Earnings tell Milo the chart in view as Financials does. The Read page's Desk is the shared Desk panel.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import TimeoutError as PWTimeout

from tests.e2e.conftest import make_account
from tests.e2e.test_pass1_journeys import DESKTOP, PHONE, open_page
from tests.e2e.test_pass2_axe import TAGS
from tests.e2e.test_pass2_milo_view import PERIOD_KEY, route_statements
from tests.e2e.visual_fixtures import route_company, route_home

ROOT = Path(__file__).resolve().parents[2]
APP_JS = (ROOT / "static" / "v2" / "js" / "app.js").read_text()
# the hash for a view nav.js gives no address for; each one is checked to parse back to its view
EXTRA = {"signin": "#/signin", "terms": "#/terms", "privacy": "#/privacy", "dossierstart": "#/dossier",
         "earningsweek": "#/earnings", "saved": "#/research", "instrument": "#/instrument/MSFT",
         "notfound": "#/QQQQZX", "sheet": "#/AAPL/sheet", "investigate": "#/AAPL/investigate", "stockgrid": "#/AAPL/workspace"}


def route_views():
    body = re.search(r"const PAGES = \{(.*?)\};", APP_JS, re.S).group(1)
    return sorted(set(re.findall(r"(?:^|[,{]\s*)([a-z]+):", body)))


def _signed_in(chrome, server, viewport=DESKTOP, **kw):
    _, jar = make_account(server)
    return open_page(chrome, server, level="advanced", viewport=viewport, cookies=jar, **kw)


# Walked signed in, not as a guest: the level questions send a guest to sign in first (pages/levelquiz.js)
SIGNED_IN_ONLY = {"welcome"}


def test_every_route_has_milo_docked_with_an_offer_naming_its_screen(chrome, server):
    views = [v for v in route_views() if v not in SIGNED_IN_ONLY]
    assert len(views) > 30
    # as a guest, so the sign-in page is a page (a signed-in reader is sent from it to Home)
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP)
    try:
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-milo-strip]")
        hashes = page.evaluate("""async ([views, extra]) => {
          const n = await import('/v2/js/nav.js'), r = await import('/v2/js/core/router.js');
          const out = {};
          for (const v of views) {
            let h = null; try { h = n.hrefFor(v, 'AAPL'); } catch (e) { h = null; }
            const ok = (x) => x && r.parse(x).view === v;
            out[v] = ok(h) ? h : (ok(extra[v]) ? extra[v] : (extra[v] || h || null));
          }
          return out; }""", [views, EXTRA])
        missing = [v for v, h in hashes.items() if not h]
        assert missing == [], "a route with no address to walk: {}".format(missing)
        seen = {}
        for view in views:
            page.evaluate("h => { location.hash = h; }", hashes[view])
            try:
                page.wait_for_function("v => { const s = document.querySelector('[data-v2-milo-strip]'); return s && s.dataset.v2MiloScreen === v; }",
                                       arg=view, timeout=30000)
            except Exception:                                         # noqa: BLE001 - said with what the page shows
                now = page.evaluate("() => [location.hash, (document.querySelector('[data-v2-milo-strip]') || {dataset: {}}).dataset.v2MiloScreen]")
                raise AssertionError("no strip for {} at {}: the strip names {}".format(view, now[0], now[1]))
            got = page.evaluate("""async () => { const m = await import('/v2/js/ui/milo-inline.js'), r = await import('/v2/js/core/router.js');
              const s = document.querySelector('[data-v2-milo-strip]');
              return { offer: s.querySelector('[data-v2-milo-offer-text]').textContent.trim(), want: m.offerFor({ ...r.parse(location.hash), view: s.dataset.v2MiloScreen }),
                       toggle: s.querySelector('[data-v2-milo-strip-toggle]').getAttribute('aria-expanded'),
                       label: s.getAttribute('aria-label'), inMain: !!document.querySelector('#main [data-v2-milo-strip]') }; }""")
            seen[view] = got["offer"]
            assert got["offer"] and got["offer"] == got["want"], (view, got)
            # every screen names itself: the generic sentence is only for a page added without one (round three's
            # Portfolio and Calendar shipped on it once, found on the evaluation copy 2026-11-23)
            assert got["offer"] != "Explain what is on this page", (view, got)
            assert got["toggle"] in ("true", "false") and got["label"] == "Milo on this screen" and not got["inMain"], view
        # each company screen names its company; the account and legal screens name what they are
        assert "AAPL" in seen["financials"] and "Financials" in seen["financials"]
        assert seen["settings"].startswith("Explain what each of these settings")
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


def test_the_signed_in_only_screens_have_milo_docked_with_their_own_offer(chrome, server):
    ctx, page = _signed_in(chrome, server)
    try:
        for view in sorted(SIGNED_IN_ONLY):
            page.goto(server["base"] + "/#/" + view, wait_until="domcontentloaded")
            page.wait_for_function("v => { const s = document.querySelector('[data-v2-milo-strip]'); return s && s.dataset.v2MiloScreen === v; }",
                                   arg=view, timeout=30000)
            offer = page.inner_text("[data-v2-milo-strip] [data-v2-milo-offer-text]").strip()
            assert offer and offer != "Explain what is on this page", (view, offer)
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


def test_the_offer_asks_with_the_chart_in_view_and_the_strip_opens_and_collapses_milo(chrome, server, stub):
    stub.reset("ok")
    ctx, page = _signed_in(chrome, server, store={PERIOD_KEY: "quarter"})
    held = []
    route_statements(page, held)
    try:
        page.goto(server["base"] + "/#/AAPL/financials", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.wait_for_selector("#main figure[data-v2-metric] h3")
        page.locator("#main figure[data-v2-metric] h3", has_text=re.compile(r"^Margins$")).click()
        offer = page.locator("[data-v2-milo-offer]")
        assert "the chart in view on AAPL's Financials" in offer.inner_text()
        with page.expect_request(lambda r: r.url.endswith("/api/chat") and r.method == "POST", timeout=30000) as req:
            offer.click()
        body = json.loads(req.value.post_data or "{}")
        assert body["messages"][-1]["content"] == "Explain the chart in view on AAPL's Financials"
        assert ((body.get("context") or {}).get("focus") or {}).get("in_view", {}).get("metric") == "Margins"
        page.wait_for_function("() => (document.querySelector('.milo-log') || {}).textContent.includes('Stand-in answer')", timeout=60000)
        # open beside the page at this width, and the strip says so; collapse it back from the keyboard
        assert page.evaluate("() => document.documentElement.classList.contains('milo-docked')")
        tog = page.locator("[data-v2-milo-strip-toggle]")
        assert tog.get_attribute("aria-expanded") == "true" and tog.inner_text() == "Collapse Milo"
        tog.focus()
        page.keyboard.press("Enter")
        page.wait_for_function("() => document.querySelector('[data-v2-milo-strip-toggle]').getAttribute('aria-expanded') === 'false'")
        assert page.evaluate("() => document.activeElement && document.activeElement.matches('[data-v2-milo-strip-toggle]')")
        # the page takes its width back once the panel's exit has played
        page.wait_for_function("() => !document.documentElement.classList.contains('milo-docked')", timeout=5000)
        page.keyboard.press("Enter")
        page.wait_for_selector("#milo-q")
        page.wait_for_function("() => document.querySelector('[data-v2-milo-strip-toggle]').getAttribute('aria-expanded') === 'true'")
        # the conversation was kept across the collapse
        assert "Stand-in answer" in page.locator(".milo-log").inner_text()
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


@pytest.mark.parametrize("tab", ["investing", "earnings"])
def test_investing_and_earnings_tell_milo_the_chart_in_view(chrome, server, stub, tab):
    stub.reset("ok")
    ctx, page = _signed_in(chrome, server)
    route_company(page)
    try:
        page.goto(server["base"] + "/#/AAPL/" + tab, wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.wait_for_selector("#main section[data-v2-metric] h2", timeout=30000)
        name = page.evaluate("() => { const s = [...document.querySelectorAll('#main section[data-v2-metric]')].find(x => x.offsetParent && x.querySelector('h2')); s.scrollIntoView(); s.querySelector('h2').click(); return s.querySelector('h2').textContent.replace(/\\s+/g, ' ').trim(); }")
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-q")
        page.fill("#milo-q", "Explain this chart")
        with page.expect_request(lambda r: r.url.endswith("/api/chat") and r.method == "POST", timeout=30000) as req:
            page.press("#milo-q", "Enter")
        focus = ((json.loads(req.value.post_data or "{}").get("context") or {}).get("focus") or {})
        assert (focus.get("in_view") or {}).get("metric") == name, (name, focus.get("in_view"))
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


@pytest.mark.parametrize("motion", ["no-preference", "reduce"])
def test_the_steps_arrive_before_the_answer_and_the_stance_is_named(chrome, server, stub, motion):
    stub.reset("tool")
    stub.text_delay = 1.5
    _, jar = make_account(server)
    ctx = None
    try:
        ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar,
                              store={"optic.pulse.persona.v1": "skeptic"})
        page.emulate_media(reduced_motion=motion)
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-q")
        page.evaluate("""() => { window.__order = []; new MutationObserver(() => {
            const log = document.querySelector('.milo-log');
            if (!log) return;
            if (log.querySelector('.milo-steps li') && !window.__order.includes('steps')) window.__order.push('steps');
            if (log.textContent.includes('Stand-in answer') && !window.__order.includes('text')) window.__order.push('text');
          }).observe(document.body, { childList: true, subtree: true, characterData: true }); }""")
        page.fill("#milo-q", "Where is AAPL trading?")
        page.press("#milo-q", "Enter")
        page.wait_for_function("() => (document.querySelector('.milo-log') || {}).textContent.includes('Stand-in answer')", timeout=60000)
        order = page.evaluate("() => window.__order")
        assert order[:2] == ["steps", "text"], order
        last = page.locator(".milo-msg.milo-bot").last
        assert last.locator("[data-v2-milo-stance-tag]").inner_text() == "A skeptic's reading"
        steps = last.locator(".milo-steps-done")
        assert "Steps Milo took" in steps.inner_text()
        steps.locator("summary").click()
        assert "AAPL quote" in steps.inner_text()
        assert len([m for m in stub.messages() if m["body"].get("stream")]) == 2, "one round asked for the lookup, one answered"
        if motion == "reduce":
            moving = page.evaluate("() => [...document.querySelectorAll('.milo-steps, .milo-steps li, .milo-strip')].filter(e => { const s = getComputedStyle(e); return s.animationName !== 'none' || parseFloat(s.transitionDuration) > 0; }).length")
            assert moving == 0
        assert not page.errors, page.errors[:3]
    finally:
        stub.reset("ok")
        if ctx:
            ctx.close()


def test_a_stance_is_picked_for_one_answer_from_the_keyboard_and_kept_on_the_account(chrome, server, stub):
    stub.reset("ok")
    _, jar = make_account(server)
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar)
    try:
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-stance-once")
        page.focus("#milo-q")
        page.keyboard.press("Shift+Tab")
        for _ in range(8):
            if page.evaluate("() => document.activeElement && document.activeElement.id") == "milo-stance-once":
                break
            page.keyboard.press("Shift+Tab")
        assert page.evaluate("() => document.activeElement.id") == "milo-stance-once", "reached by the keyboard"
        page.select_option("#milo-stance-once", "skeptic")
        page.fill("#milo-q", "How are margins?")
        with page.expect_request(lambda r: r.url.endswith("/api/chat") and r.method == "POST") as one:
            page.press("#milo-q", "Enter")
        assert json.loads(one.value.post_data)["persona"] == "skeptic"
        page.wait_for_function("() => (document.querySelector('.milo-log') || {}).textContent.includes('Stand-in answer')", timeout=60000)
        assert page.input_value("#milo-stance-once") == "", "back to the kept stance after one answer"
        page.fill("#milo-q", "And cash flow?")
        with page.expect_request(lambda r: r.url.endswith("/api/chat") and r.method == "POST") as two:
            page.press("#milo-q", "Enter")
        assert json.loads(two.value.post_data)["persona"] == "neutral"
        page.wait_for_function("() => document.querySelectorAll('.milo-msg.milo-bot').length >= 2 && !document.querySelector('.milo-msg .activity')", timeout=60000)
        # kept: the account's stance, written by the same PUT the Response settings menu uses
        csrf = next(c["value"] for c in ctx.cookies() if c["name"].lower().endswith("csrf"))
        r = page.evaluate("async (t) => (await fetch('/api/milo/stance', { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Optic-CSRF': t }, body: JSON.stringify({ stance: 'stoic' }) })).status", csrf)
        assert r == 200
        ctx2, page2 = open_page(chrome, server, level="advanced", viewport=DESKTOP, cookies=jar)
        # Diagnostic (2026-11-25): this wait timed out on every Ubuntu CI run and passed on the Mac and in an Ubuntu
        # container. On a timeout it prints what the second browser shows, the stance the account holds, and the
        # order of the API calls, then raises the same error; the assertion is unchanged.
        net, t0 = [], time.monotonic()

        def _log(kind, r):
            path = r.url.split(server["base"], 1)[-1]
            if path.startswith("/api/"):
                net.append([round(time.monotonic() - t0, 3), kind, getattr(r, "method", None) or r.request.method,
                            path, getattr(r, "status", None)])
        page2.on("request", lambda r: _log("request", r))
        page2.on("response", lambda r: _log("response", r))
        page2.on("requestfailed", lambda r: _log("failed", r))
        # the first page is still open on Home with Milo; what it asks the server while the second page waits
        page.on("request", lambda r: _log("page1 request", r))
        page.on("response", lambda r: _log("page1 response", r))
        page.on("requestfailed", lambda r: _log("page1 failed", r))
        try:
            page2.goto(server["base"] + "/#/", wait_until="domcontentloaded")
            page2.wait_for_selector("[data-v2-account].avatar")
            net.append([round(time.monotonic() - t0, 3), "avatar shown"])
            page2.click(".topbar-milo")
            net.append([round(time.monotonic() - t0, 3), "Milo clicked"])
            try:
                page2.wait_for_function("() => (document.querySelector('#milo-stance-once option') || {}).textContent === \"As kept: a conservative investor's reading\"", timeout=20000)
            except PWTimeout:
                shown = page2.evaluate("""async () => ({
                  options: [...document.querySelectorAll('#milo-stance-once option')].map(o => o.textContent),
                  slot: !!document.querySelector('[data-v2-milo-stance-slot]'),
                  persona_in_browser: localStorage.getItem('optic.pulse.persona.v1'),
                  account_stance: await fetch('/api/milo/stance', { credentials: 'same-origin' })
                    .then(r => r.text().then(t => r.status + ' ' + t)).catch(e => 'fetch failed: ' + e),
                })""")
                log_tail = (server["data"] / "server.log").read_text(errors="replace").splitlines()[-120:]
                print("STANCE_DIAGNOSTIC " + json.dumps({"shown": shown, "net": net, "errors": page2.errors[:5],
                                                         "server_log_tail": log_tail}))
                raise
        finally:
            ctx2.close()
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


def test_an_offtopic_question_is_declined_in_one_sentence_with_no_model_call(chrome, server, stub):
    stub.reset("ok")
    ctx, page = _signed_in(chrome, server)
    try:
        page.goto(server["base"] + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-q")
        stub.reset("ok")
        page.fill("#milo-q", "What's the weather in Boston tomorrow?")
        page.press("#milo-q", "Enter")
        page.wait_for_function("() => (document.querySelector('.milo-log') || {}).textContent.includes(\"Milo can't answer questions outside markets\")", timeout=30000)
        last = page.locator(".milo-msg.milo-bot").last
        txt = last.locator(".milo-bubble").inner_text()
        assert txt.count("Milo can't") == 1 and "it can explain today's market moves" in txt
        assert last.locator(".milo-policy").count() == 0, "said once, as the answer"
        assert [m for m in stub.messages() if m["body"].get("stream")] == []
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


def test_the_read_page_desk_is_the_shared_desk_panel(chrome, server):
    ctx, page = open_page(chrome, server, level="advanced", viewport=DESKTOP)
    route_home(page)
    try:
        page.goto(server["base"] + "/#/read", wait_until="domcontentloaded")
        sec = page.locator("section[data-v2-desk='shared']")
        sec.wait_for(timeout=30000)
        assert sec.locator("h2").inner_text() == "Optic Desk"
        page.wait_for_selector("section[data-v2-desk='shared'] .desk-grid .desk-main", timeout=30000)
        assert sec.locator(".desk-side").count() == 1, "the panel's side column: built from, saved research, questions"
        assert "Bottom line" in sec.inner_text()
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()


MILO = (".milo-strip", ".milo-inline", ".drawer", "[data-v2-milo", "#milo-", ".milo")


def _axe(page):
    """Every violation with every node (the Pass 2 helper keeps four nodes, which could hide one of Milo's)."""
    from axe_playwright_python.sync_playwright import Axe
    result = Axe().run(page, options={"runOnly": {"type": "tag", "values": TAGS}})
    return [{"id": v["id"], "impact": v["impact"], "nodes": [n["target"] for n in v["nodes"]]} for v in result.response.get("violations", [])]


def _ours(violations):
    """The violations on Milo's strip or panel. Others on the page are the page's (said in .factory/pass-3-milo-record.md:
    the axe in this suite's environment also flags label-content-name-mismatch on the top bar's search and account
    buttons and Home's sector picks, outside this work and present on the Pass 2 head)."""
    return [v for v in violations if any(any(m in sel for m in MILO) for node in v["nodes"] for sel in node)]


@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["desktop", "phone"])
@pytest.mark.parametrize("where", ["#/", "#/AAPL/financials", "#/AAPL/chart"])
def test_axe_with_milo_collapsed_and_open(chrome, server, stub, viewport, where):
    stub.reset("ok")
    ctx, page = _signed_in(chrome, server, viewport=viewport)
    route_home(page)
    route_company(page)
    try:
        page.goto(server["base"] + "/" + where, wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-account].avatar")
        page.wait_for_selector("[data-v2-milo-strip]")
        page.wait_for_timeout(1500)
        collapsed = _ours(_axe(page))
        assert collapsed == [], collapsed
        assert page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1"), "no sideways scroll"
        page.click("[data-v2-milo-strip-toggle]")
        page.wait_for_selector("#milo-q")
        page.wait_for_timeout(600)
        opened = _ours(_axe(page))
        assert opened == [], opened
        assert not page.errors, page.errors[:3]
    finally:
        ctx.close()

"""The outside runner for Optic Pass 3 (CON-58): every ask of the human test script, driven in a real browser from
outside the deployment, through the basic-auth gate, signing in on the product's own form with real passwords.

Why it exists (factory rule, operator, 2026-11-24): every test a human is asked to do is Playwright-tested from outside
first, on the deployed build. The earlier outside run (2026-11-23, on 484485f) lived in a scratchpad and is gone; this
one is committed so the next deploy can be walked the same way.

Run (from the repo root, with Playwright's Chromium and axe-playwright-python installed, requirements-dev.txt):

    python tests/outside/outside_run.py --out /path/outside/every/repo

It is not a pytest module (tests/outside/conftest.py keeps it out of every collection). It reads the evaluation key
file (~/.conjure/optic-eval.key: user=, gate=, evaluator=, admin=) into process memory only. No value read from that
file, no generated password and no reset token is ever printed, logged, put in a URL the runner writes down, or put in
a screenshot name: every line it prints and every row it records passes through scrub(). Screenshots and the JSON
results go to --out, which must be outside every repository.

What it never does: type a payment card (Checkout is opened in test mode and left unpaid; it expires on its own), make
a plan change in Stripe, set or read a Railway variable, reset or recreate the seeded evaluator or owner. The one
account whose password it changes is the fresh account it makes itself through the sign-up form.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

KIND = ("Kind of run: real browser from outside, through the gate, real passwords "
        "(Playwright Chromium, headless, from the ops Mac; not route-level, not inside the container)")
BASE = "https://edge-optic-production.up.railway.app"
MAIL = "https://edge-optic-mail-production.up.railway.app"
EVALUATOR = "con51-r2-f26b93@optic-eval.fabricated.example"
OWNER = "owner@optic-eval.fabricated.example"
FRESH_DOMAIN = "optic-eval.fabricated.example"
DESKTOP = {"width": 1440, "height": 900}
PHONE = {"width": 390, "height": 844}
TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]
ROOT = Path(__file__).resolve().parents[2]
DEPLOYED = "3ff7100"
BOOTED = "2026-11-24T16:00:35"

SECRETS: List[str] = []          # every value that must never be printed; scrub() masks each


def scrub(text: Any) -> str:
    s = str(text)
    for v in SECRETS:
        if v and len(v) >= 4:
            s = s.replace(v, "[secret]")
    # a reset or verify token in any address, whether or not it was registered yet
    s = re.sub(r"(?<![A-Za-z])(reset|verify|token)=([A-Za-z0-9_\-\.%]{8,})", r"\1=[secret]", s)
    return s


def say(*parts: Any) -> None:
    print(scrub(" ".join(str(p) for p in parts)), flush=True)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def read_key(path: Path) -> Dict[str, str]:
    mode = path.stat().st_mode & 0o777
    if mode != 0o600:
        raise SystemExit("the key file is not mode 600; stop and tell the operator")
    if Path(str(path) + "~").exists():
        raise SystemExit("an editor backup sits beside the key file; stop and tell the operator")
    out = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    for k in ("gate", "evaluator", "admin"):
        if not out.get(k):
            raise SystemExit("the key file has no {} line".format(k))
    SECRETS.extend(v for k, v in out.items() if k != "user")
    return out


class Run:
    def __init__(self, out: Path, key: Dict[str, str]):
        self.out = out
        self.key = key
        self.gate_user = key.get("user") or "optic"
        self.items: List[Dict[str, Any]] = []
        self.faults: List[str] = []
        self.fresh: Dict[str, str] = {}
        self.notes: Dict[str, Any] = {}

    # ---------------------------------------------------------------- recording
    def record(self, iid: str, ask: str, expected: str, observed: str, status: str, **extra: Any) -> None:
        row = {"id": iid, "ask": ask, "expected": expected, "observed": scrub(observed), "status": status, "at": now()}
        row.update({k: json.loads(scrub(json.dumps(v))) for k, v in extra.items()})
        self.items.append(row)
        say("[{}] {} {}: {}".format(row["at"], status.upper(), iid, row["observed"][:300]))

    def shot(self, page, name: str) -> None:
        try:
            page.screenshot(path=str(self.out / "{}.png".format(name)), full_page=False)
        except Exception as e:  # noqa: BLE001 - a missing shot is said, not fatal
            say("shot {} not taken: {}".format(name, type(e).__name__))

    def item(self, iid: str, ask: str, expected: str, fn: Callable[[], Any]) -> None:
        """Run one item; an exception is a failure with its scrubbed message, never a pass."""
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            msg = scrub("{}: {}".format(type(e).__name__, str(e).splitlines()[0] if str(e) else ""))
            self.record(iid, ask, expected, "raised " + msg, "fail", trace=scrub(traceback.format_exc()[-1500:]))

    # ---------------------------------------------------------------- the gate, over plain HTTP
    def auth_header(self, password: Optional[str]) -> Dict[str, str]:
        if password is None:
            return {}
        tok = base64.b64encode("{}:{}".format(self.gate_user, password).encode()).decode()
        SECRETS.append(tok)
        return {"Authorization": "Basic " + tok}

    def http(self, url: str, password: Optional[str] = "gate", method: str = "GET", data: Optional[bytes] = None,
             headers: Optional[Dict[str, str]] = None, timeout: float = 30):
        pw = self.key["gate"] if password == "gate" else password
        h = dict(self.auth_header(pw))
        h.update(headers or {})
        req = urllib.request.Request(url, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    # ---------------------------------------------------------------- browsers
    def context(self, browser, viewport=DESKTOP, gate: bool = True, store: Optional[Dict[str, str]] = None):
        kw: Dict[str, Any] = {"viewport": viewport, "timezone_id": "America/New_York", "locale": "en-US"}
        if gate:
            kw["http_credentials"] = {"username": self.gate_user, "password": self.key["gate"], "origin": BASE}
        ctx = browser.new_context(**kw)
        if store:
            ctx.add_init_script("""(() => { try { if (sessionStorage.getItem('out.seeded')) return; sessionStorage.setItem('out.seeded', '1');
              const s = %s; for (const k in s) localStorage.setItem(k, s[k]); } catch (e) {} })();""" % json.dumps(store))
        page = ctx.new_page()
        page.set_default_timeout(45000)
        errs: List[str] = []
        page.on("pageerror", lambda e: errs.append(str(e)[:200]))
        page.errs = errs
        return ctx, page

    def sign_in(self, page, email: str, password: str) -> None:
        page.goto(BASE + "/#/signin", wait_until="domcontentloaded")
        page.wait_for_selector("form[data-v2-auth='in'] input[name=email]")
        page.fill("form[data-v2-auth='in'] input[name=email]", email)
        page.fill("form[data-v2-auth='in'] input[name=password]", password)
        page.click("form[data-v2-auth='in'] button[type=submit]")
        page.wait_for_selector("[data-v2-account].avatar", timeout=45000)

    def me(self, page) -> Dict[str, Any]:
        return page.evaluate("async () => { const r = await fetch('/api/auth/me', {credentials: 'same-origin'}); let b = null; try { b = await r.json(); } catch (e) {} return {status: r.status, body: b}; }")

    # ---------------------------------------------------------------- mail sink (Mailpit API, through the gate)
    def mails(self) -> List[Dict[str, Any]]:
        st, body = self.http(MAIL + "/api/v1/messages?limit=100")
        if st != 200:
            raise RuntimeError("mail sink answered {}".format(st))
        return json.loads(body)["messages"]

    def mail_text(self, mid: str) -> str:
        st, body = self.http(MAIL + "/api/v1/message/" + mid)
        if st != 200:
            raise RuntimeError("mail sink message answered {}".format(st))
        d = json.loads(body)
        return (d.get("Text") or "") + "\n" + (d.get("HTML") or "")


# ==================================================================== V0, the deployment identity

def identity(run: Run) -> None:
    def go():
        st, body = run.http(BASE + "/api/health")
        h = json.loads(body)
        files = ["static/v2/js/app.js", "static/v2/js/pages/signin.js", "static/v2/js/pages/levelquiz.js",
                 "static/v2/js/ui/milo.js", "static/v2/js/pages/settings.js", "static/v2/js/pages/chart.js",
                 "static/v2/js/ui/pricechart.js", "static/v2/css/base.css", "static/v2/css/pages.css",
                 "static/v2/js/ui/shell.js", "static/v2/js/ui/milo-inline.js", "static/v2/js/ui/drawer.js"]
        same, differ = 0, []
        for f in files:
            want = subprocess.run(["git", "-C", str(ROOT), "show", "{}:{}".format(DEPLOYED, f)], capture_output=True).stdout
            url = BASE + "/" + f.replace("static/v2/", "v2/", 1) if f.startswith("static/v2/") else BASE + "/static/" + f[len("static/"):]
            s2, got = run.http(url)
            if s2 == 200 and want and hashlib.sha256(got).hexdigest() == hashlib.sha256(want).hexdigest():
                same += 1
            else:
                differ.append("{} ({})".format(f, s2))
        ok = st == 200 and str(h.get("booted_at", "")).startswith(BOOTED) and not differ
        run.notes["health"] = {"booted_at": h.get("booted_at"), "uptime_seconds": h.get("uptime_seconds"), "commit": h.get("commit")}
        run.record("V0", "The copy is still the {} deployment".format(DEPLOYED), "booted {} UTC; served scripts equal {}".format(BOOTED, DEPLOYED),
                   "/api/health {}: booted_at {}, uptime {} s; {} of {} served files equal by sha256 to {}{}".format(
                       st, h.get("booted_at"), h.get("uptime_seconds"), same, len(files), DEPLOYED,
                       "; differ: " + ", ".join(differ) if differ else ""), "pass" if ok else "fail")
    run.item("V0", "deployment identity", DEPLOYED, go)


# ==================================================================== A1 and A2

def gate_and_first_visit(run: Run, browser) -> None:
    def a1():
        paths = ["/", "/api/health", "/api/auth/me", "/v2/js/app.js", "/api/alerts", "/api/home", "/robots.txt"]
        rows = []
        for p in paths:
            rows.append((p, run.http(BASE + p, None)[0], run.http(BASE + p, "wrong-" + secrets.token_hex(4))[0], run.http(BASE + p)[0]))
        ctx, page = run.context(browser, gate=False)
        r = page.goto(BASE + "/", wait_until="domcontentloaded")
        browser_none = r.status if r else None
        body = page.inner_text("body")[:200] if r else ""
        run.shot(page, "A1-gate-no-password")
        ctx.close()
        ctx = browser.new_context(viewport=DESKTOP, http_credentials={"username": run.gate_user, "password": "wrong-" + secrets.token_hex(4), "origin": BASE})
        page = ctx.new_page()
        r = page.goto(BASE + "/", wait_until="domcontentloaded")
        browser_wrong = r.status if r else None
        ctx.close()
        ok = all(a == 401 and b == 401 and c == 200 for _, a, b, c in rows) and browser_none == 401 and browser_wrong == 401 and "Optic" not in body
        run.record("A1", "Open the site and cancel the password prompt; then a wrong password",
                   "401, no page of the product; 200 with the right password",
                   "browser: no password {}, wrong password {}; HTTP on {} paths (none/wrong/right): {}".format(
                       browser_none, browser_wrong, len(rows), "; ".join("{} {}/{}/{}".format(*x) for x in rows)),
                   "pass" if ok else "fail")
    run.item("A1", "gate", "401", a1)

    def a2():
        seen = []
        for name, vp in (("desktop", DESKTOP), ("390", PHONE)):
            ctx, page = run.context(browser, viewport=vp)
            page.goto(BASE + "/#/", wait_until="domcontentloaded")
            page.wait_for_selector("[data-v2-lc] [aria-pressed='true']")
            level = page.eval_on_selector("[data-v2-lc] [aria-pressed='true']", "e => e.dataset.v2Level")
            page.wait_for_selector("#ws-new", timeout=30000)
            card = page.inner_text("#ws-new")
            sideways = page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
            run.shot(page, "A2-first-visit-" + name)
            seen.append((name, level, "New to Optic? Three ways to start" in card, sideways, card.splitlines()[0] if card else ""))
            ctx.close()
        ok = all(l == "beginner" and c and s for _, l, c, s, _ in seen)
        run.record("A2", "Enter the gate; first visit to Home, desktop and 390 wide",
                   "Home at Beginner with 'New to Optic? Three ways to start'",
                   "; ".join("{}: level {}, card {} ('{}'), no sideways scroll {}".format(n, l, "shown" if c else "MISSING", first, s) for n, l, c, s, first in seen),
                   "pass" if ok else "fail")
    run.item("A2", "first visit", "Beginner", a2)


# ==================================================================== A3, A4 and the reset walk, on a fresh account

def fresh_account(run: Run, browser) -> None:
    email = "con58-outside-{}@{}".format(secrets.token_hex(3), FRESH_DOMAIN)
    password = "Ou7side-" + secrets.token_urlsafe(18)
    SECRETS.append(password)
    run.fresh = {"email": email, "password": password}
    run.notes["fresh_account"] = email
    ctx, page = run.context(browser)
    run.notes["fresh_ctx"] = (ctx, page)

    def a3():
        page.goto(BASE + "/#/signin?mode=up", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-auth='up']")
        f = "[data-v2-auth='up'] "
        page.fill(f + "input[name=first_name]", "Outside")
        page.fill(f + "input[name=last_name]", "Runner")
        page.fill(f + "input[name=email]", email)
        page.fill(f + "input[name=password]", password)
        page.fill(f + "input[name=confirm]", password)
        page.click(f + "button[type=submit]")
        page.wait_for_selector("[data-v2-account].avatar", timeout=45000)
        page.wait_for_selector("[data-v2-lq-form], [data-v2-lq-offer]", timeout=30000)
        where = page.evaluate("() => location.hash")
        band = page.locator("[data-v2-lq-offer]").count()
        form = page.locator("[data-v2-lq-form]").count()
        run.shot(page, "A3-fresh-after-sign-up")
        providers = (run.me(page).get("body") or {}).get("providers") or {}
        avail = sorted(k for k, v in providers.items() if isinstance(v, dict) and v.get("available"))
        run.notes["providers_available"] = avail
        # the offer is once: Home on a reload offers nothing more (the questions page recorded it as shown)
        page.goto(BASE + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-lc] [aria-pressed='true']")
        page.wait_for_timeout(2500)
        again = page.locator("[data-v2-lq-offer]").count()
        page.goto(BASE + "/#/welcome", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-lq-form]", timeout=30000)
        run.record("A3", "A new account is offered the six level questions once (band with Answer them / Not now, the same size)",
                   "the questions offered once; on the band, Answer them and Not now the same size",
                   "fresh account made through the sign-up form at {}: the product went straight to {} with the questions form ({} form, {} band); "
                   "Home afterwards offered no band ({}). The band itself is drawn only for an account made without the form (Google, Apple, "
                   "passkey: pages/levelquiz.js offer()); sign-in providers available on the copy: {}. The band's two buttons could not be "
                   "measured from a form-made account".format(email.split("@")[0] + "@...", where, form, band, again, avail or "none"),
                   "not reached" if band == 0 else "pass")
    run.item("A3", "level questions offered", "band", a3)

    def a4():
        page.wait_for_selector("[data-v2-lq-form]")
        c = page.locator("[data-v2-lq-form] button[type=submit]").bounding_box()
        s = page.locator("[data-v2-lq-skip]").bounding_box()
        same = abs(c["width"] - s["width"]) <= 1 and abs(c["height"] - s["height"]) <= 1
        qs = page.locator(".lq-q").count()
        for i in range(2):
            page.locator(".lq-q").nth(i).locator("label.check").last.click()
        page.click("[data-v2-lq-form] button[type=submit]")
        page.wait_for_selector("[data-v2-lq-result]", timeout=30000)
        suggested = page.get_attribute("[data-v2-lq-result]", "data-v2-lq-result")
        why = page.inner_text("[data-v2-lq-why]") if page.locator("[data-v2-lq-why]").count() else ""
        head = page.inner_text("#lq-sug") if page.locator("#lq-sug").count() else ""
        run.shot(page, "A4-suggestion")
        page.click("[data-v2-lq-accept]")
        page.wait_for_function("() => !location.hash.startsWith('#/welcome')", timeout=30000)
        page.goto(BASE + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-lc] [aria-pressed='true']")
        level = page.eval_on_selector("[data-v2-lc] [aria-pressed='true']", "e => e.dataset.v2Level")
        # and on a new browser, read from the account
        ctx2, p2 = run.context(browser)
        run.sign_in(p2, email, password)
        p2.goto(BASE + "/#/", wait_until="domcontentloaded")
        p2.wait_for_selector("[data-v2-lc] [aria-pressed='true']")
        p2.wait_for_timeout(1500)
        level2 = p2.eval_on_selector("[data-v2-lc] [aria-pressed='true']", "e => e.dataset.v2Level")
        ctx2.close()
        sentences = len([x for x in re.split(r"(?<=[.!?])\s+", why.strip()) if x])
        ok = same and suggested in ("beginner", "intermediate", "advanced") and sentences == 1 and level == suggested == level2
        run.record("A4", "Answer two of the six, Continue, Use; Home's level control shows it; Skip the size of Continue",
                   "a suggested level with one sentence of why; Use; Home shows the level; Skip as large as Continue",
                   "{} questions; Continue {}x{} and Skip {}x{} ({}); answered 2; '{}', why ({} sentence): '{}'; Use pressed; Home's control: {}; "
                   "a new browser signed in: {}".format(qs, round(c["width"]), round(c["height"]), round(s["width"]), round(s["height"]),
                                                       "same size" if same else "DIFFER", head, sentences, why, level, level2),
                   "pass" if ok else "fail")
    run.item("A4", "level questions answered", "Use", a4)

    def reset_walk():
        old_ctx, old_page = ctx, page
        before = run.me(old_page)
        t0 = time.time()
        known_ids = {m["ID"] for m in run.mails()}
        c1, p1 = run.context(browser)
        p1.goto(BASE + "/#/signin", wait_until="domcontentloaded")
        p1.wait_for_selector("form[data-v2-auth='in']")
        p1.click("[data-v2-auth-mode='forgot']")
        p1.wait_for_selector("form[data-v2-auth='forgot']")
        p1.fill("form[data-v2-auth='forgot'] input[name=email]", email)
        p1.click("form[data-v2-auth='forgot'] button[type=submit]")
        p1.wait_for_selector("form[data-v2-auth='forgot'] .stale", timeout=30000)
        said = p1.inner_text("form[data-v2-auth='forgot'] .stale")
        run.shot(p1, "RP1-forgot-sent")
        c1.close()
        mail = None
        for _ in range(40):
            for m in run.mails():
                if m["ID"] not in known_ids and any(t["Address"].lower() == email.lower() for t in m["To"]) and "Reset" in m["Subject"]:
                    mail = m
                    break
            if mail:
                break
            time.sleep(3)
        if not mail:
            run.record("RP1", "Forgot password: request a reset for the fresh account", "the reset mail arrives in the sink",
                       "page said '{}'; no reset mail to the fresh address within 120 s".format(said), "fail")
            return
        took = round(time.time() - t0, 1)
        run.record("RP1", "Forgot password: request a reset for the fresh account", "the reset mail arrives in the sink",
                   "page said '{}'; mail '{}' to the fresh address in the sink after {} s".format(said, mail["Subject"], took), "pass")
        text = run.mail_text(mail["ID"])
        links = re.findall(r"https?://[^\s\"'<>]+[?&]reset=[A-Za-z0-9_\-\.%]+", text)
        if not links:
            run.record("RP2", "The link sets a new password once", "reset form, new password, signed in", "no reset link in the mail", "fail")
            return
        link = links[0].replace("&amp;", "&")
        tok = link.split("reset=", 1)[1].split("&", 1)[0]
        SECRETS.extend([tok, link])
        host = re.match(r"https?://([^/?#]+)", link).group(1)
        newpw = "Ou7side-" + secrets.token_urlsafe(18)
        SECRETS.append(newpw)
        c2, p2 = run.context(browser)
        p2.goto(link, wait_until="domcontentloaded")
        p2.wait_for_selector("form[data-v2-auth='reset']", timeout=30000)
        scrubbed_addr = "reset=" not in p2.url
        p2.fill("form[data-v2-auth='reset'] input[name=password]", newpw)
        p2.fill("form[data-v2-auth='reset'] input[name=confirm]", newpw)
        p2.click("form[data-v2-auth='reset'] button[type=submit]")
        p2.wait_for_selector("[data-v2-account].avatar", timeout=45000)
        signed = run.me(p2)
        run.shot(p2, "RP2-new-password-set")
        c2.close()
        run.fresh["password"] = newpw
        run.record("RP2", "Follow the emailed link and set a new password", "the link opens the reset form; a new password signs the reader in",
                   "link host {} ({}); token removed from the address {}; form submitted; signed in: /api/auth/me {}".format(
                       host, "the copy" if host == BASE.split("//")[1] else "NOT the copy", scrubbed_addr, signed["status"]),
                   "pass" if host == BASE.split("//")[1] and signed["status"] == 200 else "fail")
        c3, p3 = run.context(browser)
        p3.goto(link, wait_until="domcontentloaded")
        p3.wait_for_selector("form[data-v2-auth='forgot']", timeout=30000)
        p3.wait_for_timeout(500)
        toast = p3.evaluate("() => [...document.querySelectorAll('.toast')].map(t => t.textContent.trim()).join(' | ')")
        run.shot(p3, "RP3-second-use-refused")
        reset_form = p3.locator("form[data-v2-auth='reset']").count()
        c3.close()
        st, body = run.http(BASE + "/api/auth/reset/check?token=" + tok)
        check = json.loads(body) if st == 200 else {}
        ok3 = reset_form == 0 and check.get("valid") is False
        run.record("RP3", "Use the same link a second time", "refused",
                   "the page opened the send-a-new-link form, no reset form; toast '{}'; /api/auth/reset/check valid {}".format(toast, check.get("valid")),
                   "pass" if ok3 else "fail")
        after = run.me(old_page)
        old_page.reload(wait_until="domcontentloaded")
        old_page.wait_for_timeout(3000)
        avatar = old_page.locator("[data-v2-account].avatar").count()
        u_before = (before.get("body") or {}).get("user")
        u_after = (after.get("body") or {}).get("user")
        ok4 = before["status"] == 200 and bool(u_before) and not u_after
        run.record("RP4", "The session signed in before the reset", "signed out",
                   "before the reset /api/auth/me {} ({}); after it {} ({}); the old page on reload shows the account avatar: {}".format(
                       before["status"], "signed in" if u_before else "no user", after["status"], "signed in" if u_after else "no user", bool(avatar)),
                   "pass" if ok4 else "fail")
        c4, p4 = run.context(browser)
        p4.goto(BASE + "/#/signin", wait_until="domcontentloaded")
        p4.fill("form[data-v2-auth='in'] input[name=email]", email)
        p4.fill("form[data-v2-auth='in'] input[name=password]", password)
        p4.click("form[data-v2-auth='in'] button[type=submit]")
        p4.wait_for_function("() => (document.querySelector('#si-err') || {}).textContent", timeout=30000)
        old_err = p4.inner_text("#si-err")
        c4.close()
        c5, p5 = run.context(browser)
        run.sign_in(p5, email, newpw)
        c5.close()
        run.record("RP5", "Sign in with the old password, then the new one", "old refused, new signs in",
                   "old password: '{}'; new password: signed in".format(old_err), "pass" if old_err else "fail")
        old_ctx.close()
    run.item("RP", "forgot-password walk", "end to end", reset_walk)


# ==================================================================== A3 by passkey sign-up, if the copy has one

def passkey_signup(run: Run, browser) -> None:
    """The level-questions band is drawn only for an account made without the sign-up form (pages/levelquiz.js offer()).
    A passkey account would be one such account. This asks the copy, with a WebAuthn virtual authenticator attached
    through CDP, whether a passkey can make an account; it makes one and walks A3 on it if so."""
    def go():
        ctx, page = run.context(browser)
        cdp = ctx.new_cdp_session(page)
        cdp.send("WebAuthn.enable")
        auth = cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {"protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                                                                          "hasUserVerification": True, "isUserVerified": True, "automaticPresenceSimulation": True}})
        seen = {}
        for mode in ("up", "in"):
            page.goto("about:blank")   # a hash change alone keeps the page's last mode (pages/signin.js), so each is a fresh load
            page.goto(BASE + "/#/signin" + ("?mode=up" if mode == "up" else ""), wait_until="domcontentloaded")
            page.wait_for_selector("form[data-v2-auth='{}']".format(mode), timeout=30000)
            page.wait_for_timeout(1000)
            seen[mode] = page.eval_on_selector_all("main button, main a.btn", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim()).filter(Boolean)")
        run.shot(page, "A3p-sign-up-page")
        # the one passkey control offered signed out: sign in with a passkey, from a browser whose authenticator holds none
        tried = ""
        page.goto("about:blank")
        page.goto(BASE + "/#/signin?mode=up", wait_until="domcontentloaded")
        page.wait_for_selector("form[data-v2-auth='up']")
        pk = page.locator("[data-v2-pk-signin]")
        if pk.count():
            pk.first.click()
            page.wait_for_timeout(6000)
            tried = page.evaluate("() => ((document.querySelector('#si-err') || {}).textContent || '').trim()")
        me = run.me(page)
        creds = cdp.send("WebAuthn.getCredentials", {"authenticatorId": auth["authenticatorId"]}).get("credentials", [])
        reg = page.evaluate("async () => { const r = await fetch('/api/auth/passkeys/register/options', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }); return r.status; }")
        ctx.close()
        made = bool((me.get("body") or {}).get("user"))
        up_pk = [b for b in seen["up"] if "passkey" in b.lower()]
        reachable = made or any("create" in b.lower() for b in up_pk)
        run.notes["passkey_signup"] = {"signup_page_buttons": seen["up"], "signin_page_buttons": seen["in"], "register_options_signed_out": reg,
                                       "virtual_credentials_after": len(creds), "account_made": made}
        run.record("A3p", "A3 on a fresh account made through the product's passkey sign-up (WebAuthn virtual authenticator over CDP)",
                   "the band once, Answer them and Not now the same size, not offered again on reload",
                   "no passkey sign-up path on the copy: the Create account page's passkey control is {} (a sign-in, not a sign-up); pressed from a "
                   "virtual authenticator holding no credential it made no account (/api/auth/me {} with {}; error line '{}'; credentials on the "
                   "authenticator after: {}); POST /api/auth/passkeys/register/options signed out answers {} (routes.py requires a signed-in "
                   "account; the only place to add a passkey is Settings, Add a passkey, on an account that already exists, and an account "
                   "made through the form has spent its questions offer on #/welcome)".format(
                       up_pk or "absent", me["status"], "a user" if made else "no user", tried, len(creds), reg),
                   "pass" if reachable else "not reached")
    run.item("A3p", "passkey sign-up", "band", go)


# ==================================================================== the evaluator: B, refusals, F, C, E, X, K

def evaluator(run: Run, browser) -> None:
    ctx, page = run.context(browser)
    run.sign_in(page, EVALUATOR, run.key["evaluator"])

    def band_spent():
        page.goto(BASE + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-lc] [aria-pressed='true']")
        page.wait_for_timeout(2500)
        n = page.locator("[data-v2-lq-offer]").count()
        level = page.eval_on_selector("[data-v2-lc] [aria-pressed='true']", "e => e.dataset.v2Level")
        run.notes["evaluator_level_at_start"] = level
        if level != "advanced":
            page.click("[data-v2-lc] [data-v2-level='advanced']")
            page.wait_for_selector("[data-v2-lc] [data-v2-level='advanced'][aria-pressed='true']")
            page.wait_for_timeout(2000)
            run.notes["evaluator_level_set_for_the_walk"] = "advanced (Z1 sets Beginner back)"
        run.record("A3e", "Sign in as the evaluator (script ask 3)", "the band, once",
                   "no band ({} drawn): the evaluator's offer was already spent (recorded shown 2026-11-24 16:03:20 UTC, before this run); "
                   "level control at {}".format(n, level), "not reached" if n == 0 else "pass")
    run.item("A3e", "evaluator band", "spent", band_spent)

    def b5():
        page.goto(BASE + "/#/watchlist", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-wl-alerts='AAPL']", timeout=45000)
        t = page.inner_text("[data-v2-wl-alerts='AAPL']")
        run.shot(page, "B5-watchlist")
        run.record("B5", "Open Watchlist from the rail", "AAPL's row says its alerts", "AAPL row alert line: '{}'".format(" ".join(t.split())),
                   "pass" if " ".join(t.split()) else "fail")
    run.item("B5", "watchlist", "", b5)

    def b6():
        page.goto(BASE + "/#/alerts", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-all-list]", timeout=45000)
        h1 = page.inner_text("h1")
        tabs = page.eval_on_selector_all(".tabs a", "els => els.map(e => e.textContent.trim())")
        lst = page.inner_text("[data-v2-all-list]")
        n = page.locator("[data-v2-all-item]").count()
        run.shot(page, "B6-alerts")
        ok = h1.startswith("Watchlist") and "AAPL" in lst and n >= 1
        run.record("B6", "Open #/alerts", "heading Watchlist with the Alerts view, All alerts listing the AAPL hits",
                   "h1 '{}', tabs {}, {} items, AAPL listed {}".format(" ".join(h1.split()), tabs, n, "AAPL" in lst), "pass" if ok else "fail")
    run.item("B6", "alerts", "", b6)

    def b7():
        page.goto(BASE + "/#/portfolio", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-pf-line]", timeout=45000)
        page.wait_for_timeout(3000)
        line = page.inner_text("[data-v2-pf-line]")
        heads = page.eval_on_selector_all("#main h2", "els => els.map(e => e.textContent.trim())")
        treemap = page.locator("svg[aria-label], .treemap, [data-v2-treemap]").count()
        run.shot(page, "B7-portfolio")
        ok = (line.startswith("Your book: your Paper Desk, empty so far") and "No brokerage is linked" in line
              and any("Diversification" in h for h in heads) and heads and "Optic's model portfolios" in heads[-1]
              and any("market around your books" in h.lower() for h in heads))
        run.record("B7", "Open Portfolio", "the book line, Diversification, the sector treemap, Optic's model portfolios last",
                   "line '{}'; headings in order {}; treemap-like figures {}".format(" ".join(line.split()), heads, treemap), "pass" if ok else "fail")
    run.item("B7", "portfolio", "", b7)

    def b8():
        page.goto(BASE + "/#/calendar", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-cal-sessions]", timeout=45000)
        rows = page.eval_on_selector_all("[data-v2-cal-sessions] tbody tr", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())")
        fut = page.inner_text("[data-v2-cal-futures]") if page.locator("[data-v2-cal-futures]").count() else ""
        run.shot(page, "B8-calendar")
        closed = [r for r in rows if "Thanksgiving" in r and "Closed" in r]
        early = [r for r in rows if "Early close" in r]
        ok = closed and early and "1:00" in " ".join(early) and "not modelled" in fut
        run.record("B8", "Open Markets, then Calendar", "Thanksgiving closed, the day after closing at 1:00 pm in the reader's zone (New York here), futures not modelled",
                   "closed: {}; early: {}; futures line: '{}'".format(closed, early, " ".join(fut.split())[:160]), "pass" if ok else "fail")
    run.item("B8", "calendar", "", b8)

    def refusals():
        page.goto(BASE + "/#/owner-report", wait_until="domcontentloaded")
        page.wait_for_selector("text=This is for the owner of this site", timeout=30000)
        st = page.evaluate("async () => (await fetch('/api/admin/owner-report')).status")
        run.shot(page, "R1-owner-report-evaluator")
        run.record("R1", "The owner report for the evaluator", "'This is for the owner of this site...'; 403 at the API",
                   "page says 'This is for the owner of this site...'; signals table {}; GET /api/admin/owner-report {}".format(
                       page.locator("[data-v2-or-signals]").count(), st), "pass" if st == 403 and page.locator("[data-v2-or-signals]").count() == 0 else "fail")
        got = page.evaluate("""async () => { const t = (document.cookie.match(/(?:^|; )optic_csrf=([^;]+)/) || [])[1] || '';
            const g = await (await fetch('/api/alert-delivery/me')).json();
            const r = await fetch('/api/alert-delivery/me', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Optic-CSRF': decodeURIComponent(t) }, body: JSON.stringify({ email_me: true }) });
            let b = {}; try { b = await r.json(); } catch (e) {} return { offered: g.offered, status: r.status, detail: b.detail || '' }; }""")
        page.goto(BASE + "/#/settings", wait_until="domcontentloaded")
        page.wait_for_selector("#pl-h", timeout=30000)
        page.wait_for_timeout(1500)
        btn = page.locator("[data-v2-alert-mail]").count()
        run.notes["alert_delivery_offered"] = got.get("offered")
        ok = got["status"] == 409 and got["detail"] == "Alert emails to readers are not switched on here." and btn == 0
        run.record("R2", "Alert email opt-in while the owner's switch is off", "409 'Alert emails to readers are not switched on here.'",
                   "offered {}; POST /api/alert-delivery/me {} '{}'; Settings shows the opt-in button: {}".format(got["offered"], got["status"], got["detail"], bool(btn)),
                   "pass" if ok else "fail")
    run.item("R", "refusals", "", refusals)

    def f24_f25():
        offered = run.notes.get("alert_delivery_offered")
        run.record("F24", "Reader alert delivery: opt in from Settings and receive a hit's mail",
                   "with ALERT_DELIVERY_READERS on, one mail per hit to the reader",
                   "not reached: the switch is off on the copy (offered {}), there is no in-product control for it, and Railway variables are not "
                   "this run's to change".format(offered), "not reached")
        ms = run.mails()
        mine = [m for m in ms if any(t["Address"].lower() == EVALUATOR for t in m["To"])]
        alert = [m for m in mine if m["Subject"].startswith("Optic alert: AAPL")]
        reset = [m for m in mine if m["Subject"] == "Reset your Optic Terminal password"]
        ctx2 = browser.new_context(viewport=DESKTOP, http_credentials={"username": run.gate_user, "password": run.key["gate"], "origin": MAIL})
        p2 = ctx2.new_page()
        p2.goto(MAIL + "/", wait_until="domcontentloaded")
        p2.wait_for_timeout(2500)
        listed = p2.inner_text("body")
        ctx2.close()
        ok = alert and reset and "Optic alert" in listed
        run.record("F25", "Open the mail sink", "the alert mail and a reset mail to the evaluator",
                   "sink holds {} mails, {} to the evaluator: {} alert ('{}'), {} reset; the sink's own page lists the alert subject: {}".format(
                       len(ms), len(mine), len(alert), alert[0]["Subject"] if alert else "", len(reset), "Optic alert" in listed), "pass" if ok else "fail")
    run.item("F25", "mail sink", "", f24_f25)

    charts(run, browser, page)
    milo(run, page)
    axe_scan(run, browser)
    soak(run, page)
    ctx.close()


def charts(run: Run, browser, page) -> None:
    def chart():
        page.goto(BASE + "/#/AAPL/chart", wait_until="domcontentloaded")
        page.wait_for_selector("#ch-body .pc-svg", timeout=60000)
        page.wait_for_timeout(1500)

    def c9():
        chart()
        if page.get_attribute("[data-v2-ch-count='1']", "aria-pressed") != "true":
            page.click("[data-v2-ch-count='1']")
            page.wait_for_function("() => !document.querySelector('[data-chg-slot]')")
        side_hidden = page.is_hidden("#ch-side")
        rail = page.locator(".ch-draw[role='toolbar']").is_visible()
        w0 = page.locator("#ch-body").bounding_box()["width"]
        page.click("[data-chw='options']")
        page.wait_for_selector("#chw-options [data-chw-optview]", timeout=30000)
        views = page.eval_on_selector_all("#chw-options [data-chw-optview]", "els => els.map(e => e.textContent.trim())")
        pressed = []
        for v in ("readings", "chain", "builder", "gamma", "flow"):
            page.click("#chw-options [data-chw-optview='{}']".format(v))
            page.wait_for_selector("#chw-options [data-chw-optview='{}'][aria-pressed='true']".format(v))
            pressed.append(v)
        w1 = page.locator("#ch-body").bounding_box()["width"]
        run.shot(page, "C9-options-in-dock")
        page.click("[data-chw-close='options']")
        page.wait_for_function("() => document.querySelector('#ch-side').hidden", timeout=15000)
        page.wait_for_timeout(600)
        w2 = page.locator("#ch-body").bounding_box()["width"]
        ok = side_hidden and rail and views == ["Readings", "Chain", "Builder", "Gamma", "Flow"] and w1 < w0 - 150 and w2 > w1 + 150
        run.record("C9", "AAPL Chart: the dock; Options in the dock; close it", "widgets stacked right, none open; tool rail left; five views inside; chart narrower, then wider",
                   "no widget open {}; tool rail {}; views {} each pressed; chart {} px, {} px with Options open, {} px closed".format(
                       side_hidden, rail, views, round(w0), round(w1), round(w2)), "pass" if ok else "fail")
    run.item("C9", "dock", "", c9)

    def c11():
        page.select_option("[data-v2-ch-iv]", "daily")
        page.wait_for_selector("#ch-body .pc-svg", timeout=60000)
        page.click("[data-v2-ch-range='All']")
        page.wait_for_function("() => /history here starts on/.test((document.querySelector('#ch-note') || {}).textContent || '')", timeout=60000)
        note = " ".join(page.inner_text("#ch-note").split())
        run.shot(page, "C11-all-history")
        ok = "AAPL's history here starts on Dec 12, 1980" in note and "split-adjusted" in note
        run.record("C11", "On the daily bar size, press All", "the whole history and 'AAPL's history here starts on Dec 12, 1980 ... split-adjusted'",
                   "note: '{}'".format(note[:300]), "pass" if ok else "fail")
    run.item("C11", "All", "", c11)

    def c12():
        page.click("[data-v2-ch-range='1Y']") if page.locator("[data-v2-ch-range='1Y']").count() else None
        page.wait_for_selector("#ch-body .pc-svg", timeout=60000)
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:  # noqa: BLE001 - a live socket can stay busy; the wait below still lets the redraw settle
            pass
        page.wait_for_timeout(2500)
        page.click("[data-v2-tool='fibdraw']")
        box = page.locator("#ch-body .pc-svg").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.30, box["y"] + box["height"] * 0.70)
        page.wait_for_timeout(300)
        page.mouse.click(box["x"] + box["width"] * 0.65, box["y"] + box["height"] * 0.25)
        page.wait_for_selector("#ch-body .pc-svg text.dr-t", timeout=15000)
        labels = page.eval_on_selector_all("#ch-body .pc-svg text.dr-t", """els => els.map(e => ({ t: e.textContent, anchor: e.getAttribute('text-anchor'),
            right: e.getBBox().x + e.getBBox().width, w: e.ownerSVGElement.getBoundingClientRect().width }))""")
        texts = [l["t"] for l in labels]
        run.shot(page, "C12-fibonacci")
        right = all(l["anchor"] == "end" and l["right"] > l["w"] * 0.6 for l in labels)
        prices = {t.split(" ", 1)[1] for t in texts if " " in t}
        ok = any(t.startswith("0.5 ") for t in texts) and any(t.startswith("0.618 ") for t in texts) and right and len(prices) == len(texts)
        page.click("[data-v2-ch-clear='ask']")
        page.click("[data-v2-ch-clear='yes']")
        page.wait_for_function("() => !document.querySelector('#ch-body .pc-svg text.dr-t')", timeout=10000)
        page.click("[data-v2-ch-range='6M']") if page.locator("[data-v2-ch-range='6M']").count() else None
        run.record("C12", "Draw a Fibonacci retracement from the tools", "labels on the right edge, 0.5 and 0.618 among them",
                   "drawn with two clicks; labels {} (anchored at the right edge: {}); then removed with Remove all".format(texts, right),
                   "pass" if ok else "fail")
    run.item("C12", "Fibonacci", "", c12)

    def c10():
        page.click("[data-v2-ch-count='4']")
        for i in (1, 2, 3):
            page.wait_for_selector("[data-chg-slot='{}'] .pc-svg".format(i), timeout=60000)
        boxes = page.locator("[data-chg-slot] input[name='s']").count()
        page.fill("[data-chg-slot='2'] input[name='s']", "AAPL")
        page.press("[data-chg-slot='2'] input[name='s']", "Enter")
        page.wait_for_selector("[data-chg-slot='2'][data-chg-sym='AAPL'] .pc-svg", timeout=60000)
        page.wait_for_timeout(1500)
        syms = page.eval_on_selector_all("[data-chg-slot]", "els => els.map(e => e.dataset.chgSym)")
        page.click("[data-v2-tool='hline']")
        box = page.locator("#ch-body .pc-svg").bounding_box()
        page.mouse.click(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.40)
        counts = page.evaluate("""() => new Promise((ok) => requestAnimationFrame(() => { const n = (s) => document.querySelectorAll(s + ' .pc-svg line.dr').length;
            ok([n('#ch-body'), n("[data-chg-slot='1']"), n("[data-chg-slot='2']"), n("[data-chg-slot='3']")]); }))""")
        page.wait_for_timeout(500)
        later = page.evaluate("""() => { const n = (s) => document.querySelectorAll(s + ' .pc-svg line.dr').length;
            return [n('#ch-body'), n("[data-chg-slot='1']"), n("[data-chg-slot='2']"), n("[data-chg-slot='3']")]; }""")
        run.shot(page, "C10-four-charts-shared-line")
        exp = [1] + [1 if s == "AAPL" else 0 for s in syms]
        ok = counts == exp and boxes == 3
        run.record("C10", "Press 4; AAPL in two charts; a horizontal line on the main chart", "four charts each with its own ticker box; the line on both AAPL charts at once, not on the others",
                   "charts: main AAPL + slots {}; ticker boxes on the three added charts {}; lines per chart at the first frame {} (expected {}), 0.5 s later {}".format(
                       syms, boxes, counts, exp, later), "pass" if ok else "fail")
        page.click("[data-v2-ch-clear='ask']")
        page.click("[data-v2-ch-clear='yes']")
    run.item("C10", "four charts", "", c10)

    def c13():
        page.set_viewport_size(PHONE)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("[data-chg-slot='1'] .pc-svg", timeout=60000)
        note = page.inner_text("#ch-gridnote") if page.locator("#ch-gridnote").count() else ""
        counts = page.eval_on_selector_all("[data-v2-ch-count]", "els => els.map(e => e.dataset.v2ChCount)")
        main = page.locator("#ch-body").bounding_box()
        other = page.locator("[data-chg-slot='1']").bounding_box()
        stacked = other["y"] >= main["y"] + main["height"] - 1
        sideways = page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth + 1")
        n = page.locator("[data-chg-slot]").count()
        run.shot(page, "C13-four-at-390")
        want = "This layout has 4 charts; a screen this narrow shows the first two, stacked. A wider window shows all 4."
        ok = want in " ".join(note.split()) and stacked and sideways and n == 1
        run.record("C13", "The four-chart layout at 390 wide", "two charts stacked and '{}'".format(want),
                   "charts drawn {} (main + {}); stacked {}; no sideways scroll {}; layout control offers {}; note '{}'".format(
                       n + 1, n, stacked, sideways, counts, " ".join(note.split())), "pass" if ok else "fail")
        page.set_viewport_size(DESKTOP)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#ch-body .pc-svg", timeout=60000)
        page.click("[data-v2-ch-count='1']")
    run.item("C13", "390 notice", "", c13)

    def c14():
        got = []
        for label, preset in (("Charts & Technicals", "technicals"), ("Options & Derivatives", "derivatives")):
            page.goto(BASE + "/#/AAPL", wait_until="domcontentloaded")
            page.locator(".rail-nav a.rail-row", has_text=label).first.click()
            page.wait_for_selector("[data-ws-preset='{}'][aria-selected='true']".format(preset), timeout=45000)
            page.wait_for_timeout(1500)
            n = page.locator("[data-ws-panel]:not([hidden])").count()
            run.shot(page, "C14-" + preset)
            got.append((label, preset, n))
        page.goto(BASE + "/#/?preset=positions&symbol=AAPL", wait_until="domcontentloaded")
        page.wait_for_selector("[data-ws-preset='positions'][aria-selected='true']", timeout=45000)
        page.wait_for_timeout(1500)
        n = page.locator("[data-ws-panel]:not([hidden])").count()
        run.shot(page, "C14-positions")
        got.append(("Portfolio (#/?preset=positions, the address the rail's layouts use)", "positions", n))
        ok = all(x[2] >= 4 for x in got)
        run.record("C14", "Open Charts & Technicals, Options & Derivatives (from the rail), then Portfolio's trading layout",
                   "each opens as panels on the panel grid with its tab selected",
                   "; ".join("{}: tab {} selected, {} panels".format(*x) for x in got), "pass" if ok else "fail")
    run.item("C14", "trading layouts", "", c14)

    def c14b():
        # round three D3: the rail entry that opened a trading layout is the current one, and Home is not
        cur = "() => [...document.querySelectorAll('.rail [aria-current=\"page\"]')].map(a => a.textContent.trim())"
        got, ok = [], True
        for label, preset in (("Charts & Technicals", "technicals"), ("Options & Derivatives", "derivatives")):
            page.goto(BASE + "/#/AAPL", wait_until="domcontentloaded")
            page.locator(".rail-nav a.rail-row", has_text=label).first.click()
            page.wait_for_selector("[data-ws-preset='{}'][aria-selected='true']".format(preset), timeout=45000)
            page.wait_for_function("l => [...document.querySelectorAll('.rail [aria-current=\"page\"]')].map(a => a.textContent.trim()).includes(l)",
                                   arg=label, timeout=15000)
            on = page.evaluate(cur)
            run.shot(page, "C14b-" + preset)
            got.append("{}: current {}".format(label, on))
            ok = ok and on == [label]
        page.locator(".rail-nav a.rail-row", has_text="Home").first.click()
        page.wait_for_function("() => location.hash === '#/'", timeout=15000)
        page.wait_for_timeout(800)
        on = page.evaluate(cur)
        got.append("Home pressed: current {}".format(on))
        ok = ok and on == ["Home"]
        run.record("C14b", "Open Charts & Technicals and Options & Derivatives from the rail, then Home",
                   "the entry opened is the rail's current item (aria-current) and Home is not; Home pressed is current again",
                   "; ".join(got), "pass" if ok else "fail")
    run.item("C14b", "rail current item", "", c14b)


def milo(run: Run, page) -> None:
    def e20():
        walk = [("#/AAPL/financials", "financials"), ("#/", "home"), ("#/AAPL/chart", "chart"), ("#/portfolio", None),
                ("#/calendar", "calendar"), ("#/settings", "settings")]
        seen = []
        for h, view in walk:
            page.goto(BASE + "/" + h, wait_until="domcontentloaded")
            page.wait_for_selector("[data-v2-milo-strip] [data-v2-milo-offer-text]", timeout=45000)
            page.wait_for_timeout(2000)
            got = page.evaluate("() => { const s = document.querySelector('[data-v2-milo-strip]'); return [s.dataset.v2MiloScreen, s.querySelector('[data-v2-milo-offer-text]').textContent.trim()]; }")
            seen.append((h, got[0], got[1]))
        run.shot(page, "E20-strip-settings")
        offers = [s[2] for s in seen]
        ok = all(o and o != "Explain what is on this page" for o in offers) and len(set(offers)) == len(offers) and "AAPL" in offers[0] and "Financials" in offers[0]
        run.record("E20", "The Milo strip on AAPL Financials, Home, Chart, Portfolio, Calendar, Settings", "each names its own screen ('Explain the chart in view on AAPL's Financials' on Financials)",
                   "; ".join("{} -> '{}'".format(h, o) for h, _, o in seen), "pass" if ok else "fail")
    run.item("E20", "strip", "", e20)

    def e20b():
        # round three D2(b): the stance kept on the account is what a newly opened Milo shows, in another browser.
        # The evaluator's kept stance is read first and put back after (a kept 'neutral' stays if none was kept,
        # since an account's stance cannot be unset; neutral is the default reading).
        csrf = next(c["value"] for c in page.context.cookies() if c["name"].lower().endswith("csrf"))
        put = "async ([t, s]) => (await fetch('/api/milo/stance', { method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-Optic-CSRF': t }, body: JSON.stringify({ stance: s }) })).status"
        was = page.evaluate("async () => (await (await fetch('/api/milo/stance')).json()).kept")
        want = "quant" if (was or {}).get("id") != "quant" else "stoic"
        label = {"quant": "As kept: a statistician's reading", "stoic": "As kept: a conservative investor's reading"}[want]
        st = page.evaluate(put, [csrf, want])
        ctx2, page2 = run.context(page.context.browser)
        try:
            run.sign_in(page2, EVALUATOR, run.key["evaluator"])
            t0 = time.monotonic()
            page2.click(".topbar-milo")
            page2.wait_for_selector("#milo-stance-once")
            page2.wait_for_function("k => (document.querySelector('#milo-stance-once option') || {}).textContent === k", arg=label, timeout=30000)
            took = time.monotonic() - t0
            shown = page2.eval_on_selector("#milo-stance-once option", "o => o.textContent")
            run.shot(page2, "E20b-kept-stance")
        finally:
            ctx2.close()
        back = page.evaluate(put, [csrf, (was or {}).get("id") or "neutral"])
        run.record("E20b", "Keep a stance on the account, then open Milo in another browser",
                   "the new panel shows the kept stance ('{}')".format(label),
                   "PUT {} -> {}; second browser's Milo shows '{}' {:.1f} s after the click; put back to {} ({})".format(
                       want, st, shown, took, (was or {}).get("id") or "neutral (none was kept)", back),
                   "pass" if st == 200 and shown == label and back == 200 else "fail")
    run.item("E20b", "kept stance", "", e20b)

    def e21():
        page.goto(BASE + "/#/AAPL/financials", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-milo-strip]", timeout=45000)
        page.click(".topbar-milo")
        page.wait_for_selector("#milo-q")
        page.wait_for_selector("#milo-stance-once")
        options = page.eval_on_selector_all("#milo-stance-once option", "els => els.map(e => [e.value, e.textContent.trim()])")
        page.select_option("#milo-stance-once", "skeptic")
        before = page.locator(".milo-msg.milo-bot").count()
        page.evaluate("""() => { window.__order = []; const strip = (b) => { const c = b.cloneNode(true); c.querySelectorAll('[data-v2-milo-steps], .milo-steps').forEach(x => x.remove()); return c.textContent.trim(); };
            new MutationObserver(() => { const log = document.querySelector('.milo-log'); if (!log) return;
              const bots = log.querySelectorAll('.milo-msg.milo-bot'); const last = bots[bots.length - 1];
              if (log.querySelector('.milo-steps li') && !window.__order.includes('steps')) window.__order.push('steps');
              const b = last && last.querySelector('.milo-bubble'); if (b && bots.length > %d && strip(b).length > 20 && !window.__order.includes('text')) window.__order.push('text');
            }).observe(document.body, { childList: true, subtree: true, characterData: true }); }""" % before)
        q = "What did Apple's free cash flow do over the last four quarters?"
        with page.expect_request(lambda r: r.url.endswith("/api/chat") and r.method == "POST", timeout=30000) as req:
            page.fill("#milo-q", q)
            page.press("#milo-q", "Enter")
        persona = json.loads(req.value.post_data or "{}").get("persona")
        page.wait_for_function("n => document.querySelectorAll('.milo-msg.milo-bot').length > n && !document.querySelector('.milo-msg .activity')", arg=before, timeout=180000)
        page.wait_for_timeout(800)
        last = page.locator(".milo-msg.milo-bot").last
        tag = last.locator("[data-v2-milo-stance-tag]").inner_text() if last.locator("[data-v2-milo-stance-tag]").count() else ""
        body = last.locator(".milo-bubble").inner_text()
        steps = ""
        if last.locator(".milo-steps-done").count():
            last.locator(".milo-steps-done summary").click()
            steps = " ".join(last.locator(".milo-steps-done").inner_text().split())
        order = page.evaluate("() => window.__order")
        run.shot(page, "E21-skeptic-answer")
        bad = re.findall(r"(?i)\b(price target|target price|strong buy|buy rating|sell rating|hold rating|rated (?:a )?(?:buy|sell|hold)|we forecast|i forecast|will (?:rise|fall|climb|drop) to)\b", body)
        run.notes["E21_answer"] = body
        ok = persona == "skeptic" and tag == "A skeptic's reading" and order[:2] == ["steps", "text"] and not bad
        run.record("E21", "Choose 'A skeptic's reading' and ask '{}'".format(q), "steps (tool and source) before the answer; labelled 'A skeptic's reading'; no rating, target or forecast",
                   "stance options {}; sent persona {}; order seen {}; stance tag '{}'; steps '{}'; rating/target/forecast words {}; answer {} words, begins '{}'".format(
                       [o[0] for o in options], persona, order, tag, steps[:220], bad, len(body.split()), " ".join(body.split())[:160]),
                   "pass" if ok else "fail", answer=body)
    run.item("E21", "stance answer", "", e21)

    def e22():
        before = page.locator(".milo-msg.milo-bot").count()
        q = "Can you write me a Python script that sorts a list?"
        page.fill("#milo-q", q)
        page.press("#milo-q", "Enter")
        page.wait_for_function("n => document.querySelectorAll('.milo-msg.milo-bot').length > n && !document.querySelector('.milo-msg .activity')", arg=before, timeout=120000)
        page.wait_for_timeout(500)
        txt = " ".join(page.locator(".milo-msg.milo-bot").last.locator(".milo-bubble").inner_text().split())
        sentences = [x for x in re.split(r"(?<=[.!?])\s+", txt) if x]
        run.shot(page, "E22-off-topic")
        ok = len(sentences) == 1 and "can't" in txt and " it can " in txt
        run.record("E22", "Ask '{}'".format(q), "one sentence declining that names what Optic can do", "'{}' ({} sentence)".format(txt, len(sentences)),
                   "pass" if ok else "fail")
    run.item("E22", "off-topic", "", e22)

    def e23():
        st = """() => { const t = document.querySelector('[data-v2-milo-strip-toggle]'); return { expanded: t.getAttribute('aria-expanded'), label: t.textContent.trim(),
            docked: document.documentElement.classList.contains('milo-docked'), width: Math.round(document.querySelector('#main').getBoundingClientRect().width) }; }"""
        tog = "[data-v2-milo-strip-toggle]"
        # Milo was opened from the top bar's Ask Milo for E21 and E22: the strip's control as it stands, then pressed
        a = page.evaluate(st)
        page.click(tog)
        page.wait_for_function("() => !document.documentElement.classList.contains('milo-docked')", timeout=10000)
        page.wait_for_timeout(600)
        b = page.evaluate(st)
        run.shot(page, "E23-after-first-press")
        # then the strip's own round trip: open from the strip, collapse from the strip
        page.click(tog)
        page.wait_for_function("() => document.documentElement.classList.contains('milo-docked')", timeout=10000)
        page.wait_for_timeout(600)
        c = page.evaluate(st)
        page.click(tog)
        page.wait_for_function("() => !document.documentElement.classList.contains('milo-docked')", timeout=10000)
        page.wait_for_timeout(600)
        d = page.evaluate(st)
        run.shot(page, "E23-collapsed")
        folds = a["docked"] and not b["docked"] and b["width"] > a["width"] + 100 and c["docked"] and not d["docked"] and d["width"] > c["width"] + 100
        label_true = a["expanded"] == "true" and c["expanded"] == "true" and c["label"] == "Collapse Milo" and d["expanded"] == "false"
        fmt = lambda x: "{} / aria-expanded {} / docked {} / page {} px".format(x["label"], x["expanded"], x["docked"], x["width"])
        run.record("E23", "Press the strip's collapse control", "Milo folds to the strip and the page takes the width back; the control says what it does",
                   "Milo open from the top bar: strip control '{}'; pressed: '{}'; pressed again (open from the strip): '{}'; pressed again: '{}'".format(
                       fmt(a), fmt(b), fmt(c), fmt(d)), "pass" if folds and label_true else "fail", folds=folds, label_true=label_true)
    run.item("E23", "collapse", "", e23)


SCREENS = [("home", "/#/", "[data-v2-lc]"), ("watchlist", "/#/watchlist", "[data-v2-wl-alerts], .wl-rows"),
           ("alerts", "/#/alerts", "[data-v2-all-list]"), ("portfolio", "/#/portfolio", "[data-v2-pf-line]"),
           ("calendar", "/#/calendar", "[data-v2-cal-sessions]"), ("aapl-overview", "/#/AAPL", "#ov-analysis"),
           ("aapl-financials", "/#/AAPL/financials", "#main figure[data-v2-metric], #main section"),
           ("aapl-chart", "/#/AAPL/chart", "#ch-body .pc-svg"), ("settings", "/#/settings", "#pl-h"),
           ("terms", "/#/terms", "[data-v2-legal]")]


def axe_scan(run: Run, browser) -> None:
    def go():
        from axe_playwright_python.sync_playwright import Axe
        axe = Axe()
        rows, total = [], 0
        for vp_name, vp in (("1440", DESKTOP), ("390", PHONE)):
            ctx, page = run.context(browser, viewport=vp)
            run.sign_in(page, EVALUATOR, run.key["evaluator"])
            for name, path, sel in SCREENS:
                page.goto(BASE + path, wait_until="domcontentloaded")
                page.wait_for_selector(sel, timeout=60000)
                try:
                    page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:  # noqa: BLE001 - live feeds can keep a socket busy; the scan runs on what is drawn
                    pass
                page.wait_for_timeout(1500)
                res = axe.run(page, options={"runOnly": {"type": "tag", "values": TAGS}})
                v = [{"id": x["id"], "impact": x["impact"], "nodes": [n["target"] for n in x["nodes"]][:4]} for x in res.response.get("violations", [])]
                total += len(v)
                rows.append({"screen": name, "width": vp_name, "violations": v})
            ctx.close()
        bad = [r for r in rows if r["violations"]]
        run.record("X1", "axe (WCAG 2.1 A and AA) on the main screens, signed in, at 1440 and 390",
                   "0 violations", "{} scans, {} violations{}".format(len(rows), total,
                                                                     "; " + "; ".join("{} at {}: {}".format(r["screen"], r["width"], [x["id"] for x in r["violations"]]) for r in bad) if bad else ""),
                   "pass" if not bad else "fail", scans=rows)
    run.item("X1", "axe", "", go)


def soak(run: Run, page) -> None:
    def go():
        stats = {"requests": 0, "finished": 0, "failed": 0, "statuses": {}, "five_xx": [], "failed_urls": [], "hosts": {}}

        pending: Dict[Any, str] = {}

        def on_req(r):
            stats["requests"] += 1
            pending[r] = "{} {}".format(r.resource_type, r.url.split("?")[0][-90:])
            h = re.match(r"https?://([^/]+)", r.url)
            h = h.group(1) if h else r.url[:20]
            stats["hosts"][h] = stats["hosts"].get(h, 0) + 1

        def on_fin(r):
            pending.pop(r, None)
            stats["finished"] += 1
            try:
                resp = r.response()
                st = resp.status if resp else 0
            except Exception:  # noqa: BLE001
                st = 0
            stats["statuses"][str(st)] = stats["statuses"].get(str(st), 0) + 1
            if st >= 400:
                stats.setdefault("four_xx", []).append("{} {}".format(st, r.url.split("?")[0][-90:]))
            if st >= 500:
                stats["five_xx"].append("{} {}".format(st, r.url.split("?")[0]))

        def on_fail(r):
            pending.pop(r, None)
            stats["failed"] += 1
            stats["failed_urls"].append("{} ({})".format(r.url.split("?")[0][-80:], r.failure))
        page.on("request", on_req)
        page.on("requestfinished", on_fin)
        page.on("requestfailed", on_fail)
        times = []
        t0 = now()
        for i in range(30):
            name, path, sel = SCREENS[i % len(SCREENS)]
            page.goto("about:blank")
            s = time.perf_counter()
            page.goto(BASE + path, wait_until="load")
            try:
                page.wait_for_selector(sel, timeout=45000)
            except Exception:  # noqa: BLE001 - recorded as a slow load, the counts still stand
                pass
            times.append(time.perf_counter() - s)
            page.wait_for_timeout(1200)
        page.goto("about:blank")
        page.wait_for_timeout(1500)
        page.remove_listener("request", on_req)
        page.remove_listener("requestfinished", on_fin)
        page.remove_listener("requestfailed", on_fail)
        times.sort()
        still = sorted(pending.values())
        accounted = stats["finished"] + stats["failed"] + len(still) == stats["requests"]
        aborted = [u for u in stats["failed_urls"] if "ABORTED" in u.upper()]
        other_fail = [u for u in stats["failed_urls"] if "ABORTED" not in u.upper()]
        ok = accounted and not stats["five_xx"] and not other_fail
        run.record("K1", "The HTTP soak: 30 full page loads signed in, through the edge",
                   "every request accounted, 0 5xx",
                   "{} to {}: {} requests, {} finished + {} failed + {} still open when the last page was left {} = {} (accounted {}); statuses {}; 5xx {}; failed: {} aborted by the next navigation, {} other {}; "
                   "page ready median {:.1f} s, worst {:.1f} s; hosts {}".format(
                       t0, now(), stats["requests"], stats["finished"], stats["failed"], len(still), still, stats["finished"] + stats["failed"] + len(still), accounted, stats["statuses"],
                       len(stats["five_xx"]), len(aborted), len(other_fail), other_fail[:5], times[len(times) // 2], times[-1], stats["hosts"]),
                   "pass" if ok else "fail", failed_urls=stats["failed_urls"][:60], five_xx=stats["five_xx"], four_xx=stats.get("four_xx", [])[:60])
    run.item("K1", "soak", "", go)


# ==================================================================== the owner: D, G

def owner(run: Run, browser) -> None:
    ctx, page = run.context(browser)
    run.sign_in(page, OWNER, run.key["admin"])

    def settings():
        page.goto(BASE + "/#/settings", wait_until="domcontentloaded")
        page.wait_for_selector("#pl-h", timeout=45000)
        page.wait_for_function("() => !document.body.innerText.includes('Checking plans...')", timeout=45000)
        page.wait_for_timeout(1000)

    def d15():
        settings()
        page.wait_for_selector("[data-v2-plans]", timeout=30000)
        buttons = page.eval_on_selector_all("[data-v2-plan]", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim())")
        plan = " ".join(page.inner_text("section[aria-labelledby='pl-h']").split())
        run.shot(page, "D15-ladder")
        run.notes["owner_plan_text"] = plan[:200]
        ok = "Choose Pro, $20 a month" in buttons and "Choose Enterprise, $200 a month" in buttons
        run.record("D15", "As the owner, open Settings", "'Choose Pro, $20 a month' and 'Choose Enterprise, $200 a month'",
                   "buttons {}; plan section begins '{}'".format(buttons, plan[:140]), "pass" if ok else "fail")
    run.item("D15", "ladder", "", d15)

    def d16():
        page.click("[data-v2-plan='pro']")
        page.wait_for_url(re.compile(r"https://checkout\.stripe\.com/.*"), timeout=45000)
        url = page.url
        if "cs_live_" in url:
            run.record("D16", "Choose Pro", "Stripe's hosted Checkout in TEST MODE", "a LIVE Checkout session opened; the run stopped at once", "fail")
            raise SystemExit("cs_live_ session: stop")
        page.wait_for_timeout(4000)
        txt = page.inner_text("body")
        test_badge = bool(re.search(r"(?i)test mode|sandbox", txt))
        run.shot(page, "D16-checkout-test-mode")
        session = "cs_test_" in url
        run.notes["checkout_session"] = "cs_test_ (one, unpaid, left to expire on Stripe's own 24 hour expiry)" if session else url[:40]
        run.record("D16a", "Press Choose Pro", "Stripe's hosted Checkout, marked TEST MODE",
                   "checkout.stripe.com, session id starts cs_test_ {}; page shows a test-mode or sandbox mark {}; price on the page $20: {}".format(
                       session, test_badge, "$20" in txt), "pass" if session and test_badge else "fail")
        run.record("D16b", "Pay with the published test card 4242 4242 4242 4242; Settings shows Pro",
                   "paid; back on Optic; Settings shows Pro within a minute",
                   "not reached: this runner does not type a payment card (the agent's standing rule allows a test payment only on a local "
                   "development host); the Checkout session was left unpaid. The operator's ask 16", "not reached")
        page.goto(BASE + "/#/settings", wait_until="domcontentloaded")
    run.item("D16", "checkout", "", d16)

    def d17():
        settings()
        btn = page.locator("[data-v2-billing='portal']")
        label = btn.inner_text().strip() if btn.count() else ""
        if not btn.count():
            run.record("D17", "Press Manage billing", "Stripe's customer portal (test mode)", "no portal button on Settings", "fail")
            return
        btn.click()
        page.wait_for_url(re.compile(r"https://billing\.stripe\.com/.*"), timeout=45000)
        page.wait_for_timeout(4000)
        txt = page.inner_text("body")
        test_badge = bool(re.search(r"(?i)test mode|sandbox", txt))
        switch = bool(re.search(r"(?i)update (plan|subscription)|change plan", txt))
        run.shot(page, "D17-portal")
        run.record("D17", "Press Manage billing (on a Free owner the button reads '{}')".format(label), "Stripe's customer portal (test mode)",
                   "billing.stripe.com opened; test-mode mark {}; a plan-change control on the page {} (no subscription is current)".format(test_badge, switch),
                   "pass" if test_badge else "fail")
        run.record("D18", "Change the plan in the portal (or cancel there); Settings follows", "the plan follows within a minute",
                   "not reached: the owner holds no subscription (D16b was not paid), so the portal has no plan to change or cancel; "
                   "and a portal plan change is a test-mode payment flow this runner does not drive off a local host. The operator's ask 18",
                   "not reached")
        page.goto(BASE + "/#/settings", wait_until="domcontentloaded")
    run.item("D17", "portal", "", d17)

    def d19():
        page.goto(BASE + "/#/terms", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-legal]", timeout=45000)
        ph = page.inner_text("[data-v2-legal='placeholder']") if page.locator("[data-v2-legal='placeholder']").count() else ""
        doc = page.locator(".legal-doc h2").count()
        run.shot(page, "D19-terms")
        ok = "Optic's terms of use and privacy policy are being prepared with counsel." in ph and doc > 0
        run.record("D19", "Open Terms", "'Optic's terms of use and privacy policy are being prepared with counsel.' above the current text",
                   "placeholder '{}'; text in force below with {} headings".format(" ".join(ph.split())[:200], doc), "pass" if ok else "fail")
    run.item("D19", "terms", "", d19)

    def g26():
        t = time.perf_counter()
        with page.expect_response(lambda r: "/api/admin/owner-report" in r.url, timeout=45000) as got:
            page.goto(BASE + "/#/owner-report", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-or-signals]", timeout=45000)
        took = time.perf_counter() - t
        text = page.inner_text("#main")
        group = page.get_attribute("[data-v2-or-group]", "data-v2-or-group") if page.locator("[data-v2-or-group]").count() else None
        weeks = page.locator("[data-v2-or-weeks] tbody tr").count()
        levels = page.locator("[data-v2-or-levels] tbody tr").count()
        signals = page.eval_on_selector_all("[data-v2-or-signals] tbody tr", "els => els.map(e => e.textContent.replace(/\\s+/g, ' ').trim().slice(0, 60))")
        run.shot(page, "G26-owner-report")
        ok = got.value.status == 200 and "%" not in text and group == "everyone" and "Group: everyone." in text and weeks > 0 and levels > 0
        run.record("G26", "As the owner, open #/owner-report", "the three signals per week and over 30 days, levels used, the screens; counts only; 'Group: everyone.'",
                   "API {} , drawn in {:.2f} s; signals {}; weeks {} rows; levels {} rows; '%' on the page {}; group {}".format(
                       got.value.status, took, signals, weeks, levels, "%" in text, group), "pass" if ok else "fail")
    run.item("G26", "owner report", "", g26)

    def g27():
        page.goto(BASE + "/#/metrics", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-modes]", timeout=45000)
        modes = page.eval_on_selector_all("[data-v2-mode]", "els => els.map(e => e.dataset.v2Mode + ': ' + e.textContent.replace(/\\s+/g, ' ').trim().slice(0, 90))")
        run.shot(page, "G27-metrics")
        joined = " ".join(modes).lower()
        need = {"billing": "billing" in joined, "legal": "legal" in joined, "alert delivery": "alert" in joined,
                "chart history": "history" in joined, "off-topic": "off-topic" in joined or "off topic" in joined}
        run.record("G27", "Open Metrics", "'How this site is set' listing billing, legal text, alert delivery, the chart history limit, Milo's off-topic set",
                   "rows {}; found {}".format(modes, need), "pass" if all(need.values()) else "fail")
    run.item("G27", "metrics", "", g27)
    ctx.close()


# ==================================================================== the evaluator's level, back to Beginner

def level_back(run: Run, browser) -> None:
    def go():
        ctx, page = run.context(browser)
        run.sign_in(page, EVALUATOR, run.key["evaluator"])
        page.goto(BASE + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-lc] [aria-pressed='true']")
        page.wait_for_timeout(1500)
        was = page.eval_on_selector("[data-v2-lc] [aria-pressed='true']", "e => e.dataset.v2Level")
        if was != "beginner":
            page.click("[data-v2-lc] [data-v2-level='beginner']")
            page.wait_for_selector("[data-v2-lc] [data-v2-level='beginner'][aria-pressed='true']")
            page.wait_for_timeout(2500)
        ctx.close()
        ctx, page = run.context(browser)
        run.sign_in(page, EVALUATOR, run.key["evaluator"])
        page.goto(BASE + "/#/", wait_until="domcontentloaded")
        page.wait_for_selector("[data-v2-lc] [aria-pressed='true']")
        page.wait_for_timeout(2500)
        now_level = page.eval_on_selector("[data-v2-lc] [aria-pressed='true']", "e => e.dataset.v2Level")
        run.shot(page, "Z1-evaluator-level")
        ctx.close()
        run.record("Z1", "Set the evaluator's level back to Beginner through Home's level control", "Beginner, kept on the account",
                   "was {}; pressed Beginner; a new browser signed in reads {}".format(was, now_level), "pass" if now_level == "beginner" else "fail")
    run.item("Z1", "level back", "", go)


GROUPS = ["identity", "gate", "fresh", "passkey", "evaluator", "owner", "level"]


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", required=True, help="results and screenshots; outside every repository")
    ap.add_argument("--key", default=str(Path.home() / ".conjure" / "optic-eval.key"))
    ap.add_argument("--only", default=",".join(GROUPS), help="comma list of groups: " + ",".join(GROUPS))
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--deployed", default=DEPLOYED, help="the commit the copy runs (V0 compares served files to it)")
    ap.add_argument("--booted", default=BOOTED, help="the boot time /api/health reports, as its ISO prefix")
    a = ap.parse_args(argv)
    globals().update(DEPLOYED=a.deployed, BOOTED=a.booted)
    print(KIND, flush=True)
    out = Path(a.out).resolve()
    probe = subprocess.run(["git", "-C", str(out.parent if not out.exists() else out), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    if probe.returncode == 0:
        raise SystemExit("--out is inside a git repository ({}); choose a folder outside every repository".format(probe.stdout.strip()))
    out.mkdir(parents=True, exist_ok=True)
    key = read_key(Path(a.key).expanduser())
    run = Run(out, key)
    say("Product Optic, issue CON-58, Pass 3; environment {} (Railway conjure-optic-eval, production); deployed {}; started {} UTC".format(BASE, DEPLOYED, now()))
    groups = [g.strip() for g in a.only.split(",") if g.strip()]
    from playwright.sync_api import sync_playwright
    started = now()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=not a.headed)
            if "identity" in groups:
                identity(run)
            if "gate" in groups:
                gate_and_first_visit(run, browser)
            if "fresh" in groups:
                fresh_account(run, browser)
            if "passkey" in groups:
                passkey_signup(run, browser)
            if "evaluator" in groups:
                evaluator(run, browser)
            if "owner" in groups:
                owner(run, browser)
            if "level" in groups:
                level_back(run, browser)
            if "identity" in groups:
                identity(run)
            browser.close()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - said scrubbed, and the results so far are still written
        say("the run stopped: " + scrub(traceback.format_exc()[-2000:]))
    notes = {k: v for k, v in run.notes.items() if k not in ("fresh_ctx",)}
    result = {"kind": KIND, "base": BASE, "deployed": DEPLOYED, "started": started, "ended": now(), "groups": groups,
              "items": run.items, "notes": json.loads(scrub(json.dumps(notes, default=str)))}
    name = "outside-run-{}.json".format(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    (out / name).write_text(json.dumps(result, indent=1))
    counts: Dict[str, int] = {}
    for it in run.items:
        counts[it["status"]] = counts.get(it["status"], 0) + 1
    say("done {}: {} items {}; results {}".format(now(), len(run.items), counts, out / name))
    return 0 if all(it["status"] == "pass" for it in run.items) else 1


if __name__ == "__main__":
    sys.exit(main())

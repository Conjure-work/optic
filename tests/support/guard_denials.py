"""A denial test for every protected route (audit round, 2026-11-27).

tests/support/guard_inventory.py finds the guards by reading the code; it sends no request. This sends one: for each
guarded route and method in the inventory, a request that the guard must refuse, and the code it must refuse with.

- signed out: `require_user`, `require_verified`, both owner guards and `_write_guard` answer 401 (the owner guards
  only on a deployment that names an owner, ADMIN_EMAILS; `_write_guard` only on one that has a write token);
  `verify_signature` unsigned answers 400; `provider.verify_webhook` unsigned answers 401;
- a signed-in reader who is not the owner: both owner guards answer 403; `_write_guard` answers 401 (it falls
  through to the write token, which the reader does not have).

Nothing here sends a request that could succeed: no probe carries a session that may do the thing, a body that is
valid, or a signature. `run(send)` takes any callable, so the same sweep runs in process (the test) and over HTTP
against a running copy:

    python -m tests.support.guard_denials --base https://host [--reader-cookie-file path]

The cookie file holds the Cookie header of a signed-in reader who is not the owner (for example
"optic_session=...; optic_csrf=..."); without it only the signed-out half runs. Exit code 1 on any miss.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple

from app import investigation
from tests.support import guard_inventory

# What each guard refuses with, signed out and as a signed-in reader who is not the owner (None: not asked).
EXPECT: Dict[str, Tuple[int, Optional[int]]] = {
    "require_user": (401, None),
    "require_verified": (401, None),
    "_owner_session_guard": (401, 403),
    "_owner_only": (401, 403),
    "_write_guard": (401, 401),
    "verify_signature": (400, None),
    "provider.verify_webhook": (401, None),
}

# Harmless stand-ins for a path parameter, by name; anything else is "does-not-exist".
PLACEHOLDERS: Dict[str, str] = {"ticker": "AAPL", "symbol": "AAPL", "provider": "google", "name": "does-not-exist"}

# "METHOD path" -> {"path": ..., "body": ..., "reason": ...} for a route where input is checked before its guard, so a
# placeholder never reaches the guard. An override changes the request, never the expected refusal.
OVERRIDES: Dict[str, Dict[str, Any]] = {
    "POST /api/investigate/{ticker}/step": {
        "path": "/api/investigate/AAPL/step", "body": {"step": investigation.STEP_IDS[0], "item_id": "does-not-exist"},
        "reason": "the step name is checked (422) before the saved investigation is looked up and the guard runs, so the "
                  "body names a real step and an item that is not there; the guard is what refuses it"},
    "GET /api/auth/{provider}/start": {
        "path": "/api/auth/google/start?link=1",
        "reason": "the session guard runs only when the request asks to link a provider to the signed-in account "
                  "(link=1); without it the route is the public start of a sign-in and redirects"},
}

# Routes whose guard is a question, not a refusal: the route answers anyone, and the guard decides what the caller is
# allowed to do (the owner's or the write token's extra powers). No request that must be refused exists for them, and
# sending one signed out would start the work (a scan, a feed read, a model call), so the sweep does not send them.
# "METHOD path" -> what the guard decides there. A new route that uses a guard this way must be added here on purpose.
PREDICATE: Dict[str, str] = {
    "POST /api/alerts/seen": "anyone may call it; without the write guard it answers 200 and marks nothing (tested directly)",
    "POST /api/catalysts/refresh": "open to everyone with a cooldown; the guard (via _is_operator) lifts the cooldown and the window",
    "POST /api/tracker/mark": "open to everyone with a cooldown; the guard (via _is_operator) lifts the cooldown",
    "POST /api/tracker/scan": "open to everyone with a cooldown; the guard (via _is_operator) lifts the cooldown and allows a caller's own list",
    "GET /api/weekly": "reading is open to everyone; the guard (via _is_operator) decides whether force=true may rewrite the update",
}


class Probe(dict):
    """One request that must be refused: line, guard, method, path, body, out (signed-out code), reader (code or None)."""


def _fill(path: str) -> str:
    return re.sub(r"\{([^}:]+)(?::[^}]*)?\}", lambda m: PLACEHOLDERS.get(m.group(1), "does-not-exist"), path)


def probes(app) -> List[Probe]:
    """One probe per guarded row of the inventory, less the routes that use a guard as a question (PREDICATE)."""
    out: List[Probe] = []
    for row in guard_inventory.inventory(app)["rows"]:
        if row["class"] != "guarded":
            continue
        if row["line"] in PREDICATE:
            continue
        method, template = row["line"].split(" ", 1)
        guards = [g[0] for g in row["guards"]]
        known = [g for g in guards if g in EXPECT]
        if not known:
            raise KeyError("{} is guarded by {} and the denial sweep has no expectation for it".format(row["line"], guards))
        guard = known[0]
        # the strictest guard decides the signed-in answer: an owner guard before a plain session guard
        for g in known:
            if EXPECT[g][1] is not None:
                guard = g
                break
        out_code, reader_code = EXPECT[guard]
        over = OVERRIDES.get(row["line"], {})
        out.append(Probe(line=row["line"], guard=guard, guards=guards, method=method,
                         path=over.get("path") or _fill(template),
                         body=over.get("body", {} if method in ("POST", "PUT", "PATCH", "DELETE") else None),
                         out=out_code, reader=reader_code, reason=over.get("reason", "")))
    return out


Sender = Callable[[Probe, bool], int]


def run(send: Sender, app, reader: bool = True) -> List[Dict[str, Any]]:
    """Send every probe signed out and, where it asks, as a reader; one row per request:
    line, guard, sent ("METHOD path as who"), status, expected, pass."""
    rows: List[Dict[str, Any]] = []
    for p in probes(app):
        for as_reader in (False, True):
            if as_reader and (not reader or p["reader"] is None):
                continue
            want = p["reader"] if as_reader else p["out"]
            try:
                got = send(p, as_reader)
            except Exception as exc:                                  # a refused connection is a miss, not a crash
                got = "error: {}".format(exc)
            rows.append({"line": p["line"], "guard": p["guard"], "sent": "{} {} as {}".format(
                p["method"], p["path"], "a reader" if as_reader else "nobody"),
                "status": got, "expected": want, "pass": got == want})
    return rows


def http_sender(base: str, cookie: str = "") -> Sender:
    """A sender over HTTP for a running copy. Never follows a redirect; a refusal is an HTTPError carrying its code."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect)
    csrf = re.search(r"optic_csrf=([^;\s]+)", cookie or "")

    def send(p: Probe, as_reader: bool) -> int:
        data = json.dumps(p["body"]).encode() if p["body"] is not None else None
        req = urllib.request.Request(base.rstrip("/") + p["path"], data=data, method=p["method"])
        if data is not None:
            req.add_header("Content-Type", "application/json")
        if as_reader:
            req.add_header("Cookie", cookie)
            if csrf:
                req.add_header("x-optic-csrf", csrf.group(1))
        try:
            with opener.open(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    return send


def main(argv: List[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True)
    ap.add_argument("--reader-cookie-file")
    args = ap.parse_args(argv)
    cookie = open(args.reader_cookie_file).read().strip() if args.reader_cookie_file else ""
    import app.main as m
    rows = run(http_sender(args.base, cookie), m.app, reader=bool(cookie))
    for r in rows:
        print("{}  {:<34} {}  got {} want {}  [{}]".format("ok  " if r["pass"] else "MISS", r["guard"], r["sent"], r["status"], r["expected"], r["line"]))
    missed = [r for r in rows if not r["pass"]]
    print("{} requests, {} refused as expected, {} missed".format(len(rows), len(rows) - len(missed), len(missed)))
    return 1 if missed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

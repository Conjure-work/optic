"""Every protected route refuses a caller who may not use it (audit round, 2026-11-27).

The sweep is tests/support/guard_denials.py: one refused request for each guarded route and method in the guard
inventory, signed out, and as a signed-in reader for the owner routes. Run in process here with FastAPI's TestClient;
`python -m tests.support.guard_denials --base <url>` runs the same sweep over HTTP against a running copy.
"""
from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import app.main as main
from app import db as accounts_db
from app.auth import config, deps, store
from app.brokerage import service as brokerage_service
from tests.support import guard_denials as G
from tests.support import guard_inventory

OWNER = "owner@example.com"
PASSWORD = "tungsten-carbide-9"
# the rate limiter's and the usage meters' own bookkeeping is not the reader's data
NOT_COUNTED = {"auth_attempts", "usage_event", "activity_days", "milo_questions", "schema_migrations"}


@pytest.fixture
def desk(accounts, monkeypatch):
    """An owner is named, a write token is set, and a verified reader who is not the owner is signed in on `reader`."""
    monkeypatch.setenv("ADMIN_EMAILS", OWNER)
    monkeypatch.setattr(main, "WRITE_TOKEN", "a-write-token-the-reader-does-not-have")
    # the two webhooks refuse an unsigned delivery only on a deployment that has them switched on
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test_not_a_real_secret")
    monkeypatch.setenv("BROKERAGE_PROVIDER", "sandbox")
    monkeypatch.setenv("OPTIC_DATA_KEY", base64.urlsafe_b64encode(b"k" * 32).decode())
    monkeypatch.delenv("RAILWAY_ENVIRONMENT", raising=False)
    monkeypatch.setattr(brokerage_service, "_provider", None)
    monkeypatch.setattr(brokerage_service, "_provider_key", None)
    guest = TestClient(main.app, follow_redirects=False)
    reader = TestClient(main.app, follow_redirects=False)
    r = reader.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": "reader@example.com",
                                                "password": PASSWORD, "confirm_password": PASSWORD})
    assert r.status_code in (200, 201), r.text
    user = store.get_user_by_email("reader@example.com") if hasattr(store, "get_user_by_email") else None
    if user:
        store.mark_verified(user["id"])
    else:
        accounts_db.execute("UPDATE users SET email_verified = 1 WHERE email = ?", ("reader@example.com",))
    return {"guest": guest, "reader": reader}


def sender(desk):
    def send(p, as_reader):
        c = desk["reader"] if as_reader else desk["guest"]
        headers = {"x-optic-csrf": c.cookies.get(config.CSRF_COOKIE) or ""} if as_reader else {}
        if p["body"] is None:
            return c.request(p["method"], p["path"], headers=headers).status_code
        return c.request(p["method"], p["path"], json=p["body"], headers=headers).status_code
    return send


def counts():
    """Row counts of every table that holds a person's data: accounts, watchlists, layouts, saved research,
    subscriptions, valuations, theses, watches, brokerage records and the rest."""
    names = [r["name"] for r in accounts_db.rows("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    out = {n: accounts_db.row("SELECT COUNT(*) AS n FROM {}".format(n))["n"] for n in names if n not in NOT_COUNTED}
    assert {"users", "watchlists", "chart_layouts", "saved_research", "subscriptions"} <= set(out)
    return out


def test_the_probes_cover_every_guarded_route_and_method():
    guarded = [r["line"] for r in guard_inventory.inventory(main.app)["rows"] if r["class"] == "guarded"]
    got = [p["line"] for p in G.probes(main.app)]
    assert len(guarded) == 116 and sorted(got + sorted(G.PREDICATE)) == sorted(guarded), sorted(set(guarded) ^ set(got))
    assert set(G.PREDICATE) <= set(guarded) and not set(G.PREDICATE) & set(got)
    for p in G.probes(main.app):
        assert "{" not in p["path"], "{} still has a path parameter: {}".format(p["line"], p["path"])


def test_every_override_names_a_guarded_route_and_gives_a_reason():
    guarded = {p["line"] for p in G.probes(main.app)}
    for line, o in G.OVERRIDES.items():
        assert line in guarded and o.get("reason", "").strip(), line


def test_signed_out_every_protected_route_is_refused_with_its_code(desk):
    rows = G.run(sender(desk), main.app, reader=False)
    assert len(rows) == len(G.probes(main.app))
    missed = [r for r in rows if not r["pass"]]
    assert not missed, "\n".join("{line}: {sent} answered {status}, wanted {expected} ({guard})".format(**r) for r in missed)
    assert not [r for r in rows if isinstance(r["status"], int) and 200 <= r["status"] < 300]


def test_a_signed_in_reader_is_refused_on_every_owner_route(desk):
    rows = [r for r in G.run(sender(desk), main.app) if r["sent"].endswith("as a reader")]
    owner_rows = [p for p in G.probes(main.app) if p["reader"] is not None]
    assert len(rows) == len(owner_rows) and len(rows) >= 11
    missed = [r for r in rows if not r["pass"]]
    assert not missed, "\n".join("{line}: {sent} answered {status}, wanted {expected}".format(**r) for r in missed)
    assert {r["status"] for r in rows if r["guard"] in ("_owner_session_guard", "_owner_only")} == {403}


def test_a_guard_used_as_a_question_gives_a_caller_without_it_nothing(desk):
    """The one PREDICATE route whose refusal is checkable without starting work: the inbox's read state is the owner's."""
    r = desk["guest"].post("/api/alerts/seen", json={})
    assert r.status_code == 200 and r.json()["marked"] == 0 and r.json()["shared"] is False, r.text
    r = desk["reader"].post("/api/alerts/seen", json={}, headers={"x-optic-csrf": desk["reader"].cookies.get(config.CSRF_COOKIE) or ""})
    assert r.status_code == 200 and r.json()["marked"] == 0 and r.json()["shared"] is False, r.text


def test_the_sweep_changes_nothing(desk):
    before = counts()
    G.run(sender(desk), main.app)
    assert counts() == before


def test_the_sweep_is_caught_failing_on_a_route_that_does_not_refuse():
    """A canary: two routes the inventory reads as guarded, one that refuses and one whose guard sits behind a flag
    the probe does not send, so it answers a signed-out caller. The sweep passes the first and fails the second."""
    probe = FastAPI()

    @probe.get("/api/probe/refuses")
    async def refuses(request: Request):
        return deps.require_user(request)

    @probe.get("/api/probe/leaks")
    async def leaks(request: Request, check: bool = False):
        if check:
            deps.require_user(request)
        return {"ok": True}

    c = TestClient(probe, follow_redirects=False)
    rows = {r["line"]: r for r in G.run(lambda p, r: c.request(p["method"], p["path"]).status_code, probe)}
    assert rows["GET /api/probe/refuses"]["pass"] is True
    assert rows["GET /api/probe/leaks"]["pass"] is False and rows["GET /api/probe/leaks"]["status"] == 200

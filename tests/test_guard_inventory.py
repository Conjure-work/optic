"""Round three D4 (2026-11-25): every route is guarded with its guard, or public with a reason, and TESTING.md says
which, generated from the app's own route table (tests/support/guard_inventory.py)."""
from __future__ import annotations

import pytest

from app.auth import deps
from app.main import app
from tests.support import guard_inventory as G


@pytest.fixture(scope="module")
def inv():
    return G.inventory(app)


def test_every_route_is_guarded_or_public_with_a_reason(inv):
    missing = [r["line"] for r in inv["rows"] if r["class"] == "unclassified"]
    assert missing == [], ("routes with no guard and no public reason; give each a guard or a reason in "
                           "tests/support/guard_inventory.py PUBLIC: {}".format(missing))


def test_no_public_route_calls_a_guard_and_none_is_stale(inv):
    both = [r["line"] for r in inv["rows"] if r["class"] == "guarded" and r.get("listed_public")]
    assert both == [], "listed as public but guarded; take it out of PUBLIC: {}".format(both)
    assert inv["stale_public"] == [], "listed as public but no longer served: {}".format(inv["stale_public"])


def test_the_inventory_covers_the_whole_route_table(inv):
    served = {"{} {}".format(m, p) for m, p, _ in G.pairs(app)}
    assert {r["line"] for r in inv["rows"]} == served
    assert len(served) >= 285


def test_testing_md_carries_the_generated_inventory():
    section = G.section_in(G.TESTING.read_text())
    assert section is not None, "TESTING.md has lost its guard-inventory markers"
    assert section == G.markdown(app), "TESTING.md's guard inventory is out of date: python -m tests.support.guard_inventory --write"


def test_the_guards_are_found_by_identity():
    import importlib
    for mod, name in G.GUARDS:
        assert callable(getattr(importlib.import_module(mod), name)), "{}.{} no longer exists".format(mod, name)


@pytest.mark.parametrize("line,guard", [
    ("GET /api/admin/usage-signals", "_owner_session_guard"),
    ("GET /api/admin/owner-report", "_owner_only"),
    ("PUT /api/milo/stance", "require_user"),
    ("GET /api/brokerage/workspace/overview", "require_user"),   # through the module's _reader helper
    ("POST /api/tracker/mark", "_write_guard"),
    ("POST /api/billing/webhook", "verify_signature"),
    ("POST /api/brokerage/webhook", "provider.verify_webhook"),
])
def test_known_guards_are_found_on_their_routes(inv, line, guard):
    row = next(r for r in inv["rows"] if r["line"] == line)
    assert row["class"] == "guarded" and guard in [g for g, _ in row["guards"]], row


def test_a_route_that_loses_its_guard_is_caught():
    """A guard taken out of a route moves it to unclassified, which the first test refuses."""
    from fastapi import FastAPI

    probe = FastAPI()

    @probe.get("/api/probe/guarded")
    async def guarded(request: "Request"):                    # noqa: F821 - the annotation is never resolved
        return deps.require_user(request)

    @probe.get("/api/probe/open")
    async def opened():
        return {}

    rows = {r["line"]: r["class"] for r in G.inventory(probe)["rows"]}
    assert rows["GET /api/probe/guarded"] == "guarded"
    assert rows["GET /api/probe/open"] == "unclassified"

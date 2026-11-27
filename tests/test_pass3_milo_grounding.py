"""Round three: Milo kept on Optic's data (flow 12 b).

Each screen names the tools Milo may call there (app/milo_tools.py SCREEN_TOOLS); a tool outside the screen's list is
never offered and never run, whatever the model asks for. A figure in an answer is cited with the lookup that produced
it, and a money figure with no data behind it is taken out of the answer with a note, as an advice sentence is.
"""
import re
import types
from pathlib import Path

import pytest

from app import ai, ai_policy as P, milo_tools
from tests import pass3_milo_fakes as F

ROOT = Path(__file__).resolve().parent.parent
APP_JS = (ROOT / "static" / "v2" / "js" / "app.js").read_text()


def _route_views():
    body = re.search(r"const PAGES = \{(.*?)\};", APP_JS, re.S).group(1)
    return sorted(set(re.findall(r"(?:^|[,{]\s*)([a-z]+):", body)))


def test_every_v2_route_names_its_tools_on_purpose():
    views = _route_views()
    assert len(views) > 30, views                          # the route table was read, not an empty match
    missing = [v for v in views if v not in milo_tools.SCREEN_TOOLS]
    assert missing == [], "a page with no tool list: place it in milo_tools.SCREEN_TOOLS"
    for v, tools in milo_tools.SCREEN_TOOLS.items():
        assert set(tools) <= set(milo_tools.MARKET_TOOLS + milo_tools.PERSONAL_TOOLS), v


def test_the_account_and_legal_screens_offer_only_the_general_tools():
    for v in ("settings", "terms", "privacy", "signin", "metrics"):
        assert "screen_stocks" not in milo_tools.allowed_for(v) and "get_options" not in milo_tools.allowed_for(v)
        assert "get_quote" in milo_tools.allowed_for(v)
    assert set(milo_tools.allowed_for("financials")) >= set(milo_tools.MARKET_TOOLS)


def _box(view):
    import app.main as m
    ctx = {"view": view, "focus": {"view": view, "scope": "auto"}}
    return m._milo_toolbox(types.SimpleNamespace(), ctx, [{"role": "user", "content": "What moved?"}]), ctx


@pytest.mark.parametrize("view", ["settings", "terms", "financials", "home", "chart"])
def test_the_route_offers_exactly_the_screens_tools(view):
    box, _ = _box(view)
    offered = {d["name"] for d in box.definitions()}
    assert offered <= set(milo_tools.allowed_for(view))
    assert offered, view


def test_a_tool_outside_the_screens_list_is_never_called_even_when_the_model_asks(monkeypatch):
    import app.main as m
    called = []
    monkeypatch.setattr(m, "_tool_screen", lambda **kw: called.append(kw) or {"status": "ok"})
    box, ctx = _box("settings")
    assert "screen_stocks" not in {d["name"] for d in box.definitions()}
    sent = F.install(monkeypatch, [F.tool_round("screen_stocks", {"screen": "momentum"}), F.text_round("Done. ")])
    events = F.run("Screen for momentum names.", context=ctx, toolbox=box)
    assert called == [], "the screener never ran on Settings"
    assert all("screen_stocks" not in [t.get("name") for t in (kw.get("tools") or [])] for kw in sent)
    steps = [d for k, d in events if k == "step" and d.get("tool") == "screen_stocks"]
    assert steps and steps[-1]["text"].startswith("Not run")


def test_a_figure_is_cited_with_the_lookup_that_produced_it(monkeypatch):
    box = milo_tools.Toolbox(runners={"get_quote": lambda ticker: {"status": "ok", "source": "Yahoo Finance",
                                                                    "price": 199.04, "as_of_utc": "2026-11-20T21:00:00Z"}})
    F.install(monkeypatch, [F.tool_round("get_quote", {"ticker": "AAPL"}), F.text_round("AAPL last traded at $199.04. ")])
    events = F.run("Where is AAPL trading?", toolbox=box)
    done = [d for k, d in events if k == "done"][-1]
    assert done["cited"] and done["cited"][0]["figure"] == "$199.04" and done["cited"][0]["tool"] == "get_quote"
    assert "AAPL" in done["cited"][0]["label"]
    assert "amend" not in [k for k, _ in events]


def test_a_money_figure_with_nothing_behind_it_is_taken_out_with_a_note(monkeypatch):
    # audit F04: the draft is written again once from the data that remains, and the note says how many went
    sent = F.install(monkeypatch, [F.text_round("Revenue is growing. ", "Next year it will earn $412.50 a share. "),
                                   F.text_round("Revenue is growing. The data here has no forecast. ")])
    events = F.run("Tell me about the business.")
    amend = [d for k, d in events if k == "amend"]
    assert len(sent) == 2
    assert amend and "$412.50" not in amend[0]["text"] and "Revenue is growing." in amend[0]["text"]
    assert "unsupported_figure" in amend[0]["rules"] and amend[0]["note"] == P.ground_note(1, "rewritten")
    assert amend[0]["kind"] == "rewritten"


def test_grounding_reads_units_and_rounding():
    ctx = '{"revenue": 394328000000, "price": 199.04, "margin": 0.3125}'
    g = P.ground("Revenue was $394.3 billion. The price is $199. Margin is 31.3%.", ctx, [])
    assert g["removed"] == 0
    assert P.ground("It trades at $250.", ctx, [])["removed"] == 1

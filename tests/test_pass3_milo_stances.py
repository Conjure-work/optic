"""Round three: Milo's named stances (flow 12 c) and the streamed steps (flow 12 d), at the route and in the stream.

Each answer is labelled with its stance in plain words; the reader picks one per answer or keeps one, kept on the
account when signed in (user_preferences.milo_stance through /api/milo/stance, guarded: no user, the wrong user, no
CSRF header). Every stance runs through the advice policy's set: the policy rules ride in every request, the
declined-question block reads after the stance's own block, and no stance text breaks the policy itself.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import ai, ai_policy as P, milo_tools
from app.auth import config
from tests import pass3_milo_fakes as F

client = TestClient(main.app)
GOOD = "tungsten-carbide-9"
SET_E = json.loads((Path(__file__).parent / "milo_eval" / "advice_sets" / "set_e_2026_11_02.json").read_text())["questions"]


@pytest.fixture
def fresh(accounts):
    client.cookies.clear()
    yield accounts
    client.cookies.clear()


def register(email):
    client.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": email,
                                            "password": GOOD, "confirm_password": GOOD})
    return client.cookies.get(config.CSRF_COOKIE)


def test_every_persona_is_a_named_stance_in_plain_words():
    assert set(ai.STANCE_LABELS) == set(ai.PERSONAS)
    assert ai.STANCE_LABELS["stoic"] == "a conservative investor's reading"
    assert ai.STANCE_LABELS["skeptic"] == "a skeptic's reading"
    for sid, label in ai.STANCE_LABELS.items():
        assert label.startswith("a ") and label.endswith("reading"), sid
    assert ai.stance_of("bogus")["id"] == ai.DEFAULT_PERSONA


@pytest.mark.parametrize("stance", sorted(ai.PERSONAS))
def test_every_stance_runs_through_the_advice_policy_set(stance):
    assert P.check_output(ai.PERSONAS[stance]["prompt"] or "") == [], "a stance's own words never break the policy"
    assert P.check_output(ai.STANCE_LABELS[stance]) == []
    for q in SET_E:
        kw, meta = ai.build_chat_request([{"role": "user", "content": q["text"]}], persona=stance)
        texts = [b["text"] for b in kw["system"]]
        assert P.POLICY_TEXT in texts[0], "the rules ride in every stance's request"
        assert meta["stance"]["id"] == stance
        if meta["policy_kinds"]:
            assert texts[-1].startswith("## This question asks for something"), "the policy block reads after the stance"
        if ai.PERSONAS[stance]["prompt"]:
            assert ai.PERSONAS[stance]["prompt"] in texts


def test_each_answer_is_labelled_with_its_stance_before_the_text(monkeypatch):
    F.install(monkeypatch, [F.text_round("The margin narrowed. ")])
    events = F.run("How are margins?", persona="skeptic")
    kinds = [k for k, _ in events]
    assert kinds.index("stance") < kinds.index("delta")
    st = dict(events)["stance"]
    assert st == {"id": "skeptic", "label": "a skeptic's reading", "name": ai.PERSONAS["skeptic"]["label"]}
    assert dict(events)["done"]["stance"]["label"] == "a skeptic's reading"


def test_steps_and_sources_arrive_before_the_answer_text(monkeypatch):
    box = milo_tools.Toolbox(runners={"get_quote": lambda ticker: {"status": "ok", "source": "Yahoo Finance",
                                                                    "price": 101.5}})
    F.install(monkeypatch, [F.tool_round("get_quote", {"ticker": "MSFT"}), F.text_round("MSFT is at $101.50. ")])
    events = F.run("Where is MSFT?", toolbox=box)
    kinds = [k for k, _ in events]
    steps = [d for k, d in events if k == "step"]
    assert [s["kind"] for s in steps] == ["tool", "source"]
    assert steps[1]["text"].startswith("Read MSFT") and steps[1]["source"] == "Yahoo Finance"
    first_text = kinds.index("delta")
    assert all(i < first_text for i, (k, _) in enumerate(events) if k == "step")


def test_the_research_packs_sources_are_steps_before_the_model_starts(monkeypatch):
    sent = F.install(monkeypatch, [F.text_round("Fine. ")])
    pack = {"research": {"ticker": "AAPL", "items": [{"source": "SEC EDGAR", "label": "10-Q", "url": "https://www.sec.gov/x"}]}}
    events = F.run("What did the filing say?", context=pack)
    steps = [d for k, d in events if k == "step"]
    assert steps and steps[0]["source"] == "SEC EDGAR" and steps[0]["text"].startswith("Read ")
    assert sent


# ---------------------------------------------------------------------------------------- the account's stance


def test_a_guest_reads_the_stances_and_keeps_one_in_the_browser(fresh):
    r = client.get("/api/milo/stance")
    assert r.status_code == 200 and r.json()["kept_on"] == "browser" and r.json()["kept"] is None
    assert {s["id"] for s in r.json()["stances"]} == set(ai.PERSONAS)
    assert client.put("/api/milo/stance", json={"stance": "quant"}).status_code == 401      # no user


def test_a_reader_keeps_a_stance_on_the_account_and_only_their_own(fresh):
    csrf = register("first@example.com")
    assert client.put("/api/milo/stance", json={"stance": "stoic"}).status_code == 403      # no CSRF header
    r = client.put("/api/milo/stance", json={"stance": "stoic"}, headers={"X-Optic-CSRF": csrf})
    assert r.status_code == 200 and r.json()["kept"]["label"] == "a conservative investor's reading"
    assert client.get("/api/milo/stance").json()["kept"]["id"] == "stoic"
    assert client.put("/api/milo/stance", json={"stance": "bullish"}, headers={"X-Optic-CSRF": csrf}).status_code == 400
    client.cookies.clear()
    csrf2 = register("second@example.com")                                                  # the wrong user
    assert client.get("/api/milo/stance").json()["kept"] is None, "another reader's stance is never read"
    client.put("/api/milo/stance", json={"stance": "quant"}, headers={"X-Optic-CSRF": csrf2})
    from app.auth import store
    first = fresh.rows("SELECT id FROM users WHERE email = 'first@example.com'")[0]["id"]
    assert store.round_three_preferences(first)["milo_stance"] == "stoic"


def test_the_chat_route_uses_the_accounts_kept_stance_when_the_page_sends_none(fresh, monkeypatch):
    csrf = register("kept@example.com")
    client.put("/api/milo/stance", json={"stance": "quant"}, headers={"X-Optic-CSRF": csrf})
    seen = {}

    async def capture(history, **kw):
        seen.update(kw)
        yield ai._sse("done", {})
    monkeypatch.setattr(main.ai, "stream_chat", capture)
    monkeypatch.setattr(main, "_spend_guard", lambda request: None)
    client.post("/api/chat", json={"messages": [{"role": "user", "content": "What is a P/E?"}]},
                headers={"X-Optic-CSRF": csrf})
    assert seen.get("persona") == "quant"

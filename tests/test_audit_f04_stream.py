"""Audit F04 (2026-11-27): the stream after the grounding check. An answer with a statement taken out is written
again once from the data Milo holds, checked the same way, and replaced by the server's own limit answer when that
does not hold; a clean answer costs no extra call. Anthropic is the scripted stand-in in tests/pass3_milo_fakes.py."""
from app import ai, ai_policy as P, milo_tools
from tests import pass3_milo_fakes as F

DRAFT = ("AAPL trades at $199.04. ", "Next year it will earn $412.50 a share.\n\n| Quarter | OCF |\n|---|---|\n"
         "| Q4 | $91.2 billion |\n")


def _box():
    return milo_tools.Toolbox(runners={"get_quote": lambda ticker: {"status": "ok", "source": "Yahoo Finance",
                                                                    "price": 199.04, "as_of_utc": "2026-11-20T21:00:00Z"}})


def _go(monkeypatch, *rounds, question="Where is AAPL trading?"):
    sent = F.install(monkeypatch, [F.tool_round("get_quote", {"ticker": "AAPL"}), *rounds])
    events = F.run(question, toolbox=_box())
    return sent, events, [d for k, d in events if k == "amend"], [d for k, d in events if k == "done"][-1]


def test_a_clean_rewrite_is_one_amend_one_extra_request_and_cites_from_the_rewrite(monkeypatch):
    sent, events, amend, done = _go(monkeypatch, F.text_round(*DRAFT), F.text_round("The data here carries no forecast. "))
    assert len(sent) == 3                                   # the tool round, the draft, the one rewrite
    assert len(amend) == 1 and amend[0]["kind"] == "rewritten"
    assert amend[0]["text"] == "The data here carries no forecast. "
    assert amend[0]["removed"] == 2 and "unsupported_figure" in amend[0]["rules"]
    assert amend[0]["note"] == P.ground_note(2, "rewritten") and "2 statements" in amend[0]["note"]
    assert done["cited"] == []                              # the draft's $199.04 is not in the final text
    assert [d["state"] for k, d in events if k == "status"].count("checking the figures") == 1


def test_a_rewrite_that_keeps_a_supported_figure_cites_it(monkeypatch):
    _, _, amend, done = _go(monkeypatch, F.text_round(*DRAFT), F.text_round("AAPL trades at $199.04. The data has no forecast. "))
    assert amend[0]["kind"] == "rewritten" and [c["figure"] for c in done["cited"]] == ["$199.04"]


def test_a_rewrite_that_is_still_unsupported_is_the_limit_answer(monkeypatch):
    sent, _, amend, _ = _go(monkeypatch, F.text_round(*DRAFT), F.text_round("It will earn $500.00 a share. "))
    assert len(sent) == 3                                   # one attempt, never a loop
    assert amend[0]["kind"] == "limited"
    assert amend[0]["text"] == P.limit_answer(["AAPL trades at $199.04."])
    assert amend[0]["note"] == P.ground_note(2, "limited") and P.integrity(amend[0]["text"]) == []


def test_a_rewrite_with_a_broken_table_is_the_limit_answer(monkeypatch):
    _, _, amend, _ = _go(monkeypatch, F.text_round(*DRAFT), F.text_round("Here it is:\n\n| A | B |\n|---|---|\n"))
    assert amend[0]["kind"] == "limited"


def test_a_rewrite_call_that_raises_is_the_limit_answer_with_no_error_event(monkeypatch):
    sent, events, amend, done = _go(monkeypatch, F.text_round(*DRAFT), F.failing_round())
    assert len(sent) == 3 and amend[0]["kind"] == "limited"
    assert "error" not in [k for k, _ in events] and done


def test_a_rewrite_that_comes_back_empty_is_the_limit_answer(monkeypatch):
    _, _, amend, _ = _go(monkeypatch, F.text_round(*DRAFT), F.text_round(""))
    assert amend[0]["kind"] == "limited"


def test_a_clean_draft_makes_no_extra_request_and_no_grounding_amend(monkeypatch):
    sent, events, amend, done = _go(monkeypatch, F.text_round("AAPL trades at $199.04. "))
    assert len(sent) == 2 and amend == []
    assert "checking the figures" not in [d.get("state") for k, d in events if k == "status"]
    assert done["cited"] and done["cited"][0]["figure"] == "$199.04"


def test_a_draft_that_does_not_read_whole_is_written_again_even_with_nothing_removed(monkeypatch):
    bad = "Cash flow by quarter.\n\n| Quarter | OCF |\n|---|---|\n| Q4 | 28.101 |\n| Q3 | 27.9 |"
    sent, _, amend, _ = _go(monkeypatch, F.text_round(bad), F.text_round("The data carries one figure only. "))
    assert len(sent) == 3 and amend[0]["kind"] == "rewritten" and amend[0]["removed"] == 0
    assert "0 statements" not in amend[0]["note"]


def test_the_rewrite_request_has_no_tool_calls_and_names_what_was_removed(monkeypatch):
    sent, _, _, _ = _go(monkeypatch, F.text_round(*DRAFT), F.text_round("Fine. "))
    first, rewrite = sent[1], sent[2]
    assert first.get("tool_choice") != {"type": "none"}
    assert rewrite["tool_choice"] == {"type": "none"}
    assert rewrite["max_tokens"] == ai.MILO_REWRITE_MAX_TOKENS < first["max_tokens"] and rewrite["timeout"] == ai.MILO_REWRITE_TIMEOUT
    assert rewrite["model"] == first["model"] and rewrite["system"] == first["system"]
    msgs = rewrite["messages"]
    assert msgs[-2]["role"] == "assistant" and "$412.50" not in msgs[-2]["content"]       # the repaired draft
    assert msgs[-1]["role"] == "user" and "$412.50 a share" in msgs[-1]["content"] and "$91.2 billion" in msgs[-1]["content"]
    # the conversation so far, tool result included
    assert any(m["role"] == "user" and isinstance(m["content"], list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
               for m in msgs)


def test_the_rewrite_tokens_are_in_the_done_usage(monkeypatch):
    _, _, _, done = _go(monkeypatch, F.text_round(*DRAFT), F.text_round("Fine. "))
    assert done["usage"]["output_tokens"] == 3              # tool round, draft, rewrite: one each from the fake


def test_the_format_prompt_asks_for_units_in_the_cell_or_the_heading():
    assert "currency and unit, in the cell or in the column heading" in " ".join(ai.FORMAT_PROMPT.split())

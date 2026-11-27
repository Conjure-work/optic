"""Audit F04 (2026-11-27): the shape of Milo's answer after the grounding check.

Taking a statement out of an answer must leave an answer that still reads whole: a table keeps its header, separator
and rows together, no table is left with no rows, no lead-in is left with nothing after it, and a heading is never
left alone. Unit tests of `app/ai_policy.py` blocks, ground, repair, integrity, ground_note and limit_answer.
"""
import re

import pytest

from app import ai_policy as P

DATA = "Operating cash flow 28101000000 capital spending 2000000000"


def _is_table_whole(text):
    """Every pipe line in `text` belongs to one contiguous table: header, separator, then at least one row."""
    lines = text.split("\n")
    pipes = [i for i, ln in enumerate(lines) if ln.strip().startswith("|")]
    if not pipes:
        return True
    return pipes == list(range(pipes[0], pipes[-1] + 1)) and len(pipes) >= 3 and "---" in lines[pipes[0] + 1]


def test_a_table_with_some_supported_rows_stays_one_table():
    # the regression for the join at ai_policy.py:1513, which put a blank line between every kept row
    answer = ("Cash generation was strong.\n\n| Quarter | Operating cash flow |\n|---|---|\n"
              "| Q4 FY2026 | $28.1 billion |\n| Q3 FY2026 | $99.9 billion |\n| Q2 FY2026 | $2.0 billion |\n\n"
              "→ How does that compare?")
    g = P.ground(answer, DATA, [])
    assert g["removed"] == 1 and g["removed_items"] == [{"kind": "table_row", "text": "| Q3 FY2026 | $99.9 billion |"}]
    assert "| Q4 FY2026 | $28.1 billion |\n| Q2 FY2026 | $2.0 billion |" in g["text"]
    assert _is_table_whole(g["text"]) and "\n\n|" not in g["text"].split("| Quarter")[1]
    assert P.integrity(P.repair(g["text"])) == []


def test_a_list_keeps_its_items_together():
    answer = "Highlights:\n- Cash flow was $28.1 billion\n- Capex was $77.7 billion\n- Margins widened\n"
    g = P.ground(answer, DATA, [])
    assert g["text"] == "Highlights:\n- Cash flow was $28.1 billion\n- Margins widened\n"
    assert g["removed_items"][0]["kind"] == "list_item"


def test_the_audits_shape_leaves_no_table_fragment():
    # a prose conclusion, a table whose every row is unsupported, "What stands out", "My arithmetic"
    answer = ("**Free cash flow improved.** Apple's operating cash flow was $28.1 billion in Q4.\n\n"
              "| Quarter | Operating cash flow | Capex | Free cash flow |\n|---|---|---|---|\n"
              "| Q4 FY2026 | $91.2 billion | $12.4 billion | $78.8 billion |\n"
              "| Q3 FY2026 | $88.0 billion | $11.9 billion | $76.1 billion |\n\n"
              "**What stands out**\n\nCash conversion held up.\n\n**My arithmetic**\n\n"
              "Free cash flow is operating cash flow less capital spending: 28.101 minus 2.0.\n\n"
              "→ What drove the change?")
    g = P.ground(answer, DATA, [])
    assert g["removed"] == 2
    fixed = P.repair(g["text"])
    assert "|" not in fixed and "---" not in fixed
    assert P.integrity(fixed) == []
    assert "Cash conversion held up." in fixed and fixed.endswith("→ What drove the change?")
    assert "\n\n\n" not in fixed


def test_a_lead_in_whose_list_is_gone_is_dropped():
    answer = "Apple's cash flow was strong.\n\nThe figures:\n- Operating cash flow of $91 billion\n- Capex of $12 billion\n\nThat is the picture."
    g = P.ground(answer, DATA, [])
    assert g["removed"] == 2
    assert P.integrity(g["text"]) == ["dangling_intro"]
    fixed = P.repair(g["text"])
    assert "figures:" not in fixed and P.integrity(fixed) == []
    assert fixed == "Apple's cash flow was strong.\n\nThat is the picture."


def test_a_heading_with_nothing_under_it_is_dropped():
    text = "Cash flow was fine.\n\n## Detail\n\n## Risks\n\nNothing was found."
    assert P.integrity(text) == ["orphan_heading"]
    assert P.repair(text) == "Cash flow was fine.\n\n## Risks\n\nNothing was found."
    assert P.integrity("Cash flow was fine.\n\n## Detail") == ["orphan_heading"]


def test_an_empty_table_and_a_stray_table_line_are_named():
    assert "empty_table" in P.integrity("Intro.\n\n| A | B |\n|---|---|\n\nOutro.")
    assert "stray_table_line" in P.integrity("Intro.\n\n| just one line |\n\nOutro.")
    assert "stray_table_line" in P.integrity("Intro.\n\n| A | B |\n| 1 | 2 |\n\nOutro.")
    assert P.repair("Intro.\n\n| A | B |\n|---|---|\n\nOutro.") == "Intro.\n\nOutro."


def test_a_table_of_bare_numbers_under_a_heading_with_no_unit():
    bare = "Here it is.\n\n| Quarter | Operating cash flow |\n|---|---|\n| Q4 | 28.101 |\n| Q3 | 27.9 |"
    assert P.integrity(bare) == ["unitless_table"]
    assert P.integrity(bare.replace("Operating cash flow", "Operating cash flow ($ billions)")) == []
    assert P.integrity(bare.replace("| 28.101 |", "| $28.101 |").replace("| 27.9 |", "| $27.9 |")) == []
    assert P.integrity(bare.replace("Operating cash flow", "Share of revenue").replace("28.101", "28.1%").replace("27.9", "27.9%")) == []
    # a column of years is a label, not a figure
    assert P.integrity("Years.\n\n| Event | Year |\n|---|---|\n| Split | 2020 |\n| Buyback | 2024 |") == []


def test_an_untouched_answer_comes_back_byte_for_byte():
    answer = ("  Opening line with $28.1 billion.\n\n\n| A | $ |\n|---|---|\n| x | $2.0 billion |\n\n"
              "- one\n- two\n\n```\ncode\n\nmore code\n```\n\n[[chart AAPL 3m]]\n\n→ Next?\n\n")
    g = P.ground(answer, DATA, [])
    assert g["removed"] == 0 and g["text"] == answer and g["note"] is None
    assert P.repair(answer) == answer and P.integrity(answer) == []
    assert "".join(b["text"] + b["sep"] for b in P.blocks(answer)) == answer.strip()
    kinds = [b["kind"] for b in P.blocks(answer)]
    assert kinds == ["paragraph", "table", "list", "fence", "tag", "followups"]


@pytest.mark.parametrize("n,kind,start", [
    (1, "rewritten", "Milo removed 1 statement whose"), (3, "rewritten", "Milo removed 3 statements whose"),
    (1, "limited", "Milo removed 1 statement whose"), (2, "limited", "Milo removed 2 statements whose")])
def test_ground_note_counts_and_names_the_outcome(n, kind, start):
    note = P.ground_note(n, kind)
    assert note.startswith(start) and note.endswith("Every figure it gives comes from the page or a lookup listed under the answer.")
    assert ("rewrote the answer from the figures that remain" in note) == (kind == "rewritten")
    assert ("says above what it could not support" in note) == (kind == "limited")
    assert "—" not in note and "–" not in note
    assert len(note) < 260


@pytest.mark.parametrize("kept", [[], ["Operating cash flow was $28.1 billion"], ["- one $1", "| Q4 | $2 |", "|---|---|"]])
def test_the_limit_answer_reads_whole(kept):
    text = P.limit_answer(kept)
    assert P.integrity(text) == [], text
    assert text.startswith("Optic's data behind this answer does not carry some of the figures this question asks for")
    assert ("What the data does support:" in text) == bool(kept)
    assert "|" not in text


def test_the_longest_set_of_notes_fits_what_the_page_stores():
    notes = " ".join([P.AMEND_NOTE, P.ground_note(100, "rewritten"), P.ECHO_NOTE, P.READ_NOTE])
    assert len(notes) < 900
    assert re.search(r"AMENDED_MAX = (\d+)", open("static/v2/js/ui/milo.js").read()).group(1) == "900"

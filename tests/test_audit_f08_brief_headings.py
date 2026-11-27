"""F08: the earnings brief's headings are headings, not raw "##" markers (audit round, 2026-11-27).

Pure function and the brief's own markup, run in JavaScriptCore like tests/test_fiscal_periods.py.
"""
import json
from pathlib import Path

import pytest

from tests.test_frontend_v2_stage0 import _run

JS = Path(__file__).resolve().parent.parent / "static" / "v2" / "js"

FIXTURE = ["## The setup", "Reports in 12 days.", "## The track record", "Eight beats from eight."]


def blocks(tmp_path, paragraphs):
    return _run(tmp_path, f"""
      const ER = await import('{(JS / "pages/earnings.js").as_posix()}');
      print(JSON.stringify(ER.briefBlocks({json.dumps(paragraphs)})));
    """)


def test_the_suite_fixture_reads_as_headings_and_paragraphs(tmp_path):
    assert blocks(tmp_path, FIXTURE) == [
        {"kind": "h", "text": "The setup"}, {"kind": "p", "text": "Reports in 12 days."},
        {"kind": "h", "text": "The track record"}, {"kind": "p", "text": "Eight beats from eight."}]


def test_other_levels_and_closing_markers(tmp_path):
    got = blocks(tmp_path, ["# One", "x", "### Three ###", "y"])
    assert [b["text"] for b in got if b["kind"] == "h"] == ["One", "Three"]


def test_a_heading_and_text_in_one_paragraph_split(tmp_path):
    got = blocks(tmp_path, ["## Risks\nThe estimate is high.\nIt may fall."])
    assert got == [{"kind": "h", "text": "Risks"}, {"kind": "p", "text": "The estimate is high. It may fall."}]


def test_trailing_heading_and_marker_only_paragraphs_are_dropped(tmp_path):
    got = blocks(tmp_path, ["## A", "text", "##", "## Dangling"])
    assert got == [{"kind": "h", "text": "A"}, {"kind": "p", "text": "text"}]


def test_list_markers_are_removed(tmp_path):
    got = blocks(tmp_path, ["- first\n* second"])
    assert got == [{"kind": "p", "text": "first"}, {"kind": "p", "text": "second"}]


def test_no_block_text_starts_with_a_marker(tmp_path):
    got = blocks(tmp_path, ["## H", "#### Deep", "body", "####### Seven", "x"])
    assert all(not b["text"].startswith("#") for b in got)


def test_model_markup_is_escaped_and_bold_survives(tmp_path):
    got = _run(tmp_path, f"""
      const ER = await import('{(JS / "pages/earnings.js").as_posix()}');
      const F = await import('{(JS / "core/format.js").as_posix()}');
      const bs = ER.briefBlocks(['## <script>alert(1)</script>', 'a <img src=x onerror=alert(1)> and **bold** text', 'x']);
      print(JSON.stringify(bs.map((b) => F.bolded(b.text))));
    """)
    assert "<script" not in got[0] and "&lt;script&gt;" in got[0]
    assert "<img" not in got[1] and "&lt;img" in got[1]
    assert "<b>bold</b>" in got[1]


def test_the_brief_renders_headings_as_h3_and_paragraphs_as_p():
    src = (JS / "pages/earnings.js").read_text()
    assert "briefBlocks(b.paragraphs)" in src
    assert '<h3 class="t-label">' in src

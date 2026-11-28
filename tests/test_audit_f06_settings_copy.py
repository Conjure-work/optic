"""F06: the Settings sentence about the knowledge level agrees with Home's control (audit round, 2026-11-27).

Settings used to say the level "does not change what a page shows"; Home and a stock's page lay themselves out from
the level, and Home's own control says so. Both now say the same thing. The View setting (density) no longer changes
Home or the stock page, so its two strings say that.
"""
from pathlib import Path

from tests.test_frontend_v2_stage0 import V2

JS = V2 / "js"
SET = (JS / "pages/settings.js").read_text()
LC = (JS / "ui/levelcontrol.js").read_text()


def test_the_old_clause_is_gone_everywhere():
    for p in Path(V2).rglob("*"):
        if p.is_file() and p.suffix in (".js", ".html", ".css"):
            assert "does not change what a page shows" not in p.read_text(errors="ignore").lower(), p


def test_settings_says_the_level_changes_the_words_and_how_much_home_and_a_stock_page_show():
    assert ("On Home and a stock's page it also sets how much the screen shows. "
            "It never changes a figure, a source, a caveat or a disclosure.") in SET
    assert "worded for this level" in SET


def test_home_control_says_the_same():
    assert "It changes the words and how much each screen shows. Never a figure, a caveat or a disclosure." in LC


def test_neither_says_a_figure_caveat_or_disclosure_changes():
    for text in (SET, LC):
        low = text.lower()
        assert "never changes a figure" in low or "never a figure" in low
        assert "changes the words, never the figures" not in low


def test_the_view_setting_strings_say_home_and_the_stock_page_follow_the_level():
    assert "Advanced opens it. Home and a stock's page follow the level below instead." in SET
    assert "'It does not change how Milo explains things.'" in SET
    assert "Home shows every panel of its layout" not in SET
    assert "Show advanced analysis" not in SET

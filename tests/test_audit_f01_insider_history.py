"""F01 class (audit 2026-11-27): the full insider history says unavailable or partial, never "none found", unless the
period's Form 4 list was read whole. Invented rows, a fixed day, no network: the kept Form 4 store is a temporary
file and the background reader is replaced."""
from __future__ import annotations

import datetime as dt
import json
import time

import pytest
from fastapi.testclient import TestClient

from app import form4_store, insider_fill as F, main
from tests.test_frontend_v2_stage0 import V2, _run

TODAY = dt.date(2026, 11, 28)
SINCE5 = "2021-11-29"
CIK = "1321655"


@pytest.fixture
def kept(tmp_path, monkeypatch):
    monkeypatch.setattr(form4_store, "DB_PATH", str(tmp_path / "form4.db"))
    monkeypatch.setattr(F, "ENABLED", True)
    F._LAST_RUN.clear()
    F._RUNNING.discard("PLTR")
    started = []
    monkeypatch.setattr(F, "start", lambda *a: started.append(a) or True)
    yield started
    F._LAST_RUN.clear()


def _row(date, action="sale"):
    return {"insider": "A. INSIDER", "position": "Director", "date": date, "shares": 100.0, "value": 10000.0,
            "action": action, "detail": "x"}


def _yahoo(rows):
    return {"summary_6m": {}, "transactions": rows}


def _ok(acc, trades=()):
    form4_store.save(acc, CIK, {"available": True, "issuer_cik": CIK, "insider": "B. OFFICER", "roles": ["Officer"],
                                "trades": list(trades)})


def _whole(filings):
    form4_store.save_list("PLTR", CIK, filings, "2010-01-01")


def test_empty_yahoo_and_nothing_kept_is_reading_never_none(kept):
    h = F.history("PLTR", _yahoo([]), 5, today=TODAY)
    c = h["coverage"]
    assert c["state"] == "reading" and c["list_pending"] is True and c["none"] is False
    assert c["complete"] is False and c["covered_from"] is None and h["since"] == SINCE5
    assert len(kept) == 1 and kept[0][0] == "PLTR"


def test_a_failed_reader_run_is_unavailable_and_is_retried_only_after_the_wait(kept):
    F._LAST_RUN["PLTR"] = {"at": time.time(), "ok": False, "why": "sec_unreachable"}
    c = F.history("PLTR", _yahoo([]), 5, today=TODAY)["coverage"]
    assert c["state"] == "unavailable" and c["why"] == "sec_unreachable" and c["covered_from"] is None
    assert c["none"] is False and kept == [], "no restart inside the wait"
    F._LAST_RUN["PLTR"]["at"] = time.time() - F.RETRY_AFTER - 1
    c = F.history("PLTR", _yahoo([]), 5, today=TODAY)["coverage"]
    assert len(kept) == 1 and c["state"] == "reading", "after the wait it asks again, and reads as reading"


def test_a_whole_list_with_every_filing_readable_and_no_trades_is_the_genuine_none(kept):
    _whole([["0001-26-1", "2026-03-01"], ["0001-24-1", "2024-03-01"]])
    _ok("0001-26-1"), _ok("0001-24-1")
    c = F.history("PLTR", _yahoo([]), 5, today=TODAY)["coverage"]
    assert c["state"] == "complete" and c["none"] is True and c["covered_from"] == SINCE5 and c["complete"] is True
    assert c["sec_filings"] == 2 and c["why"] is None and kept == []


def test_a_whole_list_with_no_form_4_at_all_is_complete_and_says_zero_filings(kept):
    _whole([])
    c = F.history("PLTR", _yahoo([]), 5, today=TODAY)["coverage"]
    assert c["state"] == "complete" and c["none"] is True and c["sec_filings"] == 0 and c["covered_from"] == SINCE5


def test_a_filing_that_could_not_be_parsed_is_partial_not_complete(kept):
    _whole([["0001-26-1", "2026-03-01"], ["0001-25-1", "2025-03-01"]])
    _ok("0001-26-1")
    form4_store.save("0001-25-1", CIK, {"available": False, "reason": "no ownership document"})
    c = F.history("PLTR", _yahoo([]), 5, today=TODAY)["coverage"]
    assert c["sec_failed"] == 1 and c["complete"] is False and c["state"] == "partial"
    assert c["why"] == "filings_unreadable" and c["none"] is False
    assert c["covered_from"] == "2026-03-01", "read without a break only from the newest filing"


def test_unread_filings_are_reading_and_say_how_far_back_the_read_reaches(kept):
    _whole([["0001-26-3", "2026-10-01"], ["0001-26-2", "2026-06-01"], ["0001-24-1", "2024-02-01"]])
    _ok("0001-26-3")
    c = F.history("PLTR", _yahoo([]), 5, today=TODAY)["coverage"]
    assert c["state"] == "reading" and c["sec_unread"] == 2 and c["sec_read_from"] == "2026-10-01"
    assert c["covered_from"] == "2026-10-01" and c["none"] is False and c["complete"] is False


def test_two_years_an_empty_feed_is_unavailable_and_a_short_whole_list_is_complete(kept):
    F._LAST_RUN["PLTR"] = {"at": time.time(), "ok": False, "why": "sec_unreachable"}
    c = F.history("PLTR", _yahoo([]), 2, today=TODAY)["coverage"]
    assert c["state"] == "unavailable" and c["complete"] is False
    rows = [_row("2026-%02d-%02d" % (1 + i % 10, 1 + i)) for i in range(20)]
    h = F.history("PLTR", _yahoo(rows), 2, today=TODAY)
    assert h["coverage"]["state"] == "complete" and h["coverage"]["covered_from"] == h["since"] and len(h["rows"]) == 20
    assert kept == [], "nothing for the SEC to fill, so no reader"


def test_yahoo_rows_with_the_sec_unreachable_is_partial_from_the_two_years_a_short_list_covers(kept):
    F._LAST_RUN["PLTR"] = {"at": time.time(), "ok": False, "why": "sec_unreachable"}
    h = F.history("PLTR", _yahoo([_row("2026-09-01"), _row("2025-01-10")]), 5, today=TODAY)
    c = h["coverage"]
    assert c["state"] == "partial" and c["covered_from"] == "2024-11-28" and c["why"] == "sec_unreachable"
    assert len(h["rows"]) == 2 and c["yahoo_answered"] is True and c["none"] is False


def test_the_chart_and_six_month_paths_still_treat_an_empty_list_as_whole_at_two_years():
    ins = _yahoo([])
    assert F.complete("PLTR", ins, TODAY, days=730) is ins
    assert F.gap([], TODAY, 730) is None
    assert F.gap([], TODAY, 730, empty_is_gap=True) == ("2024-11-28", "2026-11-28")


def test_the_route_with_the_feed_down_is_never_complete(kept, monkeypatch):
    monkeypatch.setattr(main.YF_PROVIDER, "insiders", lambda sym: (_ for _ in ()).throw(RuntimeError("down")))
    for years in (2, 5):
        j = TestClient(main.app).get("/api/insiders/PLTR/history?years=%d" % years).json()
        assert j["yahoo_answered"] is False and j["coverage"]["yahoo_answered"] is False
        assert j["coverage"]["state"] != "complete" and j["coverage"]["none"] is False


def test_a_reader_run_that_fails_is_remembered(monkeypatch):
    F._LAST_RUN.clear()
    monkeypatch.setattr(F, "fill", lambda *a, **k: {"listed": 0, "read": 0, "why": "not_a_filer"})
    F._RUNNING.add("ZZZ")
    F._run("ZZZ", "2026-11-28")
    assert F._LAST_RUN["ZZZ"]["ok"] is False and F._LAST_RUN["ZZZ"]["why"] == "not_a_filer" and "ZZZ" not in F._RUNNING
    monkeypatch.setattr(F, "fill", lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
    F._RUNNING.add("ZZZ")
    F._run("ZZZ", "2026-11-28")
    assert F._LAST_RUN["ZZZ"]["why"] == "sec_unreachable"
    monkeypatch.setattr(F, "fill", lambda *a, **k: {"listed": 3, "read": 3})
    F._RUNNING.add("ZZZ")
    F._run("ZZZ", "2026-11-28")
    assert F._LAST_RUN["ZZZ"]["ok"] is True
    F._LAST_RUN.clear()


# ------------------------------------------------------------------------------------------- the page's wording

def _payload(state, rows=0, **cov):
    base = {"since": SINCE5, "ticker": "PLTR", "rows": [{"action": "sale", "date": "2026-01-02"} for _ in range(rows)],
            "coverage": dict({"state": state, "covered_to": "2026-11-28", "covered_from": None, "yahoo_rows": 0,
                              "sec_rows": 0, "sec_unread": 0}, **cov)}
    return base


def _read(tmp_path, payloads, opts=None):
    return _run(tmp_path, f"""
      const I = await import('{(V2 / "js/core/insider.js").as_posix()}');
      print(JSON.stringify({json.dumps(payloads)}.map((p) => I.insiderHistoryRead(p, {json.dumps(opts)}))));
    """)


S, T = "Nov 29, 2021", "Nov 28, 2026"


def test_every_line_of_the_wording_table_exactly(tmp_path):
    cases = [
        (_payload("complete", 3, sec_filings=4), f"0 open-market purchases and 3 sales from {S} to {T}."),
        (_payload("complete", 0, sec_filings=4), f"No open-market purchases or sales by insiders from {S} to {T}. Every Form 4 filed in the period was read."),
        (_payload("complete", 0, sec_filings=0), f"No Form 4 filings by PLTR's insiders are on file with the SEC from {S} to {T}, so there are no open-market purchases or sales to list."),
        (_payload("partial", 2, covered_from="2024-11-28"), f"0 open-market purchases and 2 sales found so far. This list is partial: it covers Nov 28, 2024 to {T}, not the full period from {S}."),
        (_payload("partial", 0, covered_from="2024-11-28"), f"Insider trades are only partly read: no open-market purchases or sales from Nov 28, 2024 to {T}, and the period from {S} to Nov 28, 2024 is unavailable right now. That is not the same as no activity."),
        (_payload("partial", 0), f"Insider trades are only partly read for the period from {S}. That is not the same as no activity."),
        (_payload("partial", 1), "0 open-market purchases and 1 sale found so far. This list is partial."),
        (_payload("reading", 2), f"0 open-market purchases and 2 sales found so far, since {S}."),
        (_payload("reading", 0), f'Insider trades since {S} are still being read. Nothing is shown as "none" until the read finishes.'),
        (_payload("unavailable", 0), f"Insider trades from {S} to {T} are unavailable right now. That is not the same as no activity."),
    ]
    got = _read(tmp_path, [c[0] for c in cases])
    for (_, want), g in zip(cases, got):
        assert g["line"] == want
        assert "found since" not in g["line"] and "could not be read in full" not in g["line"] + g["coverage"]
    assert sorted(i for i, g in enumerate(got) if g["line"].startswith("No ")) == [1, 2]
    assert [g["poll"] for g in got] == [False] * 7 + [True, True, False]
    assert all(g["state"] == s for g, s in zip(got, ["complete"] * 3 + ["partial"] * 4 + ["reading"] * 2 + ["unavailable"]))


def test_a_partial_line_with_a_covered_date_names_both_ends(tmp_path):
    g = _read(tmp_path, [_payload("partial", 0, covered_from="2024-11-28"), _payload("partial", 3, covered_from="2024-11-28")])
    for x in g:
        assert "Nov 28, 2024" in x["line"] and T in x["line"]


def test_the_line_under_the_table_by_state(tmp_path):
    tail = " Awards, option exercises, tax withholding and gifts are not trades and are left out."
    cases = [
        (_payload("complete", 0, yahoo_rows=150, yahoo_from="2025-06-24", sec_rows=3, listed=True, sec_filings=5),
         "Yahoo Finance lists its latest 150 rows, back to Jun 24, 2025. Before that, 3 trades come from Form 4 filings read from SEC EDGAR. Complete for the period."),
        (_payload("complete", 0, yahoo_rows=20), "Yahoo Finance lists its latest 20 rows. Complete for the period."),
        (_payload("reading", 0, sec_unread=7, listed=True), "Yahoo Finance returned no insider rows this time. 7 filings are still being read; this table fills in as they are."),
        (_payload("reading", 0, list_pending=True, listed=False), "Yahoo Finance returned no insider rows this time. The SEC's list of Form 4 filings is being read; this table fills in as it is."),
        (_payload("partial", 1, sec_failed=2, why="filings_unreadable"), "Yahoo Finance returned no insider rows this time. 2 Form 4 filings in the period could not be read, so trades in them are missing."),
        (_payload("partial", 1, covered_from="2024-11-28", why="sec_unreachable", yahoo_rows=2), "Yahoo Finance lists its latest 2 rows. The SEC's filing list could not be reached this time, so trades before Nov 28, 2024 are not shown."),
        (_payload("unavailable", 0, why="sec_unreachable"), "Yahoo Finance returned no insider rows this time. The SEC's filing list could not be reached this time, so the period is not covered."),
        (_payload("unavailable", 0, why="not_a_filer"), "Yahoo Finance returned no insider rows this time. PLTR is not in the SEC's company directory, so there are no Form 4 filings to read."),
    ]
    got = _read(tmp_path, [c[0] for c in cases])
    for (_, want), g in zip(cases, got):
        assert g["coverage"] == want + tail
    assert "Complete for the period" not in " ".join(g["coverage"] for g in got[2:])


def test_a_payload_with_no_state_maps_as_the_older_server_did_and_gaveup_words_what_is_on_hand(tmp_path):
    old = [{"since": SINCE5, "ticker": "X", "rows": [], "coverage": {"sec_unread": 3, "complete": False}},
           {"since": SINCE5, "ticker": "X", "rows": [], "coverage": {"sec_unread": 0, "complete": False}},
           {"since": SINCE5, "ticker": "X", "rows": [{"action": "sale"}], "coverage": {"sec_unread": 0, "complete": False}},
           {"since": SINCE5, "ticker": "X", "rows": [], "coverage": {"sec_unread": 0, "complete": True, "sec_filings": 2}}]
    assert [g["state"] for g in _read(tmp_path, old)] == ["reading", "unavailable", "partial", "complete"]
    gave = _read(tmp_path, [_payload("reading", 0), _payload("reading", 2), _payload("reading", 0, covered_from="2026-10-01", sec_unread=2)], {"gaveUp": True})
    assert [g["state"] for g in gave] == ["unavailable", "partial", "partial"]
    assert gave[2]["coverage"].count("2 Form 4 filings in the period have not been read yet, so trades in them are missing.") == 1
    assert not any(g["poll"] for g in gave)


def test_financials_words_the_history_through_the_one_reader():
    src = (V2 / "js" / "pages" / "financials.js").read_text()
    body = src[src.index("function insiderHistory("):src.index("function filings()")]
    assert body.count("insiderHistoryRead(") == 2
    assert "No open-market purchases or sales found since" not in src and "could not be read in full" not in src
    assert "read.line" in body and "read.coverage" in body and "gaveUp" in body

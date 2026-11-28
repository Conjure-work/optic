"""F01 (audit 2026-11-27): an insider summary that was not read says so; it is never "neutral" or "even".
Fixed fixtures in tests/fixtures/audit_financials.py; invented rows."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from app import insider_fill
from app.analytics import fundamentals
from tests.fixtures import audit_financials as fx
from tests.test_frontend_v2_stage0 import V2, _run

NOW = dt.date.fromisoformat(fx.INSIDER_NOW)


def own(kind, **kw):
    return fundamentals.analyse_ownership(fx.insiders_raw(kind), fx.institutions_raw(), now=NOW, **kw)


def test_recent_sales_are_selling_with_hand_worked_counts():
    o = own("recent_sales")
    s = o["insider_6m"]
    assert o["insider_state"] == "ok" and o["insider_signal"] == "selling" and s["source"] == "yahoo" and s["zero"] is False
    assert s["sale_count"] == 2 and s["sale_shares"] == 1500.0 and s["purchase_count"] == 0 and s["net_shares"] == -1500.0
    assert s["other_count"] == 1


def test_genuinely_none_is_a_true_zero():
    o = own("none")
    s = o["insider_6m"]
    assert o["insider_state"] == "ok" and o["insider_signal"] == "neutral" and s["zero"] is True
    assert s["purchase_count"] == 0 and s["sale_count"] == 0 and s["other_count"] == 1


def test_offsetting_purchases_and_sales_are_even_not_zero():
    o = own("offsetting")
    s = o["insider_6m"]
    assert o["insider_state"] == "ok" and o["insider_signal"] == "neutral" and s["zero"] is False and s["net_shares"] == 0.0
    assert s["purchase_count"] == 1 and s["sale_count"] == 1


def test_an_empty_list_with_no_kept_sec_coverage_is_unavailable(monkeypatch):
    monkeypatch.setattr(insider_fill, "six_month_rows", lambda t, today=None, days=182: ([], False))
    for o in (own("unavailable"), own("unavailable", ticker="AAPL")):
        s = o["insider_6m"]
        assert o["insider_state"] == "unavailable" and o["insider_signal"] == "unavailable"
        assert s["basis"] == "unavailable" and all(s[k] is None for k in (
            "purchase_count", "purchase_shares", "sale_count", "sale_shares", "net_shares", "other_count"))
        assert s["reason"] == "The feed returned no insider transaction rows, and Optic's kept SEC Form 4 filings do not yet cover the six months."
        assert o["notes"][0] == "Insider transactions for the last six months are unavailable right now. This is not a reading of no activity."
        assert "yahoo_tally_6m" in o


def test_the_yahoo_tally_is_never_the_signal():
    ins = {"transactions": [], "summary_6m": {"Purchases": {"shares": 5000.0, "transactions": 4}, "Sales": {"shares": 100.0, "transactions": 1},
                                             "Net Shares Purchased (Sold)": {"shares": 4900.0}}}
    o = fundamentals.analyse_ownership(ins, fx.institutions_raw(), now=NOW)
    assert o["insider_signal"] == "unavailable" and o["insider_6m"]["net_shares"] is None
    assert o["yahoo_tally_6m"]["acquired_count"] == 4


def test_empty_yahoo_list_with_complete_kept_sec_sales_reads_from_sec(monkeypatch):
    sec = [dict(fx._row("2026-11-05", "sale", 700.0), source="sec")]
    monkeypatch.setattr(insider_fill, "six_month_rows", lambda t, today=None, days=182: (sec, True))
    o = own("unavailable", ticker="AAPL")
    assert o["insider_state"] == "ok" and o["insider_signal"] == "selling"
    assert o["insider_6m"]["source"] == "sec" and o["insider_6m"]["sale_count"] == 1 and o["insider_6m"]["net_shares"] == -700.0


def test_empty_yahoo_list_with_complete_kept_sec_and_no_trades_is_a_true_zero(monkeypatch):
    monkeypatch.setattr(insider_fill, "six_month_rows", lambda t, today=None, days=182: ([], True))
    o = own("unavailable", ticker="AAPL")
    assert o["insider_state"] == "ok" and o["insider_signal"] == "neutral" and o["insider_6m"]["zero"] is True
    assert o["insider_6m"]["purchase_count"] == 0 and o["insider_6m"]["sale_count"] == 0


@pytest.mark.parametrize("kind", ["recent_sales", "none", "offsetting", "unavailable"])
def test_window_and_types_are_present_in_every_state(kind):
    s = own(kind)["insider_6m"]
    assert s["until"] == "2026-11-27" and s["since"] == "2026-05-29" and s["window_days"] == 182
    assert s["types"] == "Open-market purchases and sales, Form 4 codes P and S"
    assert s["excluded"] == "awards, grants, gifts and option exercises"


def test_six_month_rows_reads_only_the_kept_store(monkeypatch):
    from app import form4_store
    monkeypatch.setattr(form4_store, "load_list", lambda t: None)
    assert insider_fill.six_month_rows("AAPL", NOW) == ([], False)
    kept = {"cik": "0000320193", "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(), "reaches": "2025-01-01",
            "filings": [["0001-26-1", "2026-11-06"], ["0001-26-2", "2026-03-01"]]}
    parsed = {"0001-26-1": {"available": True, "issuer_cik": "0000320193", "insider": "X", "roles": ["CFO"],
                            "trades": [{"code": "S", "date": "2026-11-04", "shares": 10.0, "price": 5.0, "value": 50.0},
                                       {"code": "S", "date": "2026-02-01", "shares": 99.0, "price": 5.0, "value": 495.0}]}}
    monkeypatch.setattr(form4_store, "load_list", lambda t: kept)
    monkeypatch.setattr(form4_store, "load_many", lambda accs: {a: parsed[a] for a in accs if a in parsed})
    rows, complete = insider_fill.six_month_rows("AAPL", NOW)
    assert complete and [r["date"] for r in rows] == ["2026-11-04"], "the window, the issuer's own, nothing older"
    parsed.pop("0001-26-1")
    assert insider_fill.six_month_rows("AAPL", NOW)[1] is False, "an unread filing in the window is not complete"


def _read(tmp_path, kind):
    o = own(kind)
    return _run(tmp_path, f"""
      const I = await import('{(V2 / "js/core/insider.js").as_posix()}');
      print(JSON.stringify(I.insiderRead({json.dumps(o)})));
    """)


def test_insider_read_for_each_case(tmp_path):
    u = _read(tmp_path, "unavailable")
    assert u["state"] == "unavailable" and u["short"] == "Unavailable" and u["signal"] == "unavailable"
    assert u["headline"] == "Insider transactions for the six months to Nov 27, 2026 are unavailable right now. That is not the same as no activity."
    z = _read(tmp_path, "none")
    assert z["state"] == "ok" and z["short"] == "None"
    assert z["headline"].startswith("No open-market purchases or sales by insiders from May 29, 2026 to Nov 27, 2026.")
    assert "1 award, grant or exercise not counted." in z["headline"]
    e = _read(tmp_path, "offsetting")
    assert e["short"] == "Even" and e["headline"].startswith("Open-market purchases and sales by insiders offset from May 29, 2026 to Nov 27, 2026")
    s = _read(tmp_path, "recent_sales")
    assert s["signal"] == "selling" and "May 29, 2026 to Nov 27, 2026" in s["headline"] and "over six months" not in s["headline"]
    assert s["window"] == "May 29, 2026 to Nov 27, 2026" and s["types"].startswith("Open-market purchases and sales")


FORBIDDEN = ("Even", "Neutral", "No net insider buying or selling", "No net")


def test_no_surface_prints_a_neutral_word_for_the_unavailable_state(tmp_path):
    """Each surface's string for the unavailable state, taken from the one reader plus the surface's own wording."""
    u = _read(tmp_path, "unavailable")
    for text in (u["headline"], u["short"], json.dumps(u["counts"])):
        for word in FORBIDDEN:
            assert word not in text, (word, text)
    for name in ("pages/financials.js", "pages/dossier.js", "pages/workspace.js", "pages/chart-widgets.js"):
        src = (V2 / "js" / name).read_text()
        assert "insiderRead" in src, name + " reads the shared reader"
    ws = (V2 / "js" / "pages" / "workspace.js").read_text()
    cw = (V2 / "js" / "pages" / "chart-widgets.js").read_text()
    assert "insiderRead(own).short" in cw and "insiderRead(o).headline" in (V2 / "js" / "pages" / "dossier.js").read_text()
    assert "No net insider buying or selling over six months." not in (V2 / "js" / "pages" / "dossier.js").read_text()
    assert "(i6.net_shares || 0)" not in (V2 / "js" / "pages" / "financials.js").read_text()
    assert "capFirst(o.insider_signal" not in ws


def test_classic_prints_unavailable_without_a_signal_row():
    src = (V2.parent / "app.js").read_text()
    assert src.count("Insider transactions are unavailable right now.") == 2


def test_classic_insider_tile_says_unavailable_not_a_dash():
    """F01 on the Classic view: with no transactions net_shares is None, and the tile read "— sh"."""
    src = (Path(__file__).resolve().parents[1] / "static" / "app.js").read_text(encoding="utf-8")
    line = next(l for l in src.splitlines() if "tile('Insider net (6m)'" in l)
    assert "net_shares == null ? 'Unavailable'" in line

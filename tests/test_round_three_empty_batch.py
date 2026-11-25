"""Round three, the options page that stayed on "Loading contracts" (2026-11-25).

With the feeds refused, yf.download answers an empty frame for a whole basket (it has already asked each name inside).
batch_history then asked every name again, one gated history read each, so one empty macro basket put about thirty
requests certain to fail in the limiter's queue ahead of every reader, and the options page's contracts request waited
past the 30 s the workflow journey allows. An empty batch now serves only what each name last had; a partial batch
still asks for the names it left out."""
from __future__ import annotations

import pandas as pd

from app.providers import yf as Y


def _empty(names):
    cols = pd.MultiIndex.from_product([names, ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    return pd.DataFrame(columns=cols)


def _frame(names):
    idx = pd.date_range("2026-01-02", periods=3, freq="D")
    cols = pd.MultiIndex.from_product([names, ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    return pd.DataFrame(1.0, index=idx, columns=cols)


def test_an_empty_batch_asks_no_name_again(monkeypatch):
    asked = []
    monkeypatch.setattr(Y.yf, "download", lambda names, **kw: _empty(list(names)))
    monkeypatch.setattr(Y.YFinanceProvider, "history", lambda self, sym, **kw: asked.append(sym) or pd.DataFrame())
    Y._CACHE.clear()
    names = ["E{:02d}".format(i) for i in range(30)]
    got = Y.YFinanceProvider().batch_history(names, period="6mo", interval="1d")
    assert asked == [], "an empty batch asked {} names again one at a time".format(len(asked))
    assert got == {} or len(got) == 0


def test_an_empty_batch_serves_what_each_name_last_had(monkeypatch):
    monkeypatch.setattr(Y.yf, "download", lambda names, **kw: _empty(list(names)))
    monkeypatch.setattr(Y.YFinanceProvider, "history", lambda self, sym, **kw: (_ for _ in ()).throw(AssertionError("asked again")))
    Y._CACHE.clear()
    kept = _frame(["K1"])["K1"]
    Y._keep_good(Y._hist_key("K1", "6mo", "1d"), kept)
    got = Y.YFinanceProvider().batch_history(["K1", "K2"], period="6mo", interval="1d")
    assert set(got) == {"K1"}
    assert got["K1"].attrs.get("stand_in_since")


def test_a_partial_batch_still_asks_for_the_names_it_left_out(monkeypatch):
    asked = []
    monkeypatch.setattr(Y.yf, "download", lambda names, **kw: _frame([n for n in names if n != "P3"]))
    monkeypatch.setattr(Y.YFinanceProvider, "history", lambda self, sym, **kw: asked.append(sym) or _frame([sym])[sym])
    Y._CACHE.clear()
    got = Y.YFinanceProvider().batch_history(["P1", "P2", "P3"], period="6mo", interval="1d")
    assert asked == ["P3"] and set(got) == {"P1", "P2", "P3"}

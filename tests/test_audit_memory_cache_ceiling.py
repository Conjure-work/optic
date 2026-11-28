"""The provider cache has a ceiling by size as well as by count (audit round, package E, 2026-11-27).

The soak (docs/operations/memory-and-open-files.md) found app/providers/yf.py `_CACHE` holding about 3 MB of price and
chain frames for every symbol served, bounded only by its 20,000 entries, so memory grew with every new symbol. Past
YF_CACHE_MAX_MB the oldest entries holding frames go first.
"""
import numpy as np
import pandas as pd
import pytest

from app.providers import yf


def _frame(rows: int) -> pd.DataFrame:
    return pd.DataFrame(np.zeros((rows, 4)), columns=list("OHLC"))


@pytest.fixture
def cache(monkeypatch):
    monkeypatch.setattr(yf, "_CACHE", {})
    monkeypatch.setattr(yf, "_KEY_LOCKS", {})
    return yf._CACHE


def test_the_oldest_frames_go_first_when_the_cache_is_past_its_byte_ceiling(cache, monkeypatch):
    one = yf._frame_bytes(_frame(10_000))
    monkeypatch.setattr(yf, "CACHE_MAX_BYTES", one * 3 + 1000)
    now = 1_000_000.0
    for i in range(6):
        cache["hist:S%d:2y:1d" % i] = (now - 100 + i, _frame(10_000))
    cache["quote:S0"] = (now - 500, {"price": 1.0})           # not a frame: never counted, never dropped for size
    yf.sweep_cache(now)
    assert sorted(k for k in cache if k.startswith("hist:")) == ["hist:S3:2y:1d", "hist:S4:2y:1d", "hist:S5:2y:1d"]
    assert "quote:S0" in cache


def test_a_frame_held_under_two_keys_counts_once(cache, monkeypatch):
    frame = _frame(10_000)
    monkeypatch.setattr(yf, "CACHE_MAX_BYTES", yf._frame_bytes(frame) + 1000)
    now = 1_000_000.0
    cache["hist:AAPL:2y:1d"] = (now - 10, frame)
    cache["good:hist:AAPL:2y:1d"] = (now - 10, frame)           # the stand-in is the same object
    yf.sweep_cache(now)
    assert len(cache) == 2


def test_a_batch_of_frames_is_counted_by_its_members(cache, monkeypatch):
    one = yf._frame_bytes(_frame(10_000))
    monkeypatch.setattr(yf, "CACHE_MAX_BYTES", one * 2 + 1000)
    now = 1_000_000.0
    cache["batch:old"] = (now - 50, {"A": _frame(10_000), "B": _frame(10_000)})
    cache["batch:new"] = (now - 5, {"C": _frame(10_000), "D": _frame(10_000)})
    yf.sweep_cache(now)
    assert list(cache) == ["batch:new"]


def test_under_the_ceiling_nothing_goes(cache):
    now = 1_000_000.0
    cache["hist:AAPL:2y:1d"] = (now - 5, _frame(500))
    assert yf.sweep_cache(now) == 0 and len(cache) == 1


def test_a_text_column_is_counted_at_more_than_its_pointers():
    plain = pd.DataFrame({"x": np.zeros(1000)})
    texty = pd.DataFrame({"contract": ["AAPL251219C00100000"] * 1000})
    assert yf._frame_bytes(texty) > yf._frame_bytes(plain) * 5


def test_a_cached_list_of_rows_counts_and_goes_with_the_oldest(cache, monkeypatch):
    monkeypatch.setattr(yf, "CACHE_MAX_BYTES", 400 * yf._ROW_BYTES + 100)
    now = 1_000_000.0
    cache["actions:OLD"] = (now - 50, [{"firm": "x"}] * 400)
    cache["actions:NEW"] = (now - 5, [{"firm": "x"}] * 400)
    yf.sweep_cache(now)
    assert list(cache) == ["actions:NEW"]

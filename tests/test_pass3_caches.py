"""Round three, memory and open files at rest: every cache that grew without end now has a size and an age.

The causes and the measurements are in docs/operations/memory-and-open-files.md. Each module's cache is asserted to be
bounded by reading the object the module actually uses, not a list kept here, and the bound is driven past.
"""

import asyncio
import sqlite3
import threading

import pytest

from app import ai, boundcache, contracts, replays
from app.analytics import screen
from app.providers import yf_caches
from app.research import service as research_service
from app.valuation import service as valuation_service


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_a_bounded_cache_drops_the_oldest_past_its_size():
    c = boundcache.BoundedCache(maxsize=3, max_age=60)
    for k in "abcd":
        c[k] = k
    assert list(c) == ["b", "c", "d"]
    c["b"] = "again"                       # a rewrite moves to the back
    c["e"] = "e"
    assert list(c) == ["d", "b", "e"]


def test_a_bounded_cache_forgets_an_entry_past_its_age():
    clock = _Clock()
    c = boundcache.BoundedCache(maxsize=10, max_age=60, clock=clock)
    c["a"] = 1
    clock.now += 30
    c["b"] = 2
    assert c.get("a") == 1
    clock.now += 31
    assert c.get("a") is None and "a" not in c      # read past its age: gone
    c["c"] = 3                                      # a write sweeps what has aged
    clock.now += 61
    c["d"] = 4
    assert list(c) == ["d"]


def test_a_bounded_cache_is_still_a_dict_for_the_modules_and_their_tests():
    c = boundcache.BoundedCache(maxsize=2, max_age=60)
    c["x"] = (1.0, {"v": 1})
    assert isinstance(c, dict) and c.get("missing", "d") == "d" and c["x"][1] == {"v": 1}
    c.clear()
    assert len(c) == 0
    with pytest.raises(ValueError):
        boundcache.BoundedCache(maxsize=0, max_age=1)


@pytest.mark.parametrize("module, ttl_name", [
    (contracts, "TTL"), (replays, "_TTL"), (valuation_service, "INPUT_TTL"),
    (screen, "CACHE_TTL_SECONDS"), (research_service, "CACHE_TTL"),
])
def test_each_module_cache_is_bounded_and_keeps_entries_as_long_as_the_module_serves_them(module, ttl_name):
    cache = module._CACHE
    assert isinstance(cache, boundcache.BoundedCache), module.__name__
    # never shorter than the module's own freshness check, so nothing it would still serve is dropped early
    assert cache.max_age >= getattr(module, ttl_name)
    size = cache.maxsize
    saved = dict(cache)
    try:
        for i in range(size + 25):
            cache["probe-{}".format(i)] = (0.0, None)
        assert len(cache) == size
    finally:
        cache.clear()
        for k, v in saved.items():
            cache[k] = v


def test_yfinance_caches_are_optics_and_hold_no_connection_per_thread(tmp_path):
    from yfinance import cache as yf_cache
    assert yf_caches.installed()
    assert isinstance(yf_cache.get_tz_cache(), yf_caches.TimezoneCache)
    assert isinstance(yf_cache.get_cookie_cache(), yf_caches.CookieCache)
    assert isinstance(yf_cache.get_isin_cache(), yf_caches.IsinCache)

    store = yf_caches.TimezoneCache(str(tmp_path))
    threads = [threading.Thread(target=store.store, args=("SYM{}".format(i), "America/New_York")) for i in range(40)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert store.lookup("SYM7") == "America/New_York"
    # what a deploy keeps: a fresh process reads the timezones back from the file
    assert yf_caches.TimezoneCache(str(tmp_path)).lookup("SYM39") == "America/New_York"
    with sqlite3.connect(str(tmp_path / "optic-tz.db")) as conn:
        assert conn.execute("SELECT COUNT(*) FROM tz").fetchone()[0] == 40
    store.store("SYM7", None)
    assert store.lookup("SYM7") is None


def test_the_cookie_and_isin_stand_ins_answer_as_yfinance_expects():
    c = yf_caches.CookieCache()
    assert c.lookup("curlCffi") is None
    c.store("curlCffi", {"x": 1})
    hit = c.lookup("curlCffi")
    assert hit["cookie"] == {"x": 1} and hit["age"].total_seconds() >= 0
    c.store("curlCffi", None)
    assert c.lookup("curlCffi") is None
    i = yf_caches.IsinCache()
    i.store("US0378331005", "AAPL")
    assert i.lookup("US0378331005") == "AAPL"


def test_the_sync_anthropic_client_is_built_once_per_configuration(monkeypatch):
    import anthropic
    made = []

    class Fake:
        def __init__(self, **kw):
            made.append(kw)

        def close(self):
            pass

    monkeypatch.setattr(anthropic, "Anthropic", Fake)
    monkeypatch.setattr(ai, "_SHARED_SYNC", type(ai._SHARED_SYNC)())
    a = ai._sync_client(max_retries=3)
    assert ai._sync_client(max_retries=3) is a
    assert ai._sync_client(max_retries=2) is not a
    assert len(made) == 2
    # a changed credential gets a new client; the key holds a digest, never the value
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    assert ai._sync_client(max_retries=3) is not a
    assert all("sk-test-not-real" not in repr(k) for k in ai._SHARED_SYNC)
    ai.close_shared_clients()
    assert ai.shared_clients()["sync"] == 0


def test_the_async_client_is_shared_within_a_loop_and_not_across_loops(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    async def two():
        return ai._client(), ai._client()

    a1, a2 = asyncio.run(two())
    b1, _ = asyncio.run(two())
    assert a1 is a2 and a1 is not None
    assert b1 is not a1

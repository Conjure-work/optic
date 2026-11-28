"""A large feed document is not kept parsed in memory (audit round, package E, second part, 2026-11-28).

With real feeds the host held about 22 MB for every new symbol: `app.feeds._MEM`, which has no ceiling, kept EDGAR's
companyfacts for each (5 MB of JSON, 25 to 38 MB parsed). Documents over FEED_BIG_BYTES are kept as gzip files beside the
disk cache and parsed on demand into a cache of FEED_PARSED_MAX.
"""
import json

import pytest

from app import feeds


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(feeds, "CACHE_PATH", str(tmp_path / "feed_cache.json"))
    monkeypatch.setattr(feeds, "_MEM", {})
    monkeypatch.setattr(feeds, "_DISK", {})
    monkeypatch.setattr(feeds, "_PARSED", None)
    monkeypatch.setattr(feeds, "_PARSED_MAX", 2)
    monkeypatch.setattr(feeds, "BIG_JSON_BYTES", 1000)
    calls = []

    def fake_fetch(url, accept, **kw):
        calls.append(url)
        return json.dumps({"url": url, "pad": "x" * 5000}).encode()
    monkeypatch.setattr(feeds, "_fetch", fake_fetch)
    return calls


def test_a_large_document_is_kept_on_disk_not_in_memory(store):
    got = feeds.fetch_json("https://example.invalid/a", 3600, key="sec:facts:1")
    assert got["url"].endswith("/a")
    assert "sec:facts:1" not in feeds._MEM and "sec:facts:1" not in feeds._load_disk()
    assert feeds.big_entry("sec:facts:1")["at"] > 0
    assert feeds.cached_json("sec:facts:1")["url"].endswith("/a")


def test_a_second_read_does_not_fetch_again(store):
    feeds.fetch_json("https://example.invalid/a", 3600, key="sec:facts:1")
    feeds._PARSED.clear()                                      # as after the parsed cache has moved on: read from the file
    assert feeds.fetch_json("https://example.invalid/a", 3600, key="sec:facts:1")["url"].endswith("/a")
    assert store == ["https://example.invalid/a"]


def test_an_expired_large_document_is_fetched_again_and_stale_is_still_readable(store):
    feeds.fetch_json("https://example.invalid/a", 3600, key="sec:facts:1")
    feeds.fetch_json("https://example.invalid/a", 0, key="sec:facts:1")
    assert len(store) == 2
    assert feeds.cached_json("sec:facts:1") is not None


def test_few_parsed_documents_are_held_however_many_are_read(store):
    for i in range(10):
        feeds.fetch_json("https://example.invalid/%d" % i, 3600, key="sec:facts:%d" % i)
    assert len(feeds._PARSED) <= 2
    assert not [k for k in feeds._MEM if k.startswith("sec:facts")]
    assert feeds.cached_json("sec:facts:0")["url"].endswith("/0")       # still readable, from its file


def test_a_small_document_is_kept_as_before(store, monkeypatch):
    monkeypatch.setattr(feeds, "BIG_JSON_BYTES", 10 ** 9)
    feeds.fetch_json("https://example.invalid/s", 3600, key="small")
    assert "small" in feeds._MEM and feeds.big_entry("small") is None


def test_an_older_disk_cache_with_a_large_entry_is_moved_out_when_it_is_read(tmp_path, monkeypatch):
    path = tmp_path / "feed_cache.json"
    path.write_text(json.dumps({"sec:facts:9": {"at": 1_700_000_000.0, "json": {"pad": "y" * 5000}, "error": None},
                                "tiny": {"at": 1.0, "json": {"a": 1}, "error": None}}))
    monkeypatch.setattr(feeds, "CACHE_PATH", str(path))
    monkeypatch.setattr(feeds, "_MEM", {})
    monkeypatch.setattr(feeds, "_DISK", {})
    monkeypatch.setattr(feeds, "_PARSED", None)
    monkeypatch.setattr(feeds, "BIG_JSON_BYTES", 1000)
    disk = feeds._load_disk()
    assert "sec:facts:9" not in disk and "tiny" in disk
    assert "sec:facts:9" not in json.loads(path.read_text())
    assert feeds.big_entry("sec:facts:9")["at"] == 1_700_000_000.0
    assert feeds.cached_json("sec:facts:9")["pad"] == "y" * 5000

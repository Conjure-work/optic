"""Optic's own stand-ins for yfinance's three small caches (exchange timezones, the Yahoo cookie, ISIN lookups).

Why: yfinance keeps each of these in a SQLite file through peewee, and peewee opens one connection per thread and
keeps it for the thread's life. Every thread that ever read a price (this app runs about a hundred: the ticker-leg
pool of 32, the document pool of 24, uvicorn's worker threads and the background lanes) holds its own connection to
two databases, each with its write-ahead log, so four open files per thread. Measured on a local run on 2026-11-23
(docs/operations/memory-and-open-files.md): 510 of a process's 910 open descriptors were these files after a mixed
load; on the evaluation copy the same climb read 85 descriptors at boot and about 540 after use.

These stand-ins hold the same answers with one connection opened and closed per write, under one lock, and an
in-memory copy for reads, so the count stays flat however many threads ask. The timezone cache keeps its disk file
(the point of `_persist_timezones` in yf.py: a deploy keeps the timezones it learned); the cookie and the ISIN map stay
in memory, bounded, which costs one request after a restart and nothing else.

They are installed over yfinance's private cache managers by `install()`; if a yfinance release renames those, the
install does nothing and yfinance's own caches stand (the old behaviour), which `installed()` reports.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import os
import sqlite3
import threading
from collections import OrderedDict
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

_MAX_KEYS = 20000
_STATE = {"installed": False}


class _Memory:
    """A bounded in-memory key-value map, oldest out first."""

    def __init__(self, maxsize: int = _MAX_KEYS):
        self.maxsize = maxsize
        self._data: "OrderedDict[str, Any]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: Any) -> None:
        with self._lock:
            if value is None:
                self._data.pop(key, None)
                return
            self._data.pop(key, None)
            self._data[key] = value
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


class TimezoneCache:
    """yfinance's tz cache interface (lookup, store), one file, one connection per write."""

    def __init__(self, directory: Optional[str] = None):
        self.path = os.path.join(directory, "optic-tz.db") if directory else None
        self._memory = _Memory()
        self._lock = threading.Lock()
        if self.path:
            try:
                with self._conn() as conn:
                    conn.execute("CREATE TABLE IF NOT EXISTS tz (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
                    for key, value in conn.execute("SELECT key, value FROM tz LIMIT ?", (_MAX_KEYS,)):
                        self._memory.put(key, value)
            except sqlite3.Error as exc:
                log.info("timezone cache on disk unavailable, kept in memory: %s", type(exc).__name__)
                self.path = None

    @contextlib.contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def lookup(self, key: str) -> Optional[str]:
        return self._memory.get(key)

    def store(self, key: str, value: Optional[str]) -> None:
        if self._memory.get(key) == value:
            return
        self._memory.put(key, value)
        if not self.path:
            return
        try:
            with self._lock, self._conn() as conn:
                if value is None:
                    conn.execute("DELETE FROM tz WHERE key = ?", (key,))
                else:
                    conn.execute("INSERT INTO tz (key, value) VALUES (?, ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        except sqlite3.Error as exc:                              # the memory copy still answers
            log.info("timezone cache write failed: %s", type(exc).__name__)

    @property
    def tz_db(self) -> None:
        return None


class CookieCache:
    """yfinance's cookie cache interface: lookup(strategy) gives {'cookie', 'age'} or None."""

    def __init__(self) -> None:
        self._memory = _Memory(maxsize=8)

    def lookup(self, strategy: str) -> Optional[Dict[str, Any]]:
        hit = self._memory.get(strategy)
        if hit is None:
            return None
        cookie, fetched = hit
        return {"cookie": cookie, "age": dt.datetime.now() - fetched}

    def store(self, strategy: str, cookie: Any) -> None:
        self._memory.put(strategy, None if cookie is None else (cookie, dt.datetime.now()))

    @property
    def Cookie_db(self) -> None:                                  # noqa: N802 - yfinance's name
        return None


class IsinCache:
    def __init__(self) -> None:
        self._memory = _Memory(maxsize=4096)

    def lookup(self, isin: str) -> Optional[str]:
        return self._memory.get(isin)

    def store(self, isin: str, ticker: Optional[str]) -> None:
        self._memory.put(isin, ticker)

    @property
    def tz_db(self) -> None:
        return None


def install(directory: Optional[str] = None) -> bool:
    """Put the three stand-ins in place of yfinance's caches. Returns whether it could."""
    try:
        from yfinance import cache as yf_cache
        managers = (yf_cache._TzCacheManager, yf_cache._CookieCacheManager, yf_cache._ISINCacheManager)
        for m, attr in zip(managers, ("_tz_cache", "_Cookie_cache", "_isin_cache")):
            if not hasattr(m, attr):
                return False
        yf_cache._TzCacheManager._tz_cache = TimezoneCache(directory)
        yf_cache._CookieCacheManager._Cookie_cache = CookieCache()
        yf_cache._ISINCacheManager._isin_cache = IsinCache()
    except Exception as exc:                                      # noqa: BLE001 - yfinance's own caches stand
        log.info("yfinance caches left as yfinance's: %s", type(exc).__name__)
        return False
    _STATE["installed"] = True
    return True


def installed() -> bool:
    return bool(_STATE["installed"])

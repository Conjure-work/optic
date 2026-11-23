"""A dict with a ceiling: at most `maxsize` entries, none older than `max_age` seconds.

Why: five modules kept a module-level dict per symbol (contracts, replays, valuation, the screen's ranking, the
research pack) with a time-to-live checked on read and nothing that ever removed an entry. A process that served a
few hundred symbols held every one of them for its life; replays' entries are full-history price frames. Measured on
a local run (docs/operations/memory-and-open-files.md) this is part of the climb in resident memory with use.

It is a dict, so every existing `.get`, `[key] = value` and `monkeypatch.setattr(module, "_CACHE", {})` keeps working.
The modules' own freshness checks stay as they were; this only bounds what is kept. Eviction is oldest first by
insertion (a value written again moves to the back), and runs on every write, so a read never pays for it.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Hashable, Optional


class BoundedCache(OrderedDict):

    def __init__(self, maxsize: int, max_age: float, clock: Optional[Callable[[], float]] = None):
        super().__init__()
        if maxsize < 1 or max_age <= 0:
            raise ValueError("a bounded cache needs a positive size and age")
        self.maxsize = int(maxsize)
        self.max_age = float(max_age)
        self._clock = clock or time.monotonic
        self._born: Dict[Hashable, float] = {}
        self._lock = threading.RLock()

    def __setitem__(self, key: Hashable, value: Any) -> None:
        with self._lock:
            if key in self:
                OrderedDict.__delitem__(self, key)
            OrderedDict.__setitem__(self, key, value)
            self._born[key] = self._clock()
            self._evict()

    def __delitem__(self, key: Hashable) -> None:
        with self._lock:
            OrderedDict.__delitem__(self, key)
            self._born.pop(key, None)

    def get(self, key: Hashable, default: Any = None) -> Any:
        with self._lock:
            born = self._born.get(key)
            if born is not None and self._clock() - born > self.max_age:
                self.__delitem__(key)
                return default
            return OrderedDict.get(self, key, default)

    def clear(self) -> None:
        with self._lock:
            OrderedDict.clear(self)
            self._born.clear()

    def _evict(self) -> None:
        now = self._clock()
        for key in [k for k, born in self._born.items() if now - born > self.max_age]:
            self.__delitem__(key)
        while len(self) > self.maxsize:
            oldest = next(iter(self))
            self.__delitem__(oldest)

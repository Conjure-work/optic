"""The soak's hooks in the server process (audit round, package E). Test only: Python loads this at start-up only when
the soak puts this directory on PYTHONPATH (the pattern of tests/support/small_machine/sitecustomize.py), and it acts
only in the uvicorn process. The app is not edited.

- Replaces yfinance's entry points with tests/support/soak/synthetic.py, so no feed is asked and the app's own provider
  code, caches and analytics run for real on deterministic data.
- SIGUSR1 runs gc.collect() and writes, to SOAK_OUT, a numbered `snap-NNN.json` (resident memory, live objects by type,
  live pandas frames, every module-level cache's entries and estimated size, the provider cache by key prefix) and,
  when SOAK_TRACE=1 (tracemalloc, SOAK_FRAMES frames, default 25, started here), `snap-NNN.tm` (the tracemalloc snapshot) and the traced
  memory.
- SIGUSR2 does what the file SOAK_OUT/cmd says and writes `ctl-NNN.json` with resident memory before and after: "gc"
  collects (the settled measurement), "trim" calls malloc_trim(0) on Linux, to tell memory the allocator holds from
  memory the program holds. Kept apart from SIGUSR1 because the census allocates a great deal of its own.
"""
import os
import sys

_IN_SERVER = "uvicorn" in " ".join(getattr(sys, "orig_argv", sys.argv))

if _IN_SERVER and os.environ.get("SOAK_OUT"):
    import gc
    import json
    import signal
    import threading
    import time
    from collections import Counter

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import synthetic                                              # noqa: E402
    import yfinance as _yf                                        # noqa: E402

    if os.environ.get("SOAK_REAL") != "1":                        # SOAK_REAL=1: the real feeds, for a measurement by hand
        _yf.Ticker = synthetic.Ticker
        _yf.download = synthetic.download
        _yf.Search = synthetic.Search
    _OUT = os.environ["SOAK_OUT"]
    _TRACE = os.environ.get("SOAK_TRACE") == "1"
    _seq = {"snap": 0, "trim": 0}
    if _TRACE:
        import tracemalloc
        tracemalloc.start(int(os.environ.get("SOAK_FRAMES", "25")))

    def _rss_kb() -> int:
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1])
        except OSError:
            pass
        import subprocess
        return int(subprocess.run(["ps", "-o", "rss=", "-p", str(os.getpid())], capture_output=True, text=True).stdout.strip() or 0)

    def _deep(obj, seen, depth=0) -> int:
        """Bytes held by `obj` and what it holds, each object once per `seen`, to any depth (a parsed EDGAR document is
        nested well past six levels). Frames and arrays by their buffers."""
        try:
            import numpy as np
            import pandas as pd
        except Exception:                                         # noqa: BLE001
            np = pd = None
        total = 0
        stack = [obj]
        while stack:
            o = stack.pop()
            if id(o) in seen:
                continue
            seen.add(id(o))
            if pd is not None and isinstance(o, pd.DataFrame):
                total += int(o.memory_usage(deep=True, index=True).sum()) + sys.getsizeof(o)
                continue
            if pd is not None and isinstance(o, pd.Series):
                total += int(o.memory_usage(deep=True, index=True)) + sys.getsizeof(o)
                continue
            if np is not None and isinstance(o, np.ndarray):
                total += int(o.nbytes) + sys.getsizeof(o)
                continue
            total += sys.getsizeof(o)
            if isinstance(o, dict):
                for k, v in list(o.items()):
                    stack.append(k)
                    stack.append(v)
            elif isinstance(o, (list, tuple, set, frozenset)):
                stack.extend(list(o))
            elif hasattr(o, "__dict__") and not isinstance(o, type):
                stack.append(vars(o))
        return total

    def _caches() -> list:
        out = []
        for modname, mod in sorted(list(sys.modules.items())):
            if not (modname == "app" or modname.startswith("app.")) or mod is None:
                continue
            for name, val in list(vars(mod).items()):
                if name.startswith("__"):
                    continue
                kind = type(val).__name__
                if hasattr(val, "cache_info") and hasattr(val, "cache_clear"):
                    info = val.cache_info()
                    out.append({"where": modname + "." + name, "kind": "lru_cache", "entries": info.currsize,
                                "max": info.maxsize, "bytes": None})
                    continue
                if not isinstance(val, (dict, list, set)) or isinstance(val, type):
                    continue
                named = "cache" in name.lower()
                if not named and len(val) < 50:
                    continue
                try:
                    n = len(val)
                    size = _deep(val, set())
                except Exception:                                 # noqa: BLE001
                    continue
                out.append({"where": modname + "." + name, "kind": kind, "named_cache": named, "entries": n,
                            "max": getattr(val, "maxsize", None), "bytes": size})
        return out

    def _provider_cache() -> dict:
        mod = sys.modules.get("app.providers.yf")
        cache = getattr(mod, "_CACHE", None)
        if cache is None:
            return {}
        by: dict = {}
        seen: set = set()
        unique = 0
        for key, entry in list(cache.items()):
            prefix = str(key).split(":", 1)[0] if ":" in str(key) else "(bare)"
            row = by.setdefault(prefix, {"entries": 0, "bytes": 0})
            row["entries"] += 1
            row["bytes"] += _deep(entry, set())                   # standalone: what the prefix would hold alone
            unique += _deep(entry, seen)                          # each shared object once across the whole cache
        frames, held, deep_held = set(), 0, 0                                   # frame buffers by shallow size, each frame once: what a
        for entry in list(cache.values()):                        # byte ceiling on the cache would count
            value = entry[1] if isinstance(entry, tuple) and len(entry) == 2 else None
            try:
                import pandas as pd
                found = [value] if isinstance(value, pd.DataFrame) else (
                    [v for v in value.values() if isinstance(v, pd.DataFrame)] if isinstance(value, dict) else [])
                for f in found:
                    if id(f) not in frames:
                        frames.add(id(f))
                        held += int(f.memory_usage(deep=False, index=True).sum())
                        deep_held += int(f.memory_usage(deep=True, index=True).sum())
            except Exception:                                     # noqa: BLE001
                pass
        return {"frame_bytes_shallow_unique": held, "frame_bytes_deep_unique": deep_held, "frames_held": len(frames), "by_prefix": by, "standalone_bytes_total": sum(r["bytes"] for r in by.values()),
                "unique_bytes_total": unique, "entries": len(cache), "max": getattr(mod, "CACHE_MAX", None)}

    def _feeds() -> dict:
        """app.feeds._MEM and the disk copy it shares entries with, by key, deep."""
        mod = sys.modules.get("app.feeds")
        if mod is None:
            return {}
        out: dict = {}
        seen: set = set()
        rows = []
        for name in ("_MEM",):
            for k, v in list(getattr(mod, name, {}).items()):
                rows.append((k, _deep(v, seen)))
        disk = {}
        for path, d in list(getattr(mod, "_DISK", {}).items()):
            disk = d
        drows = [(k, _deep(v, seen)) for k, v in list(disk.items())]
        by = lambda r: sorted(r, key=lambda x: -x[1])[:25]
        return {"mem_entries": len(rows), "mem_bytes": sum(b for _, b in rows), "disk_entries": len(drows),
                "disk_bytes_not_in_mem": sum(b for _, b in drows), "mem_top": by(rows), "disk_top": by(drows)}

    def _frames() -> dict:
        try:
            import pandas as pd
        except Exception:                                         # noqa: BLE001
            return {}
        n, total = 0, 0
        for o in gc.get_objects():
            if isinstance(o, pd.DataFrame):
                n += 1
                try:
                    total += int(o.memory_usage(deep=False, index=True).sum())
                except Exception:                                 # noqa: BLE001
                    pass
        return {"live_frames": n, "live_frame_bytes": total}

    def _snapshot(signum=None, frame=None) -> None:
        _seq["snap"] += 1
        n = _seq["snap"]
        t0 = time.time()
        gc.collect()
        gc.collect()
        rec = {"n": n, "at": t0, "rss_kb": _rss_kb(), "threads": threading.active_count()}
        if _TRACE:
            import tracemalloc
            cur, peak = tracemalloc.get_traced_memory()
            rec.update({"traced_bytes": cur, "traced_peak_bytes": peak})
            tracemalloc.take_snapshot().dump(os.path.join(_OUT, "snap-%03d.tm" % n))
        rec["objects_by_type"] = dict(Counter(type(o).__name__ for o in gc.get_objects()).most_common(60))
        rec.update(_frames())
        rec["caches"] = _caches()
        rec["provider_cache"] = _provider_cache()
        rec["feeds"] = _feeds()
        rec["took_s"] = round(time.time() - t0, 2)
        tmp = os.path.join(_OUT, "snap-%03d.json.tmp" % n)
        with open(tmp, "w") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(_OUT, "snap-%03d.json" % n))

    def _control(signum=None, frame=None) -> None:
        """SIGUSR2: do what SOAK_OUT/cmd says, "gc" (collect) or "trim" (malloc_trim, Linux), and write ctl-NNN.json."""
        _seq["trim"] += 1
        try:
            with open(os.path.join(_OUT, "cmd")) as f:
                cmd = f.read().strip()
        except OSError:
            cmd = "gc"
        before = _rss_kb()
        result = None
        if cmd == "gc":
            gc.collect()
            gc.collect()
        elif cmd == "trim":
            try:
                import ctypes
                result = int(ctypes.CDLL("libc.so.6").malloc_trim(0))
            except Exception as exc:                              # noqa: BLE001
                result = "unavailable: %s" % exc
        rec = {"n": _seq["trim"], "cmd": cmd, "rss_before_kb": before, "rss_after_kb": _rss_kb(), "result": result}
        tmp = os.path.join(_OUT, "ctl-%03d.json.tmp" % _seq["trim"])
        with open(tmp, "w") as f:
            json.dump(rec, f)
        os.replace(tmp, os.path.join(_OUT, "ctl-%03d.json" % _seq["trim"]))

    signal.signal(signal.SIGUSR1, _snapshot)
    signal.signal(signal.SIGUSR2, _control)

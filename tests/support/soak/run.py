"""The memory soak (audit round, package E): `python -m tests.support.soak.run --symbols 40 --cycles 12 --fresh 3 --out DIR`.

Starts the recording Anthropic stub and the server (tests/support/memprobe.py Server) with the soak's hooks on
PYTHONPATH (tests/support/soak/sitecustomize.py: synthetic market data, census on SIGUSR1, collect or malloc_trim on SIGUSR2),
walks it (workload.py) and writes `soak.json` and `soak.md` to DIR.

Phase A, same symbols, `--cycles` identical cycles: a cache fills in cycle 1 and is flat after; a leak keeps growing.
Phase B, new symbols, `--fresh` cycles each over a new set of the same size: growth that stops at a ceiling is a bounded
cache; growth that does not stop is an unbounded one. Phase C, idle: wait, collect, measure again (settled).

`--no-trace` runs without tracemalloc, for the headline memory figures (tracing adds its own memory and time);
the traced run is for attribution. `--env NAME=VALUE` (repeatable) sets a variable in the server, e.g.
PYTHONMALLOC=malloc or MALLOC_ARENA_MAX=2, to test the allocator.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tests.support.anthropic_stub import AnthropicStub
from tests.support.memprobe import ROOT, Server, fds_and_rss
from tests.support.soak import workload

SOAK_DIR = Path(__file__).resolve().parent


def _mb(kb: float) -> float:
    return round(kb / 1024.0, 1)


def _wait_file(path: Path, seconds: float = 180.0) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if path.exists():
            return True
        time.sleep(0.3)
    return False


class Soak:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.out = Path(args.out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.data = Path(tempfile.mkdtemp(prefix="soak-data-"))
        self.measures: List[Dict[str, Any]] = []
        self.samples: List[Any] = []
        self._stop = threading.Event()
        self.snaps = 0
        self.trims = 0
        self.census_spans: List[Any] = []

    # ------------------------------------------------------------- measuring
    def measure(self, label: str, **extra: Any) -> Dict[str, Any]:
        fds, rss = self.server.settle(self.args.settle)
        row = {"label": label, "rss_kb": rss, "fds": fds, "at": round(time.time() - self.t0, 1), **extra}
        self.measures.append(row)
        print("%-18s rss %7.1f MB  fds %4d  %s" % (label, _mb(rss), fds, extra or ""), flush=True)
        return row

    def snapshot(self, label: str) -> Optional[Dict[str, Any]]:
        self.snaps += 1
        target = self.out / ("snap-%03d.json" % self.snaps)
        if target.exists():
            target.unlink()
        began = time.time() - self.t0
        os.kill(self.server.proc.pid, signal.SIGUSR1)
        arrived = _wait_file(target)
        self.census_spans.append((began, time.time() - self.t0 + 5.0))
        if not arrived:
            print("snapshot %d did not arrive" % self.snaps, flush=True)
            return None
        rec = json.loads(target.read_text())
        rec["label"] = label
        return rec

    def control(self, cmd: str) -> Optional[Dict[str, Any]]:
        """Ask the server to "gc" or (Linux only) "trim", and return what it recorded."""
        if cmd == "trim" and not sys.platform.startswith("linux"):
            return None
        self.trims += 1
        target = self.out / ("ctl-%03d.json" % self.trims)
        if target.exists():
            target.unlink()
        (self.out / "cmd").write_text(cmd)
        os.kill(self.server.proc.pid, signal.SIGUSR2)
        return json.loads(target.read_text()) if _wait_file(target, 60) else None

    def _sampler(self) -> None:
        while not self._stop.wait(2.0):
            try:
                self.samples.append((round(time.time() - self.t0, 1), fds_and_rss(self.server.proc.pid)[1]))
            except Exception:                                     # noqa: BLE001
                pass

    # ------------------------------------------------------------------ run
    def run(self) -> Dict[str, Any]:
        a = self.args
        stub = AnthropicStub().start()
        env = {"PYTHONPATH": os.pathsep.join(p for p in [str(SOAK_DIR), str(ROOT), os.environ.get("PYTHONPATH", "")] if p),
               "SOAK_OUT": str(self.out), "SOAK_TRACE": "0" if a.no_trace else "1",
               "ADMIN_EMAILS": "soak-reader@example.com"}
        for item in a.env or []:
            k, _, v = item.partition("=")
            env[k] = v
        self.t0 = time.time()
        self.server = Server(self.data, anthropic_url=stub.url, extra_env=env,
                             start_timeout=300)   # tracemalloc at import makes the start about a minute
        threading.Thread(target=self._sampler, daemon=True).start()
        snaps: Dict[str, Any] = {}
        ctl: Dict[str, Any] = {}
        settled = 0
        codes: Dict[str, Any] = {}
        try:
            reader = workload.Reader(self.server.base, self.data)
            base = self.measure("baseline")
            sets = [workload.symbol_set(0, a.symbols)]
            every = a.snapshots == "all"
            for c in range(1, a.cycles + 1):
                t = time.time()
                got = workload.cycle(reader, sets[0])
                codes["A%d" % c] = got
                self.measure("A%d" % c, phase="A", seconds=round(time.time() - t, 1))
                if every and c == 2:
                    snaps["after_A2"] = self.snapshot("after A2")
                if every and c == a.cycles:
                    snaps["end_A"] = self.snapshot("end of A")
            for k in range(1, a.fresh + 1):
                t = time.time()
                got = workload.cycle(reader, workload.symbol_set(k, a.symbols))
                codes["B%d" % k] = got
                self.measure("B%d" % k, phase="B", seconds=round(time.time() - t, 1))
            if every:
                snaps["end_B"] = self.snapshot("end of B")
            time.sleep(a.idle)
            self.measure("idle", phase="C")
            ctl["gc"] = self.control("gc")
            self.measure("settled", phase="C")           # after a collection, before anything else is asked of it
            settled = self.measures[-1]["rss_kb"]
            ctl["trim"] = self.control("trim")
            if ctl["trim"]:
                self.measure("after_trim", phase="C")
            if a.snapshots != "none":                    # last: the census allocates a great deal of its own
                snaps["end"] = self.snapshot("end, settled")
        finally:
            self._stop.set()
            self.server.stop()
            stub.stop()
        # the census allocates a great deal of its own, so samples taken while it ran are not the app's peak
        peak = max([r for t, r in self.samples if not any(a <= t <= b for a, b in self.census_spans)]
                   + [m["rss_kb"] for m in self.measures])
        try:
            commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT), capture_output=True, text=True).stdout.strip()
        except Exception:                                         # noqa: BLE001
            commit = "?"
        result = {
            "settings": {k: v for k, v in vars(a).items()}, "commit": commit, "platform": platform.platform(),
            "python": sys.version.split()[0], "machine": platform.machine(), "baseline_kb": base["rss_kb"],
            "peak_kb": peak, "settled_kb": settled,
            "measures": self.measures, "samples": self.samples, "codes": codes, "snapshots": snaps, "control": ctl,
        }
        (self.out / "soak.json").write_text(json.dumps(result, indent=1))
        (self.out / "soak.md").write_text(report(result, self.out))
        print("wrote", self.out / "soak.md", flush=True)
        return result


# ---------------------------------------------------------------- the report
def _growth(measures: List[Dict[str, Any]], phase: str) -> Dict[str, Any]:
    rows = [m for m in measures if m.get("phase") == phase]
    if len(rows) < 2:
        return {}
    kb = [m["rss_kb"] for m in rows]
    steps = [b - a for a, b in zip(kb, kb[1:])]
    half = len(kb) // 2
    return {"first": kb[0], "last": kb[-1], "per_cycle_mean_kb": sum(steps) / len(steps),
            "last_half_per_cycle_kb": (kb[-1] - kb[half]) / max(len(kb) - 1 - half, 1), "steps_kb": steps}


def _tm_diff(a: Path, b: Path, limit: int = 20) -> List[str]:
    try:
        import tracemalloc
        sa, sb = tracemalloc.Snapshot.load(str(a)), tracemalloc.Snapshot.load(str(b))
    except Exception as exc:                                      # noqa: BLE001
        return ["(no tracemalloc snapshots: %s)" % exc]
    flt = [tracemalloc.Filter(False, tracemalloc.__file__), tracemalloc.Filter(False, "<frozen *>")]
    sa, sb = sa.filter_traces(flt), sb.filter_traces(flt)
    lines = []
    for st in sb.compare_to(sa, "lineno")[:limit]:
        f = st.traceback[0]
        lines.append("| %s:%d | %+.0f KB | %+d | %.0f KB |" % (f.filename.replace(str(ROOT) + "/", ""), f.lineno, st.size_diff / 1024.0,
                                                               st.count_diff, st.size / 1024.0))
    return lines


def report(r: Dict[str, Any], out: Path) -> str:
    s = r["settings"]
    m = r["measures"]
    L: List[str] = []
    L.append("# Memory soak")
    L.append("")
    L.append("Commit %s, %s, Python %s. %d symbols, phase A %d identical cycles, phase B %d fresh cycles of new symbols, "
             "idle %ds. Tracing %s. Server env: %s." % (r["commit"], r["platform"], r["python"], s["symbols"], s["cycles"], s["fresh"],
                                                       s["idle"], "off" if s["no_trace"] else "on (tracemalloc, 25 frames)",
                                                       ", ".join(s.get("env") or []) or "default"))
    L.append("")
    L.append("## Resident memory (measured)")
    L.append("")
    L.append("- Baseline (booted, signed in, before the walk): **%.1f MB**" % _mb(r["baseline_kb"]))
    L.append("- Peak (sampled every 2 s and after every cycle): **%.1f MB**" % _mb(r["peak_kb"]))
    L.append("- Settled (after %ds idle and a forced collection): **%.1f MB**" % (s["idle"], _mb(r["settled_kb"])))
    for ph, name in (("A", "A, same symbols"), ("B", "B, new symbols")):
        g = _growth(m, ph)
        if g:
            L.append("- Phase %s: %.1f MB to %.1f MB; mean growth per cycle %+.1f MB, over the second half %+.1f MB per cycle"
                     % (name, _mb(g["first"]), _mb(g["last"]), _mb(g["per_cycle_mean_kb"]), _mb(g["last_half_per_cycle_kb"])))
    L.append("")
    L.append("| Step | Resident MB | Open files | Seconds |")
    L.append("| --- | --- | --- | --- |")
    for row in m:
        L.append("| %s | %.1f | %d | %s |" % (row["label"], _mb(row["rss_kb"]), row["fds"], row.get("seconds", "")))
    L.append("")
    L.append("Status counts per cycle (the walk is not judged on its answers; a refusal still exercises the path):")
    for k, v in r["codes"].items():
        L.append("- %s: %s" % (k, json.dumps(v)))
    snaps = {k: v for k, v in r["snapshots"].items() if v}
    if snaps:
        L.append("")
        L.append("## Traced Python memory against resident memory (measured)")
        L.append("")
        L.append("| Snapshot | Resident MB | Traced MB | Live frames | Frame data MB | Provider cache entries | Provider cache MB (unique) | Threads |")
        L.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for k, v in snaps.items():
            pc = v.get("provider_cache") or {}
            L.append("| %s | %.1f | %s | %s | %.1f | %s | %.1f | %s |" % (
                v["label"], _mb(v["rss_kb"]), "%.1f" % (v["traced_bytes"] / 1048576.0) if "traced_bytes" in v else "-",
                v.get("live_frames", "-"), v.get("live_frame_bytes", 0) / 1048576.0, pc.get("entries", "-"),
                pc.get("unique_bytes_total", 0) / 1048576.0, v.get("threads", "-")))
        L.append("")
        L.append("## Caches at each snapshot (entries, estimated MB; estimate = deep size of what each holds, shared objects once)")
        L.append("")
        names = sorted({c["where"] for v in snaps.values() for c in v["caches"]})
        L.append("| Cache | " + " | ".join(v["label"] for v in snaps.values()) + " |")
        L.append("| --- |" + " --- |" * len(snaps))
        for n in names:
            cells = []
            for v in snaps.values():
                c = next((c for c in v["caches"] if c["where"] == n), None)
                cells.append("-" if c is None else "%d%s" % (c["entries"], (" / %.1f" % (c["bytes"] / 1048576.0)) if c.get("bytes") is not None else ""))
            if any(x not in ("-", "0", "0 / 0.0") for x in cells):
                L.append("| %s | %s |" % (n, " | ".join(cells)))
        L.append("")
        L.append("Provider cache (`app.providers.yf._CACHE`) by key prefix at each snapshot (entries / standalone MB):")
        L.append("")
        pref = sorted({p for v in snaps.values() for p in (v.get("provider_cache") or {}).get("by_prefix", {})})
        L.append("| Prefix | " + " | ".join(v["label"] for v in snaps.values()) + " |")
        L.append("| --- |" + " --- |" * len(snaps))
        for p in pref:
            cells = []
            for v in snaps.values():
                row = ((v.get("provider_cache") or {}).get("by_prefix") or {}).get(p)
                cells.append("-" if not row else "%d / %.1f" % (row["entries"], row["bytes"] / 1048576.0))
            L.append("| %s | %s |" % (p, " | ".join(cells)))
        L.append("")
        L.append("## Object types that grew (measured; live objects by type, end of A against after A2, and end of B against end of A)")
        for a_, b_ in (("after_A2", "end_A"), ("end_A", "end_B")):
            if a_ in snaps and b_ in snaps:
                oa, ob = snaps[a_]["objects_by_type"], snaps[b_]["objects_by_type"]
                grew = sorted(((ob.get(t, 0) - oa.get(t, 0), t) for t in set(ob) | set(oa)), reverse=True)[:12]
                L.append("")
                L.append("%s to %s: %s" % (a_, b_, ", ".join("%s %+d" % (t, d) for d, t in grew if d > 0) or "nothing"))
        if not s["no_trace"]:
            for a_, b_, title in (("after_A2", "end_A", "after cycle 2 to the end of A"), ("end_A", "end_B", "the end of A to the end of B")):
                if a_ not in snaps or b_ not in snaps:
                    continue
                fa, fb = out / ("snap-%03d.tm" % snaps[a_]["n"]), out / ("snap-%03d.tm" % snaps[b_]["n"])
                if fa.exists() and fb.exists():
                    L.append("")
                    L.append("## Top allocation differences, %s (tracemalloc, by file and line)" % title)
                    L.append("")
                    L.append("| Where | Size change | Count change | Size now |")
                    L.append("| --- | --- | --- | --- |")
                    L.extend(_tm_diff(fa, fb))
    L.append("")
    L.append("## Collection and malloc_trim (measured, after the idle wait; trim is Linux only)")
    L.append("")
    for k, v in r["control"].items():
        if not v:
            L.append("- %s: not available on this platform." % k)
            continue
        L.append("- %s: resident %.1f MB before, %.1f MB after (returned %.1f MB)%s" % (
            k, _mb(v["rss_before_kb"]), _mb(v["rss_after_kb"]), _mb(v["rss_before_kb"] - v["rss_after_kb"]),
            "" if k == "gc" else ", malloc_trim returned %s" % v.get("result")))
    L.append("")
    L.append("Limit: the synthetic source replaces yfinance, so curl_cffi's own network path is not exercised; the soak can "
             "clear or implicate everything above it.")
    return "\n".join(L) + "\n"


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbols", type=int, default=40)
    p.add_argument("--cycles", type=int, default=12)
    p.add_argument("--fresh", type=int, default=3)
    p.add_argument("--idle", type=int, default=30, help="seconds idle before the settled measurement")
    p.add_argument("--settle", type=float, default=3.0, help="seconds to wait before each measurement")
    p.add_argument("--no-trace", action="store_true")
    p.add_argument("--snapshots", choices=["all", "end", "none"], default=None,
                   help="when to take the census (it allocates a great deal of its own, so a clean headline run "
                        "takes it only at the end); default all with tracing, end without")
    p.add_argument("--env", action="append", help="NAME=VALUE set in the server process")
    p.add_argument("--out", required=True)
    args = p.parse_args(argv)
    args.snapshots = args.snapshots or ("end" if args.no_trace else "all")
    Soak(args).run()


if __name__ == "__main__":
    main()

"""Open files and resident memory of a running Optic server, and a mix of requests to load it with.

Used by tests/test_pass3_memory.py and by hand (`python -m tests.support.memprobe`), so the figures in the runbook
(docs/operations/memory-and-open-files.md) and the test's band come from the same requests and the same counting.

Counting: on Linux (the container) /proc/<pid>/fd and VmRSS; on macOS `lsof` (numeric descriptors only, not the
mapped libraries lsof also lists) and `ps -o rss`. No new dependency.
"""

from __future__ import annotations

import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
CLOSED = "http://127.0.0.1:9"

SYMBOLS = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "V", "XOM",
           "UNH", "HD", "PG", "KO", "PEP", "COST", "AMD", "NFLX", "DIS", "BA"]

# What the browser journeys and a reader's walk ask for: the page and its files, the reads every screen makes, and the
# per-symbol reads that fill the module caches. Feeds are refused at the closed port, so the per-symbol reads exercise
# the failure path, which is where an unclosed client or an unbounded cache shows first.
PAGES = ["/", "/v2/", "/v2/index.html", "/v2/js/app.js", "/v2/js/nav.js", "/v2/js/core/store.js",
         "/v2/css/components.css", "/robots.txt"]
READS = ["/healthz", "/api/health", "/api/delays", "/api/legal", "/api/session", "/api/auth/providers",
         "/api/billing/status", "/api/knowledge/modes", "/api/personas", "/api/ai-allowance", "/api/build",
         "/api/home", "/api/market", "/api/indices", "/api/sectors", "/api/macro", "/api/watchlist"]
PER_SYMBOL = ["/api/quote/{s}", "/api/ticker/{s}", "/api/daily-bars/{s}", "/api/news/{s}", "/api/figures/{s}",
              "/api/valuation/{s}", "/api/session/{s}", "/api/earnings/{s}", "/api/symbol-check?symbol={s}",
              "/api/sparklines?symbols={s}"]


# The suite's mix (tests/test_pass3_memory.py): the same kinds of request, with the per-symbol reads that wait on a
# refused feed cut to one in ten, so 200 requests finish in about a minute instead of four. One in ten still reads
# prices on the provider's threads, which is where the per-thread files of yfinance's caches opened.
QUICK_READS = ["/healthz", "/api/health", "/api/delays", "/api/legal", "/api/auth/providers", "/api/billing/status",
               "/api/knowledge/modes", "/api/personas", "/api/ai-allowance", "/api/build", "/api/watchlist",
               "/api/indices", "/api/sectors", "/api/figures/{s}", "/api/valuation/{s}", "/api/symbol-check?symbol={s}"]
SLOW_READS = ["/api/daily-bars/{s}", "/api/quote/{s}", "/api/sparklines?symbols={s}", "/api/session/{s}"]


def quick_paths(n: int) -> List[str]:
    out: List[str] = []
    i = 0
    while len(out) < n:
        s = SYMBOLS[i % len(SYMBOLS)]
        if i % 10 == 9:
            out.append(SLOW_READS[(i // 10) % len(SLOW_READS)].format(s=s))
        elif i % 2:
            out.append(QUICK_READS[i % len(QUICK_READS)].format(s=s))
        else:
            out.append(PAGES[i % len(PAGES)])
        i += 1
    return out


def mixed_paths(n: int) -> List[str]:
    """`n` request paths, cycling pages, reads and per-symbol reads over twenty symbols."""
    out: List[str] = []
    i = 0
    while len(out) < n:
        out.append(PAGES[i % len(PAGES)])
        out.append(READS[i % len(READS)])
        s = SYMBOLS[i % len(SYMBOLS)]
        out.append(PER_SYMBOL[i % len(PER_SYMBOL)].format(s=s))
        out.append(PER_SYMBOL[(i + 3) % len(PER_SYMBOL)].format(s=SYMBOLS[(i * 7) % len(SYMBOLS)]))
        i += 1
    return out[:n]


def fds_and_rss(pid: int) -> Tuple[int, int]:
    """(open file descriptors, resident set in KiB) of process `pid`."""
    proc = Path("/proc/{}/fd".format(pid))
    if proc.exists():
        fds = len(os.listdir(proc))
        status = Path("/proc/{}/status".format(pid)).read_text()
        rss = int(re.search(r"VmRSS:\s+(\d+)", status).group(1))
        return fds, rss
    out = subprocess.run(["lsof", "-n", "-P", "-p", str(pid), "-F", "f"], capture_output=True, text=True).stdout
    fds = sum(1 for line in out.splitlines() if re.fullmatch(r"f\d+", line))
    rss = int(subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip() or 0)
    return fds, rss


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_env(data: Path, port: int, anthropic_url: str = CLOSED) -> Dict[str, str]:
    env = {k: v for k, v in os.environ.items()
           if not k.upper().endswith(("_KEY", "_TOKEN", "_SECRET"))
           and not k.startswith(("ANTHROPIC", "OPTIC_", "STRIPE", "SNAPTRADE", "TRADIER"))}
    env.update({
        "TRACKER_DATA_DIR": str(data), "ACCOUNTS_DB_PATH": str(data / "accounts.db"),
        "ANTHROPIC_BASE_URL": anthropic_url, "ANTHROPIC_API_KEY": "test-key-not-real",
        "ANTHROPIC_MAX_RETRIES": "0", "ANTHROPIC_TIMEOUT_SECONDS": "3",
        "HTTP_PROXY": CLOSED, "HTTPS_PROXY": CLOSED, "http_proxy": CLOSED, "https_proxy": CLOSED,
        "ALL_PROXY": CLOSED, "NO_PROXY": "127.0.0.1,localhost", "no_proxy": "127.0.0.1,localhost",
        "APP_URL": "http://127.0.0.1:{}".format(port), "OPTIC_OVERNIGHT_FEED": "off", "PYTHONUNBUFFERED": "1",
    })
    return env


class Server:
    """The app under uvicorn in a subprocess, on a free port and a fresh data directory."""

    def __init__(self, data: Path, anthropic_url: str = CLOSED, extra_env: Optional[Dict[str, str]] = None,
                 start_timeout: float = 60):
        self.data = data
        self.port = _free_port()
        self.base = "http://127.0.0.1:{}".format(self.port)
        self._log = open(data / "server.log", "w")
        env = server_env(data, self.port, anthropic_url)
        env.update(extra_env or {})                               # the soak's PYTHONPATH and hooks; none for the suite
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=str(ROOT), env=env, stdout=self._log,
            stderr=subprocess.STDOUT)
        deadline = time.time() + start_timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(self.base + "/healthz", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:                                     # noqa: BLE001 - not up yet
                time.sleep(0.3)
        self.stop()
        raise RuntimeError("the server did not start; see " + str(data / "server.log"))

    def get(self, path: str, timeout: float = 30) -> int:
        try:
            with urllib.request.urlopen(self.base + path, timeout=timeout) as r:
                r.read()
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception:                                         # noqa: BLE001 - a timeout counts as an answer
            return 0

    def load(self, n: int, workers: int = 8, quick: bool = False) -> Dict[int, int]:
        """`n` mixed requests, `workers` at a time (a browser opens about six connections to a host)."""
        from concurrent.futures import ThreadPoolExecutor
        codes: Dict[int, int] = {}
        paths = quick_paths(n) if quick else mixed_paths(n)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for c in pool.map(self.get, paths):
                codes[c] = codes.get(c, 0) + 1
        return codes

    def settle(self, seconds: float = 3.0) -> Tuple[int, int]:
        """Wait for background reads started by the requests to finish, then count."""
        time.sleep(seconds)
        return fds_and_rss(self.proc.pid)

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self._log.close()


def main() -> None:                                               # pragma: no cover - a hand measurement
    import tempfile
    quick = "--quick" in sys.argv
    steps = [int(a) for a in sys.argv[1:] if a.isdigit()] or [200, 800]
    with tempfile.TemporaryDirectory() as d:
        s = Server(Path(d))
        try:
            print("boot", s.settle(2.0), flush=True)
            for n in steps:
                t = time.time()
                codes = s.load(n, quick=quick)
                print("after +{} requests ({:.0f} s) settled 3 s {} codes {}".format(
                    n, time.time() - t, s.settle(), codes), flush=True)
                print("  settled 15 s more", s.settle(15.0), flush=True)
        finally:
            s.stop()


if __name__ == "__main__":                                        # pragma: no cover
    main()

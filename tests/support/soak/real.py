"""A memory measurement against the REAL feeds, by hand (audit round, package E, second part). Network is used: never run
from a test. `python -m tests.support.soak.real --out DIR sets` walks sets of real symbols with the stock page's reads
and reads resident memory after each; `... endpoints` walks one kind of read at a time over fresh symbols to say which
read retains. The server is the working tree's, with the soak's census hooks (SOAK_REAL=1 leaves yfinance alone).
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests.support.memprobe import PER_SYMBOL, ROOT, Server
from tests.support.soak import workload

SOAK_DIR = Path(__file__).resolve().parent
SETS = [
    "AAPL MSFT NVDA AMZN GOOGL META TSLA AVGO JPM V MA UNH XOM JNJ PG HD COST ABBV MRK CVX KO PEP WMT BAC ORCL CRM ADBE NFLX AMD INTC CSCO TMO ACN MCD LIN ABT DHR WFC DIS TXN".split(),
    "PM NEE VZ CMCSA UPS RTX HON AMGN IBM QCOM LOW SPGI CAT GS INTU UNP BA SBUX ISRG GE PLD BLK MDT ELV DE AMAT BKNG ADP GILD LMT MDLZ SYK TJX CVS ADI VRTX MMC CB C".split(),
    "MO SCHW CI ZTS PGR SO REGN DUK BDX TMUS EQIX ITW SLB CL NOC MU APD CSX EOG SHW ICE AON CME FDX PNC USB HUM ETN BSX NSC MCO EMR WM GD MAR F GM KLAC PYPL".split(),
]


def start(out: Path, trace: bool, extra=None):
    data = Path(tempfile.mkdtemp(prefix="soak-real-"))
    env = {"PYTHONPATH": os.pathsep.join([str(SOAK_DIR), str(ROOT)]), "SOAK_OUT": str(out), "SOAK_REAL": "1",
           "SOAK_TRACE": "1" if trace else "0", "SOAK_FRAMES": "6", "ADMIN_EMAILS": "soak-reader@example.com",
           "HTTP_PROXY": "", "HTTPS_PROXY": "", "http_proxy": "", "https_proxy": "", "ALL_PROXY": "", "NO_PROXY": "",
           "no_proxy": "", "OPTIC_OVERNIGHT_FEED": "off"}
    env.update(extra or {})
    server = Server(data, extra_env=env, start_timeout=300)
    return server, workload.Reader(server.base, data)


def census(server, out: Path, n: int):
    target = out / ("snap-%03d.json" % n)
    if target.exists():
        target.unlink()
    os.kill(server.proc.pid, signal.SIGUSR1)
    end = time.time() + 600
    while time.time() < end and not target.exists():
        time.sleep(1)
    return json.loads(target.read_text()) if target.exists() else None


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["sets", "endpoints"])
    p.add_argument("--out", required=True)
    p.add_argument("--trace", action="store_true")
    p.add_argument("--per", type=int, default=8, help="endpoints mode: fresh symbols per kind of read")
    p.add_argument("--only", help="endpoints mode: only the read whose path contains this")
    p.add_argument("--env", action="append")
    a = p.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    extra = dict(i.split("=", 1) for i in a.env or [])
    server, reader = start(out, a.trace, extra)
    rows = []
    try:
        def rss(label, **kw):
            fds, kb = server.settle(5.0)
            rows.append({"label": label, "rss_mb": round(kb / 1024.0, 1), "fds": fds, **kw})
            print("%-28s rss %7.1f MB fds %4d %s" % (label, kb / 1024.0, fds, kw), flush=True)
        rss("boot")
        reader.request("/api/home")
        rss("after home")
        if a.mode == "sets":
            snaps = {}
            for i, syms in enumerate(SETS + [SETS[0]]):
                paths = workload.HOME + [t.format(s=s) for s in syms for t in PER_SYMBOL]
                with ThreadPoolExecutor(8) as ex:
                    list(ex.map(reader.request, paths))
                rss("set%d %s" % (i + 1, "repeat" if i == 3 else "new"), codes=dict(reader.codes))
                if a.trace and i in (0, 2):
                    snaps["after_set%d" % (i + 1)] = census(server, out, len(snaps) + 1)
            snaps["end"] = census(server, out, len(snaps) + 1)
            result = {"rows": rows, "snapshots": snaps}
        else:
            pool = [s for syms in SETS for s in syms]
            k = 0
            for path in [x for x in PER_SYMBOL if not a.only or a.only in x]:
                syms = pool[k:k + a.per]
                k += a.per
                with ThreadPoolExecutor(8) as ex:
                    list(ex.map(reader.request, [path.format(s=s) for s in syms]))
                rss(path.split("/")[2].split("?")[0] + " x%d" % a.per, path=path, codes=dict(reader.codes))
            result = {"rows": rows, "snapshots": {"end": census(server, out, 1)}}
        (out / "real.json").write_text(json.dumps(result, indent=1))
    finally:
        server.stop()


if __name__ == "__main__":
    main()

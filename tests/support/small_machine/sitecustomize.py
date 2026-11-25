"""A small, slow machine for a journey's server (round three D2, 2026-11-25). Test only: loaded by Python at start-up
only when a journey puts this directory on PYTHONPATH (tests/e2e/test_round_three_stall.py), never by the app.

On GitHub's Ubuntu runners one scheduled batch download of about a hundred names held the provider lock for about
26 s; on the Mac the same download fails in milliseconds, so the stall was never seen there. This stands in for that
machine, so the journey fails on any machine if the stall comes back:

- SMALL_MACHINE_CPUS: what os.cpu_count() answers (the loop's default executor is sized from it).
- SMALL_MACHINE_JOB_SECONDS_PER_NAME: a scheduled job's yf.download takes this long per name before it runs (a
  reader's download is not slowed).
- SMALL_MACHINE_MARK: a file written when a slowed job download starts, so the journey knows the batch is running.
"""
import os
import sys
import time

if os.environ.get("SMALL_MACHINE_CPUS") and "uvicorn" in " ".join(getattr(sys, "orig_argv", sys.argv)):
    _n = int(os.environ["SMALL_MACHINE_CPUS"])
    os.cpu_count = lambda: _n
    if hasattr(os, "process_cpu_count"):
        os.process_cpu_count = lambda: _n

if os.environ.get("SMALL_MACHINE_JOB_SECONDS_PER_NAME") and "uvicorn" in " ".join(getattr(sys, "orig_argv", sys.argv)):
    import yfinance as _yf

    _download = _yf.download
    _per_name = float(os.environ["SMALL_MACHINE_JOB_SECONDS_PER_NAME"])

    def _slow_for_jobs(tickers, *args, **kwargs):
        try:
            from app.providers import yf as _provider
            job = _provider.in_background()
        except Exception:                                        # noqa: BLE001 - not the app's provider: leave it be
            job = False
        if job:
            names = tickers if isinstance(tickers, (list, tuple)) else str(tickers).split()
            mark = os.environ.get("SMALL_MACHINE_MARK")
            if mark:
                with open(mark, "a") as f:
                    f.write("{:.3f} {}\n".format(time.time(), len(names)))
            time.sleep(_per_name * len(names))
        return _download(tickers, *args, **kwargs)

    _yf.download = _slow_for_jobs

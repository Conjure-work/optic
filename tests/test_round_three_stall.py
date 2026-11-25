"""Round three D2 (2026-11-25): the server kept answering while a scheduled market-data batch ran.

On GitHub's two-CPU Ubuntu runners one scheduled download of about a hundred names held the provider lock for about
26 s. The readers' legs queued on it filled the loop's default executor (min(32, CPUs + 4) threads: six there), so every
route that runs through `_run` waited, and a browser's six connections to the host were all held by them. The fixes,
each held here: the readers' pool is installed at a size that does not depend on the machine; the jobs' lane runs in a
pool of its own; and a job's batch download takes the provider lock one part at a time, so a reader waiting for the
lock is let in between parts. The journey that runs the whole thing on a slowed two-CPU server is
tests/e2e/test_round_three_stall.py.
"""
from __future__ import annotations

import asyncio
import inspect
import threading
import time

import pandas as pd
import pytest
from concurrent.futures import ThreadPoolExecutor

from app import main
from app.providers import yf as Y


@pytest.fixture(autouse=True)
def own_pools(monkeypatch):
    """Pools of the app's sizes for each test: asyncio.run shuts the loop's default executor down when it ends, so the
    app's own reader pool is not handed to it."""
    monkeypatch.setattr(main, "_READER_POOL", ThreadPoolExecutor(max_workers=main.READER_THREADS, thread_name_prefix="reader"))
    monkeypatch.setattr(main, "_JOB_POOL", ThreadPoolExecutor(max_workers=main.JOB_THREADS, thread_name_prefix="job"))
    yield
    main._JOB_POOL.shutdown(wait=False)


def test_the_readers_pool_does_not_depend_on_the_cpu_count(monkeypatch):
    monkeypatch.setattr("os.cpu_count", lambda: 2)

    async def go():
        main._install_reader_pool()
        loop = asyncio.get_running_loop()
        names = await asyncio.gather(*[loop.run_in_executor(None, lambda: threading.current_thread().name) for _ in range(3)])
        return loop._default_executor, names

    executor, names = asyncio.run(go())
    assert executor is main._READER_POOL
    assert main._READER_POOL._max_workers == main.READER_THREADS == 32
    assert main.JOB_THREADS < main.READER_THREADS
    assert all(n.startswith("reader") for n in names)


def test_startup_installs_the_readers_pool_first():
    src = inspect.getsource(main._start_tracker)
    body = src[src.index(":\n") + 2:].strip().splitlines()
    assert body[0].strip() == "_install_reader_pool()"


def test_a_job_runs_in_the_jobs_pool_and_never_takes_a_readers_thread():
    release = threading.Event()

    async def go():
        main._install_reader_pool()
        # every job thread busy with a job that waits, as a batch behind the provider lock does
        token = main._BACKGROUND_JOB.set(True)
        try:
            held = [main._run(release.wait, 10) for _ in range(main.JOB_THREADS + 2)]
        finally:
            main._BACKGROUND_JOB.reset(token)
        t0 = time.monotonic()
        name = await asyncio.wait_for(main._run(lambda: threading.current_thread().name), 2)
        took = time.monotonic() - t0
        release.set()
        await asyncio.gather(*held)
        return name, took, None

    name, took, _ = asyncio.run(go())
    assert name.startswith("reader")
    assert took < 0.5, "a reader waited {:.2f}s behind the jobs".format(took)


def test_a_jobs_work_runs_on_a_job_thread():
    async def go():
        main._install_reader_pool()
        token = main._BACKGROUND_JOB.set(True)
        try:
            return await main._run(lambda: (threading.current_thread().name, Y.in_background()))
        finally:
            main._BACKGROUND_JOB.reset(token)

    name, lane = asyncio.run(go())
    assert name.startswith("job") and lane is True


def _frame(names):
    idx = pd.date_range("2026-01-02", periods=3, freq="D")
    cols = pd.MultiIndex.from_product([names, ["Open", "High", "Low", "Close", "Adj Close", "Volume"]])
    return pd.DataFrame(1.0, index=idx, columns=cols)


def test_a_jobs_batch_lets_a_waiting_reader_take_the_lock_between_parts(monkeypatch):
    calls = []

    def fake_download(names, **kw):
        calls.append(list(names))
        time.sleep(0.3)
        return _frame(list(names))

    monkeypatch.setattr(Y.yf, "download", fake_download)
    Y._CACHE.clear()
    names = ["N{:03d}".format(i) for i in range(100)]
    provider = Y.YFinanceProvider()
    got = {}

    def job():
        with Y.background():
            got.update(provider.batch_history(names, period="1y", interval="1d"))

    t = threading.Thread(target=job, daemon=True)
    t.start()
    while not calls:
        time.sleep(0.01)
    t0 = time.monotonic()
    with Y._NET_LOCK:                        # a reader's turn at the lock, asked while the job's first part downloads
        waited = time.monotonic() - t0
    t.join(30)
    assert [len(c) for c in calls] == [Y.JOB_DOWNLOAD_PART] * 5
    assert len(got) == 100
    assert waited < 0.6, "the reader waited {:.2f}s, the whole batch rather than one part".format(waited)


def test_a_readers_batch_is_still_one_download(monkeypatch):
    calls = []
    monkeypatch.setattr(Y.yf, "download", lambda names, **kw: calls.append(list(names)) or _frame(list(names)))
    Y._CACHE.clear()
    names = ["R{:03d}".format(i) for i in range(60)]
    got = Y.YFinanceProvider().batch_history(names, period="1y", interval="1d")
    assert [len(c) for c in calls] == [60] and len(got) == 60


def test_a_refusal_mid_batch_stops_asking_and_keeps_what_came(monkeypatch):
    calls = []

    def fake_download(names, **kw):
        calls.append(list(names))
        if len(calls) == 2:
            raise RuntimeError("Too Many Requests")
        return _frame(list(names))

    monkeypatch.setattr(Y.yf, "download", fake_download)
    monkeypatch.setattr(Y.YFinanceProvider, "_fill_missing", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked again after a refusal")))
    Y._CACHE.clear()
    names = ["F{:03d}".format(i) for i in range(60)]
    with Y.background():
        got = Y.YFinanceProvider().batch_history(names, period="1y", interval="1d")
    assert len(calls) == 2, "no part asked after the refusal"
    assert set(got) == set(names[:Y.JOB_DOWNLOAD_PART])

# Pass 3 health record: memory and open files, the suite on GitHub, the brokerage sandbox

Round three's carried-in items 8, 9 and 10, on `factory/pass-3-investor-charts-billing-milo`. Measured 2026-11-23 on
the ops Mac; the evaluation copy's figures are taken at its deploy and recorded with it.

## Memory and open files at rest

**Seen on the private test site (2026-11-18):** about 85 open files and 0.4 GB at boot, about 540 and 1.8 GB after use.

**Measured locally** (app under uvicorn, fresh data directory, feeds refused at a closed port, eight requests at a
time from `tests/support/memprobe.py`; open descriptors from `lsof`, resident memory from `ps`):

| Run | Boot | After 200 | Later |
| --- | --- | --- | --- |
| Full mix, before | 31 fds, 314 MB | 751 fds, 331 MB | 881 fds, 296 MB after 1,000 |
| Full mix, after | 11 fds, 316 MB | 461 fds (requests still in flight), 318 MB | 210 fds, 263 MB after 1,000 |
| Quick mix (the test's), before, settled 15 s | 25 fds, 312 MB | 257 fds, 311 MB | 264 fds after 400 |
| Quick mix, after, settled 15 s | 11 fds, 310 MB | 37 fds, 306 MB | 80 after 400, 85 after 600 |

**Causes found (verified, not assumed):**

1. yfinance's timezone, cookie and ISIN caches are SQLite files opened through peewee with one connection per thread,
   kept for the thread's life, four open files per thread with write-ahead logging: 510 of 910 descriptors in the
   before run. Fixed by `app/providers/yf_caches.py` (the same caches in memory, bounded; timezones also written to
   one file on the volume with one connection per write).
2. A new Anthropic client (and its connection pool) for every chat, brief and `/api/health` read, never closed.
   Fixed in `app/ai.py`: one client per configuration, per event loop for the async one, closed at shutdown.
3. Five module caches keyed by symbol with no eviction (`app/contracts.py`, `app/replays.py`,
   `app/valuation/service.py`, `app/analytics/screen.py`, `app/research/service.py`). Each is now a bounded cache
   (`app/boundcache.py`) with a size and an age no shorter than the module's own freshness check.
4. The two thread pools named in the survey (`_LEG_POOL` 32, `_DOC_POOL` 24) were already fixed sizes; unchanged.

**What remains, with its library:** curl_cffi (libcurl) holds one pipe pair per live thread per HTTP session,
released when the thread ends; bounded by the app's thread count, not by requests (the 37 to 85 above). Resident
memory did not climb locally because no feed answers; with real data the caches now have ceilings, and Python's
allocator keeps freed arenas, so resident memory after a busy hour stays near its peak. Runbook:
`docs/operations/memory-and-open-files.md`.

**Tests:** `tests/test_pass3_memory.py` (band: at most 60 open files and 150 MB over boot after 200 mixed requests;
the code before the fix fails it at 225 more open files), `tests/test_pass3_caches.py` (11 cases: size and age
eviction, each module's cache bounded, yfinance's caches replaced, the shared Anthropic clients).

## The suite on GitHub

Per-file durations from the phase 0 clean run's JUnit times (2,093 s in all): Python files 284 s together; browser
journeys 1,809 s, of which `tests/e2e/test_pass1_journeys.py` alone took 1,112 s. So the split is by test:

| Shard | What | Measured on the Mac | Tests (floor) |
| --- | --- | --- | --- |
| py | every Python file outside tests/e2e | about 5.5 min | 9,074 collected (9,073 passed, the one standing skip) |
| e2e-1 to e2e-6 | the journeys dealt round-robin in collection order (`tests/support/shard_plugin.py --slice i/6`) | about 5 min each | 23, 23, 23, 23, 23, 22 |

`SUITE_FLOOR` 9,210 is the sum of the shard floors. Each shard checks its own floor; the `count` job adds the JUnit
files and fails on a missing shard, any failure, or a total under the floor. On GitHub's runner each shard is expected
under 15 minutes including the install (timeout 30); the image and secrets jobs are unchanged. `tests/test_ci_shards.py`
checks the matrix equals the shard list, every test file is in exactly one shard, the slices partition the journeys,
and the floors add up. The two settings that are the repository owner's, with the clicks:
`docs/operations/ci-on-github.md`. The floors are set again at the end of the pass, when every piece has landed.

## The brokerage sandbox

Untested end to end on the private test site: the SnapTrade sandbox Client ID and Consumer Key have not been received.
`/api/health` now carries `modes.brokerage` (`provider`, `enabled`, and `snaptrade`: `not configured`,
`configured (sandbox)` or `configured (production)`, never a value); `tests/test_brokerage_health_mode.py` (3 cases).
Runbook: `docs/operations/brokerage-sandbox.md`.

## The suite on this piece

From the branch at this piece's last code commit, on the ops Mac (2026-11-23, 17:06 to 17:41 UTC, 2,097 s): 9,187
passed, 23 failed, 1 skipped (`test_live_qqq`) of 9,211. The 23 failures are the same 23 as the phase 0 run from a
clean clone of the shared ground, every one an axe scan, every one the rule `label-content-name-mismatch` on the top
bar's `.search-btn` (its accessible name "Search companies, tickers and pages, or ask Milo" does not contain its
visible text "Search or ask"). The rule fires since axe-core 4.14.0, which `axe-playwright-python` 0.1.9 (the version
`requirements-dev.txt` now installs) carries; it is not caused by this piece and is fixed where the top bar is owned.

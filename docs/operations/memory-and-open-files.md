# Memory and open files at rest

What a running Optic process holds, why, and what is bounded. Measured 2026-11-23.

## What was seen

On the private test site (Railway, one process, SQLite) the process read about 85 open files and 0.4 GB resident at
boot and climbed with use to about 540 open files and 1.8 GB after a day of browsing and a full test walk, flat during
a 30-page soak. Nothing failed, but the climb did not stop on its own.

## What was found, on a local run

The app under uvicorn on a fresh data directory, every market feed refused at a closed port, requests from
`tests/support/memprobe.py` eight at a time (`python -m tests.support.memprobe 200 800` for the full mix,
`--quick` for the suite's mix). Counts: open descriptors from `lsof` (numeric ones only), resident memory from `ps`.

| Run | Boot | After 200 | After 1,000 |
| --- | --- | --- | --- |
| Full mix, before | 31 fds, 314 MB | 751 fds, 331 MB | 881 fds, 296 MB |
| Full mix, after | 11 fds, 316 MB | 461 fds (in flight), 318 MB | 210 fds, 263 MB |
| Quick mix, before, settled 15 s | 25 fds, 312 MB | 257 fds, 311 MB | 264 fds after 400 |
| Quick mix, after, settled 15 s | 11 fds, 310 MB | 37 fds, 306 MB | 80 fds after 400, 85 after 600 |

1. **Open files: yfinance's caches, one SQLite connection per thread.** yfinance keeps exchange timezones, the Yahoo
   cookie and ISIN lookups in SQLite files through peewee, which opens a connection per thread and keeps it for the
   thread's life; with write-ahead logging that is four open files per thread that ever read a price. Before the fix,
   510 of 910 descriptors in one process were `tkr-tz.db`, `cookies.db` and their logs. Fixed by
   `app/providers/yf_caches.py`: the same three caches held in memory, bounded, with the timezones also written to
   one file on the volume through one connection per write (so a deploy still keeps them, as `_persist_timezones`
   intended). Read from outside: no `tkr-tz.db` or `cookies.db` descriptors.
2. **Anthropic clients: a new one for every chat, every brief and every `/api/health` read**, each with its own
   connection pool, never closed. Fixed in `app/ai.py`: one client per configuration (per event loop for the async
   client), closed on shutdown; `ai.shared_clients()` gives the count.
3. **Module caches with no end.** Five module-level dicts kept an entry per symbol for the life of the process
   (`app/contracts.py`, `app/replays.py` with full-history price frames, `app/valuation/service.py`,
   `app/analytics/screen.py`, `app/research/service.py`). Each is now an `app/boundcache.py` `BoundedCache`: a size
   (256 entries; replays 16; the screen's rankings 8) and an age no shorter than the module's own freshness check.
4. **The thread pools are fixed sizes** (`_LEG_POOL` 32 in `app/main.py`, `_DOC_POOL` 24 in `app/providers/yf.py`);
   their threads persist by design (warm connections) and are counted in the next section.

## What remains, and whose it is

- **curl_cffi (libcurl): one pipe pair per live thread per HTTP session.** Released when the thread ends, so it is
  bounded by the number of threads the app runs (the two pools above, uvicorn's worker threads, the background
  lanes), not by the number of requests. This is the 37 to 85 descriptors after the fix in the table.
- **Resident memory in a local run does not climb** because every feed is refused and no price history is cached.
  With real data the process holds what the caches hold; the caches now have ceilings (`yf.py`'s own
  `YF_CACHE_MAX`, 20,000 entries, and the five above). Python's allocator (pymalloc) does not return freed arenas to
  the system promptly, so resident memory after a busy hour stays near its peak even when the caches have emptied;
  that is Python's, not a leak.

## How it is checked

- `tests/test_pass3_memory.py`: the app in a subprocess, 200 mixed requests, open files within 60 of boot and
  resident memory within 150 MB of boot (the code before the fix failed it at 225 more open files).
- `tests/test_pass3_caches.py`: each cache evicts by size and by age; yfinance's caches are Optic's; the Anthropic
  client is shared per configuration and per loop.
- On a deployment: open files and resident memory from inside the container (`ls /proc/1/fd | wc -l`, `VmRSS` in
  `/proc/1/status`, or the process uvicorn runs as) at boot, after a walk, and after a soak.

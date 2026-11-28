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
- **Resident memory in a local run with the feeds refused does not climb**, because no price history is cached.
  That run could not see growth that comes from holding data, and the paragraph that stood here, which put the climb
  down to Python's allocator ("that is Python's, not a leak"), was a guess. The soak below, which serves real-sized data,
  shows two causes, one of them the cache and one of them the allocator, and both are named with figures.

## The soak: what real-sized data does to memory (2026-11-27)

Round-four audit, package E. On the deployed copy resident memory went from 353 MB at boot to 701 MB after a soak and
1.04 GB after the outside run, and nothing attributed it. `tests/support/soak/` is a repeatable run that does.

### How to run it

```
cd <repo root>
.venv/bin/python -m tests.support.soak.run --symbols 40 --cycles 12 --fresh 3 --out <dir> --no-trace     # the figures
.venv/bin/python -m tests.support.soak.run --symbols 10 --cycles 4 --fresh 2 --out <dir> --env SOAK_FRAMES=8   # what is retained
```

In the image (glibc, as the host is), with the repo's `tests/` mounted over the image's:

```
docker build -t optic-soak .
docker run --rm --entrypoint python -v "$PWD/tests:/app/tests:ro" -v "<dir>:/out" optic-soak \
  -m tests.support.soak.run --symbols 40 --cycles 12 --fresh 3 --no-trace --out /out
```

The server starts with `tests/support/soak/` on `PYTHONPATH`: its `sitecustomize.py` replaces yfinance with
`synthetic.py` (two years of daily bars, intraday bars, the six statements, a twenty-expiry by hundred-strike chain,
insiders, holders, estimates and news, each seeded by the symbol), so the app's provider code, caches and analytics run
for real and no feed is asked. Anthropic is the recording stub. `workload.py` signs in one reader and walks Home, the
stock page's reads for every symbol, Financials, Earnings, Options and Insiders, one Milo question, one deep research,
one earnings brief and the Markets pages, eight requests at a time. Phase A repeats the same symbols (a cache fills in
the first cycle; a leak keeps growing), phase B uses new symbols each cycle (a bounded cache stops growing, an unbounded
one does not), then an idle wait, a forced collection (the settled figure), and on Linux `malloc_trim`. The census (live
objects by type, every module cache's size, the provider cache by key prefix, tracemalloc differences when traced) is
taken last, because it allocates a great deal of its own; `--snapshots all` takes it between cycles for attribution.
`--env NAME=VALUE` sets a variable in the server (`PYTHONMALLOC=malloc`, `MALLOC_ARENA_MAX=2`).
`tests/test_audit_memory_soak.py` runs a small version in CI to keep the tool alive; it is not the measurement.

### What was measured

Resident memory, MB, 40 symbols a cycle, ~1,100 requests a cycle, all answered 200. Reports for every run are in
`Conjure/customers/optic/audit-response-2026-11-27/evidence/memory/`.

| Run | Boot | A, first cycle | A, last cycle | B cycles (new symbols) | Peak | Settled | After `malloc_trim` |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Image, run 2 (8 A, 3 B) | 295 | 458 | 579 | 620, 677, 740 | 740 | 740 | 683 |
| Image, run 1 (12 A, 3 B) | 296 | 455 | 642 | 654, 712, 765 | see note | see note | - |
| Mac, run 2 (8 A, 3 B) | 306 | 377 | 388 | 431, 430, 484 | 484 | 484 | - |
| Mac, run 1 (12 A, 3 B) | 303 | 375 | 413 | 467, 531, 580 | see note | see note | - |
| Image, `MALLOC_ARENA_MAX=2` | 294 | 396 | 429 | 489, 558, 629 | 629 | 629 | 626 |
| Image, `PYTHONMALLOC=malloc` | 298 | 519 | 672 | 688, 741, 807 | 807 | 807 | 744 |

Note: runs 1 took the census between cycles, which adds its own memory; their cycle figures are as measured and their
peak and settled figures are not the app's. Runs 2 onward take it last. Repeats: image A1 to A8 reads 455 to 614 in run 1
and 458 to 579 in run 2; B3 765 and 740.

Retained objects, the provider cache `app.providers.yf._CACHE` (counted by the census at the end of 200 symbols served):
9,249 entries, **193 MB of frame buffers** held once each (price histories and option chains, 3,727 live frames),
about 46 entries and 1 MB of frames a symbol, and lists of analyst rows besides (`actions:`, 282 entries). The count
bound (`CACHE_MAX`, 20,000) is about 430 symbols and 500 MB of frames; entries live up to a day. Phase B growth tracks
the cache: new symbols add entries, and nothing but age or the count removes any. Traced runs (tracemalloc, ten symbols):
live frames stayed at 478 across phase A and rose from 478 to 835 in phase B; the allocations that grew in B are pandas
frame construction (`pandas/core/internals/blocks.py:822`, +13.7 MB) and the provider's row lists (`app/providers/yf.py`
analyst actions, +2.2 MB).

### Reading the result

1. **Measured: the provider cache holds memory by count, not by size, and it grows with every new symbol served.** In
   the image, resident memory rose 60 MB a cycle over new symbols (59.8 MB mean across B, run 2) while the cache's
   entries rose from 2,579 (end of A) to 7,635 (end of B) in the Mac run 1 census. With the cache capped (below), the same walk settles 150 MB lower.
2. **Measured: the allocator adds to it on the host's allocator and not on the Mac's.** Over eight identical cycles the
   same symbols took resident memory in the image from 458 to 579 MB (+121 MB) and on the Mac from 377 to 388 MB (+11 MB);
   live frames did not change in the traced run. `MALLOC_ARENA_MAX=2` took the image's phase A to 396 to 429 MB and the
   settled figure from 740 to 629 MB (about 110 MB) and from 798 to 510 MB with the cache cap (the pair below).
   `malloc_trim` gave back 45 to 134 MB, so part of what the image holds is free memory the allocator has not returned.
   Switching pymalloc off made it worse (807 MB).
3. **Inferred, not shown by a run: that it is glibc's per-thread arenas.** The runs show a lower figure with two arenas
   and none with one, on a process of about 70 threads (the two pools, uvicorn's workers, the lanes); they do not
   show arena fragmentation directly. The `malloc_info` of the process on the host would.
4. **Not established:** curl_cffi's own buffers (the synthetic source fetches nothing, so the network path is not
   exercised); the soak clears or implicates everything above it. Mac resident memory is a lower bound, since macOS
   compresses idle pages and `ps` does not count them (the Mac's growth over boot is under half the image's for the same
   cache). The soak's 1 MB a symbol is for synthetic data of the sizes above; real statements and chains can be larger.

### The fix, and the two settings

- **Applied (`app/providers/yf.py`):** a ceiling by size on `_CACHE`, `YF_CACHE_MAX_MB`, 100 by default: past it the oldest
  stored entries holding frames (and lists of rows, at 480 bytes a row) go first, a frame held under two keys counting
  once. Before and after, image, same walk (40 symbols, 2 identical cycles, 4 fresh), settled after the idle wait:

  | | Settled | After `malloc_trim` | Cache entries | Frames held |
  | --- | --- | --- | --- | --- |
  | Before | 798 | 753 | 9,249 | 193.5 MB |
  | After, 200 MB | 783 | 696 | 7,036 | 122.5 MB |
  | After, 100 MB (the default) | 648 | 562 | 5,074 | 58.1 MB |
  | After, 100 MB and `MALLOC_ARENA_MAX=2` | 510 | 496 | 5,145 | 60.6 MB |

  200 MB, the first choice, did little at 200 symbols, because the cache held 193 MB; 100 MB took the default. The cost
  is a refetch of a symbol evicted and read again. Cycle times in these runs are set by the walk's waits and by four
  runs sharing the machine, so they do not show that cost. The "After, 100 MB" run set `YF_CACHE_MAX_MB=100` in the
  environment, which is the new default.
- **Proposed, not applied (`Dockerfile` is the integrator's):** `ENV MALLOC_ARENA_MAX=2`, which is worth 110 to 140 MB in
  these runs. Measure it on the host after the deploy before keeping it: it can slow allocation-heavy threads.
- **Left alone:** the census's "MB (unique)" columns in the earlier reports are deep estimates that count a frame's
  Python overhead twice in places and a text cell at its full size; they are not used above. The frame-buffer figures and
  resident memory are.

### With real feeds: what the host held (2026-11-28)

The soak above uses a synthetic source and found about 1 MB a symbol. The host, walked from outside (Home plus the ten
per-symbol reads of `memprobe.PER_SYMBOL` for three new sets of 40 real symbols, then the first set again, eight at a
time), held about 22 MB a symbol: 940 MB at the start, 1,841, 2,820 and 3,618 MB after the sets, 3,628 MB on the
repeat, flat on repeat. `python -m tests.support.soak.real sets --out DIR` runs the same walk against a local server
with the real feeds (network; by hand, never from a test) and the census hooks loaded; `real endpoints` walks one kind
of read at a time over fresh symbols.

- **Measured: the cause is `app.feeds._MEM`, not the provider cache.** After the four sets the census found 403 entries in
  `_MEM` holding 2,314 MB of a 2,497 MB process (image, the deployed code: 3,278 MB). Each `sec:facts:<CIK>` entry, EDGAR's
  companyfacts for one filer, is 5 MB of JSON and 25 to 38 MB parsed; about 100 of them were held. `_MEM` had no ceiling
  and the disk cache's sixty entries are held parsed too; `tracemalloc` attributes the bytes to `json/decoder.py` called
  from `app/analytics/sec_facts.py` through `app/valuation/inputs.py` (98 MB after one or two symbols). By kind of read, over
  eight fresh symbols each: `/api/figures` (+485 MB) and `/api/ticker` (+650 MB, which reads the filings) account for it; the
  quote, daily-bars, news, session, earnings, symbol-check and sparklines reads move memory by under 70 MB each.
- **Measured: the provider cache's ceiling was working and was not the problem.** The frames it holds were 97 to 100 MB with
  real data, counted the same shallow and deep (object columns and nested dicts add under 1 MB); it holds about 120 MB of
  other objects besides (entries by prefix: none above 12 MB), which its ceiling does not count.
- **Fix (`app/feeds.py`):** a JSON document of 512 KB or more (`FEED_BIG_BYTES`) is written as a gzip file in
  `feed_big/` beside the disk cache and parsed on demand into a cache of four (`FEED_PARSED_MAX`), not stored in `_MEM` or
  the disk cache's dict; an older disk cache's large entries are moved out when it is read (a restart no longer reads
  gigabytes back); `_MEM` is capped at 300 entries (`FEED_MEM_MAX`), the oldest fetched going first.
- **Before and after, same walk** (resident MB after each set; set 4 is set 1 again):

  | | Set 1 | Set 2 | Set 3 | Set 4 (repeat) | `_MEM` after |
  | --- | --- | --- | --- | --- | --- |
  | Host, c95f3be (as reported) | 1,841 | 2,820 | 3,618 | 3,628 | |
  | Image, c95f3be, `MALLOC_ARENA_MAX=2` | 1,470 | 2,424 | 3,272 | 3,278 | 402 entries, 2,314 MB |
  | Image, this fix | 726 | 882 | 944 | 967 | 277 entries, 130 MB |
  | Local (macOS), before | 1,547 | 2,162 | 2,708 | 2,497 | 403 entries, 2,314 MB |
  | Local (macOS), this fix | 795 | 883 | 1,020 | 1,036 | 277 entries, 130 MB |

  What remains (about 600 MB over the start) is the provider cache at its ceiling (about 220 MB), the entries of `_MEM`
  (130 MB), the valuation cache (24 MB), and allocator slack; it stopped growing by the third set. Reports are in
  `Conjure/customers/optic/audit-response-2026-11-27/evidence/memory-real/`.
- **Not established:** whether the host's per-set figures differ from the image's (940 MB at the start there, 327 MB in
  the image) because of the evaluator's own state; the walk's order and symbols were the host's.

## How it is checked

- `tests/test_pass3_memory.py`: the app in a subprocess, 200 mixed requests, open files within 60 of boot and
  resident memory within 150 MB of boot (the code before the fix failed it at 225 more open files).
- `tests/test_pass3_caches.py`: each cache evicts by size and by age; yfinance's caches are Optic's; the Anthropic
  client is shared per configuration and per loop.
- `tests/test_audit_memory_cache_ceiling.py`: the provider cache drops its oldest frames past `YF_CACHE_MAX_MB`, counts a
  shared frame once, and counts a batch and a list of rows.
- `tests/test_audit_memory_feeds_big.py`: a large feed document is kept as a file and parsed on demand, a second read does
  not fetch again, an older disk cache's large entry is moved out, `_MEM` has a ceiling.
- `tests/test_audit_memory_soak.py`: a small soak runs, writes its report, names the provider cache, and phase A does not
  grow between its last two cycles by more than a stated band.
- On a deployment: open files and resident memory from inside the container (`ls /proc/1/fd | wc -l`, `VmRSS` in
  `/proc/1/status`, or the process uvicorn runs as) at boot, after a walk, and after a soak.

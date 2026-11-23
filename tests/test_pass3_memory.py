"""Open files and resident memory stay within a band of boot after 200 mixed requests (round three, 2026-11-23).

The app runs under uvicorn in a subprocess on a fresh data directory, feeds refused at the closed port (as in every
journey); 200 requests from tests/support/memprobe.py `quick_paths` (pages and their files, the reads every screen
makes, and one in ten a per-symbol price read), eight at a time; then 15 seconds for the reads those started.

Measured on the ops Mac, 2026-11-23, this mix (docs/operations/memory-and-open-files.md):

| Code | Boot | After 200 | After 400 |
| --- | --- | --- | --- |
| Before the fix (92dbcca plus the round-three migrations) | 25 fds, 312 MB | 257 fds, 311 MB | 264 fds, 315 MB |
| After | 11 fds, 310 MB | 37 fds, 306 MB | 80 fds, 309 MB |

The band: at most 60 more open files than at boot (the old code was 232 more), and at most 150 MB more resident
memory. What remains of the open files is curl_cffi's (libcurl): one pipe pair per live thread per session, released
when the thread ends, so it is bounded by the app's fixed thread pools. Memory does not climb in this run because
every feed is refused, so no price history is cached; the bounded caches (tests/test_pass3_caches.py) are what keep a
run with real data from holding every symbol it has served, and the evaluation copy's figures are the measure there.
"""

import os
import sys

import pytest

from tests.support.memprobe import Server

FD_BAND = 60
RSS_BAND_KB = 150 * 1024

pytestmark = pytest.mark.skipif(sys.platform not in ("darwin", "linux"), reason="counts open files with lsof or /proc")


def test_open_files_and_memory_after_200_mixed_requests_stay_within_the_band_of_boot(tmp_path):
    server = Server(tmp_path)
    try:
        boot_fds, boot_rss = server.settle(2.0)
        codes = server.load(200, quick=True)
        fds, rss = server.settle(15.0)
    finally:
        server.stop()
    assert sum(codes.values()) == 200 and codes.get(500, 0) == 0, codes
    assert fds - boot_fds <= FD_BAND, "open files {} at boot, {} after 200 requests".format(boot_fds, fds)
    assert rss - boot_rss <= RSS_BAND_KB, "resident {} KiB at boot, {} KiB after".format(boot_rss, rss)


def test_the_probe_counts_this_process():
    from tests.support.memprobe import fds_and_rss
    fds, rss = fds_and_rss(os.getpid())
    assert fds > 2 and rss > 1024

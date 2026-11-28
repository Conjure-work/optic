"""The memory soak tool stays alive (audit round, package E, 2026-11-27).

A small run of tests/support/soak/run.py: two symbols, three identical cycles, one fresh cycle, tracing on (one frame
deep, so the server starts quickly). It asserts that the tool runs, writes its report, names the provider cache in its
cache table, and that phase A's last two cycles differ by less than a stated band. It is not the measurement: the
measurement is `python -m tests.support.soak.run --symbols 40 --cycles 12 --fresh 3 --out DIR`
(docs/operations/memory-and-open-files.md).
"""
import json
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform not in ("darwin", "linux"), reason="counts memory with /proc or ps")

# Two symbols, identical cycles: whatever the first cycle cached is cached; a tool or an app that grows by more than
# this between cycles 2 and 3 is leaking in this small a walk (measured on the ops Mac: a few MB either way).
BAND_KB = 80 * 1024


def test_a_small_soak_runs_writes_its_report_and_names_the_provider_cache(tmp_path):
    from tests.support.soak import run

    out = tmp_path / "soak"
    run.main(["--symbols", "2", "--cycles", "3", "--fresh", "1", "--idle", "1", "--settle", "1", "--out", str(out),
              "--snapshots", "end", "--env", "SOAK_FRAMES=1"])
    result = json.loads((out / "soak.json").read_text())
    report = (out / "soak.md").read_text()

    assert result["baseline_kb"] > 0 and result["peak_kb"] >= result["baseline_kb"] and result["settled_kb"] > 0
    assert "Baseline" in report and "Peak" in report and "Settled" in report
    assert sum(sum(c.values()) for c in result["codes"].values()) > 0

    snap = result["snapshots"]["end"]
    assert "traced_bytes" in snap, "tracing was asked for and did not run"
    assert any(c["where"] == "app.providers.yf._CACHE" and c["entries"] > 0 for c in snap["caches"])
    assert "app.providers.yf._CACHE" in report
    assert snap["provider_cache"]["entries"] > 0

    a = [m["rss_kb"] for m in result["measures"] if m.get("phase") == "A"]
    assert len(a) == 3
    assert abs(a[2] - a[1]) < BAND_KB, "phase A grew {} KiB between its last two cycles".format(a[2] - a[1])

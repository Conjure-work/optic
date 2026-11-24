"""The GitHub workflow's shards cover the suite exactly once (round three, 2026-11-23).

Files are enumerated from the tests directory, never from a list kept here, so a new file that no shard would run
fails this test rather than going unrun on GitHub."""

import re
from pathlib import Path

import pytest

from tests.support import ci_count, shard_plugin, shards

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "tests.yml").read_text()


def test_the_workflow_matrix_is_the_shard_list():
    m = re.search(r"shard: \[([^\]]+)\]", WORKFLOW)
    assert m, "the suite job has a shard matrix"
    assert [s.strip() for s in m.group(1).split(",")] == shards.names()
    assert "python -m tests.support.shards $SHARD" in WORKFLOW
    assert "python -m tests.support.ci_count total" in WORKFLOW


def test_every_test_file_is_in_exactly_one_shard():
    on_disk = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("tests/**/test_*.py"))
    assert on_disk == sorted(shards.all_test_files()), "a test file outside tests/ and tests/e2e would run nowhere"
    py = set(shards.args("py"))
    e2e = {f for f in on_disk if shards.shard_of(f) == "e2e"}
    assert py.isdisjoint(e2e) and py | e2e == set(on_disk)
    for i in range(1, shards.E2E_SLICES + 1):
        assert shards.args("e2e-{}".format(i))[0] == "tests/e2e"     # every slice collects the whole journey set


@pytest.mark.parametrize("count", [0, 1, 5, 6, 7, 137, 500])
def test_the_journey_slices_partition_the_collection(count):
    n = shards.E2E_SLICES
    picked = [k for i in range(1, n + 1) for k in shard_plugin.pick(count, i, n)]
    assert sorted(picked) == list(range(count))
    sizes = [len(shard_plugin.pick(count, i, n)) for i in range(1, n + 1)]
    assert max(sizes) - min(sizes) <= 1


def test_a_bad_slice_is_refused():
    for bad in ("0/6", "7/6", "1/0"):
        with pytest.raises(ValueError):
            shard_plugin.parse(bad)


def test_the_shard_floors_add_up_to_the_suite_floor():
    floor = int(re.search(r'SUITE_FLOOR: "(\d+)"', WORKFLOW).group(1))
    assert set(shards.SHARD_FLOORS) == set(shards.names())
    assert sum(shards.SHARD_FLOORS.values()) == floor


def _junit(tmp_path, name, tests, failures=0, skipped=(), unnamed_skips=0):
    """A JUnit file in pytest's shape; `skipped` names the skipped tests as (classname, name) pairs."""
    cases = "".join('<testcase classname="{}" name="{}"><skipped message="x"/></testcase>'.format(c, n)
                    for c, n in skipped)
    (tmp_path / "junit-{}.xml".format(name)).write_text(
        '<testsuites><testsuite tests="{}" failures="{}" errors="0" skipped="{}">{}</testsuite></testsuites>'.format(
            tests, failures, len(skipped) + unnamed_skips, cases))


KNOWN = ("tests.test_brokerage_exposure", "test_live_qqq")


def test_the_count_fails_a_missing_shard_a_failure_or_a_total_under_the_floor(tmp_path, monkeypatch):
    def junit(name, tests, failures=0, skipped=()):
        _junit(tmp_path, name, tests, failures, skipped)
    for name in shards.names():
        junit(name, shards.SHARD_FLOORS[name] + (1 if name == "py" else 0), skipped=(KNOWN,) if name == "py" else ())
    monkeypatch.setenv("SUITE_FLOOR", str(sum(shards.SHARD_FLOORS.values())))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert ci_count.total(str(tmp_path)) == 0
    junit("e2e-3", shards.SHARD_FLOORS["e2e-3"], failures=1)
    assert ci_count.total(str(tmp_path)) == 1
    junit("e2e-3", shards.SHARD_FLOORS["e2e-3"])
    (tmp_path / "junit-e2e-6.xml").unlink()
    assert ci_count.total(str(tmp_path)) == 1


def test_the_count_fails_any_skip_but_the_known_one(tmp_path, monkeypatch):
    """Zero skips is the rule (2026-11-24): a test skipped for want of JavaScriptCore used to pass the run."""
    monkeypatch.setenv("SUITE_FLOOR", str(sum(shards.SHARD_FLOORS.values())))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    for name in shards.names():
        _junit(tmp_path, name, shards.SHARD_FLOORS[name] + (1 if name == "py" else 0),
               skipped=(KNOWN,) if name == "py" else ())
    assert ci_count.total(str(tmp_path)) == 0
    assert ci_count.shard("py", str(tmp_path / "junit-py.xml")) == 0
    assert ci_count.skipped_ids(tmp_path / "junit-py.xml") == ["tests/test_brokerage_exposure.py::test_live_qqq"]
    # one more skip, in a journey slice, with the floor still met
    _junit(tmp_path, "e2e-2", shards.SHARD_FLOORS["e2e-2"] + 1, skipped=(("tests.e2e.test_x", "test_y"),))
    assert ci_count.total(str(tmp_path)) == 1
    assert ci_count.shard("e2e-2", str(tmp_path / "junit-e2e-2.xml")) == 1
    # a skip the file counts but does not name
    _junit(tmp_path, "e2e-2", shards.SHARD_FLOORS["e2e-2"] + 1, unnamed_skips=1)
    assert ci_count.total(str(tmp_path)) == 1
    assert ci_count.shard("e2e-2", str(tmp_path / "junit-e2e-2.xml")) == 1

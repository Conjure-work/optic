"""The counts the GitHub workflow publishes (round three, 2026-11-23). Standard library only: the `count` job runs it
on a bare runner.

`python -m tests.support.ci_count shard <name> <junit.xml>`: one shard's line in the run summary; fails if anything
failed or the shard passed fewer than its floor (tests/support/shards.py SHARD_FLOORS).
`python -m tests.support.ci_count total <dir>`: every shard's JUnit file in <dir> added together; fails if a shard's
file is missing, anything failed, or the total passed is below SUITE_FLOOR (the workflow's env).
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict

from tests.support import shards


def counts(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return {"passed": total - failed - skipped, "failed": failed, "skipped": skipped, "total": total}


def line(name: str, c: Dict[str, int]) -> str:
    return "{}: {} passed, {} failed, {} skipped, {} in all".format(
        name, c["passed"], c["failed"], c["skipped"], c["total"])


def _summary(text: str) -> None:
    print(text)
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if out:
        with open(out, "a") as f:
            f.write(text + "\n")


def shard(name: str, path: str) -> int:
    floor = shards.SHARD_FLOORS[name]
    if not Path(path).exists():
        _summary("### {}: no JUnit file; the tests did not run".format(name))
        return 1
    c = counts(Path(path))
    _summary("### {}\n\nFloor: {} passed.".format(line(name, c), floor))
    if c["failed"]:
        return 1
    if c["passed"] < floor:
        print("{} passed is below the floor of {}".format(c["passed"], floor))
        return 1
    return 0


def total(directory: str) -> int:
    floor = int(os.environ["SUITE_FLOOR"])
    sums = {"passed": 0, "failed": 0, "skipped": 0, "total": 0}
    rows, missing = [], []
    for name in shards.names():
        path = Path(directory) / "junit-{}.xml".format(name)
        if not path.exists():
            missing.append(name)
            continue
        c = counts(path)
        rows.append(line(name, c))
        for k in sums:
            sums[k] += c[k]
    text = "### Tests: {} passed, {} failed, {} skipped, {} in all\n\nFloor: {} passed.\n\n{}".format(
        sums["passed"], sums["failed"], sums["skipped"], sums["total"], floor, "\n".join("- " + r for r in rows))
    if missing:
        text += "\n\nShards with no result: " + ", ".join(missing)
    _summary(text)
    if missing or sums["failed"] or sums["passed"] < floor:
        return 1
    return 0


def main(argv) -> int:
    if len(argv) == 3 and argv[0] == "shard":
        return shard(argv[1], argv[2])
    if len(argv) == 2 and argv[0] == "total":
        return total(argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

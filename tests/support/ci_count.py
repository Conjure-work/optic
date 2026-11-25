"""The counts the GitHub workflow publishes (round three, 2026-11-23). Standard library only: the `count` job runs it
on a bare runner.

`python -m tests.support.ci_count shard <name> <junit.xml>`: one shard's line in the run summary; fails if anything
failed, anything skipped other than KNOWN_SKIPS, or the shard passed fewer than its floor (tests/support/shards.py
SHARD_FLOORS).
`python -m tests.support.ci_count total <dir>`: every shard's JUnit file in <dir> added together; fails if a shard's
file is missing, anything failed, anything skipped other than KNOWN_SKIPS, or the total passed is below SUITE_FLOOR
(the workflow's env).

Skips (2026-11-24, with the move to Ubuntu runners): before, a skip was only subtracted from passed, so a test that
skipped for want of JavaScriptCore cost nothing unless it pushed a shard under its floor. The factory rule is zero
skips. Every skipped test is now named in the summary, and any skip not in KNOWN_SKIPS fails the run. The one known
skip is still a skip and is still counted and shown; whether to allow it is the operator's decision, not this file's.
"""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

# Skips the count lets through, by pytest node id. test_live_qqq reads EDGAR and runs only with OPTIC_LIVE_EDGAR=1;
# outbound HTTP is pinned to a closed port in CI, so it cannot run there.
KNOWN_SKIPS = frozenset({"tests/test_brokerage_exposure.py::test_live_qqq"})

from tests.support import shards


def counts(path: Path) -> Dict[str, int]:
    root = ET.parse(str(path)).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    total = sum(int(s.get("tests", 0)) for s in suites)
    failed = sum(int(s.get("failures", 0)) + int(s.get("errors", 0)) for s in suites)
    skipped = sum(int(s.get("skipped", 0)) for s in suites)
    return {"passed": total - failed - skipped, "failed": failed, "skipped": skipped, "total": total}


def _node_id(case: ET.Element) -> str:
    """pytest's JUnit classname is the module path dotted, plus the class for a method: tests.test_x.TestY."""
    parts = (case.get("classname") or "").split(".")
    name = case.get("name") or ""
    mod = []
    for i, part in enumerate(parts):
        mod.append(part)
        if part.startswith("test_") or i == len(parts) - 1:
            rest = parts[i + 1:]
            return "::".join(["/".join(mod) + ".py"] + rest + [name])
    return name


def skipped_ids(path: Path) -> List[str]:
    root = ET.parse(str(path)).getroot()
    return sorted(_node_id(c) for c in root.iter("testcase") if c.find("skipped") is not None)


def unknown_skips(path: Path, c: Dict[str, int]) -> List[str]:
    """Skips not in KNOWN_SKIPS. A skip the file counts but does not name is unknown too."""
    ids = skipped_ids(path)
    bad = [i for i in ids if i not in KNOWN_SKIPS]
    unnamed = c["skipped"] - len(ids)
    if unnamed > 0:
        bad.append("{} skipped test(s) the JUnit file does not name".format(unnamed))
    return bad


def _skip_text(path: Path) -> str:
    ids = skipped_ids(path)
    if not ids:
        return ""
    return "\n\nSkipped:\n" + "\n".join("- {}{}".format(i, " (known skip)" if i in KNOWN_SKIPS else "") for i in ids)


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
    _summary("### {}\n\nFloor: {} passed.{}".format(line(name, c), floor, _skip_text(Path(path))))
    if c["failed"]:
        return 1
    bad = unknown_skips(Path(path), c)
    if bad:
        print("skips outside KNOWN_SKIPS: " + "; ".join(bad))
        return 1
    if c["passed"] < floor:
        print("{} passed is below the floor of {}".format(c["passed"], floor))
        return 1
    return 0


def total(directory: str) -> int:
    floor = int(os.environ["SUITE_FLOOR"])
    sums = {"passed": 0, "failed": 0, "skipped": 0, "total": 0}
    rows, missing, bad, skips = [], [], [], []
    for name in shards.names():
        path = Path(directory) / "junit-{}.xml".format(name)
        if not path.exists():
            missing.append(name)
            continue
        c = counts(path)
        rows.append(line(name, c))
        bad += unknown_skips(path, c)
        skips += skipped_ids(path)
        for k in sums:
            sums[k] += c[k]
    text = "### Tests: {} passed, {} failed, {} skipped, {} in all\n\nFloor: {} passed.\n\n{}".format(
        sums["passed"], sums["failed"], sums["skipped"], sums["total"], floor, "\n".join("- " + r for r in rows))
    if missing:
        text += "\n\nShards with no result: " + ", ".join(missing)
    if skips:
        text += "\n\nSkipped:\n" + "\n".join(
            "- {}{}".format(i, " (known skip)" if i in KNOWN_SKIPS else "") for i in sorted(skips))
    if bad:
        text += "\n\nSkips outside KNOWN_SKIPS (these fail the run): " + "; ".join(bad)
    _summary(text)
    if missing or bad or sums["failed"] or sums["passed"] < floor:
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

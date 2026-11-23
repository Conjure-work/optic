"""How the GitHub workflow splits the suite into parallel jobs (round three, 2026-11-23).

As one job the suite took about 33 minutes from clean on a fast Mac and timed out at 40 on GitHub's shared macOS
runner. Measured per file on the clean run of 2026-11-23 (JUnit times, 2,093 s in all): the Python files took 284 s
together, the browser journeys 1,809 s, of which one file, tests/e2e/test_pass1_journeys.py, took 1,112 s. So the
split is by test, not only by file:

- `py`: every Python file outside tests/e2e, one job (about five minutes on the Mac).
- `e2e-1` to `e2e-6`: the browser journeys, dealt round-robin in collection order, so every journey is in exactly one
  slice, a slow file is spread across all six, and a journey added later lands in a slice with no change here. Each
  journey starts its own server and browser (tests/e2e/conftest.py), so a slice needs nothing from another.

The slicing is done by `tests/support/shard_plugin.py` (`-p tests.support.shard_plugin --slice i/n`).
`tests/test_ci_shards.py` checks that the workflow's matrix is this list, that every test file is in exactly one
shard, that the slices partition the journeys, and that SHARD_FLOORS add up to the workflow's SUITE_FLOOR.

`python -m tests.support.shards <name>` prints the pytest arguments for a shard; `--names` the shard names;
`--floors` the count each shard collects now (to set SHARD_FLOORS from a green run).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"

# Ten, not six (2026-11-23): on the GitHub macOS runner a journey takes about twice as long as on the ops Mac, and six
# slices of 37 ran past 20 minutes each
E2E_SLICES = 10

# Each shard's floor: what it passed when the floors were last set (the one standing skip, test_live_qqq, is in py).
# The workflow's SUITE_FLOOR is their sum.
SHARD_FLOORS: Dict[str, int] = {
    "py": 9384,
    "e2e-1": 23, "e2e-2": 22, "e2e-3": 22, "e2e-4": 22, "e2e-5": 22, "e2e-6": 22, "e2e-7": 22, "e2e-8": 22,
    "e2e-9": 22, "e2e-10": 22,
}


def names() -> List[str]:
    return ["py"] + ["e2e-{}".format(i) for i in range(1, E2E_SLICES + 1)]


def all_test_files() -> List[str]:
    found = sorted(TESTS.glob("test_*.py")) + sorted((TESTS / "e2e").glob("test_*.py"))
    return [str(p.relative_to(ROOT)) for p in found]


def shard_of(path: str) -> str:
    """The shard a test file runs in: `py`, or `e2e` for the journeys (dealt across the e2e slices by test)."""
    return "e2e" if Path(path).parent.name == "e2e" else "py"


def args(shard: str) -> List[str]:
    if shard not in names():
        raise SystemExit("no shard named {!r}; the shards are {}".format(shard, ", ".join(names())))
    if shard == "py":
        return [f for f in all_test_files() if shard_of(f) == "py"]
    i = int(shard.split("-")[1])
    return ["tests/e2e", "-p", "tests.support.shard_plugin", "--slice", "{}/{}".format(i, E2E_SLICES)]


def collected(shard: str) -> int:
    out = subprocess.run([sys.executable, "-m", "pytest", "-q", "--collect-only", "-p", "no:cacheprovider"]
                         + args(shard), cwd=str(ROOT), capture_output=True, text=True).stdout
    return sum(1 for line in out.splitlines() if "::" in line)


def main(argv: List[str]) -> None:
    if argv[:1] == ["--names"]:
        print("\n".join(names()))
        return
    if argv[:1] == ["--floors"]:
        counts = {s: collected(s) for s in names()}
        print(counts, "sum", sum(counts.values()))
        return
    if len(argv) != 1:
        raise SystemExit("usage: python -m tests.support.shards <shard> | --names | --floors")
    print(" ".join(args(argv[0])))


if __name__ == "__main__":
    main(sys.argv[1:])

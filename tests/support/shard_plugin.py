"""`--slice i/n`: keep every n-th collected test starting at the i-th, deselect the rest (round three, 2026-11-23).

Loaded only by the GitHub workflow's journey shards (`-p tests.support.shard_plugin`), never by a plain
`python -m pytest`. Round-robin over the collection order, which pytest makes stable (files sorted, tests in file
order), so the n slices partition the collection exactly and a slow file is shared out across all of them.
"""

from __future__ import annotations

from typing import List, Tuple


def pytest_addoption(parser):
    parser.addoption("--slice", default=None, help="i/n: run the i-th of n round-robin slices of the collected tests")


def parse(value: str) -> Tuple[int, int]:
    i, n = (int(x) for x in value.split("/"))
    if not (n >= 1 and 1 <= i <= n):
        raise ValueError("--slice wants i/n with 1 <= i <= n, got {}".format(value))
    return i, n


def pick(count: int, i: int, n: int) -> List[int]:
    return [k for k in range(count) if k % n == i - 1]


def pytest_collection_modifyitems(config, items):
    value = config.getoption("--slice")
    if not value:
        return
    i, n = parse(value)
    keep = set(pick(len(items), i, n))
    kept = [it for k, it in enumerate(items) if k in keep]
    dropped = [it for k, it in enumerate(items) if k not in keep]
    if dropped:
        config.hook.pytest_deselected(items=dropped)
    items[:] = kept

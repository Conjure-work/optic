"""The modes round three adds to /api/health, registered by the module that owns each one.

Why a registry: billing, the legal text, alert delivery, the chart feed's history limit and Milo's off-topic set are
owned by five different modules, and /api/health is one function in main.py. Each owner registers a reader here at
import time, so a mode is reported by the code that decides it and main.py stays one line. The owner Metrics page reads
the same snapshot, so the two never disagree.

A reader returns a small JSON-safe dict. It must never return a credential, a key's value or an address: names of
missing variables are fine, their values never. A reader that raises is reported as {"error": "unavailable"} rather
than taking /api/health down with it.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Tuple

log = logging.getLogger(__name__)

_READERS: Dict[str, Tuple[Callable[[], Dict[str, Any]], bool]] = {}


def register(name: str, reader: Callable[[], Dict[str, Any]], public: bool = True) -> None:
    """Report `reader()` under `name` on /api/health; `public=False` shows it to the operator only."""
    _READERS[name] = (reader, public)


def snapshot(operator: bool = False) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, (reader, public) in sorted(_READERS.items()):
        if not public and not operator:
            continue
        try:
            out[name] = reader()
        except Exception:  # a broken reader must not take the health endpoint down
            log.exception("health reader %s failed", name)
            out[name] = {"error": "unavailable"}
    return out

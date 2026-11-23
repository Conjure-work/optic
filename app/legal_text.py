"""Terms of use and the privacy policy from two files in the repository (round three, 2026-11-23).

`legal/terms.md` and `legal/privacy.md` hold the owner's counsel's text, written as plain Markdown, and the pages at
#/terms and #/privacy render whatever they say. Until counsel's text is in them each file carries the placeholder
marker (`optic-legal: placeholder`), and then:

- the pages show one line, "being prepared with counsel", above the draft already published on Oct 19, 2026 (kept in
  static/v2/js/pages/legalpages.js; nothing that was public is taken down);
- /api/health and the owner's Metrics page say "legal text: placeholder";
- Checkout is refused with CHECKOUT_REFUSAL (app/billing.py), so nobody pays under terms that are not final.

Removing the marker line and writing counsel's text into a file is the whole switch: no setting, no code change. A
missing or empty file counts as the placeholder, never as final text.
"""

from __future__ import annotations

import os
from typing import Any, Dict

from fastapi import APIRouter

from . import health_extra

MARKER = "optic-legal: placeholder"
DOCS = ("terms", "privacy")
PENDING = "Optic's terms of use and privacy policy are being prepared with counsel."
CHECKOUT_REFUSAL = PENDING + " Plans can be bought once they are published here."
MAX_BYTES = 200_000

router = APIRouter(prefix="/api/legal-text", tags=["legal"])


def _dir() -> str:
    return os.environ.get("LEGAL_TEXT_DIR") or os.path.join(os.path.dirname(os.path.dirname(__file__)), "legal")


def read(doc: str) -> Dict[str, Any]:
    """{"state": "counsel" | "placeholder", "markdown": text or None} for one document."""
    if doc not in DOCS:
        raise ValueError(doc)
    try:
        with open(os.path.join(_dir(), doc + ".md"), encoding="utf-8") as fh:
            text = fh.read(MAX_BYTES)
    except OSError:
        text = ""
    if not text.strip() or MARKER in text:
        return {"state": "placeholder", "markdown": None}
    return {"state": "counsel", "markdown": text}


def placeholder() -> bool:
    """True while either document is still the placeholder."""
    return any(read(d)["state"] == "placeholder" for d in DOCS)


def health() -> Dict[str, Any]:
    states = {d: read(d)["state"] for d in DOCS}
    return {"state": "placeholder" if "placeholder" in states.values() else "counsel", **states}


@router.get("/{doc}")
async def legal_text(doc: str) -> Dict[str, Any]:
    if doc not in DOCS:
        return {"state": "unknown", "markdown": None, "pending": PENDING}
    out = read(doc)
    out["pending"] = PENDING if out["state"] == "placeholder" else None
    return out


health_extra.register("legal_text", health)

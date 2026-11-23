"""Round three routes (Pass 3, 2026-11-23). Kept out of main.py so the round's work lands in its own module.

Milo's stance: the persona an answer is written in, named in plain words (app/ai.py STANCE_LABELS). A signed-in
reader's kept stance is on the account (user_preferences.milo_stance); a guest's stays in the browser. Reading the
list is open; writing needs the reader's own session and the CSRF check, and writes only that reader's row.
"""

from typing import Any, Dict

from fastapi import APIRouter, Body, HTTPException, Request

from . import ai, ai_policy, health_extra
from .auth import deps, store

router = APIRouter()

# The size of the off-topic set the shipped patterns were held to in the suite (tests/milo_eval/offtopic.py; a test
# asserts this equals the set's length and that every case was refused). Reported on /api/health so a deploy says
# which set its refusals passed.
OFFTOPIC_SET_SIZE = 24


def _stances() -> list:
    return [{"id": k, "name": ai.PERSONAS[k]["label"], "label": ai.STANCE_LABELS[k]} for k in ai.STANCE_LABELS]


@router.get("/api/milo/stance")
async def get_stance(request: Request) -> Dict[str, Any]:
    """The stances, and the reader's kept one: on the account when signed in, else none (the browser keeps it)."""
    user = deps.current_user(request)
    kept = store.round_three_preferences(user["id"])["milo_stance"] if user else None
    return {"stances": _stances(), "kept": ai.stance_of(kept) if kept else None,
            "kept_on": "account" if user else "browser"}


@router.put("/api/milo/stance")
async def put_stance(request: Request, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    user = deps.require_user(request)
    deps.csrf_guard(request)
    stance = payload.get("stance")
    if stance not in ai.STANCE_LABELS:
        raise HTTPException(status_code=400, detail="That is not one of Milo's stances.")
    got = store.set_round_three_preferences(user["id"], {"milo_stance": stance})
    return {"kept": ai.stance_of(got["milo_stance"]), "kept_on": "account"}


health_extra.register("milo_offtopic", lambda: {"version": ai_policy.OFFTOPIC_VERSION,
                                                "kinds": list(ai_policy.OFFTOPIC_KINDS),
                                                "set_cases_refused_in_suite": OFFTOPIC_SET_SIZE})

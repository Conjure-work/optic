"""Round three routes (Pass 3, 2026-11-23): Investor mode. Kept out of main.py so the round's work lands in its own
module. The logic is app/investor.py; these are the doors, each with its auth decision:

* GET  /api/markets/calendar            open, as every research route (CLAUDE.md: nothing gates the terminal)
* GET  /api/admin/owner-report          the owner only, the same guard as Metrics (no user 401, others 403)
* GET  /api/account/level-questions     a signed-in reader (401 without), whether to offer and the questions
* POST /api/account/level-questions/... a signed-in reader with the CSRF header
* POST /api/portfolio-risk/positions    open: a browser-kept book's diversification, nothing stored
"""

import asyncio
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from . import investor
from .auth import admin as auth_admin
from .auth import deps as auth_deps

router = APIRouter()


def _owner_only(request: Request) -> None:
    """The guard Metrics uses (main._owner_session_guard), restated so this module does not import main."""
    refusal = HTTPException(status_code=403, detail="This page is for the owner of this site.")
    if not auth_admin.configured():
        raise refusal
    try:
        user = auth_deps.current_user(request)
    except (sqlite3.Error, OSError):
        raise HTTPException(status_code=503, detail="The accounts database is unavailable.")
    if not user:
        raise HTTPException(status_code=401, detail="Sign in with the owner's account to see this page.")
    if not auth_admin.is_admin(user):
        raise refusal
    auth_deps.csrf_guard(request)


@router.get("/api/markets/calendar")
async def markets_calendar(days: int = Query(14, ge=1, le=60)) -> Dict[str, Any]:
    """The sessions ahead (holidays and early closes from app/session.py) and the scheduled releases (app/events.py,
    best effort: a calendar that cannot be fetched is named, never silently dropped). Earnings come from
    /api/earnings-week, which the page asks itself."""
    from . import events as events_mod
    from . import session as session_mod
    today = session_mod.market_today()
    out: Dict[str, Any] = {"days": investor.session_days(today, days), "futures_note": investor.FUTURES_NOTE,
                           "time_zone_of_record": "America/New_York"}
    try:
        data = await asyncio.wait_for(run_in_threadpool(events_mod.upcoming), timeout=20)
        out["releases"] = {"available": True, "events": (data or {}).get("events") or []}
    except Exception:                                             # noqa: BLE001 - named on the page
        out["releases"] = {"available": False, "events": [],
                           "reason": "The economic release calendar could not be read just now."}
    out["generated_at"] = datetime.now(timezone.utc).isoformat()
    return out


@router.get("/api/admin/owner-report")
async def owner_report(request: Request, owner_kind: Optional[str] = Query(None), owner_id: Optional[str] = Query(None),
                       weeks: int = Query(12, ge=1, le=52)) -> JSONResponse:
    _owner_only(request)
    group, problem = investor.clean_group(owner_kind, owner_id)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    out = await run_in_threadpool(investor.owner_report, None, weeks, group)
    return JSONResponse(content=out, headers={"Cache-Control": "no-store"})


def _reader(request: Request) -> Dict[str, Any]:
    return auth_deps.require_user(request)


@router.get("/api/account/level-questions")
async def level_questions(request: Request) -> Dict[str, Any]:
    user = _reader(request)
    return {"offer": investor.offer_questions(user["id"]), "questions": investor.public_questions(),
            "state": investor.quiz_state(user["id"]) or None}


@router.post("/api/account/level-questions/shown")
async def level_questions_shown(request: Request) -> Dict[str, Any]:
    user = _reader(request)
    auth_deps.csrf_guard(request)
    return {"level_quiz": investor.mark_shown(user["id"])}


@router.post("/api/account/level-questions/suggest")
async def level_questions_suggest(request: Request, payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """Scores the answers and forgets them: nothing in the body is written anywhere."""
    _reader(request)
    auth_deps.csrf_guard(request)
    answers = payload.get("answers") if isinstance(payload, dict) else None
    return investor.suggest(answers if isinstance(answers, dict) else {})


@router.post("/api/account/level-questions/decide")
async def level_questions_decide(request: Request, payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    user = _reader(request)
    auth_deps.csrf_guard(request)
    try:
        return investor.decide(user["id"], str(payload.get("outcome") or ""), payload.get("suggested"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Choose to use the suggested level, or skip.")


@router.post("/api/portfolio-risk/positions")
async def portfolio_risk_positions(payload: Dict[str, Any] = Body(default={})) -> Dict[str, Any]:
    """The diversification read for positions the page sends (the Paper Desk lives in the browser). Nothing stored."""
    from . import main as main_mod
    from .analytics import portfolio_risk as portfolio_risk_mod
    positions = investor.positions_from_body((payload or {}).get("positions"))
    if not positions:
        return {"available": False, "reason": "No open positions to analyse."}
    def build() -> Dict[str, Any]:
        out = portfolio_risk_mod.build(main_mod.YF_PROVIDER, positions)
        out["generated_at"] = datetime.now(timezone.utc).isoformat()
        return out
    try:
        return await asyncio.wait_for(run_in_threadpool(build), timeout=60)
    except Exception:                                             # noqa: BLE001 - a reader's sentence, not a trace
        return {"available": False, "reason": "Price history is unavailable just now, so the book's diversification "
                                              "could not be measured."}

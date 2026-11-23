"""Round three's chart routes (Pass 3, 2026-11-23): chart layouts on the account, favourite intervals, and the free
feed's history limit.

Chart layouts. One, two or four charts on the chart page, each slot its own symbol, timeframe (bar size) and range. A
guest's layout stays in the browser (`optic.v2.chart.layout.v1`); a signed-in reader can name one and keep it on the
account, at most 20, private to that reader. The page sends the slots; this module checks their shape and never
interprets them beyond that.

Favourite intervals. The bar sizes a reader keeps in a row above each chart, kept in the browser
(`optic.v2.chart.intervals.v1`) and mirrored to the account on sign-in the way the level is. Stored through
`store.set_round_three_preferences`, which drops anything that is not an interval.

History limit. "History back to the IPO" is the free feed's daily history (`/api/daily-bars`, period=max). Two
things limit it and the chart says both when they apply: the first bar can be later than the listing, and the prices
are split-adjusted, so an old close is not the price printed that day. `history_limit` builds that sentence from the
bars themselves, so the page never claims more history than it drew.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Request

from . import db, health_extra
from .auth import deps, store

router = APIRouter(tags=["charts"])

MAX_LAYOUTS = 20
COUNTS = (1, 2, 4)
NAME = re.compile(r"^[A-Za-z0-9 &'.,:()/\-]{1,40}$")
SYMBOL = re.compile(r"^[A-Z0-9.^=\-]{1,12}$")
# the chart page's bar sizes (static/v2/js/pages/chart.js INTERVALS) and ranges (RANGES)
INTERVAL_KEYS = ("1", "5", "15", "30", "60", "240", "daily", "weekly")
RANGE_KEYS = ("1M", "3M", "6M", "1Y", "All")
# the same bar sizes as the reader's favourites are named (store._INTERVAL): 5m, 1h, 1d, 1wk
FAVOURITE_NAMES = {"1": "1m", "5": "5m", "15": "15m", "30": "30m", "60": "1h", "240": "4h", "daily": "1d", "weekly": "1wk"}
SOURCE = "Yahoo Finance's free daily history"


def _name(raw: Any) -> str:
    name = re.sub(r"\s+", " ", str(raw or "")).strip()
    if not NAME.match(name):
        raise HTTPException(status_code=400, detail="A layout's name is 1 to 40 letters, numbers, spaces or simple punctuation.")
    return name


def check_layout(body: Any) -> Dict[str, Any]:
    """{count: 1|2|4, slots: [{symbol, interval, range}]}, one slot per chart. Anything else is refused."""
    if not isinstance(body, dict) or body.get("count") not in COUNTS or not isinstance(body.get("slots"), list):
        raise HTTPException(status_code=400, detail="A chart layout is one, two or four charts.")
    slots = []
    for s in body["slots"][:body["count"]]:
        if not isinstance(s, dict) or not SYMBOL.match(str(s.get("symbol") or "").upper()):
            raise HTTPException(status_code=400, detail="Each chart in the layout needs a ticker.")
        interval = s.get("interval") if s.get("interval") in INTERVAL_KEYS else "daily"
        rng = s.get("range") if s.get("range") in RANGE_KEYS else "6M"
        slots.append({"symbol": str(s["symbol"]).upper(), "interval": interval, "range": rng})
    if len(slots) != body["count"]:
        raise HTTPException(status_code=400, detail="The layout names {} charts and describes {}.".format(body["count"], len(slots)))
    return {"count": body["count"], "slots": slots}


def _out(r: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": r["name"], "count": r["count"], "slots": json.loads(r["slots"]), "updated_at": r["updated_at"]}


def mine(user_id: str) -> List[Dict[str, Any]]:
    return [_out(r) for r in db.rows("SELECT * FROM chart_layouts WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))]


@router.get("/api/chart/layouts")
async def list_chart_layouts(request: Request) -> Dict[str, Any]:
    user = deps.require_user(request)
    return {"layouts": mine(user["id"]), "max": MAX_LAYOUTS}


@router.put("/api/chart/layouts/{name}")
async def save_chart_layout(name: str, request: Request, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    user = deps.require_user(request)
    deps.csrf_guard(request)
    name = _name(name)
    body = check_layout(payload.get("layout"))
    now = db.utcnow()
    have = db.row("SELECT id FROM chart_layouts WHERE user_id = ? AND name = ?", (user["id"], name))
    if have:
        db.execute("UPDATE chart_layouts SET count = ?, slots = ?, updated_at = ? WHERE id = ?",
                   (body["count"], json.dumps(body["slots"]), now, have["id"]))
    else:
        n = (db.row("SELECT COUNT(*) AS n FROM chart_layouts WHERE user_id = ?", (user["id"],)) or {}).get("n", 0)
        if n >= MAX_LAYOUTS:
            raise HTTPException(status_code=409, detail="You have {} saved chart layouts, the most an account keeps. Delete one to save another.".format(MAX_LAYOUTS))
        db.execute("INSERT INTO chart_layouts (id, user_id, name, count, slots, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                   (db.new_id(), user["id"], name, body["count"], json.dumps(body["slots"]), now, now))
    return {"saved": True, "name": name, "replaced": bool(have), "layouts": mine(user["id"])}


@router.delete("/api/chart/layouts/{name}")
async def delete_chart_layout(name: str, request: Request) -> Dict[str, Any]:
    user = deps.require_user(request)
    deps.csrf_guard(request)
    gone = db.execute("DELETE FROM chart_layouts WHERE user_id = ? AND name = ?", (user["id"], _name(name)))
    if not gone:
        raise HTTPException(status_code=404, detail="No saved chart layout by that name.")
    return {"deleted": True, "layouts": mine(user["id"])}


@router.get("/api/chart/intervals")
async def get_intervals(request: Request) -> Dict[str, Any]:
    user = deps.require_user(request)
    return {"intervals": store.round_three_preferences(user["id"])["favourite_intervals"]}


@router.put("/api/chart/intervals")
async def put_intervals(request: Request, payload: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    user = deps.require_user(request)
    deps.csrf_guard(request)
    want = payload.get("intervals")
    if not isinstance(want, list) or not all(isinstance(x, str) and x in FAVOURITE_NAMES.values() for x in want):
        raise HTTPException(status_code=400, detail="Favourite intervals are bar sizes the chart offers, such as 5m, 1h or 1d.")
    return {"intervals": store.set_round_three_preferences(user["id"], {"favourite_intervals": want})["favourite_intervals"]}


# ------------------------------------------------------------------ the history limit

def _day(iso: str) -> str:
    """A date as the page writes it: Jan 2, 2025."""
    try:
        d = date.fromisoformat(str(iso)[:10])
    except ValueError:
        return str(iso)
    return "{} {}, {}".format(d.strftime("%b"), d.day, d.year)


def history_limit(symbol: str, dates: List[str], listed: Optional[str] = None, adjusted: str = "split") -> Dict[str, Any]:
    """What the chart can say about how far back its daily bars go, from the bars it drew.

    `listed` is the listing date when the feed gives one (YYYY-MM-DD); `adjusted` names the adjustment the feed applies
    ("split" for Yahoo's history as Optic reads it: splits applied, dividends not added back). The sentence is shown
    under the chart whenever it is not empty."""
    first = dates[0] if dates else None
    later = bool(first and listed and first > listed)
    parts = []
    if first:
        parts.append("{}'s history here starts on {}, the first daily bar in {}.".format(symbol, _day(first), SOURCE))
    if later:
        parts.append("{} listed on {}, so the bars before {} are not in the free feed.".format(symbol, _day(listed), _day(first)))
    if adjusted == "split":
        parts.append("Prices are split-adjusted, so an old close is not the price printed that day; dividends are not added back.")
    return {"first_bar": first, "listed": listed, "later_than_listing": later, "adjusted": adjusted,
            "source": SOURCE, "sentence": " ".join(parts) if first else ""}


def _health() -> Dict[str, Any]:
    return {"source": SOURCE, "period": "max", "adjusted": "split",
            "limit": "the free feed's first daily bar, which can be later than the listing; prices split-adjusted"}


health_extra.register("chart_history", _health)

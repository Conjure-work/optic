"""Round three's Investor mode, the server half (Pass 3, 2026-11-23).

Five things live here, each small, each read by one page:

* the market calendar's sessions: every day in a window, open, a full closure or a 1:00 pm close, from the rules
  app/session.py already models (futures holidays are not modelled, and the page says so);
* the owner report: what people open, which level they use and the three signals, per week and over 30 days, counts
  only, never a percentage or a rate, with an optional group filter that today admits only "everyone";
* the sign-up questions: six optional questions that suggest a level, with one sentence of why. The answers are scored
  and dropped; only the suggestion, the outcome and that the questions were shown are kept (user_preferences.level_quiz);
* the diversification read for a book the reader keeps in the browser (the Paper Desk), the same measure the model
  books use (app/analytics/portfolio_risk.py);
* the one setting that shows the old Alerts page and the model portfolios page as separate pages again.
"""

from __future__ import annotations

import os
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import db, health_extra, knowledge, session as session_mod

# ------------------------------------------------------------------ the setting for the old separate pages

SEPARATE_SETTING = "OPTIC_SEPARATE_ALERTS_AND_MODELS"


def separate_pages() -> bool:
    """On: #/alerts is its own page again and #/portfolio opens Optic's model books, as before round three. Off (the
    default): Watchlist holds the lists and the alerts as two views, and Portfolio is the reader's own books first."""
    return str(os.environ.get(SEPARATE_SETTING, "")).strip().lower() in ("1", "on", "true", "yes")


health_extra.register("investor_pages", lambda: {
    "watchlist_and_alerts": "separate pages" if separate_pages() else "one place, two views",
    "portfolio": "Optic's model books" if separate_pages() else "the reader's own books first",
    "setting": SEPARATE_SETTING,
})


# ------------------------------------------------------------------ the market calendar

FUTURES_NOTE = ("Futures holidays are not modelled here: the CME's own holiday hours differ from the stock "
                "exchanges', so this calendar covers US stock trading only.")


def session_days(start: date, days: int) -> List[Dict[str, Any]]:
    """Each day from `start`: open, closed for a holiday, an early close, or a weekend. Times are New York's, as
    ISO instants, so the page shows them in the reader's own time zone."""
    out: List[Dict[str, Any]] = []
    et = session_mod.ET
    for i in range(max(1, min(days, 60))):
        d = start + timedelta(days=i)
        row: Dict[str, Any] = {"date": d.isoformat(), "weekday": d.strftime("%A")}
        holiday = session_mod.market_holidays(d.year).get(d)
        early = session_mod.early_closes(d.year).get(d)
        if d.weekday() >= 5:
            row.update(status="weekend", note="No regular session on weekends.")
        elif holiday:
            row.update(status="holiday", name=holiday, note="US stock markets are closed for {}.".format(holiday))
        else:
            opens = datetime(d.year, d.month, d.day, 9, 30, tzinfo=et)
            close_min = session_mod.EARLY_REGULAR_END if early else session_mod.REGULAR_END
            closes = datetime(d.year, d.month, d.day, close_min // 60, close_min % 60, tzinfo=et)
            row.update(status="early_close" if early else "open", opens=opens.isoformat(), closes=closes.isoformat())
            if early:
                row.update(name=early, note="The regular session closes at 1:00 pm New York time, {}.".format(early))
        out.append(row)
    return out


# ------------------------------------------------------------------ the owner report

EVENTS = ("home_stock_open", "milo_question", "visit")
GROUP_KINDS = ("everyone", "user", "org")


def _monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _owner_refs() -> List[str]:
    from . import metrics
    return sorted(str(i) for i in metrics.owner_ids())


def owner_report(now: Optional[datetime] = None, weeks: int = 12, group: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Counts only: per week (Monday to Sunday, UTC) and over the last 30 days. The owner's own signed-in rows are
    left out, as the signals table on the Metrics page leaves them out.

    `group` is the filter the organization round will use ({kind, id}, the names saved layouts carry). Today only
    "everyone" is read: any other group is accepted, named in the answer as not applied, and the counts are
    everyone's."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    weeks = max(1, min(int(weeks or 12), 52))
    asked = dict(group or {})
    kind = asked.get("kind") or "everyone"
    applied = "everyone"
    start = _monday(now.date()) - timedelta(weeks=weeks - 1)
    since_week = start.strftime("%Y-%m-%dT00:00:00Z")
    since_30 = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    owners = _owner_refs()
    skip = " AND NOT (actor_kind = 'signed_in' AND actor_ref IN ({}))".format(",".join("?" * len(owners))) if owners else ""
    rows = db.rows("SELECT occurred_at, actor_ref, event, symbol, source_screen, level FROM usage_event "
                   "WHERE occurred_at >= ?" + skip + " ORDER BY occurred_at", (min(since_week, since_30), *owners))
    week_ids = [(start + timedelta(weeks=i)).isoformat() for i in range(weeks)]
    per_week: Dict[str, Dict[str, Any]] = {w: {"week": w, "events": Counter(), "readers": defaultdict(set),
                                               "levels": Counter(), "screens": Counter()} for w in week_ids}
    last30 = {"events": Counter(), "readers": defaultdict(set), "levels": Counter(), "screens": Counter(),
              "symbols": Counter()}
    for r in rows:
        at = r["occurred_at"]
        day = datetime.strptime(at[:10], "%Y-%m-%d").date()
        targets = []
        w = _monday(day).isoformat()
        if w in per_week:
            targets.append(per_week[w])
        if at >= since_30:
            targets.append(last30)
            if r["event"] == "home_stock_open" and r["symbol"]:
                last30["symbols"][r["symbol"]] += 1
        for t in targets:
            t["events"][r["event"]] += 1
            t["readers"][r["event"]].add(r["actor_ref"])
            t["levels"][r["level"] or "not recorded"] += 1
            if r["source_screen"]:
                t["screens"][(r["source_screen"], r["event"])] += 1

    # came back within a week, per weekly group of first visits, as counts (never a rate): of the readers whose first
    # visit fell in that week and who have had seven days since, how many visited again within seven days
    from . import usage as usage_mod
    visits = db.rows("SELECT actor_ref, occurred_at FROM usage_event WHERE event = 'visit'" + skip, tuple(owners))
    days_by: Dict[str, List[date]] = defaultdict(list)
    for v in visits:
        days_by[v["actor_ref"]].append(datetime.strptime(v["occurred_at"][:10], "%Y-%m-%d").date())
    back: Dict[str, List[int]] = {w: [0, 0] for w in week_ids}
    today = now.date()
    for ds in days_by.values():
        first = min(ds)
        w = _monday(first).isoformat()
        if w not in back or (today - first).days < 7:
            continue
        back[w][1] += 1
        if any(0 < (d - first).days <= 7 for d in ds):
            back[w][0] += 1
    came_back_30, eligible_30 = usage_mod.returned_within_week(
        [v for v in visits if v["occurred_at"] >= since_30], now)

    def _shape(t: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "signals": {e: {"events": int(t["events"][e]), "readers": len(t["readers"][e])} for e in EVENTS},
            "levels": [{"level": k, "events": int(n)} for k, n in sorted(t["levels"].items(), key=lambda x: (-x[1], x[0]))],
            "screens": [{"screen": s, "event": e, "events": int(n)}
                        for (s, e), n in sorted(t["screens"].items(), key=lambda x: (-x[1], x[0]))][:12],
        }

    return {
        "available": True,
        "group": {"asked": {"kind": kind, "id": asked.get("id") or None}, "applied": applied,
                  "note": None if kind == "everyone" else "Reading one group is not built yet; these counts are everyone's."},
        "weeks": [dict(_shape(per_week[w]), week=w, came_back={"readers": back[w][0], "had_a_full_week": back[w][1]})
                  for w in week_ids],
        "last_30_days": dict(_shape(last30), came_back={"readers": came_back_30, "had_a_full_week": eligible_30},
                             symbols=[{"symbol": s, "opens": int(n)} for s, n in last30["symbols"].most_common(10)]),
        "owners_left_out": len(owners),
        "what_is_counted": ("Three events only, recorded since round one: a stock opened from Home, a question to Milo, "
                            "and a reader's first visit of a day. 'Screens' are where those events happened. Counts, "
                            "never percentages: on a handful of readers a percentage reads as more than it is."),
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def clean_group(kind: Optional[str], ident: Optional[str]) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """The filter from the address: (group, problem). A kind outside the three is a problem; an id is kept short."""
    k = (kind or "everyone").strip().lower()
    if k not in GROUP_KINDS:
        return None, "A group is one of everyone, user or org."
    return {"kind": k, "id": (ident or "").strip()[:80] or None}, None


# ------------------------------------------------------------------ the sign-up questions

QUESTIONS: List[Dict[str, Any]] = [
    {"id": "experience", "text": "How long have you been investing?",
     "choices": [("none", "Not yet", 0), ("under_1", "Less than a year", 0), ("1_5", "One to five years", 1),
                 ("over_5", "More than five years", 2)]},
    {"id": "goal", "text": "What brings you to Optic most?",
     "choices": [("learn", "Learning how markets work", 0), ("research", "Researching companies I might own", 1),
                 ("trade", "Planning and tracking trades", 2)]},
    {"id": "horizon", "text": "How long do you usually hold an investment?",
     "choices": [("unsure", "Not sure yet", 0), ("years", "Years", 1), ("months", "Months", 1),
                 ("days", "Days or weeks", 2)]},
    {"id": "tools", "text": "What do you use today?",
     "choices": [("nothing", "Nothing yet", 0), ("broker_app", "A brokerage app", 0),
                 ("sheets", "Spreadsheets or a stock screener", 1), ("charting", "Charting or options tools", 2)]},
    {"id": "charts", "text": "When you look at a price chart, what do you read?",
     "choices": [("direction", "Mostly whether it went up or down", 0), ("trends", "Trends and moving averages", 1),
                 ("indicators", "Indicators, volume and patterns", 2)]},
    {"id": "milo", "text": "What would you most like from Milo?",
     "choices": [("explain", "Plain explanations of the terms", 0), ("second", "A second opinion on my research", 1),
                 ("fast", "Fast answers with the figures", 2)]},
]

WHY = {
    "beginner": "Your answers point to starting out, so Beginner explains each term the first time it appears and keeps "
                "the screens to the essentials.",
    "intermediate": "Your answers point to some experience, so Intermediate explains the less common terms and shows "
                    "the fuller set of panels.",
    "advanced": "Your answers point to a lot of experience, so Advanced keeps explanations short and shows every panel "
                "and figure.",
}


def public_questions() -> List[Dict[str, Any]]:
    return [{"id": q["id"], "text": q["text"], "choices": [{"id": c[0], "label": c[1]} for c in q["choices"]]}
            for q in QUESTIONS]


def suggest(answers: Dict[str, Any]) -> Dict[str, Any]:
    """A level from whatever was answered (every question is optional). Nothing answered suggests nothing."""
    scores = []
    for q in QUESTIONS:
        got = (answers or {}).get(q["id"])
        for cid, _label, score in q["choices"]:
            if got == cid:
                scores.append(score)
    if not scores:
        return {"suggested": None, "why": None, "answered": 0}
    avg = sum(scores) / len(scores)
    level = "beginner" if avg < 0.75 else "intermediate" if avg < 1.5 else "advanced"
    return {"suggested": level, "why": WHY[level], "answered": len(scores)}


def quiz_state(user_id: str) -> Dict[str, Any]:
    from .auth import store
    return store.round_three_preferences(user_id).get("level_quiz") or {}


def offer_questions(user_id: str) -> bool:
    """Offered once, on the first signed-in visit of any account that has not seen them, however it signed up."""
    from .auth import store
    return store.round_three_preferences(user_id).get("level_quiz") is None


def mark_shown(user_id: str) -> Dict[str, Any]:
    from .auth import store
    current = quiz_state(user_id)
    if current:
        return current
    return store.set_round_three_preferences(user_id, {"level_quiz": {"shown": True, "suggested": None,
                                                                      "outcome": None}})["level_quiz"]


def decide(user_id: str, outcome: str, suggested: Optional[str]) -> Dict[str, Any]:
    """Accepted: the suggestion becomes the account's level. Skipped: nothing but the outcome is written."""
    from .auth import store
    if outcome not in ("accepted", "skipped"):
        raise ValueError("outcome")
    level = knowledge.three(suggested) if suggested and knowledge.known(suggested) else None
    if outcome == "accepted" and not level:
        raise ValueError("suggested")
    quiz = store.set_round_three_preferences(user_id, {"level_quiz": {"shown": True, "suggested": level,
                                                                      "outcome": outcome}})["level_quiz"]
    prefs = store.set_preferences(user_id, {"knowledge_level": level}) if outcome == "accepted" else store.preferences(user_id)
    return {"level_quiz": quiz, "knowledge_level": prefs.get("knowledge_level")}


# ------------------------------------------------------------------ a browser-kept book's diversification

MAX_POSITIONS = 50


def positions_from_body(body: Any) -> List[Dict[str, Any]]:
    out = []
    for p in (body or [])[:MAX_POSITIONS] if isinstance(body, list) else []:
        if not isinstance(p, dict):
            continue
        sym = str(p.get("ticker") or p.get("symbol") or "").upper().strip()[:12]
        try:
            qty, price = float(p.get("qty")), float(p.get("entry_price"))
        except (TypeError, ValueError):
            continue
        if not sym or qty <= 0 or price <= 0:
            continue
        row = {"ticker": sym, "qty": qty, "entry_price": price,
               "direction": "short" if str(p.get("direction") or "").lower() == "short" else "long",
               "instrument": "option" if p.get("instrument") == "option" else "shares"}
        for k in ("option_type", "strike", "expiry"):
            if p.get(k) is not None:
                row[k] = p.get(k)
        out.append(row)
    return out

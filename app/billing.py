"""Paid plans through Stripe: Checkout to subscribe, the Customer Portal to
manage or cancel, and a verified webhook that is the only thing allowed to
change a plan.

**The browser never grants a plan.** Returning from Checkout shows a "thanks,
confirming" state; the plan changes when Stripe's signed webhook says the
subscription is active, and not before. A success URL is a page anyone can
type.

**Test mode only until the owner says otherwise.** A live secret key
(`sk_live_` or `rk_live_`) is refused unless `BILLING_LIVE_APPROVED=true` is
also set, so live billing cannot start by pasting the wrong key.

**Webhooks:** signature checked against the raw body (`Stripe-Signature`,
`t=`/`v1=`, HMAC-SHA256 of `"{t}.{body}"` with the `whsec_` secret, five-minute
tolerance; Stripe's docs as read 2026-10-12). Each event id is processed once:
the insert into `webhook_events` is the lock, and a handler that fails removes
its row so Stripe's retry is processed rather than acknowledged. Events can
arrive out of order, so each subscription row remembers the `created` time of
the last event applied and ignores anything older.

**Only Optic's prices count, and the price decides the plan.** The plan
ladder (round three, 2026-11-23) is the plans in `auth.store.PLANS` (free, pro,
enterprise today) with one Stripe price id per paid plan, read from
`STRIPE_PRICE_ID_<PLAN>` (`STRIPE_PRICE_ID_PRO`, `STRIPE_PRICE_ID_ENTERPRISE`;
`STRIPE_PRICE_ID` is still read as the pro price, so a deploy configured before
this keeps working). A subscription grants the highest plan whose price is one
of its items, and nothing else: metadata the app wrote at Checkout is never
read for the plan, because the customer portal, a schedule or a Dashboard edit
changes the price and leaves the metadata alone. `invoice.paid` re-reads the
subscription from Stripe and derives the plan again, as a safety net for an
event missed or applied out of order. The same Stripe account selling
something else must not hand out Optic plans.

**Caps.** What each plan allows lives in `PLANS` and is enforced in one place
(`auth.store.subscription`, read by Milo's spend guard and the brokerage
entitlement). Billing off changes nothing there: plans stay what the stored
rows say, as before round three; billing on, Stripe's webhook writes the rows.

**Terms first.** Checkout is refused while the terms and privacy text is the
placeholder (app/legal_text.py), with the sentence the pages show. On a test
key only, `BILLING_TEST_IGNORE_LEGAL_PLACEHOLDER=true` lifts that, so the
Checkout round trip can be proved on an evaluation copy before counsel's text
exists; a live key ignores it.

No SDK: four endpoints over `requests`, which is already a dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any, Dict, Optional

import requests
from fastapi import APIRouter, Body, HTTPException, Request

from . import db, health_extra, legal_text, runtime
from .auth import deps, store as auth_store
from .brokerage import service as brokerage
from .brokerage import store as bstore

log = logging.getLogger("optic.billing")
router = APIRouter(prefix="/api/billing", tags=["billing"])

API = "https://api.stripe.com/v1"
TOLERANCE = 300
PAID_PLAN = "pro"            # the plan a Checkout with no plan named buys (the Settings button before round three)
TERMINAL = ("canceled", "incomplete_expired")
NOT_ON_SALE = "Plans are not on sale yet. Every account is on Free."


def _api() -> str:
    """Stripe's base address, a setting so the suite can pin it to a local recording stub."""
    return (os.environ.get("STRIPE_API_BASE") or API).rstrip("/")


def _timeout() -> float:
    """Seconds before Stripe is called down; a setting so a test can play a timeout without waiting 20 s."""
    try:
        return max(0.5, float(os.environ.get("STRIPE_TIMEOUT_SECONDS") or 20))
    except ValueError:
        return 20.0


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


# ------------------------------------------------------------------ the ladder


def paid_plans() -> list:
    """The paid plans in ladder order (cheapest first), from auth.store.PLANS."""
    return [p for p in auth_store.PLANS if p != "free"]


def price_id(plan: str) -> str:
    """The Stripe price that sells `plan`: STRIPE_PRICE_ID_<PLAN>; for pro, STRIPE_PRICE_ID as before."""
    own = _env("STRIPE_PRICE_ID_" + plan.upper())
    if own or plan != "pro":
        return own
    return _env("STRIPE_PRICE_ID")


def plan_for_price(pid: str) -> Optional[str]:
    for plan in paid_plans():
        if pid and price_id(plan) == pid:
            return plan
    return None


def _plan_label(plan: str) -> str:
    return _env("BILLING_PLAN_LABEL_" + plan.upper()) or auth_store.PLANS[plan]["label"]


def ladder() -> list:
    """Free, then every paid plan that has a price id, with what each allows. Read by the pricing panel."""
    out = [{"plan": "free", "label": _plan_label("free"), "price_label": None,
            "limits": {k: v for k, v in auth_store.PLANS["free"].items() if k != "label"}}]
    for plan in paid_plans():
        if price_id(plan):
            out.append({"plan": plan, "label": _plan_label(plan), "price_label": price_label(plan=plan),
                        "limits": {k: v for k, v in auth_store.PLANS[plan].items() if k != "label"}})
    return out


def missing() -> list:
    """The variable names billing still needs; empty when it can run. Names only, never values."""
    need = [n for n in ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET") if not _env(n)]
    if not any(price_id(p) for p in paid_plans()):
        need.append("STRIPE_PRICE_ID_PRO")
    return need


def anything_set() -> bool:
    names = ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET", "STRIPE_PRICE_ID"] + [
        "STRIPE_PRICE_ID_" + p.upper() for p in paid_plans()]
    return any(_env(n) for n in names)


def _legal_override() -> bool:
    """The evaluation copy's switch, honoured on a test key only (see the module docstring)."""
    return mode() == "test" and _env("BILLING_TEST_IGNORE_LEGAL_PLACEHOLDER").lower() == "true"


def checkout_refusal() -> Optional[str]:
    """Why Checkout cannot open while billing is otherwise on, or None."""
    if legal_text.placeholder() and not _legal_override():
        return legal_text.CHECKOUT_REFUSAL
    return None


def _key() -> str:
    return (os.environ.get("STRIPE_SECRET_KEY") or "").strip()


def mode() -> Optional[str]:
    k = _key()
    if not k:
        return None
    return "live" if "_live_" in k else "test"


def status() -> Dict[str, Any]:
    need = missing()
    if need:
        return {"available": False, "reason": runtime.for_reader(
            NOT_ON_SALE, "Billing is off: set {}.".format(", ".join(need)))}
    if mode() == "live" and (os.environ.get("BILLING_LIVE_APPROVED") or "").lower() != "true":
        return {"available": False, "reason": runtime.for_reader(
            NOT_ON_SALE,
            "A live Stripe key is set but BILLING_LIVE_APPROVED is not true. Refusing live billing.")}
    refusal = checkout_refusal()
    return {"available": True, "mode": mode(), "price_label": price_label(), "plans": ladder(),
            "checkout_open": refusal is None, "checkout_refusal": refusal}


def health() -> Dict[str, Any]:
    """Billing's line on /api/health (public): on or off, the mode, the plan count, and how caps are decided."""
    st = status()
    on = bool(st.get("available"))
    return {"state": "on" if on else "off", "mode": mode() if on else None,
            "plans": len(st.get("plans") or []) if on else 0,
            "checkout_open": bool(st.get("checkout_open")) if on else False,
            "caps": ("per plan, derived from Stripe's prices" if on else
                     "per stored plan, as before round three (billing off: nothing on sale, plans granted by the owner)")}


def health_operator() -> Dict[str, Any]:
    """The owner's half: which variable names are missing (names only), and whether the copy's legal switch is on."""
    return {"missing": missing() if anything_set() else [], "configured": anything_set(),
            "legal_override": _legal_override()}


health_extra.register("billing", health)
health_extra.register("billing_setup", health_operator, public=False)


# The price the button names (Pass 2, 2026-11-17): BILLING_PRICE_LABEL when the owner sets one, else read from the
# Stripe price itself (amount, currency, interval), so the button can never name a price Stripe will not charge. It
# said "$20 a month" by default before, a figure no variable set. Read once an hour; when Stripe cannot be read, the
# button names no price rather than a guess.
_PRICE = {"id": None, "at": 0.0, "label": None}
PRICE_TTL = 3600


def _money(amount: Any, currency: str) -> Optional[str]:
    try:
        value = int(amount) / 100.0
    except (TypeError, ValueError):
        return None
    sym = {"usd": "$", "eur": "\u20ac", "gbp": "\u00a3", "cad": "CA$", "aud": "A$"}.get((currency or "").lower())
    num = ("{:,.0f}" if value == int(value) else "{:,.2f}").format(value)
    return "{}{}".format(sym, num) if sym else "{} {}".format(num, (currency or "").upper())


_PRICES: Dict[str, Dict[str, Any]] = {}


def price_label(now: Optional[float] = None, plan: str = PAID_PLAN) -> Optional[str]:
    own = _env("BILLING_PRICE_LABEL_" + plan.upper()) or (_env("BILLING_PRICE_LABEL") if plan == "pro" else "")
    if own:
        return own
    pid = price_id(plan)
    if not pid:
        return None
    now = time.time() if now is None else now
    # pro keeps the one cache it always had (tests reset it); each other plan has its own
    cached = _PRICE if plan == PAID_PLAN else _PRICES.setdefault(plan, {"id": None, "at": 0.0, "label": None})
    if cached["id"] == pid and now - cached["at"] < PRICE_TTL:
        return cached["label"]
    label = None
    try:
        p = _stripe("GET", "/prices/" + pid)
        money = _money(p.get("unit_amount"), p.get("currency") or "")
        every = ((p.get("recurring") or {}).get("interval") or "")
        label = "{} a {}".format(money, every) if money and every else money
    except HTTPException:
        label = None
    cached.update({"id": pid, "at": now, "label": label})
    return label


def _stripe(method: str, path: str, data: Optional[Dict[str, Any]] = None,
            idempotency_key: Optional[str] = None) -> Dict[str, Any]:
    headers = {"Authorization": "Bearer " + _key()}
    if idempotency_key:
        headers["Idempotency-Key"] = idempotency_key
    try:
        resp = requests.request(method, _api() + path, data=data, headers=headers, timeout=_timeout())
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail="The payment provider did not answer. Try again "
                                                    "in a minute.") from exc
    if resp.status_code >= 400:
        # The body can name the customer; log the status and Stripe's error
        # type only.
        try:
            kind = (resp.json().get("error") or {}).get("type")
        except ValueError:
            kind = None
        log.warning("stripe %s %s -> %s (%s)", method, path, resp.status_code, kind)
        raise HTTPException(status_code=502, detail="The payment provider refused the request.")
    return resp.json()


def _sub_row(user_id: str) -> Optional[Dict[str, Any]]:
    return db.row("SELECT * FROM subscriptions WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,))


# ------------------------------------------------------------------ routes


@router.get("/status")
async def billing_status(request: Request) -> Dict[str, Any]:
    user = deps.current_user(request)
    out = status()
    if user:
        out["subscription"] = auth_store.subscription(user["id"])
        out["can_manage"] = bool((_sub_row(user["id"]) or {}).get("provider_customer_id"))
    return out


@router.post("/checkout")
async def checkout(request: Request, payload: Optional[Dict[str, Any]] = Body(default=None)) -> Dict[str, Any]:
    # Signed in, not necessarily confirmed: Stripe collects and confirms the
    # billing email itself, and production mail is not configured yet, so
    # requiring a confirmed address would mean nobody could subscribe.
    user = deps.require_user(request)
    deps.csrf_guard(request)
    st = status()
    if not st["available"]:
        raise HTTPException(status_code=503, detail=st["reason"])
    if not st.get("checkout_open"):
        raise HTTPException(status_code=503, detail=st["checkout_refusal"])
    plan = str((payload or {}).get("plan") or PAID_PLAN)
    if plan not in paid_plans() or not price_id(plan):
        raise HTTPException(status_code=400, detail="That plan is not on sale.")
    sub = auth_store.subscription(user["id"])
    row = _sub_row(user["id"]) or {}
    open_sub = row.get("provider_subscription_id") and row.get("provider_status") not in TERMINAL
    if sub["plan"] != "free" or open_sub:
        # Also refused while a subscription exists that has not ended, even
        # before its webhook made the plan Pro: two quick checkouts used to be
        # two subscriptions on one account (review M6).
        # A change of plan goes through the customer portal, which Stripe prices and prorates; a second
        # Checkout would be a second subscription.
        raise HTTPException(status_code=409, detail="You already have a {} subscription. Use Manage billing "
                                                    "to change or cancel it.".format(sub["label"]
                                                                                      if sub["plan"] != "free"
                                                                                      else "paid"))
    base = runtime.base_url()
    data: Dict[str, Any] = {
        "mode": "subscription",
        "line_items[0][price]": price_id(plan),
        "line_items[0][quantity]": "1",
        "client_reference_id": user["id"],
        "metadata[user_id]": user["id"],
        "subscription_data[metadata][user_id]": user["id"],
        "success_url": base + "/?billing=success#/settings",
        "cancel_url": base + "/?billing=cancel#/settings",
        "allow_promotion_codes": "true",
    }
    if row.get("provider_customer_id"):
        data["customer"] = row["provider_customer_id"]
    else:
        data["customer_email"] = user["email"]
    # A double click inside the same minute returns the same session rather
    # than two open checkouts.
    session = _stripe("POST", "/checkout/sessions", data,
                      idempotency_key="optic-checkout-{}-{}-{}".format(user["id"], plan, int(time.time() // 60)))
    return {"url": session.get("url")}


@router.post("/portal")
async def portal(request: Request) -> Dict[str, Any]:
    user = deps.require_user(request)
    deps.csrf_guard(request)
    st = status()
    if not st["available"]:
        raise HTTPException(status_code=503, detail=st["reason"])
    customer = (_sub_row(user["id"]) or {}).get("provider_customer_id")
    if not customer:
        raise HTTPException(status_code=404, detail="There is no billing account for this sign-in yet.")
    session = _stripe("POST", "/billing_portal/sessions",
                      {"customer": customer, "return_url": runtime.base_url() + "/#/settings"})
    return {"url": session.get("url")}


@router.post("/webhook")
async def webhook(request: Request) -> Dict[str, Any]:
    body = await request.body()
    secret = (os.environ.get("STRIPE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Billing is not configured.")
    if not verify_signature(body, request.headers.get("stripe-signature") or "", secret):
        raise HTTPException(status_code=400, detail="Signature did not verify.")
    import json
    try:
        event = json.loads(body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Not JSON.")
    if bool(event.get("livemode")) != (mode() == "live"):
        # A test event at a live endpoint, or the reverse: never apply it.
        return {"ok": True, "ignored": "mode mismatch"}
    eid, etype = str(event.get("id") or ""), str(event.get("type") or "")
    if not eid:
        raise HTTPException(status_code=400, detail="No event id.")
    if not bstore.first_delivery("stripe", eid, etype):
        return {"ok": True, "duplicate": True}
    try:
        result = apply_event(event)
    except Exception:
        bstore.forget_delivery("stripe", eid)
        log.exception("stripe webhook %s failed", etype)
        raise HTTPException(status_code=500, detail="Not processed; retry.")
    return {"ok": True, "result": result}


# ---------------------------------------------------------------- the logic


def verify_signature(body: bytes, header: str, secret: str, now: Optional[float] = None) -> bool:
    parts: Dict[str, list] = {}
    for item in header.split(","):
        k, _, v = item.strip().partition("=")
        parts.setdefault(k, []).append(v)
    try:
        stamp = int((parts.get("t") or [""])[0])
    except ValueError:
        return False
    if abs((now or time.time()) - stamp) > TOLERANCE:
        return False
    expected = hmac.new(secret.encode(), "{}.".format(stamp).encode() + body, hashlib.sha256).hexdigest()
    # bytes: two str with a non-ASCII character raise TypeError, a 500 instead of a refusal (SEC-11, Phase 10)
    return any(hmac.compare_digest(expected.encode("utf-8"), sig.encode("utf-8")) for sig in parts.get("v1") or [])


def _find_user(obj: Dict[str, Any]) -> Optional[str]:
    uid = (obj.get("metadata") or {}).get("user_id") or obj.get("client_reference_id")
    if uid and auth_store.get_user(uid):
        return uid
    for col, val in (("provider_subscription_id", obj.get("subscription") if obj.get("object") != "subscription"
                      else obj.get("id")), ("provider_customer_id", obj.get("customer"))):
        if val:
            found = db.row("SELECT user_id FROM subscriptions WHERE provider = 'stripe' AND {} = ?".format(col),
                           (val,))
            if found:
                return found["user_id"]
    return None


def plan_of(sub: Dict[str, Any]) -> Optional[str]:
    """The highest plan whose price is an item of this subscription, or None. Prices only; metadata never."""
    found = [plan_for_price(((item.get("price") or {}).get("id")) or "")
             for item in ((sub.get("items") or {}).get("data") or [])]
    ranked = [p for p in paid_plans() if p in found]
    return ranked[-1] if ranked else None


def _has_our_price(sub: Dict[str, Any]) -> bool:
    return plan_of(sub) is not None


def _period_end(sub: Dict[str, Any]) -> Optional[str]:
    end = sub.get("current_period_end")
    if end is None:
        items = (sub.get("items") or {}).get("data") or []
        end = items[0].get("current_period_end") if items else None
    if not end:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(int(end)))


def _write(user_id: str, created: int, **fields: Any) -> bool:
    """Apply fields to the user's subscription row if this event is newer than
    the last one applied. Returns whether anything was written."""
    row = _sub_row(user_id)
    if row and row.get("last_event_at") and int(row["last_event_at"]) > created:
        return False
    fields["last_event_at"] = created
    fields["updated_at"] = db.utcnow()
    if not row:
        db.execute("INSERT INTO subscriptions (id, user_id, plan, status, created_at, updated_at) "
                   "VALUES (?,?,'free','active',?,?)", (db.new_id(), user_id, db.utcnow(), db.utcnow()))
        row = _sub_row(user_id)
    cols = ", ".join("{} = ?".format(k) for k in fields)
    db.execute("UPDATE subscriptions SET {} WHERE id = ?".format(cols), tuple(fields.values()) + (row["id"],))
    return True


def apply_event(event: Dict[str, Any]) -> str:
    etype = event.get("type") or ""
    obj = ((event.get("data") or {}).get("object") or {})
    created = int(event.get("created") or 0)
    if etype == "checkout.session.completed":
        uid = _find_user(obj)
        if not uid:
            return "no-user"
        # Links the Stripe customer and subscription to the account. The plan
        # itself comes from the subscription events, which carry its status.
        _write(uid, created - 1, provider="stripe", provider_customer_id=obj.get("customer"),
               provider_subscription_id=obj.get("subscription"))
        return "linked"
    if etype in ("customer.subscription.created", "customer.subscription.updated",
                 "customer.subscription.deleted", "customer.subscription.paused",
                 "customer.subscription.resumed"):
        uid = _find_user(obj)
        if not uid:
            return "no-user"
        stripe_status = "canceled" if etype == "customer.subscription.deleted" else str(obj.get("status") or "")
        row = _sub_row(uid) or {}
        stored = row.get("provider_subscription_id")
        if stored and stored != obj.get("id") and row.get("provider_status") in auth_store.ENTITLED_STATUSES:
            # A second subscription while the stored one is live. Applying it
            # would let cancelling either one end Pro while the other keeps
            # billing. Logged for a refund by hand.
            log.error("stripe: second subscription %s for a user who already has %s; not applied",
                      obj.get("id"), stored)
            return "second-subscription"
        ours = plan_of(obj)
        entitled = bool(ours) and stripe_status in auth_store.ENTITLED_STATUSES
        wrote = _write(uid, created,
                       plan=ours if entitled else "free",
                       status=stripe_status if stripe_status in auth_store.ENTITLED_STATUSES else "active",
                       provider="stripe", provider_status=stripe_status,
                       provider_customer_id=obj.get("customer"), provider_subscription_id=obj.get("id"),
                       cancel_at_period_end=1 if obj.get("cancel_at_period_end") else 0,
                       current_period_end=_period_end(obj))
        if wrote:
            brokerage.on_plan_change(uid)
        return (ours if entitled else "free") if wrote else "stale"
    if etype == "invoice.paid":
        # The safety net (billing truth): read the subscription as Stripe bills it now and derive the plan again, so a
        # missed or reordered subscription event cannot leave a reader on the wrong plan for a billing period.
        sid = obj.get("subscription") or (((obj.get("parent") or {}).get("subscription_details") or {})
                                          .get("subscription"))
        if not sid:
            return "no-subscription"
        current = _stripe("GET", "/subscriptions/{}".format(sid))
        return apply_event({"type": "customer.subscription.updated", "created": created,
                            "data": {"object": current}})
    if etype == "invoice.payment_failed":
        # The subscription's own update event moves it to past_due; nothing
        # to change here, and past_due stays entitled while Stripe retries.
        return "noted"
    return "ignored"


def cancel_for_deletion(user_id: str) -> None:
    """Cancel a live Stripe subscription immediately, before the account it
    belongs to is deleted. Raises a 502 if Stripe will not, so the deletion
    stops rather than leaving a subscription nobody can manage."""
    row = _sub_row(user_id) or {}
    if row.get("provider") != "stripe" or not row.get("provider_subscription_id"):
        return
    if row.get("provider_status") in ("canceled", "incomplete_expired"):
        return
    if not _key():
        raise HTTPException(status_code=503, detail="Your subscription could not be cancelled because "
                                                    "billing is unavailable. Nothing was deleted.")
    _stripe("DELETE", "/subscriptions/{}".format(row["provider_subscription_id"]))

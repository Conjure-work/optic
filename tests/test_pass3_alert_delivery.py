"""Alert delivery per reader, behind the owner's switch (round three, carried item 7; amendment DD-13 reading).

Off (the default): nothing is sent to a reader, the Settings control is not offered, and the owner summary is exactly
as built. On: a reader who asked for it gets one digest per pass of the hits on their own watches, at their own
address, each hit once; a send the relay refuses or that times out stays pending for the next pass.

Mail is recorded at the mailer's transport (`_send_smtp`), so the real `mailer.send` builds every message; nothing
leaves the machine.
"""

from __future__ import annotations

import socket
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import alerts, health_extra, watch_runner
from app.auth import config, mailer, store as auth_store

GOOD = "tungsten-carbide-9"


class Outbox(list):
    """Every message the transport was handed; `alerts` is the alert mail alone (sign-up confirmations also go out
    once a mail server is set, and are not what these tests are about)."""
    @property
    def alerts(self):
        return [m for m in self if m["Subject"].startswith("Optic alert")]


@pytest.fixture
def outbox(accounts, monkeypatch):
    sent = Outbox()
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.recorder.invalid")
    monkeypatch.setattr(mailer, "EMAIL_FROM", "alerts@example.test")
    monkeypatch.setattr(mailer, "_send_smtp", lambda message: sent.append(message))
    monkeypatch.delenv("ALERT_DELIVERY_READERS", raising=False)
    return sent


def reader(email):
    c = TestClient(main.app)
    c.post("/api/auth/register", json={"first_name": "R", "last_name": "Eader", "email": email,
                                       "password": GOOD, "confirm_password": GOOD})
    c.headers["X-Optic-CSRF"] = c.cookies.get(config.CSRF_COOKIE)
    return c, auth_store.get_user_by_email(email)


def hit(db, uid, symbol="AAPL", title=None, ago_hours=1):
    now = datetime.now(timezone.utc)
    wid = uuid.uuid4().hex
    db.execute("INSERT INTO watches (id, user_id, symbol, kind, params, created_at) VALUES (?,?,?,?,?,?)",
               (wid, uid, symbol, "day_move", '{"n": "%s"}' % wid, now.isoformat()))
    hid = uuid.uuid4().hex
    db.execute("INSERT INTO watch_hits (id, user_id, watch_id, symbol, kind, title, body, created_at, dedupe_key, "
               "condition) VALUES (?,?,?,?,?,?,?,?,?,?)",
               (hid, uid, wid, symbol, "day_move", title or "{} moved 3% today".format(symbol), "Up from 100 to 103.",
                (now - timedelta(hours=ago_hours)).isoformat(), hid, "{} day move 3%".format(symbol)))
    return hid


def opt_in(uid):
    auth_store.set_round_three_preferences(uid, {"alert_email": True})


def test_off_by_default_nothing_goes_to_a_reader_even_one_who_opted_in(accounts, outbox):
    _, u = reader("off@example.com")
    opt_in(u["id"])
    hit(accounts, u["id"])
    assert alerts.readers_on() is False
    assert alerts.deliver_to_readers() == {"sent": 0, "readers": 0, "mode": "owner summary"}
    assert outbox.alerts == [] and accounts.rows("SELECT * FROM watch_delivery") == []
    assert alerts.delivery_mode()["mode"] == "owner summary"


def test_off_the_settings_control_is_not_offered_and_cannot_be_set(accounts, outbox):
    c, _ = reader("off-settings@example.com")
    assert c.get("/api/alert-delivery/me").json() == {"offered": False, "email_me": False}
    assert c.post("/api/alert-delivery/me", json={"email_me": True}).status_code == 409


def test_the_owner_summary_is_unchanged_with_the_switch_on(accounts, outbox, monkeypatch):
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    monkeypatch.setenv("ALERT_EMAIL_TO", "owner@example.test")
    monkeypatch.setenv("ALERT_ALWAYS_ON", "true")
    assert alerts.raise_alert("idea", "Owner book alert (test) {}".format(uuid.uuid4().hex), ticker="AAPL")
    out = alerts.deliver_pending()
    assert out["sent"] >= 1
    assert [m["To"] for m in outbox.alerts] == ["owner@example.test"]


def test_on_an_opted_in_reader_gets_their_own_hits_at_their_own_address_once(accounts, outbox, monkeypatch):
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    _, a = reader("alice@example.com")
    _, b = reader("bob@example.com")
    _, quiet = reader("quiet@example.com")
    opt_in(a["id"])
    opt_in(b["id"])
    a1, a2 = hit(accounts, a["id"], "AAPL"), hit(accounts, a["id"], "MSFT")
    hit(accounts, b["id"], "NVDA")
    hit(accounts, quiet["id"], "TSLA")                        # never asked: nothing for them
    hit(accounts, a["id"], "OLD", ago_hours=60)               # older than the window: never mailed as backlog
    out = alerts.deliver_to_readers()
    assert out == {"sent": 3, "pending": 0, "readers": 2}
    to = sorted(m["To"] for m in outbox.alerts)
    assert to == ["alice@example.com", "bob@example.com"]
    alice = [m for m in outbox.alerts if m["To"] == "alice@example.com"][0]
    body = alice.get_content()
    assert "AAPL" in body and "MSFT" in body and "NVDA" not in body and "TSLA" not in body and "OLD" not in body
    assert "You asked: AAPL day move 3%" in body and "#/watchlist" in body
    assert {r["hit_id"] for r in accounts.rows("SELECT hit_id FROM watch_delivery WHERE user_id = ?", (a["id"],))} \
        == {a1, a2}
    # once per hit: the next pass sends nothing
    assert alerts.deliver_to_readers()["sent"] == 0 and len(outbox.alerts) == 2


def test_a_reader_who_opts_out_gets_nothing_more(accounts, outbox, monkeypatch):
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    c, u = reader("optout@example.com")
    assert c.post("/api/alert-delivery/me", json={"email_me": True}).json() == {"offered": True, "email_me": True}
    assert c.post("/api/alert-delivery/me", json={"email_me": False}).json()["email_me"] is False
    hit(accounts, u["id"])
    assert alerts.deliver_to_readers()["sent"] == 0 and outbox.alerts == []


@pytest.mark.parametrize("failure", [ConnectionRefusedError("relay refused"), socket.timeout("relay timed out")])
def test_a_relay_that_refuses_or_times_out_leaves_the_hits_pending_for_the_next_pass(accounts, outbox, monkeypatch,
                                                                                    failure):
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    _, u = reader("pending@example.com")
    opt_in(u["id"])
    hit(accounts, u["id"])

    def down(message):
        raise failure
    monkeypatch.setattr(mailer, "_send_smtp", down)
    out = alerts.deliver_to_readers()
    assert out == {"sent": 0, "pending": 1, "readers": 1}
    assert accounts.rows("SELECT * FROM watch_delivery") == []                 # nothing half-applied
    monkeypatch.setattr(mailer, "_send_smtp", lambda message: outbox.append(message))
    assert alerts.deliver_to_readers()["sent"] == 1 and len(outbox.alerts) == 1


def test_no_mail_server_sends_nothing_and_records_nothing(accounts, monkeypatch):
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    monkeypatch.setattr(mailer, "SMTP_HOST", "")
    _, u = reader("nomail@example.com")
    opt_in(u["id"])
    hit(accounts, u["id"])
    assert alerts.deliver_to_readers()["sent"] == 0
    assert accounts.rows("SELECT * FROM watch_delivery") == []


def test_the_opt_in_route_refuses_no_user_and_a_missing_csrf_and_writes_only_the_readers_own_row(accounts, outbox,
                                                                                               monkeypatch):
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    anon = TestClient(main.app)
    assert anon.get("/api/alert-delivery/me").status_code == 401
    assert anon.post("/api/alert-delivery/me", json={"email_me": True}).status_code == 401
    c, u = reader("csrf@example.com")
    _, other = reader("other-reader@example.com")
    del c.headers["X-Optic-CSRF"]
    assert c.post("/api/alert-delivery/me", json={"email_me": True}).status_code == 403
    c.headers["X-Optic-CSRF"] = c.cookies.get(config.CSRF_COOKIE)
    assert c.post("/api/alert-delivery/me", json={"email_me": "yes"}).status_code == 400
    # a body naming another reader changes nothing of theirs: the route writes the session's own row
    c.post("/api/alert-delivery/me", json={"email_me": True, "user_id": other["id"]})
    assert auth_store.round_three_preferences(other["id"])["alert_email"] is False
    assert auth_store.round_three_preferences(u["id"])["alert_email"] is True


def test_health_names_the_mode(accounts, monkeypatch):
    c = TestClient(main.app)
    assert c.get("/api/health").json()["modes"]["alert_delivery"]["mode"] == "owner summary"
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    assert c.get("/api/health").json()["modes"]["alert_delivery"]["mode"] == "readers"
    assert health_extra.snapshot()["alert_delivery"]["switch"] == "ALERT_DELIVERY_READERS"


def test_the_scheduled_pass_hands_off_to_reader_delivery_after_checking(accounts, monkeypatch):
    calls = []
    monkeypatch.setattr(alerts, "deliver_to_readers", lambda when=None: calls.append(when) or {"readers": 1,
                                                                                               "sent": 2})
    out = watch_runner.run_once(lambda symbol: {})
    assert len(calls) == 1 and out["reader_delivery"] == {"readers": 1, "sent": 2}


def test_a_delivery_failure_never_breaks_the_scheduled_pass(accounts, monkeypatch):
    def boom(when=None):
        raise RuntimeError("mail exploded")
    monkeypatch.setattr(alerts, "deliver_to_readers", boom)
    out = watch_runner.run_once(lambda symbol: {})
    assert "reader_delivery" not in out and "hits" in out


def test_delivery_rows_go_with_the_account(accounts, outbox, monkeypatch):
    monkeypatch.setenv("ALERT_DELIVERY_READERS", "1")
    c, u = reader("leaver@example.com")
    opt_in(u["id"])
    hit(accounts, u["id"])
    alerts.deliver_to_readers()
    assert accounts.rows("SELECT * FROM watch_delivery WHERE user_id = ?", (u["id"],))
    r = c.post("/api/auth/delete-account", json={"confirm_email": "leaver@example.com", "password": GOOD})
    assert r.status_code == 200
    assert accounts.rows("SELECT * FROM watch_delivery WHERE user_id = ?", (u["id"],)) == []

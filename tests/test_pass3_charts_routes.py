"""Round three, the charts' server half (Pass 3, 2026-11-23): chart layouts kept on the account (one, two or four
charts, at most 20 per account, private to their reader), the favourite intervals mirrored to the account, the free
feed's history limit under the chart's All range, and the mode on /api/health.

The three legs for every account route: no user, another user, and a write without the CSRF header.
"""
from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

import app.main as main
from app import chart_routes
from app.auth import config

GOOD = "tungsten-carbide-9"
client = TestClient(main.app)
other = TestClient(main.app)
TWO = {"layout": {"count": 2, "slots": [{"symbol": "AAPL", "interval": "60", "range": "6M"},
                                         {"symbol": "msft", "interval": "daily", "range": "1Y"}]}}
FOUR = {"layout": {"count": 4, "slots": [{"symbol": s, "interval": "daily", "range": "6M"} for s in ("AAPL", "MSFT", "NVDA", "SPY")]}}


@pytest.fixture(autouse=True)
def fresh(accounts):
    client.cookies.clear()
    other.cookies.clear()
    return accounts


def register(http, email):
    http.post("/api/auth/register", json={"first_name": "A", "last_name": "B", "email": email, "password": GOOD, "confirm_password": GOOD})
    return {"X-Optic-CSRF": http.cookies.get(config.CSRF_COOKIE)}


def test_a_chart_layout_is_kept_on_the_account_and_read_back_from_another_session():
    h = register(client, "charts@example.com")
    r = client.put("/api/chart/layouts/Two up", headers=h, json=TWO)
    assert r.status_code == 200 and r.json()["saved"] and r.json()["replaced"] is False
    again = TestClient(main.app)
    again.post("/api/auth/login", json={"email": "charts@example.com", "password": GOOD})
    got = again.get("/api/chart/layouts").json()
    assert got["max"] == 20
    assert got["layouts"][0]["name"] == "Two up" and got["layouts"][0]["count"] == 2
    assert got["layouts"][0]["slots"][1] == {"symbol": "MSFT", "interval": "daily", "range": "1Y"}
    assert client.put("/api/chart/layouts/Two up", headers=h, json=FOUR).json()["replaced"] is True


def test_chart_layouts_refuse_no_user_another_user_and_no_csrf():
    assert client.get("/api/chart/layouts").status_code == 401
    assert client.put("/api/chart/layouts/x", json=TWO).status_code in (401, 403)
    assert client.delete("/api/chart/layouts/x").status_code in (401, 403)
    h = register(client, "charts@example.com")
    assert client.put("/api/chart/layouts/Mine", json=TWO).status_code == 403, "no CSRF header"
    client.put("/api/chart/layouts/Mine", headers=h, json=TWO)
    t = register(other, "theirs@example.com")
    assert other.get("/api/chart/layouts").json()["layouts"] == [], "another reader's layouts are not listed"
    assert other.delete("/api/chart/layouts/Mine", headers=t).status_code == 404, "nor deleted"
    assert other.put("/api/chart/layouts/Mine", headers=t, json=FOUR).json()["replaced"] is False, "nor overwritten"
    assert client.get("/api/chart/layouts").json()["layouts"][0]["count"] == 2
    assert client.delete("/api/chart/layouts/Mine", headers=h).json()["layouts"] == []


def test_only_one_two_or_four_charts_are_kept():
    for bad in ({"count": 3, "slots": []}, {"count": 2, "slots": [{"symbol": "AAPL"}]},
                {"count": 1, "slots": [{"symbol": "<b>"}]}, "x", {"count": 2}):
        with pytest.raises(Exception):
            chart_routes.check_layout(bad)
    ok = chart_routes.check_layout({"count": 1, "slots": [{"symbol": "aapl", "interval": "7m", "range": "10Y", "x": 1}]})
    assert ok == {"count": 1, "slots": [{"symbol": "AAPL", "interval": "daily", "range": "6M"}]}


def test_an_account_keeps_at_most_twenty_chart_layouts(monkeypatch):
    assert chart_routes.MAX_LAYOUTS == 20
    monkeypatch.setattr(chart_routes, "MAX_LAYOUTS", 2)
    h = register(client, "charts@example.com")
    assert client.put("/api/chart/layouts/A", headers=h, json=TWO).status_code == 200
    assert client.put("/api/chart/layouts/B", headers=h, json=TWO).status_code == 200
    r = client.put("/api/chart/layouts/C", headers=h, json=TWO)
    assert r.status_code == 409 and "Delete one" in r.json()["detail"]
    assert client.put("/api/chart/layouts/B", headers=h, json=FOUR).status_code == 200, "replacing one is not a new one"


def test_favourite_intervals_are_kept_on_the_account_and_private():
    assert client.get("/api/chart/intervals").status_code == 401
    assert client.put("/api/chart/intervals", json={"intervals": ["1h"]}).status_code in (401, 403)
    h = register(client, "charts@example.com")
    assert client.get("/api/chart/intervals").json() == {"intervals": None}
    assert client.put("/api/chart/intervals", json={"intervals": ["5m"]}).status_code == 403, "no CSRF header"
    assert client.put("/api/chart/intervals", headers=h, json={"intervals": ["7m"]}).status_code == 400
    r = client.put("/api/chart/intervals", headers=h, json={"intervals": ["5m", "1h", "1d"]})
    assert r.json() == {"intervals": ["5m", "1h", "1d"]}
    register(other, "theirs@example.com")
    assert other.get("/api/chart/intervals").json() == {"intervals": None}, "another reader's favourites are their own"


class _Feed:
    name = "stub"

    def __init__(self, start="1999-01-22", listed=None):
        self.start, self.listed = start, listed

    def history(self, symbol, period="2y", interval="1d"):
        idx = pd.date_range(self.start, periods=30, freq="B")
        close = pd.Series([10 + i * 0.1 for i in range(30)], index=idx)
        df = pd.DataFrame({"Open": close, "High": close + 1, "Low": close - 1, "Close": close, "Volume": [1e6] * 30}, index=idx)
        if self.listed:
            df.attrs["first_trade_date"] = self.listed
        return df


def test_the_all_range_says_how_far_back_the_free_feed_goes(monkeypatch):
    monkeypatch.setattr(main, "YF_PROVIDER", _Feed(start="1999-01-22"))
    h = TestClient(main.app).get("/api/daily-bars/NVDA").json()["history"]
    assert h["first_bar"] == "1999-01-22" and h["adjusted"] == "split" and h["later_than_listing"] is False
    assert "starts on Jan 22, 1999" in h["sentence"] and "split-adjusted" in h["sentence"]


def test_a_first_bar_later_than_the_listing_is_said(monkeypatch):
    monkeypatch.setattr(main, "YF_PROVIDER", _Feed(start="2001-03-01", listed="1980-12-12"))
    h = TestClient(main.app).get("/api/daily-bars/AAPL").json()["history"]
    assert h["later_than_listing"] is True
    assert "AAPL listed on Dec 12, 1980, so the bars before Mar 1, 2001 are not in the free feed." in h["sentence"]


def test_no_bars_no_sentence():
    assert chart_routes.history_limit("X", [])["sentence"] == ""
    assert chart_routes.history_limit("X", ["2020-01-02"], adjusted="none")["sentence"] == \
        "X's history here starts on Jan 2, 2020, the first daily bar in Yahoo Finance's free daily history."


def test_health_names_the_chart_feeds_history_limit():
    body = TestClient(main.app).get("/api/health").json()
    ch = body["modes"]["chart_history"]
    assert ch["period"] == "max" and ch["adjusted"] == "split" and "first daily bar" in ch["limit"]

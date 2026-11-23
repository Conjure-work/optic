"""The brokerage line on /api/health says plainly whether SnapTrade is configured (round three, 2026-11-23).

On the evaluation copy no SnapTrade sandbox keys exist yet, so the brokerage flow is untested end to end there; the
health line is where that state is read from outside (docs/operations/brokerage-sandbox.md)."""

from fastapi.testclient import TestClient

from app import main
from app.brokerage import service

client = TestClient(main.app)

_VARS = ("BROKERAGE_PROVIDER", "SNAPTRADE_CLIENT_ID", "SNAPTRADE_CONSUMER_KEY", "SNAPTRADE_ENV")


def _clear(monkeypatch):
    for k in _VARS:
        monkeypatch.delenv(k, raising=False)


def test_with_nothing_set_health_says_off_and_snaptrade_not_configured(monkeypatch):
    _clear(monkeypatch)
    line = client.get("/api/health").json()["modes"]["brokerage"]
    assert line == {"provider": "off", "enabled": False, "snaptrade": "not configured"}


def test_snaptrade_chosen_without_its_keys_reads_not_configured_and_off(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BROKERAGE_PROVIDER", "snaptrade")
    line = service.health_mode()
    assert line["provider"] == "snaptrade" and line["snaptrade"] == "not configured" and line["enabled"] is False


def test_with_the_sandbox_pair_set_it_reads_configured_sandbox_and_never_the_values(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BROKERAGE_PROVIDER", "snaptrade")
    monkeypatch.setenv("SNAPTRADE_CLIENT_ID", "client-id-not-real")
    monkeypatch.setenv("SNAPTRADE_CONSUMER_KEY", "consumer-key-not-real")
    body = client.get("/api/health").text
    assert "not-real" not in body
    assert service.health_mode()["snaptrade"] == "configured (sandbox)"

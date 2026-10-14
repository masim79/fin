"""Tests for /api/health endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_health_method_not_allowed(client):
    resp = await client.post("/api/health")
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Test-support routes must stay off unless explicitly enabled (fin-b1a)
# ---------------------------------------------------------------------------


def test_test_support_disabled_by_default(monkeypatch):
    from app import testsupport

    monkeypatch.delenv("E2E_TEST_MODE", raising=False)
    assert testsupport.enabled() is False

    for value in ("false", "0", "", "TRUE_ISH", "yes"):
        monkeypatch.setenv("E2E_TEST_MODE", value)
        assert testsupport.enabled() is False, value


def test_test_support_enabled_only_by_exact_true(monkeypatch):
    from app import testsupport

    for value in ("true", "True", "TRUE"):
        monkeypatch.setenv("E2E_TEST_MODE", value)
        assert testsupport.enabled() is True, value


@pytest.mark.asyncio
async def test_reset_route_absent_in_a_normal_app(client):
    """The production app must not expose /api/test/reset at all."""
    resp = await client.post("/api/test/reset")
    assert resp.status_code == 404

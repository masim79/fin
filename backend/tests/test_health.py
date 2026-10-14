"""Tests for /api/health endpoint."""

import os

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
    """The production app must not expose /api/test/reset.

    Asserts the property that matters — the request is refused — rather than a
    specific status. The exact code depends on whether a static/ export is
    mounted: 404 from the router when it is absent, 405 from the StaticFiles
    catch-all (which serves GET/HEAD only) when it is present. Either way no
    reset route matched.
    """
    resp = await client.post("/api/test/reset")
    assert not resp.is_success, (
        f"/api/test/reset answered {resp.status_code} in a non-test app"
    )
    assert resp.status_code in (404, 405)


@pytest.mark.asyncio
async def test_reset_restores_seeded_state_when_enabled(db):
    """The gated route, when mounted, really does restore the seeded state."""
    import importlib

    from httpx import ASGITransport, AsyncClient

    import app.main as main_module
    from app.database import DEFAULT_TICKERS, get_db
    from app.market.cache import price_cache

    os.environ["E2E_TEST_MODE"] = "true"
    try:
        # Re-import so the conditional router mount is re-evaluated
        reloaded = importlib.reload(main_module)

        conn = await get_db()
        try:
            await conn.execute(
                "UPDATE users_profile SET cash_balance = 1.23 WHERE id = 'default'"
            )
            await conn.execute("DELETE FROM watchlist")
            await conn.commit()
        finally:
            await conn.close()

        price_cache.update("AAPL", 190.0)

        transport = ASGITransport(app=reloaded.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/api/test/reset")
            assert resp.status_code == 200

            portfolio = (await c.get("/api/portfolio")).json()
            assert portfolio["cash_balance"] == 10000.0
            assert portfolio["positions"] == []

            watchlist = (await c.get("/api/watchlist")).json()
            assert {w["ticker"] for w in watchlist} == set(DEFAULT_TICKERS)
    finally:
        os.environ.pop("E2E_TEST_MODE", None)
        importlib.reload(main_module)
        price_cache._prices.clear()

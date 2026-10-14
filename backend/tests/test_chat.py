"""Tests for the POST /api/chat endpoint in mock mode."""

import os

os.environ["LLM_MOCK"] = "true"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.market.cache import price_cache


@pytest.fixture(autouse=True)
def seed_prices():
    """Seed the price cache. Chat trades fill from here, not a constant."""
    price_cache.update("AAPL", 150.0)
    price_cache.update("TSLA", 250.0)
    price_cache.update("NFLX", 630.0)
    yield
    price_cache._prices.clear()


@pytest_asyncio.fixture
async def client(tmp_path):
    """Async test client with a fresh per-test SQLite DB."""
    import app.database as database

    db_file = str(tmp_path / "test.db")
    database.DB_PATH = db_file
    await database.init_db()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_chat_greeting(client):
    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "FinAlly" in data["message"]
    assert data["trades"] is None
    assert data["watchlist_changes"] is None


async def test_chat_buy_aapl(client):
    """Mock buy buys 10 shares of the matched ticker at the cached price."""
    resp = await client.post("/api/chat", json={"message": "buy some AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["trades"] is not None
    assert len(data["trades"]) == 1
    trade = data["trades"][0]
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == 10
    # No errors appended
    assert "Errors" not in data["message"]


async def test_chat_sell_insufficient(client):
    """Selling without owning shares should report error in message."""
    resp = await client.post("/api/chat", json={"message": "sell some AAPL"})
    assert resp.status_code == 200
    data = resp.json()
    # Upstream appends errors to message
    assert "Insufficient" in data["message"] or "Errors" in data["message"]


async def test_chat_buy_then_sell(client):
    """Buy then sell should succeed."""
    # Buy first (10 shares at the cached TSLA price)
    resp = await client.post("/api/chat", json={"message": "buy some TSLA"})
    data = resp.json()
    assert data["trades"][0]["ticker"] == "TSLA"
    assert "Errors" not in data["message"]

    # Sell (10 shares at avg cost)
    resp = await client.post("/api/chat", json={"message": "sell some TSLA"})
    data = resp.json()
    assert "Insufficient" not in data["message"]


async def test_chat_buy_insufficient_cash(client):
    """Buying more than cash allows should fail. AAPL is cached at $150, so
    10 shares = $1500 and we exhaust the $10k balance first."""
    # Buy 7 times: 7 * 10 * $150 = $10,500 > $10,000
    # First 6 buys: 6 * $1500 = $9000 (leaving $1000)
    for _ in range(6):
        await client.post("/api/chat", json={"message": "buy some AAPL"})

    # 7th buy: $1500 > $1000 remaining
    resp = await client.post("/api/chat", json={"message": "buy some AAPL"})
    data = resp.json()
    assert "Insufficient" in data["message"]


async def test_chat_watchlist_add(client):
    resp = await client.post("/api/chat", json={"message": "add PYPL to watchlist"})
    data = resp.json()
    assert data["watchlist_changes"] is not None
    assert data["watchlist_changes"][0]["ticker"] == "PYPL"
    assert data["watchlist_changes"][0]["action"] == "add"


async def test_chat_watchlist_remove(client):
    resp = await client.post("/api/chat", json={"message": "remove NFLX"})
    data = resp.json()
    assert data["watchlist_changes"] is not None
    assert data["watchlist_changes"][0]["ticker"] == "NFLX"
    assert data["watchlist_changes"][0]["action"] == "remove"


async def test_chat_portfolio_query(client):
    resp = await client.post("/api/chat", json={"message": "show my portfolio"})
    data = resp.json()
    assert "portfolio" in data["message"].lower()
    assert data["trades"] is None


async def test_chat_fallback(client):
    resp = await client.post("/api/chat", json={"message": "random nonsense xyz"})
    data = resp.json()
    assert "trade" in data["message"].lower() or "portfolio" in data["message"].lower()


async def test_chat_trade_fills_at_live_cache_price(client):
    """Regression (fin-b64): chat trades must fill at the live cached price,
    not a hardcoded $150 placeholder."""
    price_cache.update("AAPL", 321.5)

    resp = await client.post("/api/chat", json={"message": "buy some AAPL"})
    assert resp.status_code == 200
    assert "Errors" not in resp.json()["message"]

    portfolio = (await client.get("/api/portfolio")).json()
    position = next(p for p in portfolio["positions"] if p["ticker"] == "AAPL")
    assert position["avg_cost"] == 321.5
    # 10 shares at $321.50 — not at the old $150 placeholder
    assert portfolio["cash_balance"] == 10000.0 - (10 * 321.5)


async def test_chat_trade_without_price_reports_error(client):
    """A ticker with no cached price must surface an error, not fill at a guess."""
    price_cache._prices.clear()

    resp = await client.post("/api/chat", json={"message": "buy some AAPL"})
    assert resp.status_code == 200
    assert "No price available" in resp.json()["message"]

    portfolio = (await client.get("/api/portfolio")).json()
    assert portfolio["cash_balance"] == 10000.0
    assert portfolio["positions"] == []

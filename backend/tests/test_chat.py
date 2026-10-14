"""Tests for the POST /api/chat endpoint in mock mode."""

import json
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


# ---------------------------------------------------------------------------
# LLM response handling (fin-om1.3)
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


def _patch_llm(monkeypatch, content=None, exc=None):
    """Stub litellm.acompletion, capturing the kwargs chat.py sends."""
    from app import chat as chat_module

    captured = {}

    async def fake_acompletion(**kwargs):
        captured.update(kwargs)
        if exc is not None:
            raise exc
        return _FakeResponse(content)

    monkeypatch.setattr(chat_module, "acompletion", fake_acompletion)
    return captured


async def test_llm_request_pins_cerebras_and_json_schema(client, monkeypatch):
    """SPEC section 9: route to Cerebras and use a json_schema structured output."""
    monkeypatch.setenv("LLM_MOCK", "false")
    captured = _patch_llm(
        monkeypatch,
        content=json.dumps({"message": "Hi", "trades": None, "watchlist_changes": None}),
    )

    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Hi"

    assert captured["model"] == "openrouter/openai/gpt-oss-120b"
    assert captured["extra_body"]["provider"] == {
        "order": ["cerebras"],
        "allow_fallbacks": False,
    }

    fmt = captured["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    schema = fmt["json_schema"]["schema"]
    assert set(schema["required"]) == {"message", "trades", "watchlist_changes"}
    assert schema["properties"]["trades"]["items"]["properties"]["side"]["enum"] == [
        "buy",
        "sell",
    ]


async def test_llm_full_response_executes_actions(client, monkeypatch):
    """A valid full response auto-executes its trades."""
    monkeypatch.setenv("LLM_MOCK", "false")
    _patch_llm(
        monkeypatch,
        content=json.dumps(
            {
                "message": "Buying 2 AAPL.",
                "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 2}],
                "watchlist_changes": None,
            }
        ),
    )

    resp = await client.post("/api/chat", json={"message": "buy 2 aapl"})
    assert resp.status_code == 200

    portfolio = (await client.get("/api/portfolio")).json()
    position = next(p for p in portfolio["positions"] if p["ticker"] == "AAPL")
    assert position["quantity"] == 2
    assert position["avg_cost"] == 150.0


async def test_llm_message_only_response(client, monkeypatch):
    """message-only is valid: no trades, no watchlist changes."""
    monkeypatch.setenv("LLM_MOCK", "false")
    _patch_llm(monkeypatch, content=json.dumps({"message": "Your P&L is flat."}))

    resp = await client.post("/api/chat", json={"message": "how am i doing"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Your P&L is flat."
    assert data["trades"] is None

    assert (await client.get("/api/portfolio")).json()["positions"] == []


async def test_llm_malformed_response_degrades_gracefully(client, monkeypatch):
    """Non-JSON must not 500 — the prose is surfaced instead."""
    monkeypatch.setenv("LLM_MOCK", "false")
    _patch_llm(monkeypatch, content="I am not JSON at all.")

    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "I am not JSON at all."


async def test_llm_schema_violation_keeps_message_drops_actions(client, monkeypatch):
    """Valid JSON with a bad trades shape keeps the text and executes nothing."""
    monkeypatch.setenv("LLM_MOCK", "false")
    _patch_llm(
        monkeypatch,
        content=json.dumps({"message": "Here you go.", "trades": "not-an-array"}),
    )

    resp = await client.post("/api/chat", json={"message": "buy stuff"})
    assert resp.status_code == 200
    assert resp.json()["message"] == "Here you go."
    assert (await client.get("/api/portfolio")).json()["positions"] == []


async def test_llm_transport_error_degrades_gracefully(client, monkeypatch):
    """A provider/network failure becomes a chat message, not a 500."""
    monkeypatch.setenv("LLM_MOCK", "false")
    _patch_llm(monkeypatch, exc=RuntimeError("cerebras unavailable"))

    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    message = resp.json()["message"]
    assert "could not reach the model" in message
    # The raw provider exception must not reach the user's chat panel
    assert "cerebras unavailable" not in message


async def test_llm_mock_mode_makes_no_network_call(client, monkeypatch):
    """LLM_MOCK=true must short-circuit before any provider call."""
    monkeypatch.setenv("LLM_MOCK", "true")
    _patch_llm(monkeypatch, exc=AssertionError("acompletion must not be called"))

    resp = await client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    assert "FinAlly" in resp.json()["message"]

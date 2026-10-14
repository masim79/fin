"""Tests for the GBM market data simulator."""

import math

import numpy as np
import pytest

from app.market.simulator import (
    TICKER_CONFIG,
    TECH_TICKERS,
    FINANCE_TICKERS,
    _build_correlation_matrix,
    Simulator,
)
from app.market.cache import price_cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Keep the shared price cache from leaking between tests."""
    yield
    price_cache._prices.clear()


def test_ticker_config_has_required_fields():
    for ticker, cfg in TICKER_CONFIG.items():
        assert "seed" in cfg, f"{ticker} missing seed"
        assert "drift" in cfg, f"{ticker} missing drift"
        assert "vol" in cfg, f"{ticker} missing vol"
        assert cfg["seed"] > 0, f"{ticker} seed must be positive"
        assert cfg["vol"] > 0, f"{ticker} volatility must be positive"


def test_correlation_matrix_is_symmetric():
    tickers = list(TICKER_CONFIG.keys())
    corr = _build_correlation_matrix(tickers)
    np.testing.assert_array_almost_equal(corr, corr.T)


def test_correlation_matrix_has_ones_on_diagonal():
    tickers = list(TICKER_CONFIG.keys())
    corr = _build_correlation_matrix(tickers)
    np.testing.assert_array_almost_equal(np.diag(corr), np.ones(len(tickers)))


def test_correlation_matrix_tech_cluster():
    tickers = list(TICKER_CONFIG.keys())
    corr = _build_correlation_matrix(tickers)
    # Find two tech tickers
    i = tickers.index("AAPL")
    j = tickers.index("GOOGL")
    assert corr[i, j] == 0.6


def test_correlation_matrix_finance_cluster():
    tickers = list(TICKER_CONFIG.keys())
    corr = _build_correlation_matrix(tickers)
    i = tickers.index("JPM")
    j = tickers.index("V")
    assert corr[i, j] == 0.5


def test_correlation_matrix_cross_sector():
    tickers = list(TICKER_CONFIG.keys())
    corr = _build_correlation_matrix(tickers)
    i = tickers.index("AAPL")
    j = tickers.index("JPM")
    assert corr[i, j] == 0.2


def test_correlation_matrix_is_positive_definite():
    """A valid correlation matrix must be positive definite for Cholesky."""
    tickers = list(TICKER_CONFIG.keys())
    corr = _build_correlation_matrix(tickers)
    # Cholesky will raise if not positive definite
    np.linalg.cholesky(corr)


def test_simulator_initializes_with_seed_prices():
    sim = Simulator()
    for ticker, cfg in TICKER_CONFIG.items():
        assert sim._prices[ticker] == cfg["seed"]


def test_simulator_step_produces_valid_prices():
    sim = Simulator()
    sim._step()
    for ticker in TICKER_CONFIG:
        assert sim._prices[ticker] >= 0.01, f"{ticker} price below floor"


def test_simulator_step_changes_prices():
    """After stepping, at least some prices should have changed."""
    sim = Simulator()
    before = dict(sim._prices)
    sim._step()
    changed = sum(1 for t in TICKER_CONFIG if sim._prices[t] != before[t])
    assert changed > 0, "No prices changed after step"


def test_simulator_price_floor():
    """Prices should never go below 0.01."""
    sim = Simulator()
    # Force very low prices
    for ticker in sim._prices:
        sim._prices[ticker] = 0.02
    sim._step()
    for ticker in sim._prices:
        assert sim._prices[ticker] >= 0.01


# ---------------------------------------------------------------------------
# Dynamic ticker support (fin-dxo)
# ---------------------------------------------------------------------------


def test_add_ticker_outside_seeded_set_gets_priced():
    """A ticker with no TICKER_CONFIG entry must still be simulated."""
    sim = Simulator()
    assert "PYPL" not in sim._prices

    sim.add_ticker("PYPL")

    assert "PYPL" in sim._prices
    assert sim._prices["PYPL"] > 0
    # Published immediately so the watchlist/SSE have a price straight away
    assert price_cache.get("PYPL") is not None


def test_add_ticker_is_idempotent():
    sim = Simulator()
    sim.add_ticker("PYPL")
    price = sim._prices["PYPL"]

    sim.add_ticker("PYPL")
    sim.add_ticker("pypl")  # case-insensitive

    assert sim._tickers.count("PYPL") == 1
    assert sim._prices["PYPL"] == price


def test_added_ticker_advances_on_step():
    """The GBM step must cover added tickers, not just the seeded ones."""
    sim = Simulator()
    sim.add_ticker("PYPL")

    for _ in range(50):
        sim._step()

    assert price_cache.get("PYPL") is not None
    assert sim._prices["PYPL"] > 0


def test_added_ticker_keeps_correlation_matrix_valid():
    """Cholesky must stay decomposable as the ticker set grows."""
    sim = Simulator()
    for ticker in ("PYPL", "SHOP", "UBER", "ABNB"):
        sim.add_ticker(ticker)

    # Would raise LinAlgError if the matrix were not positive-definite
    sim._step()
    assert sim._cholesky.shape == (len(sim._tickers), len(sim._tickers))


def test_remove_ticker_stops_simulating_it():
    sim = Simulator()
    sim.add_ticker("PYPL")

    sim.remove_ticker("PYPL")

    assert "PYPL" not in sim._prices
    assert "PYPL" not in sim._tickers
    sim._step()  # must not KeyError


def test_remove_unknown_ticker_is_noop():
    sim = Simulator()
    before = len(sim._tickers)
    sim.remove_ticker("NOPE")
    assert len(sim._tickers) == before


def test_seed_price_is_stable_for_a_symbol():
    """Same symbol derives the same seed price, so adds are not jumpy."""
    a, b = Simulator(), Simulator()
    a.add_ticker("PYPL")
    b.add_ticker("PYPL")
    assert a._prices["PYPL"] == b._prices["PYPL"]


def test_step_with_no_tickers_does_not_raise():
    sim = Simulator()
    for ticker in list(sim._tickers):
        sim.remove_ticker(ticker)
    sim._step()


# ---------------------------------------------------------------------------
# Watchlist -> provider wiring (fin-dxo)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchlist_add_starts_streaming_the_ticker(client, monkeypatch):
    """POST /api/watchlist must make a non-seeded ticker start streaming."""
    import app.market.provider as provider_module

    sim = Simulator()
    monkeypatch.setattr(provider_module, "_provider", sim)

    assert price_cache.get("PYPL") is None

    resp = await client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert resp.status_code == 200
    # The add response itself already carries a price
    assert resp.json()["price"] is not None

    assert "PYPL" in sim._prices
    assert price_cache.get("PYPL") is not None

    # And it shows up in the stream payload
    assert "PYPL" in {u.ticker for u in price_cache.get_all()}


@pytest.mark.asyncio
async def test_watchlist_remove_stops_streaming_the_ticker(client, monkeypatch):
    import app.market.provider as provider_module

    sim = Simulator()
    monkeypatch.setattr(provider_module, "_provider", sim)

    await client.post("/api/watchlist", json={"ticker": "PYPL"})
    assert "PYPL" in sim._prices

    resp = await client.delete("/api/watchlist/PYPL")
    assert resp.status_code == 200
    assert "PYPL" not in sim._prices


@pytest.mark.asyncio
async def test_removing_watchlist_entry_keeps_pricing_held_position(client, monkeypatch):
    """A position still needs a price for P&L even once un-watched."""
    import app.market.provider as provider_module

    sim = Simulator()
    monkeypatch.setattr(provider_module, "_provider", sim)

    await client.post("/api/watchlist", json={"ticker": "PYPL"})
    buy = await client.post(
        "/api/portfolio/trade",
        json={"ticker": "PYPL", "quantity": 1, "side": "buy"},
    )
    assert buy.status_code == 200

    await client.delete("/api/watchlist/PYPL")

    # Still priced, because the portfolio holds it
    assert "PYPL" in sim._prices

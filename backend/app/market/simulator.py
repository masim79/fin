"""Geometric Brownian Motion market data simulator."""

import asyncio
import hashlib
import math
import random

import numpy as np

from app.market.cache import price_cache
from app.market.interface import MarketDataProvider

# Seed prices and per-ticker parameters (annual drift, annual volatility)
TICKER_CONFIG = {
    "AAPL": {"seed": 190.0, "drift": 0.08, "vol": 0.25},
    "GOOGL": {"seed": 175.0, "drift": 0.10, "vol": 0.28},
    "MSFT": {"seed": 420.0, "drift": 0.09, "vol": 0.24},
    "AMZN": {"seed": 185.0, "drift": 0.12, "vol": 0.30},
    "TSLA": {"seed": 250.0, "drift": 0.05, "vol": 0.50},
    "NVDA": {"seed": 880.0, "drift": 0.15, "vol": 0.40},
    "META": {"seed": 500.0, "drift": 0.10, "vol": 0.32},
    "JPM": {"seed": 195.0, "drift": 0.06, "vol": 0.20},
    "V": {"seed": 280.0, "drift": 0.07, "vol": 0.18},
    "NFLX": {"seed": 630.0, "drift": 0.11, "vol": 0.35},
}

# Correlation matrix sectors: tech stocks correlated, finance separate
TECH_TICKERS = ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA", "NVDA", "META", "NFLX"]
FINANCE_TICKERS = ["JPM", "V"]

# Parameters for tickers outside the seeded set (user/LLM watchlist additions).
# The seed price is derived from the symbol so a given ticker always starts at
# the same price within a process, instead of jumping around on each add.
DEFAULT_DRIFT = 0.08
DEFAULT_VOL = 0.30
DEFAULT_SEED_MIN = 20.0
DEFAULT_SEED_MAX = 400.0

UPDATE_INTERVAL = 0.5  # seconds
EVENT_PROBABILITY = 0.005  # per ticker per update
EVENT_MIN_PCT = 0.02
EVENT_MAX_PCT = 0.05


def _config_for(ticker: str) -> dict:
    """Return GBM parameters for a ticker, deriving them if it is not seeded."""
    known = TICKER_CONFIG.get(ticker)
    if known is not None:
        return known

    # Deterministic pseudo-random seed price from the symbol itself.
    digest = hashlib.sha256(ticker.encode()).digest()
    fraction = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
    seed = DEFAULT_SEED_MIN + fraction * (DEFAULT_SEED_MAX - DEFAULT_SEED_MIN)
    return {"seed": round(seed, 2), "drift": DEFAULT_DRIFT, "vol": DEFAULT_VOL}


def _build_correlation_matrix(tickers: list[str]) -> np.ndarray:
    """Build a correlation matrix with tech and finance clusters."""
    n = len(tickers)
    corr = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            ti, tj = tickers[i], tickers[j]
            if ti in TECH_TICKERS and tj in TECH_TICKERS:
                corr[i, j] = corr[j, i] = 0.6
            elif ti in FINANCE_TICKERS and tj in FINANCE_TICKERS:
                corr[i, j] = corr[j, i] = 0.5
            else:
                corr[i, j] = corr[j, i] = 0.2
    return corr


class Simulator(MarketDataProvider):
    """GBM-based market data simulator."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._tickers = list(TICKER_CONFIG.keys())
        self._prices = {t: cfg["seed"] for t, cfg in TICKER_CONFIG.items()}
        self._dt = UPDATE_INTERVAL / (252 * 6.5 * 3600)  # fraction of trading year
        self._rebuild_cholesky()

    def _rebuild_cholesky(self) -> None:
        """Recompute the Cholesky factor used for correlated random draws.

        Called on construction and whenever the ticker set changes.
        """
        corr = _build_correlation_matrix(self._tickers)
        self._cholesky = np.linalg.cholesky(corr)

    def add_ticker(self, ticker: str) -> None:
        """Start simulating `ticker`, seeding it and publishing a first price."""
        ticker = ticker.upper().strip()
        if not ticker or ticker in self._prices:
            return

        cfg = _config_for(ticker)
        self._tickers.append(ticker)
        self._prices[ticker] = cfg["seed"]
        self._rebuild_cholesky()
        # Publish immediately so the watchlist response and SSE stream have a
        # price without waiting for the next tick.
        price_cache.update(ticker, cfg["seed"])

    def remove_ticker(self, ticker: str) -> None:
        """Stop simulating `ticker`."""
        ticker = ticker.upper().strip()
        if ticker not in self._prices:
            return
        self._tickers.remove(ticker)
        del self._prices[ticker]
        self._rebuild_cholesky()

    async def start(self) -> None:
        """Start the simulation loop."""
        # Seed initial prices into cache
        for ticker, price in self._prices.items():
            price_cache.update(ticker, price)
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop the simulation loop."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run(self) -> None:
        """Main simulation loop."""
        while True:
            self._step()
            await asyncio.sleep(UPDATE_INTERVAL)

    def _step(self) -> None:
        """Advance all prices by one GBM step with correlation."""
        n = len(self._tickers)
        if n == 0:
            return
        # Correlated normal draws
        z_independent = np.random.standard_normal(n)
        z_correlated = self._cholesky @ z_independent

        for i, ticker in enumerate(self._tickers):
            cfg = _config_for(ticker)
            drift = cfg["drift"]
            vol = cfg["vol"]
            s = self._prices[ticker]

            # GBM: dS = S * (mu*dt + sigma*sqrt(dt)*Z)
            ds = s * (drift * self._dt + vol * math.sqrt(self._dt) * z_correlated[i])
            new_price = s + ds

            # Random event: sudden 2-5% move
            if random.random() < EVENT_PROBABILITY:
                pct = random.uniform(EVENT_MIN_PCT, EVENT_MAX_PCT)
                sign = random.choice([-1, 1])
                new_price *= 1 + sign * pct

            new_price = max(new_price, 0.01)  # floor at 1 cent
            self._prices[ticker] = new_price
            price_cache.update(ticker, new_price)

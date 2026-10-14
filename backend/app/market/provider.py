"""Environment-driven market data provider selection."""

import os

from app.market.interface import MarketDataProvider

# The single live provider for this process. Set by create_provider() during
# app startup and read by request handlers that need to change the ticker set.
_provider: MarketDataProvider | None = None


def create_provider() -> MarketDataProvider:
    """Create the appropriate provider based on environment and record it."""
    global _provider

    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()

    if api_key:
        from app.database import DEFAULT_TICKERS
        from app.market.massive import MassiveClient

        _provider = MassiveClient(tickers=list(DEFAULT_TICKERS))
    else:
        from app.market.simulator import Simulator

        _provider = Simulator()

    return _provider


def get_provider() -> MarketDataProvider | None:
    """Return the live provider, or None if the app has not started one."""
    return _provider

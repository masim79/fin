"""Abstract market data provider interface."""

from abc import ABC, abstractmethod


class MarketDataProvider(ABC):
    """Abstract base for market data providers."""

    @abstractmethod
    async def start(self) -> None:
        """Start producing price updates."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop producing price updates."""

    @abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """Begin producing price updates for `ticker`.

        Must be idempotent — adding a ticker already being priced is a no-op.
        Called when a ticker is added to the watchlist so that tickers outside
        the default seeded set still stream (SPEC section 6).
        """

    @abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """Stop producing price updates for `ticker`. Idempotent."""

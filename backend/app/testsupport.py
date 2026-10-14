"""Test-support endpoints, disabled unless E2E_TEST_MODE=true.

FinAlly is deliberately single-user with server-side state, so E2E tests
sharing one container would otherwise leak state into each other and could not
assert the concrete values PLAN.md section 12 calls for (the $10,000 opening
balance, an empty heatmap before the first trade). This router gives the suite
a way to start each test from the seeded state.

It is mounted only when E2E_TEST_MODE is explicitly "true", which is set in
test/docker-compose.test.yml and nowhere else. In a normal run the routes do
not exist at all.
"""

import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.database import DEFAULT_TICKERS, get_db, init_db
from app.market.cache import price_cache
from app.market.provider import get_provider

router = APIRouter(prefix="/api/test")

# Tables wiped by a reset. users_profile and watchlist are re-seeded by init_db.
_TABLES = (
    "trades",
    "positions",
    "portfolio_snapshots",
    "chat_messages",
    "watchlist",
    "users_profile",
)


def enabled() -> bool:
    """True when test-support routes should be exposed."""
    return os.environ.get("E2E_TEST_MODE", "").lower() == "true"


@router.post("/reset")
async def reset():
    """Restore the database to its freshly seeded state."""
    db = await get_db()
    try:
        for table in _TABLES:
            await db.execute(f"DELETE FROM {table}")
        await db.commit()
    finally:
        await db.close()

    # Re-create the default profile and watchlist
    await init_db()

    # Drop prices for anything no longer watched so the heatmap and watchlist
    # agree with the reset DB, then make sure the defaults stream again.
    provider = get_provider()
    for ticker in list(price_cache._prices):
        if ticker not in DEFAULT_TICKERS:
            price_cache._prices.pop(ticker, None)
            if provider is not None:
                provider.remove_ticker(ticker)

    if provider is not None:
        for ticker in DEFAULT_TICKERS:
            provider.add_ticker(ticker)

    return JSONResponse({"ok": True})

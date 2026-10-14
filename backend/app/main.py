"""FastAPI application entry point."""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.chat import router as chat_router
from app.database import init_db, load_watchlist_tickers
from app.market.provider import create_provider
from app.market.stream import router as stream_router
from app.portfolio import router as portfolio_router
from app import testsupport
from app.watchlist import router as watchlist_router
from app.snapshots import start_snapshot_recorder, stop_snapshot_recorder


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database, start market data provider and snapshot recorder."""
    await init_db()
    provider = create_provider()

    # Price every ticker already on the watchlist, not just the seeded
    # defaults, so tickers the user added in an earlier run still stream.
    for ticker in await load_watchlist_tickers():
        provider.add_ticker(ticker)

    await provider.start()
    start_snapshot_recorder()
    yield
    stop_snapshot_recorder()
    await provider.stop()


app = FastAPI(title="FinAlly", lifespan=lifespan)
app.include_router(chat_router)

app.include_router(stream_router)
app.include_router(portfolio_router)
app.include_router(watchlist_router)


# Test-support routes, present only when E2E_TEST_MODE=true (see testsupport).
if testsupport.enabled():
    app.include_router(testsupport.router)


@app.get("/api/health")
async def health():
    return JSONResponse({"status": "ok"})


# Serve static files (Next.js export) at root, if the directory exists
static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

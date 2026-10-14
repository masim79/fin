"""Tests for database initialization and schema."""

import os

import pytest
import aiosqlite

from app.database import DB_PATH, DEFAULT_TICKERS, get_db, init_db


@pytest.mark.asyncio
async def test_schema_creates_all_tables(db):
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in await cursor.fetchall()]
        expected = [
            "chat_messages",
            "portfolio_snapshots",
            "positions",
            "trades",
            "users_profile",
            "watchlist",
        ]
        assert tables == expected
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_seed_creates_default_user(db):
    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT id, cash_balance FROM users_profile")
        row = await cursor.fetchone()
        assert row is not None
        assert row[0] == "default"
        assert row[1] == 10000.0
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_seed_creates_default_watchlist(db):
    conn = await get_db()
    try:
        cursor = await conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id='default' ORDER BY ticker"
        )
        tickers = [row[0] for row in await cursor.fetchall()]
        assert tickers == sorted(DEFAULT_TICKERS)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_init_db_is_idempotent(db):
    """Running init_db twice should not duplicate seed data."""
    await init_db()
    conn = await get_db()
    try:
        cursor = await conn.execute("SELECT COUNT(*) FROM users_profile")
        row = await cursor.fetchone()
        assert row[0] == 1

        cursor = await conn.execute("SELECT COUNT(*) FROM watchlist")
        row = await cursor.fetchone()
        assert row[0] == len(DEFAULT_TICKERS)
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_wal_mode_enabled(db):
    conn = await get_db()
    try:
        cursor = await conn.execute("PRAGMA journal_mode")
        row = await cursor.fetchone()
        assert row[0] == "wal"
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_positions_table_unique_constraint(db):
    conn = await get_db()
    try:
        await conn.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES ('p1', 'default', 'AAPL', 10, 150.0, '2026-01-01T00:00:00Z')"
        )
        await conn.commit()
        with pytest.raises(aiosqlite.IntegrityError):
            await conn.execute(
                "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                "VALUES ('p2', 'default', 'AAPL', 5, 155.0, '2026-01-01T00:00:00Z')"
            )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_trades_table_accepts_buy_and_sell(db):
    conn = await get_db()
    try:
        await conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES ('t1', 'default', 'AAPL', 'buy', 10, 150.0, '2026-01-01T00:00:00Z')"
        )
        await conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES ('t2', 'default', 'AAPL', 'sell', 5, 160.0, '2026-01-01T00:00:00Z')"
        )
        await conn.commit()

        cursor = await conn.execute("SELECT COUNT(*) FROM trades")
        row = await cursor.fetchone()
        assert row[0] == 2
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# DB file location (fin-om1.2)
# ---------------------------------------------------------------------------


def test_default_db_path_is_project_root_db_dir():
    """The default must sit in <project root>/db, which is the Docker volume
    mount target (/app/db), and must NOT depend on the working directory."""
    import app.database as database

    expected = database._PROJECT_ROOT / "db" / "finally.db"
    assert database._DEFAULT_DB_PATH == expected
    # backend/app/database.py -> project root holds backend/ and db/
    assert (database._PROJECT_ROOT / "backend").is_dir()


def test_default_db_path_is_absolute_and_cwd_independent(tmp_path, monkeypatch):
    """Regression: a relative default resolved against /app/backend in the
    container, writing outside the mounted volume."""
    import app.database as database

    assert os.path.isabs(str(database._DEFAULT_DB_PATH))

    monkeypatch.chdir(tmp_path)
    from pathlib import Path

    recomputed = Path(database.__file__).resolve().parent.parent.parent / "db" / "finally.db"
    assert recomputed == database._DEFAULT_DB_PATH


def test_db_path_env_var_overrides_default(monkeypatch):
    """The Dockerfile sets DB_PATH=/app/db/finally.db explicitly."""
    import importlib

    monkeypatch.setenv("DB_PATH", "/tmp/custom/finally.db")
    import app.database as database

    reloaded = importlib.reload(database)
    try:
        assert reloaded.DB_PATH == "/tmp/custom/finally.db"
    finally:
        monkeypatch.delenv("DB_PATH", raising=False)
        importlib.reload(database)


@pytest.mark.asyncio
async def test_data_survives_reopening_the_same_file(tmp_path):
    """Stand-in for a container restart: state must persist in the DB file."""
    import importlib

    import app.database as database

    db_file = str(tmp_path / "persist.db")
    original = database.DB_PATH
    database.DB_PATH = db_file
    try:
        await database.init_db()

        db = await database.get_db()
        await db.execute(
            "UPDATE users_profile SET cash_balance = 4242.0 WHERE id = 'default'"
        )
        await db.commit()
        await db.close()

        # Re-run lazy init exactly as a fresh process would
        await database.init_db()
        db = await database.get_db()
        cursor = await db.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        )
        row = await cursor.fetchone()
        await db.close()

        assert row["cash_balance"] == 4242.0
    finally:
        database.DB_PATH = original
        importlib.reload(database)

import aiosqlite
from pathlib import Path
from loguru import logger

DB_PATH = Path("data/scalping_bot.db")


async def init_database() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    await db.execute("PRAGMA journal_mode=WAL")
    await _create_tables(db)
    logger.info(f"Base de donnees initialisee: {DB_PATH}")
    return db


async def _create_tables(db: aiosqlite.Connection) -> None:
    await db.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            side TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            size REAL NOT NULL,
            pnl_usdt REAL,
            pnl_percent REAL,
            duration_s REAL,
            reason TEXT,
            timestamp_open TEXT NOT NULL,
            timestamp_close TEXT
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            side TEXT NOT NULL,
            rsi REAL NOT NULL,
            ema_distance REAL NOT NULL,
            volume_ratio REAL NOT NULL,
            spread REAL NOT NULL,
            triggered INTEGER NOT NULL DEFAULT 0
        )
    """)
    await db.execute("""
        CREATE TABLE IF NOT EXISTS bot_stats (
            date TEXT PRIMARY KEY,
            total_trades INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            win_rate REAL NOT NULL DEFAULT 0.0,
            total_pnl REAL NOT NULL DEFAULT 0.0,
            max_drawdown REAL NOT NULL DEFAULT 0.0,
            sharpe_ratio REAL NOT NULL DEFAULT 0.0
        )
    """)
    await db.commit()


async def insert_trade(db: aiosqlite.Connection, trade: dict) -> int:
    cursor = await db.execute("""
        INSERT INTO trades (pair, side, entry_price, exit_price, size, pnl_usdt, pnl_percent, duration_s, reason, timestamp_open, timestamp_close)
        VALUES (:pair, :side, :entry_price, :exit_price, :size, :pnl_usdt, :pnl_percent, :duration_s, :reason, :timestamp_open, :timestamp_close)
    """, trade)
    await db.commit()
    return cursor.lastrowid


async def insert_signal(db: aiosqlite.Connection, signal: dict) -> int:
    cursor = await db.execute("""
        INSERT INTO signals (pair, timestamp, side, rsi, ema_distance, volume_ratio, spread, triggered)
        VALUES (:pair, :timestamp, :side, :rsi, :ema_distance, :volume_ratio, :spread, :triggered)
    """, signal)
    await db.commit()
    return cursor.lastrowid


async def update_daily_stats(db: aiosqlite.Connection, stats: dict) -> None:
    await db.execute("""
        INSERT INTO bot_stats (date, total_trades, wins, losses, win_rate, total_pnl, max_drawdown, sharpe_ratio)
        VALUES (:date, :total_trades, :wins, :losses, :win_rate, :total_pnl, :max_drawdown, :sharpe_ratio)
        ON CONFLICT(date) DO UPDATE SET
            total_trades = :total_trades,
            wins = :wins,
            losses = :losses,
            win_rate = :win_rate,
            total_pnl = :total_pnl,
            max_drawdown = :max_drawdown,
            sharpe_ratio = :sharpe_ratio
    """, stats)
    await db.commit()


async def get_open_trades(db: aiosqlite.Connection) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM trades WHERE exit_price IS NULL"
    )
    columns = [desc[0] for desc in cursor.description]
    rows = await cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]


async def get_daily_trades(db: aiosqlite.Connection, date: str) -> list[dict]:
    cursor = await db.execute(
        "SELECT * FROM trades WHERE timestamp_open LIKE :date_prefix",
        {"date_prefix": f"{date}%"}
    )
    columns = [desc[0] for desc in cursor.description]
    rows = await cursor.fetchall()
    return [dict(zip(columns, row)) for row in rows]

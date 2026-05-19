# Scalping Bot Phase 1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a production-ready crypto scalping bot core engine with pipeline architecture, multi-confirmation strategy, risk management, and dry-run mode.

**Architecture:** Event-driven pipeline using `asyncio.Queue` to connect components (DataFeed → Strategy → RiskManager → OrderExecutor → PnLTracker). Each component runs as an independent coroutine. Dual mode: dry-run (local simulation) and live (ccxt.pro WebSocket to Binance Futures testnet).

**Tech Stack:** Python 3.11+, ccxt/ccxt.pro, pandas + pandas-ta, aiosqlite, loguru, pyyaml, python-dotenv, pytest + pytest-asyncio

---

## File Structure

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Project metadata and dependencies |
| `.gitignore` | Ignore secrets, venv, db files, __pycache__ |
| `.env.example` | Template for API keys |
| `config/config.yaml` | Bot configuration (pairs, risk, timeframe) |
| `models/__init__.py` | Package init |
| `models/events.py` | All dataclasses for inter-component communication |
| `db/__init__.py` | Package init |
| `db/models.py` | Database schema, init, CRUD operations |
| `core/__init__.py` | Package init |
| `core/data_feed.py` | WebSocket data ingestion + indicator calculation |
| `core/strategy.py` | Signal generation (entry/exit conditions) |
| `core/risk_manager.py` | Position sizing, drawdown checks, approval |
| `core/order_executor.py` | Order placement, position monitoring, dry-run sim |
| `core/pnl_tracker.py` | PnL calculation, stats, DB persistence |
| `main.py` | Entrypoint, pipeline orchestration, shutdown |
| `tests/test_strategy.py` | Strategy unit tests |
| `tests/test_risk_manager.py` | Risk manager unit tests |
| `tests/test_pnl_tracker.py` | PnL tracker unit tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config/config.yaml`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "scalping-bot"
version = "0.1.0"
description = "Bot de scalping automatique pour crypto (Binance Futures)"
requires-python = ">=3.11"
dependencies = [
    "ccxt>=4.0",
    "pandas>=2.0",
    "pandas-ta>=0.3",
    "aiosqlite>=0.19",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "loguru>=0.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
]

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.backends._legacy:_Backend"
```

- [ ] **Step 2: Create .gitignore**

```
__pycache__/
*.pyc
.env
secrets.env
config/secrets.env
*.db
.venv/
venv/
dist/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 3: Create .env.example**

```env
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET=your_secret_here
```

- [ ] **Step 4: Create config/config.yaml**

```yaml
exchange: binance
testnet: true
dry_run: true
pairs:
  - BTC/USDT
  - ETH/USDT
timeframe: 1m
capital_usdt: 1000
risk_per_trade_percent: 1.0
max_drawdown_percent: 15.0
daily_drawdown_limit: 5.0
leverage: 5
max_open_positions: 3
take_profit_percent: 0.3
stop_loss_percent: 0.15
trailing_stop: true
trailing_activation_percent: 0.2
timeout_seconds: 300
slippage_percent: 0.01
fees_percent: 0.04
```

- [ ] **Step 5: Create package init files**

Create empty `__init__.py` files:
- `models/__init__.py`
- `db/__init__.py`
- `core/__init__.py`
- `tests/__init__.py`

- [ ] **Step 6: Install dependencies and verify**

Run: `pip install -e ".[dev]"`
Expected: Successful installation of all packages

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example config/config.yaml models/__init__.py db/__init__.py core/__init__.py tests/__init__.py
git commit -m "feat: scaffold project structure with dependencies and config"
```

---

## Task 2: Event Models

**Files:**
- Create: `models/events.py`

- [ ] **Step 1: Create models/events.py with all dataclasses**

```python
from dataclasses import dataclass, field
from typing import Literal
import time


@dataclass(frozen=True)
class MarketData:
    timestamp: float
    pair: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    bid: float
    ask: float
    rsi: float
    rsi_prev: float
    ema: float
    volume_ratio: float

    @property
    def spread_percent(self) -> float:
        if self.bid == 0:
            return float("inf")
        return ((self.ask - self.bid) / self.bid) * 100


@dataclass(frozen=True)
class Signal:
    timestamp: float
    pair: str
    side: Literal["LONG", "SHORT"]
    entry_price: float
    rsi: float
    ema_distance: float
    volume_ratio: float
    spread: float


@dataclass(frozen=True)
class OrderRequest:
    signal: Signal
    size: float
    entry_price: float
    stop_loss: float
    take_profit: float


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    pair: str
    side: Literal["LONG", "SHORT"]
    fill_price: float
    size: float
    stop_loss: float
    take_profit: float
    status: Literal["filled", "partial", "failed"]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class TradeClose:
    order_id: str
    pair: str
    side: Literal["LONG", "SHORT"]
    entry_price: float
    exit_price: float
    size: float
    pnl_usdt: float
    pnl_percent: float
    duration_s: float
    reason: Literal["TP", "SL", "TIMEOUT", "TRAILING"]
    timestamp: float = field(default_factory=time.time)
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from models.events import MarketData, Signal, OrderRequest, OrderResult, TradeClose; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add models/events.py
git commit -m "feat: add event dataclasses for pipeline communication"
```

---

## Task 3: Database Layer

**Files:**
- Create: `db/models.py`

- [ ] **Step 1: Create db/models.py**

```python
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
```

- [ ] **Step 2: Verify database initialization**

Run: `python -c "import asyncio; from db.models import init_database; asyncio.run(init_database()); print('DB OK')"`
Expected: `DB OK` and `data/scalping_bot.db` created

- [ ] **Step 3: Add data/ to .gitignore**

Append `data/` to `.gitignore`.

- [ ] **Step 4: Commit**

```bash
git add db/models.py .gitignore
git commit -m "feat: add SQLite database layer with trades, signals, and stats tables"
```

---

## Task 4: Strategy — Tests First

**Files:**
- Create: `tests/test_strategy.py`
- Create: `core/strategy.py`

- [ ] **Step 1: Write failing tests for strategy**

```python
import pytest
from models.events import MarketData, Signal
from core.strategy import ScalpingStrategy


def make_market_data(
    pair="BTC/USDT",
    close=50000.0,
    rsi=30.0,
    rsi_prev=28.0,
    ema=49900.0,
    volume_ratio=1.8,
    bid=49999.0,
    ask=50001.0,
) -> MarketData:
    return MarketData(
        timestamp=1000.0,
        pair=pair,
        open=49950.0,
        high=50050.0,
        low=49900.0,
        close=close,
        volume=100.0,
        bid=bid,
        ask=ask,
        rsi=rsi,
        rsi_prev=rsi_prev,
        ema=ema,
        volume_ratio=volume_ratio,
    )


class TestLongSignal:
    def setup_method(self):
        self.strategy = ScalpingStrategy()

    def test_long_signal_all_conditions_met(self):
        """Signal LONG emis quand toutes les 5 conditions sont vraies."""
        data = make_market_data(
            rsi=33.0, rsi_prev=30.0, close=50000.0, ema=49900.0,
            volume_ratio=1.8, bid=49999.0, ask=50001.0
        )
        signal = self.strategy.evaluate(data)
        assert signal is not None
        assert signal.side == "LONG"
        assert signal.pair == "BTC/USDT"

    def test_no_signal_rsi_too_high(self):
        """Pas de signal si RSI >= 35."""
        data = make_market_data(rsi=40.0, rsi_prev=38.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_rsi_not_rising(self):
        """Pas de signal si RSI ne remonte pas."""
        data = make_market_data(rsi=30.0, rsi_prev=32.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_price_below_ema(self):
        """Pas de signal si prix < EMA."""
        data = make_market_data(close=49800.0, ema=49900.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_low_volume(self):
        """Pas de signal si volume_ratio < 1.5."""
        data = make_market_data(volume_ratio=1.2)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_high_spread(self):
        """Pas de signal si spread > 0.05%."""
        data = make_market_data(bid=49900.0, ask=49950.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_position_already_open(self):
        """Pas de signal si position deja ouverte sur la paire."""
        data = make_market_data()
        self.strategy.open_positions.add("BTC/USDT")
        signal = self.strategy.evaluate(data)
        assert signal is None


class TestShortSignal:
    def setup_method(self):
        self.strategy = ScalpingStrategy()

    def test_short_signal_all_conditions_met(self):
        """Signal SHORT emis avec conditions symetriques."""
        data = make_market_data(
            rsi=68.0, rsi_prev=70.0, close=49800.0, ema=49900.0,
            volume_ratio=1.8, bid=49799.0, ask=49801.0
        )
        signal = self.strategy.evaluate(data)
        assert signal is not None
        assert signal.side == "SHORT"

    def test_no_short_signal_rsi_too_low(self):
        """Pas de signal SHORT si RSI <= 65."""
        data = make_market_data(
            rsi=60.0, rsi_prev=62.0, close=49800.0, ema=49900.0,
            volume_ratio=1.8, bid=49799.0, ask=49801.0
        )
        signal = self.strategy.evaluate(data)
        assert signal is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_strategy.py -v`
Expected: FAIL — `ImportError: cannot import name 'ScalpingStrategy' from 'core.strategy'`

- [ ] **Step 3: Implement core/strategy.py**

```python
from models.events import MarketData, Signal
from loguru import logger


class ScalpingStrategy:
    def __init__(
        self,
        rsi_long_threshold: float = 35.0,
        rsi_short_threshold: float = 65.0,
        volume_ratio_min: float = 1.5,
        spread_max_percent: float = 0.05,
    ):
        self.rsi_long_threshold = rsi_long_threshold
        self.rsi_short_threshold = rsi_short_threshold
        self.volume_ratio_min = volume_ratio_min
        self.spread_max_percent = spread_max_percent
        self.open_positions: set[str] = set()

    def evaluate(self, data: MarketData) -> Signal | None:
        if data.pair in self.open_positions:
            return None

        if data.spread_percent > self.spread_max_percent:
            return None

        if data.volume_ratio < self.volume_ratio_min:
            return None

        long_signal = self._check_long(data)
        if long_signal:
            return long_signal

        short_signal = self._check_short(data)
        if short_signal:
            return short_signal

        return None

    def _check_long(self, data: MarketData) -> Signal | None:
        if data.rsi >= self.rsi_long_threshold:
            return None
        if data.rsi <= data.rsi_prev:
            return None
        if data.close <= data.ema:
            return None

        logger.info(f"Signal LONG {data.pair} | RSI={data.rsi:.1f} vol_ratio={data.volume_ratio:.2f}")
        return Signal(
            timestamp=data.timestamp,
            pair=data.pair,
            side="LONG",
            entry_price=data.close,
            rsi=data.rsi,
            ema_distance=((data.close - data.ema) / data.ema) * 100,
            volume_ratio=data.volume_ratio,
            spread=data.spread_percent,
        )

    def _check_short(self, data: MarketData) -> Signal | None:
        if data.rsi <= self.rsi_short_threshold:
            return None
        if data.rsi >= data.rsi_prev:
            return None
        if data.close >= data.ema:
            return None

        logger.info(f"Signal SHORT {data.pair} | RSI={data.rsi:.1f} vol_ratio={data.volume_ratio:.2f}")
        return Signal(
            timestamp=data.timestamp,
            pair=data.pair,
            side="SHORT",
            entry_price=data.close,
            rsi=data.rsi,
            ema_distance=((data.ema - data.close) / data.ema) * 100,
            volume_ratio=data.volume_ratio,
            spread=data.spread_percent,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_strategy.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/strategy.py tests/test_strategy.py
git commit -m "feat: implement scalping strategy with multi-confirmation signals"
```

---

## Task 5: Risk Manager — Tests First

**Files:**
- Create: `tests/test_risk_manager.py`
- Create: `core/risk_manager.py`

- [ ] **Step 1: Write failing tests for risk manager**

```python
import pytest
from models.events import Signal, OrderRequest
from core.risk_manager import RiskManager


def make_signal(pair="BTC/USDT", side="LONG", entry_price=50000.0) -> Signal:
    return Signal(
        timestamp=1000.0,
        pair=pair,
        side=side,
        entry_price=entry_price,
        rsi=30.0,
        ema_distance=0.2,
        volume_ratio=1.8,
        spread=0.003,
    )


class TestPositionSizing:
    def setup_method(self):
        self.rm = RiskManager(
            capital=1000.0,
            risk_per_trade_percent=1.0,
            max_drawdown_percent=15.0,
            daily_drawdown_limit=5.0,
            max_open_positions=3,
            leverage=5,
            stop_loss_percent=0.15,
            take_profit_percent=0.3,
        )

    def test_calculate_size(self):
        """Taille = (capital * risk%) / (price * SL%)."""
        size = self.rm.calculate_size(50000.0)
        # (1000 * 0.01) / (50000 * 0.0015) = 10 / 75 = 0.1333...
        assert abs(size - 0.13333) < 0.001

    def test_approve_normal_conditions(self):
        """Approuve un signal dans des conditions normales."""
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is True
        assert reason == ""

    def test_reject_max_positions_reached(self):
        """Refuse si max positions atteint."""
        self.rm.open_position_count = 3
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is False
        assert "positions" in reason.lower()

    def test_reject_daily_drawdown_exceeded(self):
        """Refuse si drawdown journalier depasse 5%."""
        self.rm.daily_pnl = -51.0  # -5.1% of 1000
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is False
        assert "journalier" in reason.lower()

    def test_reject_total_drawdown_exceeded(self):
        """Refuse si drawdown total depasse 15%."""
        self.rm.total_pnl = -151.0  # -15.1% of 1000
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is False
        assert "total" in reason.lower()

    def test_build_order_request(self):
        """Construit un OrderRequest avec les bons TP/SL."""
        signal = make_signal(entry_price=50000.0)
        order = self.rm.build_order_request(signal)
        assert order.entry_price == 50000.0
        # LONG: SL = entry * (1 - 0.0015) = 49925
        assert abs(order.stop_loss - 49925.0) < 0.01
        # LONG: TP = entry * (1 + 0.003) = 50150
        assert abs(order.take_profit - 50150.0) < 0.01
        assert order.size > 0

    def test_build_order_request_short(self):
        """TP/SL inverses pour SHORT."""
        signal = make_signal(side="SHORT", entry_price=50000.0)
        order = self.rm.build_order_request(signal)
        # SHORT: SL = entry * (1 + 0.0015) = 50075
        assert abs(order.stop_loss - 50075.0) < 0.01
        # SHORT: TP = entry * (1 - 0.003) = 49850
        assert abs(order.take_profit - 49850.0) < 0.01
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_risk_manager.py -v`
Expected: FAIL — `ImportError: cannot import name 'RiskManager' from 'core.risk_manager'`

- [ ] **Step 3: Implement core/risk_manager.py**

```python
from models.events import Signal, OrderRequest
from loguru import logger


class RiskManager:
    def __init__(
        self,
        capital: float,
        risk_per_trade_percent: float,
        max_drawdown_percent: float,
        daily_drawdown_limit: float,
        max_open_positions: int,
        leverage: int,
        stop_loss_percent: float,
        take_profit_percent: float,
    ):
        self.capital = capital
        self.risk_per_trade = risk_per_trade_percent / 100.0
        self.max_drawdown = max_drawdown_percent / 100.0
        self.daily_drawdown_limit = daily_drawdown_limit / 100.0
        self.max_open_positions = max_open_positions
        self.leverage = leverage
        self.stop_loss_percent = stop_loss_percent / 100.0
        self.take_profit_percent = take_profit_percent / 100.0

        self.open_position_count: int = 0
        self.daily_pnl: float = 0.0
        self.total_pnl: float = 0.0
        self._halted: bool = False

    @property
    def is_halted(self) -> bool:
        return self._halted

    def approve(self, signal: Signal) -> tuple[bool, str]:
        if self._halted:
            return False, "Bot arrete: drawdown critique"

        if self.open_position_count >= self.max_open_positions:
            return False, f"Max positions atteint ({self.max_open_positions})"

        daily_dd = abs(self.daily_pnl) / self.capital
        if self.daily_pnl < 0 and daily_dd >= self.daily_drawdown_limit:
            self._halted = True
            logger.critical(f"Drawdown journalier {daily_dd*100:.2f}% >= {self.daily_drawdown_limit*100}% — ARRET")
            return False, f"Drawdown journalier depasse {self.daily_drawdown_limit*100:.1f}%"

        total_dd = abs(self.total_pnl) / self.capital
        if self.total_pnl < 0 and total_dd >= self.max_drawdown:
            self._halted = True
            logger.critical(f"Drawdown total {total_dd*100:.2f}% >= {self.max_drawdown*100}% — ARRET CRITIQUE")
            return False, f"Drawdown total depasse {self.max_drawdown*100:.1f}%"

        return True, ""

    def calculate_size(self, entry_price: float) -> float:
        risk_amount = self.capital * self.risk_per_trade
        size = risk_amount / (entry_price * self.stop_loss_percent)
        return round(size, 5)

    def build_order_request(self, signal: Signal) -> OrderRequest:
        size = self.calculate_size(signal.entry_price)

        if signal.side == "LONG":
            stop_loss = signal.entry_price * (1 - self.stop_loss_percent)
            take_profit = signal.entry_price * (1 + self.take_profit_percent)
        else:
            stop_loss = signal.entry_price * (1 + self.stop_loss_percent)
            take_profit = signal.entry_price * (1 - self.take_profit_percent)

        return OrderRequest(
            signal=signal,
            size=size,
            entry_price=signal.entry_price,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit, 2),
        )

    def record_trade_result(self, pnl: float) -> None:
        self.daily_pnl += pnl
        self.total_pnl += pnl

    def reset_daily(self) -> None:
        logger.info(f"Reset journalier — PnL du jour: {self.daily_pnl:.2f} USDT")
        self.daily_pnl = 0.0
        if not (self.total_pnl < 0 and abs(self.total_pnl) / self.capital >= self.max_drawdown):
            self._halted = False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_risk_manager.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/risk_manager.py tests/test_risk_manager.py
git commit -m "feat: implement risk manager with position sizing and drawdown limits"
```

---

## Task 6: PnL Tracker — Tests First

**Files:**
- Create: `tests/test_pnl_tracker.py`
- Create: `core/pnl_tracker.py`

- [ ] **Step 1: Write failing tests for PnL tracker**

```python
import pytest
from core.pnl_tracker import PnLCalculator


class TestPnLCalculation:
    def setup_method(self):
        self.calc = PnLCalculator(fees_percent=0.04)

    def test_long_profit(self):
        """PnL correct pour un LONG gagnant."""
        pnl = self.calc.calculate_pnl(
            side="LONG", entry_price=50000.0, exit_price=50150.0, size=0.1
        )
        # Brut: (50150 - 50000) * 0.1 = 15.0
        # Frais: 50000*0.1*0.0004 + 50150*0.1*0.0004 = 2.0 + 2.006 = 4.006
        # Net: 15.0 - 4.006 = 10.994
        assert abs(pnl - 10.994) < 0.01

    def test_long_loss(self):
        """PnL correct pour un LONG perdant."""
        pnl = self.calc.calculate_pnl(
            side="LONG", entry_price=50000.0, exit_price=49925.0, size=0.1
        )
        # Brut: (49925 - 50000) * 0.1 = -7.5
        # Frais: 50000*0.1*0.0004 + 49925*0.1*0.0004 = 2.0 + 1.997 = 3.997
        # Net: -7.5 - 3.997 = -11.497
        assert abs(pnl - (-11.497)) < 0.01

    def test_short_profit(self):
        """PnL correct pour un SHORT gagnant."""
        pnl = self.calc.calculate_pnl(
            side="SHORT", entry_price=50000.0, exit_price=49850.0, size=0.1
        )
        # Brut: (50000 - 49850) * 0.1 = 15.0
        # Frais: 50000*0.1*0.0004 + 49850*0.1*0.0004 = 2.0 + 1.994 = 3.994
        # Net: 15.0 - 3.994 = 11.006
        assert abs(pnl - 11.006) < 0.01

    def test_short_loss(self):
        """PnL correct pour un SHORT perdant."""
        pnl = self.calc.calculate_pnl(
            side="SHORT", entry_price=50000.0, exit_price=50075.0, size=0.1
        )
        # Brut: (50000 - 50075) * 0.1 = -7.5
        # Frais: 50000*0.1*0.0004 + 50075*0.1*0.0004 = 2.0 + 2.003 = 4.003
        # Net: -7.5 - 4.003 = -11.503
        assert abs(pnl - (-11.503)) < 0.01


class TestWinRate:
    def setup_method(self):
        self.calc = PnLCalculator(fees_percent=0.04)

    def test_win_rate_all_wins(self):
        """Win rate = 100% si tous les trades sont gagnants."""
        self.calc.record_trade(5.0)
        self.calc.record_trade(3.0)
        self.calc.record_trade(7.0)
        assert self.calc.win_rate == 100.0

    def test_win_rate_mixed(self):
        """Win rate correct pour un mix."""
        self.calc.record_trade(5.0)
        self.calc.record_trade(-3.0)
        self.calc.record_trade(7.0)
        self.calc.record_trade(-2.0)
        assert self.calc.win_rate == 50.0

    def test_win_rate_no_trades(self):
        """Win rate = 0 si aucun trade."""
        assert self.calc.win_rate == 0.0


class TestDrawdown:
    def setup_method(self):
        self.calc = PnLCalculator(fees_percent=0.04)

    def test_max_drawdown(self):
        """Max drawdown calcule correctement."""
        self.calc.record_trade(10.0)   # equity: 10
        self.calc.record_trade(5.0)    # equity: 15 (peak)
        self.calc.record_trade(-8.0)   # equity: 7, dd = 8/15 = 53.3%
        self.calc.record_trade(3.0)    # equity: 10
        assert abs(self.calc.max_drawdown_percent - 53.33) < 0.1

    def test_no_drawdown_only_profits(self):
        """Pas de drawdown si que des profits."""
        self.calc.record_trade(5.0)
        self.calc.record_trade(3.0)
        assert self.calc.max_drawdown_percent == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pnl_tracker.py -v`
Expected: FAIL — `ImportError: cannot import name 'PnLCalculator' from 'core.pnl_tracker'`

- [ ] **Step 3: Implement core/pnl_tracker.py**

```python
from datetime import datetime, timezone
from loguru import logger


class PnLCalculator:
    def __init__(self, fees_percent: float = 0.04):
        self.fees_rate = fees_percent / 100.0
        self.trades: list[float] = []
        self.equity_curve: list[float] = [0.0]
        self._peak: float = 0.0
        self._max_dd: float = 0.0

    def calculate_pnl(
        self, side: str, entry_price: float, exit_price: float, size: float
    ) -> float:
        if side == "LONG":
            gross = (exit_price - entry_price) * size
        else:
            gross = (entry_price - exit_price) * size

        fee_entry = entry_price * size * self.fees_rate
        fee_exit = exit_price * size * self.fees_rate
        net = gross - fee_entry - fee_exit
        return round(net, 4)

    def record_trade(self, pnl: float) -> None:
        self.trades.append(pnl)
        current_equity = self.equity_curve[-1] + pnl
        self.equity_curve.append(current_equity)

        if current_equity > self._peak:
            self._peak = current_equity

        if self._peak > 0:
            dd = (self._peak - current_equity) / self._peak
            if dd > self._max_dd:
                self._max_dd = dd

    @property
    def win_rate(self) -> float:
        if not self.trades:
            return 0.0
        wins = sum(1 for t in self.trades if t > 0)
        return round((wins / len(self.trades)) * 100, 2)

    @property
    def max_drawdown_percent(self) -> float:
        return round(self._max_dd * 100, 2)

    @property
    def total_pnl(self) -> float:
        return sum(self.trades)

    @property
    def profit_factor(self) -> float:
        gross_profit = sum(t for t in self.trades if t > 0)
        gross_loss = abs(sum(t for t in self.trades if t < 0))
        if gross_loss == 0:
            return float("inf") if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 2)

    def get_daily_stats(self) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        wins = sum(1 for t in self.trades if t > 0)
        losses = sum(1 for t in self.trades if t <= 0)
        total = len(self.trades)
        return {
            "date": today,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": self.win_rate,
            "total_pnl": round(self.total_pnl, 2),
            "max_drawdown": self.max_drawdown_percent,
            "sharpe_ratio": 0.0,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_pnl_tracker.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add core/pnl_tracker.py tests/test_pnl_tracker.py
git commit -m "feat: implement PnL calculator with win rate and drawdown tracking"
```

---

## Task 7: Order Executor (dry-run + live)

**Files:**
- Create: `core/order_executor.py`

- [ ] **Step 1: Implement core/order_executor.py**

```python
import asyncio
import time
import uuid
from typing import Literal

from loguru import logger

from models.events import OrderRequest, OrderResult, TradeClose


class Position:
    def __init__(self, order_result: OrderResult, stop_loss: float, take_profit: float, timeout_s: float, trailing_activation: float, trailing_stop_percent: float):
        self.order = order_result
        self.stop_loss = stop_loss
        self.take_profit = take_profit
        self.timeout_s = timeout_s
        self.trailing_activation = trailing_activation
        self.trailing_stop_percent = trailing_stop_percent
        self.opened_at = time.time()
        self.trailing_active = False
        self.trailing_stop_price: float | None = None


class OrderExecutor:
    def __init__(
        self,
        exchange=None,
        mode: Literal["live", "dry_run"] = "dry_run",
        slippage_percent: float = 0.01,
        timeout_seconds: float = 300,
        trailing_activation_percent: float = 0.2,
        trailing_stop_percent: float = 0.15,
        fees_percent: float = 0.04,
    ):
        self.exchange = exchange
        self.mode = mode
        self.slippage = slippage_percent / 100.0
        self.timeout_seconds = timeout_seconds
        self.trailing_activation = trailing_activation_percent / 100.0
        self.trailing_stop_percent = trailing_stop_percent / 100.0
        self.fees_percent = fees_percent
        self.positions: dict[str, Position] = {}
        self._current_prices: dict[str, float] = {}
        self._shutdown = False

    def update_price(self, pair: str, price: float) -> None:
        self._current_prices[pair] = price

    async def execute_order(self, request: OrderRequest) -> OrderResult:
        if self.mode == "dry_run":
            return await self._execute_dry_run(request)
        else:
            return await self._execute_live(request)

    async def _execute_dry_run(self, request: OrderRequest) -> OrderResult:
        slippage_direction = 1 if request.signal.side == "LONG" else -1
        fill_price = request.entry_price * (1 + slippage_direction * self.slippage)

        order_id = f"dry_{uuid.uuid4().hex[:8]}"
        result = OrderResult(
            order_id=order_id,
            pair=request.signal.pair,
            side=request.signal.side,
            fill_price=round(fill_price, 2),
            size=request.size,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            status="filled",
        )

        self.positions[order_id] = Position(
            order_result=result,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            timeout_s=self.timeout_seconds,
            trailing_activation=self.trailing_activation,
            trailing_stop_percent=self.trailing_stop_percent,
        )

        logger.info(f"[DRY-RUN] Ordre {result.side} {result.pair} fill@{result.fill_price} size={result.size}")
        return result

    async def _execute_live(self, request: OrderRequest) -> OrderResult:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                order_type = "market"
                side_ccxt = "buy" if request.signal.side == "LONG" else "sell"

                response = await self.exchange.create_order(
                    symbol=request.signal.pair,
                    type=order_type,
                    side=side_ccxt,
                    amount=request.size,
                )

                order_id = response["id"]
                fill_price = response.get("average", response.get("price", request.entry_price))

                result = OrderResult(
                    order_id=order_id,
                    pair=request.signal.pair,
                    side=request.signal.side,
                    fill_price=float(fill_price),
                    size=request.size,
                    stop_loss=request.stop_loss,
                    take_profit=request.take_profit,
                    status="filled",
                )

                self.positions[order_id] = Position(
                    order_result=result,
                    stop_loss=request.stop_loss,
                    take_profit=request.take_profit,
                    timeout_s=self.timeout_seconds,
                    trailing_activation=self.trailing_activation,
                    trailing_stop_percent=self.trailing_stop_percent,
                )

                logger.info(f"[LIVE] Ordre {result.side} {result.pair} fill@{result.fill_price} size={result.size}")
                return result

            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Erreur ordre (tentative {attempt+1}/{max_retries}): {e} — retry dans {wait}s")
                if attempt < max_retries - 1:
                    await asyncio.sleep(wait)

        return OrderResult(
            order_id=f"failed_{uuid.uuid4().hex[:8]}",
            pair=request.signal.pair,
            side=request.signal.side,
            fill_price=0.0,
            size=request.size,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            status="failed",
        )

    def check_positions(self) -> list[TradeClose]:
        closes: list[TradeClose] = []
        now = time.time()

        for order_id, pos in list(self.positions.items()):
            price = self._current_prices.get(pos.order.pair)
            if price is None:
                continue

            close_reason = self._evaluate_exit(pos, price, now)
            if close_reason:
                trade_close = self._close_position(pos, price, close_reason)
                closes.append(trade_close)
                del self.positions[order_id]

        return closes

    def _evaluate_exit(self, pos: Position, price: float, now: float) -> str | None:
        elapsed = now - pos.opened_at
        if elapsed >= pos.timeout_s:
            return "TIMEOUT"

        if pos.order.side == "LONG":
            if price <= pos.stop_loss:
                return "SL"
            if price >= pos.take_profit:
                return "TP"
            profit_pct = (price - pos.order.fill_price) / pos.order.fill_price
        else:
            if price >= pos.stop_loss:
                return "SL"
            if price <= pos.take_profit:
                return "TP"
            profit_pct = (pos.order.fill_price - price) / pos.order.fill_price

        if profit_pct >= pos.trailing_activation:
            if not pos.trailing_active:
                pos.trailing_active = True
                if pos.order.side == "LONG":
                    pos.trailing_stop_price = price * (1 - pos.trailing_stop_percent)
                else:
                    pos.trailing_stop_price = price * (1 + pos.trailing_stop_percent)
            else:
                if pos.order.side == "LONG":
                    new_trailing = price * (1 - pos.trailing_stop_percent)
                    if new_trailing > pos.trailing_stop_price:
                        pos.trailing_stop_price = new_trailing
                    if price <= pos.trailing_stop_price:
                        return "TRAILING"
                else:
                    new_trailing = price * (1 + pos.trailing_stop_percent)
                    if new_trailing < pos.trailing_stop_price:
                        pos.trailing_stop_price = new_trailing
                    if price >= pos.trailing_stop_price:
                        return "TRAILING"

        return None

    def _close_position(self, pos: Position, exit_price: float, reason: str) -> TradeClose:
        entry = pos.order.fill_price
        size = pos.order.size

        if pos.order.side == "LONG":
            gross = (exit_price - entry) * size
        else:
            gross = (entry - exit_price) * size

        fees = (entry * size + exit_price * size) * (self.fees_percent / 100.0)
        pnl_usdt = round(gross - fees, 4)
        pnl_percent = round((pnl_usdt / (entry * size)) * 100, 4)
        duration = time.time() - pos.opened_at

        logger.info(f"Fermeture {pos.order.side} {pos.order.pair} | raison={reason} PnL={pnl_usdt:.2f} USDT ({pnl_percent:.2f}%)")

        return TradeClose(
            order_id=pos.order.order_id,
            pair=pos.order.pair,
            side=pos.order.side,
            entry_price=entry,
            exit_price=exit_price,
            size=size,
            pnl_usdt=pnl_usdt,
            pnl_percent=pnl_percent,
            duration_s=round(duration, 1),
            reason=reason,
        )

    async def close_all_positions(self) -> list[TradeClose]:
        closes: list[TradeClose] = []
        for order_id, pos in list(self.positions.items()):
            price = self._current_prices.get(pos.order.pair, pos.order.fill_price)
            trade_close = self._close_position(pos, price, "TIMEOUT")
            closes.append(trade_close)
        self.positions.clear()
        return closes

    def shutdown(self) -> None:
        self._shutdown = True
```

- [ ] **Step 2: Quick smoke test**

Run: `python -c "from core.order_executor import OrderExecutor; e = OrderExecutor(); print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add core/order_executor.py
git commit -m "feat: implement order executor with dry-run mode and position monitoring"
```

---

## Task 8: Data Feed

**Files:**
- Create: `core/data_feed.py`

- [ ] **Step 1: Implement core/data_feed.py**

```python
import asyncio
import csv
import time
from pathlib import Path
from typing import Literal

import pandas as pd
import pandas_ta as ta
from loguru import logger

from models.events import MarketData


class DataFeed:
    def __init__(
        self,
        exchange=None,
        pairs: list[str] = None,
        timeframe: str = "1m",
        mode: Literal["live", "dry_run"] = "dry_run",
        dry_run_file: str | None = None,
    ):
        self.exchange = exchange
        self.pairs = pairs or ["BTC/USDT"]
        self.timeframe = timeframe
        self.mode = mode
        self.dry_run_file = dry_run_file
        self._shutdown = False
        self._candle_buffer: dict[str, list] = {pair: [] for pair in self.pairs}
        self._buffer_size = 21  # besoin de 20 bougies + 1 pour les indicateurs

    async def run(self, output_queue: asyncio.Queue) -> None:
        if self.mode == "dry_run":
            await self._run_dry(output_queue)
        else:
            await self._run_live(output_queue)

    async def _run_live(self, output_queue: asyncio.Queue) -> None:
        logger.info(f"DataFeed live demarre pour {self.pairs} ({self.timeframe})")

        while not self._shutdown:
            try:
                for pair in self.pairs:
                    ohlcv = await self.exchange.watch_ohlcv(pair, self.timeframe)
                    order_book = await self.exchange.watch_order_book(pair, limit=5)

                    if ohlcv:
                        latest = ohlcv[-1]
                        self._candle_buffer[pair].append(latest)
                        if len(self._candle_buffer[pair]) > self._buffer_size:
                            self._candle_buffer[pair] = self._candle_buffer[pair][-self._buffer_size:]

                    if len(self._candle_buffer[pair]) >= self._buffer_size:
                        bid = order_book["bids"][0][0] if order_book["bids"] else 0.0
                        ask = order_book["asks"][0][0] if order_book["asks"] else 0.0

                        market_data = self._compute_indicators(pair, bid, ask)
                        if market_data:
                            await output_queue.put(market_data)

            except Exception as e:
                logger.error(f"Erreur DataFeed live: {e}")
                await asyncio.sleep(1)

    async def _run_dry(self, output_queue: asyncio.Queue) -> None:
        logger.info("DataFeed dry-run demarre")

        if self.dry_run_file and Path(self.dry_run_file).exists():
            candles = self._load_csv(self.dry_run_file)
        else:
            candles = self._generate_fake_candles()

        for pair in self.pairs:
            buffer: list = []
            for candle in candles:
                buffer.append(candle)
                if len(buffer) > self._buffer_size:
                    buffer = buffer[-self._buffer_size:]

                if len(buffer) >= self._buffer_size:
                    self._candle_buffer[pair] = buffer.copy()
                    bid = candle[4] * 0.9999
                    ask = candle[4] * 1.0001
                    market_data = self._compute_indicators(pair, bid, ask)
                    if market_data:
                        await output_queue.put(market_data)
                        await asyncio.sleep(0.01)

                if self._shutdown:
                    return

        logger.info("DataFeed dry-run termine (donnees epuisees)")

    def _compute_indicators(self, pair: str, bid: float, ask: float) -> MarketData | None:
        candles = self._candle_buffer[pair]
        if len(candles) < self._buffer_size:
            return None

        df = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])

        rsi_series = ta.rsi(df["close"], length=7)
        ema_series = ta.ema(df["close"], length=20)

        if rsi_series is None or ema_series is None:
            return None

        rsi_current = rsi_series.iloc[-1]
        rsi_prev = rsi_series.iloc[-2]
        ema_current = ema_series.iloc[-1]

        if pd.isna(rsi_current) or pd.isna(ema_current):
            return None

        vol_mean = df["volume"].iloc[-21:-1].mean()
        vol_current = df["volume"].iloc[-1]
        volume_ratio = vol_current / vol_mean if vol_mean > 0 else 0.0

        latest = candles[-1]

        return MarketData(
            timestamp=latest[0] / 1000.0 if latest[0] > 1e12 else latest[0],
            pair=pair,
            open=latest[1],
            high=latest[2],
            low=latest[3],
            close=latest[4],
            volume=latest[5],
            bid=bid,
            ask=ask,
            rsi=float(rsi_current),
            rsi_prev=float(rsi_prev),
            ema=float(ema_current),
            volume_ratio=float(volume_ratio),
        )

    def _load_csv(self, filepath: str) -> list:
        candles = []
        with open(filepath, "r") as f:
            reader = csv.reader(f)
            next(reader, None)
            for row in reader:
                candles.append([float(x) for x in row])
        return candles

    def _generate_fake_candles(self) -> list:
        import random
        random.seed(42)
        candles = []
        price = 50000.0
        ts = time.time() - 3600

        for i in range(200):
            change = random.gauss(0, 0.001)
            price *= (1 + change)
            high = price * (1 + abs(random.gauss(0, 0.0005)))
            low = price * (1 - abs(random.gauss(0, 0.0005)))
            vol = random.uniform(50, 200)
            candles.append([ts + i * 60, price * 0.9999, high, low, price, vol])

        return candles

    def shutdown(self) -> None:
        self._shutdown = True
        logger.info("DataFeed arret demande")
```

- [ ] **Step 2: Verify import and fake data generation**

Run: `python -c "from core.data_feed import DataFeed; df = DataFeed(); print(len(df._generate_fake_candles()), 'candles generees')"`
Expected: `200 candles generees`

- [ ] **Step 3: Commit**

```bash
git add core/data_feed.py
git commit -m "feat: implement data feed with ccxt.pro live and dry-run modes"
```

---

## Task 9: Main Entrypoint and Pipeline Orchestration

**Files:**
- Create: `main.py`

- [ ] **Step 1: Implement main.py**

```python
import asyncio
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

from core.data_feed import DataFeed
from core.strategy import ScalpingStrategy
from core.risk_manager import RiskManager
from core.order_executor import OrderExecutor
from core.pnl_tracker import PnLCalculator
from db.models import init_database, insert_trade, insert_signal, update_daily_stats
from models.events import MarketData, Signal, OrderRequest, OrderResult, TradeClose


logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | <cyan>{name}</cyan> - {message}",
    level="INFO",
)
logger.add("logs/bot_{time:YYYY-MM-DD}.log", rotation="1 day", retention="7 days", level="DEBUG")


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


async def strategy_loop(
    market_queue: asyncio.Queue,
    signal_queue: asyncio.Queue,
    strategy: ScalpingStrategy,
    executor: OrderExecutor,
) -> None:
    while True:
        data: MarketData = await market_queue.get()
        executor.update_price(data.pair, data.close)

        sig = strategy.evaluate(data)
        if sig:
            await signal_queue.put(sig)

        market_queue.task_done()


async def risk_loop(
    signal_queue: asyncio.Queue,
    order_queue: asyncio.Queue,
    risk_manager: RiskManager,
    db,
) -> None:
    while True:
        sig: Signal = await signal_queue.get()

        signal_record = {
            "pair": sig.pair,
            "timestamp": datetime.fromtimestamp(sig.timestamp, tz=timezone.utc).isoformat(),
            "side": sig.side,
            "rsi": sig.rsi,
            "ema_distance": sig.ema_distance,
            "volume_ratio": sig.volume_ratio,
            "spread": sig.spread,
            "triggered": 0,
        }

        approved, reason = risk_manager.approve(sig)
        if approved:
            order_request = risk_manager.build_order_request(sig)
            await order_queue.put(order_request)
            signal_record["triggered"] = 1
            logger.info(f"Signal approuve: {sig.side} {sig.pair} size={order_request.size}")
        else:
            logger.info(f"Signal rejete: {sig.side} {sig.pair} — {reason}")

        await insert_signal(db, signal_record)
        signal_queue.task_done()


async def execution_loop(
    order_queue: asyncio.Queue,
    result_queue: asyncio.Queue,
    executor: OrderExecutor,
    strategy: ScalpingStrategy,
    risk_manager: RiskManager,
) -> None:
    while True:
        request: OrderRequest = await order_queue.get()

        result = await executor.execute_order(request)
        if result.status == "filled":
            strategy.open_positions.add(result.pair)
            risk_manager.open_position_count += 1
            await result_queue.put(result)

        order_queue.task_done()


async def position_monitor_loop(
    result_queue: asyncio.Queue,
    executor: OrderExecutor,
    strategy: ScalpingStrategy,
    risk_manager: RiskManager,
    pnl_calc: PnLCalculator,
    db,
) -> None:
    while True:
        closes = executor.check_positions()
        for close in closes:
            strategy.open_positions.discard(close.pair)
            risk_manager.open_position_count -= 1
            risk_manager.record_trade_result(close.pnl_usdt)
            pnl_calc.record_trade(close.pnl_usdt)

            trade_record = {
                "pair": close.pair,
                "side": close.side,
                "entry_price": close.entry_price,
                "exit_price": close.exit_price,
                "size": close.size,
                "pnl_usdt": close.pnl_usdt,
                "pnl_percent": close.pnl_percent,
                "duration_s": close.duration_s,
                "reason": close.reason,
                "timestamp_open": datetime.fromtimestamp(close.timestamp - close.duration_s, tz=timezone.utc).isoformat(),
                "timestamp_close": datetime.fromtimestamp(close.timestamp, tz=timezone.utc).isoformat(),
            }
            await insert_trade(db, trade_record)

            logger.info(
                f"Trade ferme: {close.side} {close.pair} | "
                f"PnL={close.pnl_usdt:+.2f} USDT | Raison={close.reason} | "
                f"Win rate={pnl_calc.win_rate:.1f}%"
            )

        await asyncio.sleep(0.1)


async def main() -> None:
    load_dotenv("config/secrets.env")
    config = load_config()

    logger.info("=" * 50)
    logger.info("SCALPING BOT — Demarrage")
    logger.info(f"Mode: {'DRY-RUN' if config.get('dry_run') else 'LIVE (testnet)' if config.get('testnet') else 'LIVE'}")
    logger.info(f"Paires: {config['pairs']}")
    logger.info(f"Capital: {config['capital_usdt']} USDT | Levier: {config['leverage']}x")
    logger.info("=" * 50)

    db = await init_database()

    exchange = None
    if not config.get("dry_run"):
        import ccxt.pro as ccxtpro
        import os
        exchange_class = getattr(ccxtpro, config["exchange"])
        exchange = exchange_class({
            "apiKey": os.getenv("BINANCE_API_KEY"),
            "secret": os.getenv("BINANCE_SECRET"),
            "sandbox": config.get("testnet", True),
            "options": {"defaultType": "future"},
        })
        await exchange.load_markets()

    mode = "dry_run" if config.get("dry_run") else "live"

    data_feed = DataFeed(
        exchange=exchange,
        pairs=config["pairs"],
        timeframe=config["timeframe"],
        mode=mode,
    )

    strategy = ScalpingStrategy(
        rsi_long_threshold=35.0,
        rsi_short_threshold=65.0,
        volume_ratio_min=1.5,
        spread_max_percent=0.05,
    )

    risk_manager = RiskManager(
        capital=config["capital_usdt"],
        risk_per_trade_percent=config["risk_per_trade_percent"],
        max_drawdown_percent=config["max_drawdown_percent"],
        daily_drawdown_limit=config["daily_drawdown_limit"],
        max_open_positions=config["max_open_positions"],
        leverage=config["leverage"],
        stop_loss_percent=config["stop_loss_percent"],
        take_profit_percent=config["take_profit_percent"],
    )

    executor = OrderExecutor(
        exchange=exchange,
        mode=mode,
        slippage_percent=config.get("slippage_percent", 0.01),
        timeout_seconds=config.get("timeout_seconds", 300),
        trailing_activation_percent=config.get("trailing_activation_percent", 0.2),
        trailing_stop_percent=config.get("stop_loss_percent", 0.15),
        fees_percent=config.get("fees_percent", 0.04),
    )

    pnl_calc = PnLCalculator(fees_percent=config.get("fees_percent", 0.04))

    market_queue: asyncio.Queue[MarketData] = asyncio.Queue(maxsize=100)
    signal_queue: asyncio.Queue[Signal] = asyncio.Queue(maxsize=50)
    order_queue: asyncio.Queue[OrderRequest] = asyncio.Queue(maxsize=20)
    result_queue: asyncio.Queue[OrderResult] = asyncio.Queue(maxsize=50)

    shutdown_event = asyncio.Event()

    async def graceful_shutdown():
        logger.warning("Arret en cours...")
        data_feed.shutdown()
        closes = await executor.close_all_positions()
        for close in closes:
            pnl_calc.record_trade(close.pnl_usdt)
            risk_manager.record_trade_result(close.pnl_usdt)

        stats = pnl_calc.get_daily_stats()
        await update_daily_stats(db, stats)
        await db.close()

        logger.info(f"Session terminee | Trades: {stats['total_trades']} | PnL: {stats['total_pnl']:+.2f} USDT | Win rate: {stats['win_rate']:.1f}%")
        shutdown_event.set()

    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(graceful_shutdown()))
    else:
        def win_handler(sig, frame):
            asyncio.create_task(graceful_shutdown())
        signal.signal(signal.SIGINT, win_handler)

    tasks = [
        asyncio.create_task(data_feed.run(market_queue)),
        asyncio.create_task(strategy_loop(market_queue, signal_queue, strategy, executor)),
        asyncio.create_task(risk_loop(signal_queue, order_queue, risk_manager, db)),
        asyncio.create_task(execution_loop(order_queue, result_queue, executor, strategy, risk_manager)),
        asyncio.create_task(position_monitor_loop(result_queue, executor, strategy, risk_manager, pnl_calc, db)),
    ]

    try:
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            if task.exception():
                logger.error(f"Tache terminee avec erreur: {task.exception()}")
    except asyncio.CancelledError:
        pass
    finally:
        if not shutdown_event.is_set():
            await graceful_shutdown()
        for task in tasks:
            task.cancel()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Create logs directory placeholder**

Add `logs/` to `.gitignore`.

- [ ] **Step 3: Verify syntax**

Run: `python -c "import ast; ast.parse(open('main.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add main.py .gitignore
git commit -m "feat: implement main entrypoint with pipeline orchestration and graceful shutdown"
```

---

## Task 10: Integration Test — Dry Run End-to-End

**Files:** No new files, just running the bot

- [ ] **Step 1: Run the bot in dry-run mode for a quick test**

Run: `timeout 15 python main.py || true`
Expected: Bot starts, processes fake candles, may generate signals, exits after data is exhausted or timeout.

Look for in the output:
- "SCALPING BOT — Demarrage"
- "Mode: DRY-RUN"
- "DataFeed dry-run demarre"
- No unhandled exceptions

- [ ] **Step 2: Verify database was populated**

Run: `python -c "import asyncio, aiosqlite; db = asyncio.run(aiosqlite.connect('data/scalping_bot.db')); print(asyncio.run(db.execute('SELECT COUNT(*) FROM signals')))"`

- [ ] **Step 3: Run all unit tests**

Run: `pytest tests/ -v`
Expected: All tests pass (strategy: 9, risk_manager: 7, pnl_tracker: 8 = 24 total)

- [ ] **Step 4: Commit any fixes if needed**

```bash
git add -A
git commit -m "fix: integration test fixes for dry-run pipeline"
```

---

## Task 11: Final Cleanup and Documentation

**Files:**
- Create: `README.md`

- [ ] **Step 1: Create minimal README.md**

```markdown
# Scalping Bot — Phase 1

Bot de scalping automatique pour Binance Futures.

## Installation

```bash
pip install -e ".[dev]"
cp .env.example config/secrets.env
# Editer config/secrets.env avec vos API keys
```

## Utilisation

```bash
# Mode dry-run (simulation locale)
python main.py

# Mode testnet (editer config/config.yaml: dry_run: false)
python main.py
```

## Tests

```bash
pytest tests/ -v
```

## Configuration

Editer `config/config.yaml` pour ajuster les parametres (paires, risque, TP/SL, etc.)
```

- [ ] **Step 2: Verify final project structure**

Run: `find . -type f | grep -v __pycache__ | grep -v .git/ | sort`
Expected: All files from the spec are present.

- [ ] **Step 3: Final commit**

```bash
git add README.md
git commit -m "docs: add README with installation and usage instructions"
```

---

## Summary of Commits

| # | Message | Key Files |
|---|---------|-----------|
| 1 | `feat: scaffold project structure` | pyproject.toml, .gitignore, config.yaml |
| 2 | `feat: add event dataclasses` | models/events.py |
| 3 | `feat: add SQLite database layer` | db/models.py |
| 4 | `feat: implement scalping strategy` | core/strategy.py, tests/test_strategy.py |
| 5 | `feat: implement risk manager` | core/risk_manager.py, tests/test_risk_manager.py |
| 6 | `feat: implement PnL calculator` | core/pnl_tracker.py, tests/test_pnl_tracker.py |
| 7 | `feat: implement order executor` | core/order_executor.py |
| 8 | `feat: implement data feed` | core/data_feed.py |
| 9 | `feat: implement main entrypoint` | main.py |
| 10 | `fix: integration test fixes` | (various) |
| 11 | `docs: add README` | README.md |

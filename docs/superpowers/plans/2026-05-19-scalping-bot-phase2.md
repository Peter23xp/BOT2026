# Backtesting Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backtesting engine that simulates the scalping strategy on 3 months of historical data with real fees/slippage and produces performance reports (terminal stats, CSV, PNG equity curve).

**Architecture:** Synchronous simulation loop iterating candle-by-candle over historical OHLCV data. Reuses `ScalpingStrategy` and `RiskManager` from Phase 1 directly. Separate components for data loading (with local CSV cache), trade simulation, and reporting.

**Tech Stack:** Python 3.11+, ccxt (REST for historical data), pandas, ta (RSI/EMA), matplotlib, existing core modules

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backtest/__init__.py` | Package init |
| `backtest/data_loader.py` | Download + cache historical OHLCV via ccxt |
| `backtest/simulator.py` | Simulated order execution with fees, slippage, intra-candle TP/SL |
| `backtest/engine.py` | Main simulation loop + CLI entrypoint |
| `backtest/report.py` | Stats calculation, CSV export, matplotlib equity curve PNG |
| `tests/test_simulator.py` | Unit tests for SimulatedExecutor |
| `tests/test_backtest_engine.py` | Integration test for full backtest pipeline |

---

## Task 1: Add matplotlib dependency and backtest package

**Files:**
- Modify: `pyproject.toml`
- Create: `backtest/__init__.py`

- [ ] **Step 1: Add matplotlib to dependencies in pyproject.toml**

Add `"matplotlib>=3.7"` to the dependencies list in `pyproject.toml`:

```toml
[project]
name = "scalping-bot"
version = "0.1.0"
description = "Bot de scalping automatique pour crypto (Binance Futures)"
requires-python = ">=3.11"
dependencies = [
    "ccxt>=4.0",
    "pandas>=2.0",
    "ta>=0.11",
    "aiosqlite>=0.19",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "loguru>=0.7",
    "matplotlib>=3.7",
]
```

- [ ] **Step 2: Create backtest/__init__.py**

```python
```

(empty file)

- [ ] **Step 3: Install updated dependencies**

Run: `pip install -e ".[dev]"`
Expected: Successfully installed (matplotlib added)

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml backtest/__init__.py
git commit -m "feat: add backtest package and matplotlib dependency"
```

---

## Task 2: Data Loader

**Files:**
- Create: `backtest/data_loader.py`

- [ ] **Step 1: Implement backtest/data_loader.py**

```python
import time
from pathlib import Path

import ccxt
import pandas as pd
from loguru import logger


class DataLoader:
    def __init__(self, exchange_id: str = "binance", testnet: bool = False):
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({"sandbox": testnet})
        self.cache_dir = Path("data/historical")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def load(self, pair: str, timeframe: str = "1m", days: int = 90) -> pd.DataFrame:
        cache_file = self._cache_path(pair, timeframe, days)

        if cache_file.exists():
            logger.info(f"Cache trouve: {cache_file}")
            df = pd.read_csv(cache_file)
            return df

        logger.info(f"Telechargement {pair} {timeframe} ({days} jours)...")
        df = self._download(pair, timeframe, days)
        df.to_csv(cache_file, index=False)
        logger.info(f"Donnees sauvegardees: {cache_file} ({len(df)} bougies)")
        return df

    def _download(self, pair: str, timeframe: str, days: int) -> pd.DataFrame:
        since = int((time.time() - days * 86400) * 1000)
        all_candles = []
        limit = 1000

        while True:
            candles = self.exchange.fetch_ohlcv(
                pair, timeframe, since=since, limit=limit
            )
            if not candles:
                break

            all_candles.extend(candles)
            since = candles[-1][0] + 1
            logger.debug(f"  ... {len(all_candles)} bougies telechargees")

            if len(candles) < limit:
                break

            time.sleep(self.exchange.rateLimit / 1000.0)

        df = pd.DataFrame(
            all_candles, columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        return df

    def _cache_path(self, pair: str, timeframe: str, days: int) -> Path:
        pair_sanitized = pair.replace("/", "_")
        return self.cache_dir / f"{pair_sanitized}_{timeframe}_{days}d.csv"
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from backtest.data_loader import DataLoader; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backtest/data_loader.py
git commit -m "feat: add historical data loader with CSV cache"
```

---

## Task 3: Simulated Executor — Tests First

**Files:**
- Create: `tests/test_simulator.py`
- Create: `backtest/simulator.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest
from models.events import Signal
from backtest.simulator import SimulatedExecutor


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


class TestOpenPosition:
    def setup_method(self):
        self.executor = SimulatedExecutor(fees_percent=0.04, slippage_percent=0.01)

    def test_open_long_with_slippage(self):
        """LONG fill price includes positive slippage."""
        signal = make_signal(side="LONG", entry_price=50000.0)
        pos = self.executor.open_position(signal, size=0.1, stop_loss=49925.0, take_profit=50150.0)
        # slippage: 50000 * 1.0001 = 50005
        assert abs(pos["fill_price"] - 50005.0) < 0.01
        assert pos["side"] == "LONG"
        assert pos["size"] == 0.1

    def test_open_short_with_slippage(self):
        """SHORT fill price includes negative slippage."""
        signal = make_signal(side="SHORT", entry_price=50000.0)
        pos = self.executor.open_position(signal, size=0.1, stop_loss=50075.0, take_profit=49850.0)
        # slippage: 50000 * 0.9999 = 49995
        assert abs(pos["fill_price"] - 49995.0) < 0.01
        assert pos["side"] == "SHORT"


class TestCheckExit:
    def setup_method(self):
        self.executor = SimulatedExecutor(fees_percent=0.04, slippage_percent=0.01)

    def _make_long_position(self):
        signal = make_signal(side="LONG", entry_price=50000.0)
        return self.executor.open_position(signal, size=0.1, stop_loss=49925.0, take_profit=50150.0)

    def _make_short_position(self):
        signal = make_signal(side="SHORT", entry_price=50000.0)
        return self.executor.open_position(signal, size=0.1, stop_loss=50075.0, take_profit=49850.0)

    def test_long_stop_loss_hit(self):
        """LONG SL triggered when low <= stop_loss."""
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50050, "low": 49900, "close": 49950, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "SL"
        assert result["exit_price"] == 49925.0

    def test_long_take_profit_hit(self):
        """LONG TP triggered when high >= take_profit."""
        pos = self._make_long_position()
        candle = {"open": 50100, "high": 50200, "low": 50050, "close": 50180, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "TP"
        assert result["exit_price"] == 50150.0

    def test_long_sl_priority_over_tp(self):
        """SL has priority over TP when both hit in same candle."""
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50200, "low": 49900, "close": 50100, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "SL"

    def test_timeout(self):
        """Position closed on timeout (5 minutes = 5 candles at 1m)."""
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50050, "low": 49950, "close": 50010, "timestamp": 1300.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=5)
        assert result is not None
        assert result["reason"] == "TIMEOUT"
        assert result["exit_price"] == 50010  # closes at candle close

    def test_no_exit(self):
        """No exit when price stays within bounds and no timeout."""
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50050, "low": 49950, "close": 50020, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is None

    def test_short_stop_loss_hit(self):
        """SHORT SL triggered when high >= stop_loss."""
        pos = self._make_short_position()
        candle = {"open": 50000, "high": 50100, "low": 49950, "close": 50050, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "SL"
        assert result["exit_price"] == 50075.0

    def test_short_take_profit_hit(self):
        """SHORT TP triggered when low <= take_profit."""
        pos = self._make_short_position()
        candle = {"open": 49900, "high": 49950, "low": 49800, "close": 49850, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "TP"
        assert result["exit_price"] == 49850.0

    def test_pnl_calculation_long_profit(self):
        """PnL includes fees on both entry and exit."""
        pos = self._make_long_position()
        candle = {"open": 50100, "high": 50200, "low": 50050, "close": 50180, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        # fill_price=50005, exit=50150, size=0.1
        # gross: (50150-50005)*0.1 = 14.5
        # fees: 50005*0.1*0.0004 + 50150*0.1*0.0004 = 2.0002 + 2.006 = 4.0062
        # net: 14.5 - 4.0062 = 10.4938
        assert abs(result["pnl_usdt"] - 10.4938) < 0.1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_simulator.py -v`
Expected: FAIL — ImportError

- [ ] **Step 3: Implement backtest/simulator.py**

```python
from models.events import Signal
from loguru import logger


class SimulatedExecutor:
    def __init__(
        self,
        fees_percent: float = 0.04,
        slippage_percent: float = 0.01,
        timeout_seconds: float = 300,
        trailing_activation_percent: float = 0.2,
        trailing_stop_percent: float = 0.15,
    ):
        self.fees_rate = fees_percent / 100.0
        self.slippage_rate = slippage_percent / 100.0
        self.timeout_seconds = timeout_seconds
        self.trailing_activation = trailing_activation_percent / 100.0
        self.trailing_stop_percent = trailing_stop_percent / 100.0

    def open_position(
        self, signal: Signal, size: float, stop_loss: float, take_profit: float
    ) -> dict:
        if signal.side == "LONG":
            fill_price = signal.entry_price * (1 + self.slippage_rate)
        else:
            fill_price = signal.entry_price * (1 - self.slippage_rate)

        return {
            "pair": signal.pair,
            "side": signal.side,
            "fill_price": round(fill_price, 2),
            "size": size,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_timestamp": signal.timestamp,
            "trailing_active": False,
            "trailing_stop_price": None,
        }

    def check_exit(self, position: dict, candle: dict, elapsed_candles: int) -> dict | None:
        side = position["side"]
        fill_price = position["fill_price"]
        sl = position["stop_loss"]
        tp = position["take_profit"]

        # SL check (priority 1 - worst case first)
        if side == "LONG" and candle["low"] <= sl:
            return self._close(position, sl, "SL", candle["timestamp"])
        if side == "SHORT" and candle["high"] >= sl:
            return self._close(position, sl, "SL", candle["timestamp"])

        # TP check (priority 2)
        if side == "LONG" and candle["high"] >= tp:
            return self._close(position, tp, "TP", candle["timestamp"])
        if side == "SHORT" and candle["low"] <= tp:
            return self._close(position, tp, "TP", candle["timestamp"])

        # Trailing stop check (priority 3)
        current_price = candle["close"]
        if side == "LONG":
            profit_pct = (current_price - fill_price) / fill_price
        else:
            profit_pct = (fill_price - current_price) / fill_price

        if profit_pct >= self.trailing_activation:
            if not position["trailing_active"]:
                position["trailing_active"] = True
                if side == "LONG":
                    position["trailing_stop_price"] = current_price * (1 - self.trailing_stop_percent)
                else:
                    position["trailing_stop_price"] = current_price * (1 + self.trailing_stop_percent)
            else:
                if side == "LONG":
                    new_ts = current_price * (1 - self.trailing_stop_percent)
                    if new_ts > position["trailing_stop_price"]:
                        position["trailing_stop_price"] = new_ts
                else:
                    new_ts = current_price * (1 + self.trailing_stop_percent)
                    if new_ts < position["trailing_stop_price"]:
                        position["trailing_stop_price"] = new_ts

        if position["trailing_active"] and position["trailing_stop_price"] is not None:
            if side == "LONG" and candle["low"] <= position["trailing_stop_price"]:
                return self._close(position, position["trailing_stop_price"], "TRAILING", candle["timestamp"])
            if side == "SHORT" and candle["high"] >= position["trailing_stop_price"]:
                return self._close(position, position["trailing_stop_price"], "TRAILING", candle["timestamp"])

        # Timeout check (priority 4)
        elapsed_seconds = elapsed_candles * 60
        if elapsed_seconds >= self.timeout_seconds:
            return self._close(position, candle["close"], "TIMEOUT", candle["timestamp"])

        return None

    def _close(self, position: dict, exit_price: float, reason: str, timestamp: float) -> dict:
        fill_price = position["fill_price"]
        size = position["size"]
        side = position["side"]

        if side == "LONG":
            gross = (exit_price - fill_price) * size
        else:
            gross = (fill_price - exit_price) * size

        fee_entry = fill_price * size * self.fees_rate
        fee_exit = exit_price * size * self.fees_rate
        pnl_usdt = round(gross - fee_entry - fee_exit, 4)
        pnl_percent = round((pnl_usdt / (fill_price * size)) * 100, 4)

        duration_s = timestamp - position["entry_timestamp"]

        return {
            "pair": position["pair"],
            "side": side,
            "entry_price": fill_price,
            "exit_price": exit_price,
            "size": size,
            "pnl_usdt": pnl_usdt,
            "pnl_percent": pnl_percent,
            "duration_s": duration_s,
            "reason": reason,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_simulator.py -v`
Expected: All 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backtest/simulator.py tests/test_simulator.py
git commit -m "feat: implement simulated executor with intra-candle TP/SL and trailing stop"
```

---

## Task 4: Backtest Engine

**Files:**
- Create: `backtest/engine.py`

- [ ] **Step 1: Implement backtest/engine.py**

```python
import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from loguru import logger
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator
import yaml

from backtest.data_loader import DataLoader
from backtest.simulator import SimulatedExecutor
from core.strategy import ScalpingStrategy
from core.risk_manager import RiskManager
from models.events import MarketData


@dataclass
class BacktestResult:
    trades: list[dict] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=lambda: [0.0])
    stats: dict = field(default_factory=dict)


class BacktestEngine:
    def __init__(self, config: dict):
        self.config = config
        self.strategy = ScalpingStrategy(
            rsi_long_threshold=35.0,
            rsi_short_threshold=65.0,
            volume_ratio_min=1.5,
            spread_max_percent=0.05,
        )
        self.risk_manager = RiskManager(
            capital=config["capital_usdt"],
            risk_per_trade_percent=config["risk_per_trade_percent"],
            max_drawdown_percent=config["max_drawdown_percent"],
            daily_drawdown_limit=config["daily_drawdown_limit"],
            max_open_positions=config["max_open_positions"],
            leverage=config["leverage"],
            stop_loss_percent=config["stop_loss_percent"],
            take_profit_percent=config["take_profit_percent"],
        )
        self.executor = SimulatedExecutor(
            fees_percent=config.get("fees_percent", 0.04),
            slippage_percent=config.get("slippage_percent", 0.01),
            timeout_seconds=config.get("timeout_seconds", 300),
            trailing_activation_percent=config.get("trailing_activation_percent", 0.2),
            trailing_stop_percent=config.get("stop_loss_percent", 0.15),
        )
        self.data_loader = DataLoader(
            exchange_id=config.get("exchange", "binance"),
            testnet=config.get("testnet", False),
        )

    def run(self, pair: str, days: int = 90) -> BacktestResult:
        logger.info(f"Backtest: {pair} | {days} jours | Capital: {self.config['capital_usdt']} USDT")

        df = self.data_loader.load(pair, self.config.get("timeframe", "1m"), days)
        logger.info(f"Donnees chargees: {len(df)} bougies")

        result = BacktestResult()
        open_positions: list[dict] = []
        buffer_size = 21

        for i in range(buffer_size, len(df)):
            window = df.iloc[i - buffer_size:i + 1]
            candle = df.iloc[i]

            # Check exits on open positions
            positions_to_remove = []
            for idx, pos in enumerate(open_positions):
                candle_dict = {
                    "open": candle["open"],
                    "high": candle["high"],
                    "low": candle["low"],
                    "close": candle["close"],
                    "timestamp": candle["timestamp"] / 1000.0 if candle["timestamp"] > 1e12 else candle["timestamp"],
                }
                entry_ts = pos["entry_timestamp"]
                candle_ts = candle_dict["timestamp"]
                elapsed_candles = int((candle_ts - entry_ts) / 60)

                trade = self.executor.check_exit(pos, candle_dict, elapsed_candles)
                if trade:
                    result.trades.append(trade)
                    equity = result.equity_curve[-1] + trade["pnl_usdt"]
                    result.equity_curve.append(equity)
                    self.strategy.open_positions.discard(pair)
                    self.risk_manager.open_position_count -= 1
                    self.risk_manager.record_trade_result(trade["pnl_usdt"])
                    positions_to_remove.append(idx)

            for idx in sorted(positions_to_remove, reverse=True):
                open_positions.pop(idx)

            # Compute indicators
            market_data = self._compute_indicators(window, pair, candle)
            if market_data is None:
                continue

            # Evaluate strategy
            signal = self.strategy.evaluate(market_data)
            if signal is None:
                continue

            # Risk check
            approved, reason = self.risk_manager.approve(signal)
            if not approved:
                continue

            # Open position
            order_request = self.risk_manager.build_order_request(signal)
            pos = self.executor.open_position(
                signal,
                size=order_request.size,
                stop_loss=order_request.stop_loss,
                take_profit=order_request.take_profit,
            )
            open_positions.append(pos)
            self.strategy.open_positions.add(pair)
            self.risk_manager.open_position_count += 1

        # Close remaining positions at last candle close
        if open_positions:
            last_candle = df.iloc[-1]
            for pos in open_positions:
                trade = self.executor._close(
                    pos, last_candle["close"], "TIMEOUT",
                    last_candle["timestamp"] / 1000.0 if last_candle["timestamp"] > 1e12 else last_candle["timestamp"]
                )
                result.trades.append(trade)
                equity = result.equity_curve[-1] + trade["pnl_usdt"]
                result.equity_curve.append(equity)

        # Compute stats
        result.stats = self._compute_stats(result)
        return result

    def _compute_indicators(self, window: pd.DataFrame, pair: str, candle) -> MarketData | None:
        close_series = window["close"]

        rsi_indicator = RSIIndicator(close=close_series, window=7)
        rsi_series = rsi_indicator.rsi()

        ema_indicator = EMAIndicator(close=close_series, window=20)
        ema_series = ema_indicator.ema_indicator()

        if rsi_series is None or ema_series is None:
            return None

        rsi_current = rsi_series.iloc[-1]
        rsi_prev = rsi_series.iloc[-2]
        ema_current = ema_series.iloc[-1]

        if pd.isna(rsi_current) or pd.isna(ema_current):
            return None

        vol_mean = window["volume"].iloc[:-1].mean()
        vol_current = window["volume"].iloc[-1]
        volume_ratio = vol_current / vol_mean if vol_mean > 0 else 0.0

        close_price = float(candle["close"])
        spread_sim = close_price * 0.0001

        timestamp = candle["timestamp"]
        if timestamp > 1e12:
            timestamp = timestamp / 1000.0

        return MarketData(
            timestamp=float(timestamp),
            pair=pair,
            open=float(candle["open"]),
            high=float(candle["high"]),
            low=float(candle["low"]),
            close=close_price,
            volume=float(candle["volume"]),
            bid=close_price - spread_sim,
            ask=close_price + spread_sim,
            rsi=float(rsi_current),
            rsi_prev=float(rsi_prev),
            ema=float(ema_current),
            volume_ratio=float(volume_ratio),
        )

    def _compute_stats(self, result: BacktestResult) -> dict:
        trades = result.trades
        if not trades:
            return {
                "total_trades": 0, "win_rate": 0.0, "profit_factor": 0.0,
                "total_pnl_usdt": 0.0, "total_pnl_percent": 0.0,
                "max_drawdown_percent": 0.0, "sharpe_ratio": 0.0,
                "avg_duration_s": 0.0, "best_trade": 0.0, "worst_trade": 0.0,
            }

        pnls = [t["pnl_usdt"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        total_pnl = sum(pnls)
        win_rate = (len(wins) / len(pnls)) * 100 if pnls else 0.0
        gross_profit = sum(wins) if wins else 0.0
        gross_loss = abs(sum(losses)) if losses else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

        # Max drawdown from equity curve
        peak = 0.0
        max_dd = 0.0
        for eq in result.equity_curve:
            if eq > peak:
                peak = eq
            if peak > 0:
                dd = (peak - eq) / peak
                if dd > max_dd:
                    max_dd = dd

        # Sharpe ratio (annualized from per-trade returns)
        import numpy as np
        if len(pnls) > 1:
            returns = np.array(pnls)
            sharpe = (returns.mean() / returns.std()) * np.sqrt(len(pnls)) if returns.std() > 0 else 0.0
        else:
            sharpe = 0.0

        avg_duration = sum(t["duration_s"] for t in trades) / len(trades)

        return {
            "total_trades": len(trades),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "total_pnl_usdt": round(total_pnl, 2),
            "total_pnl_percent": round((total_pnl / self.config["capital_usdt"]) * 100, 2),
            "max_drawdown_percent": round(max_dd * 100, 2),
            "sharpe_ratio": round(float(sharpe), 2),
            "avg_duration_s": round(avg_duration, 1),
            "best_trade": round(max(pnls), 2),
            "worst_trade": round(min(pnls), 2),
        }


def load_config(path: str = "config/config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="Scalping Bot Backtester")
    parser.add_argument("--pair", type=str, default=None, help="Paire a tester (ex: BTC/USDT)")
    parser.add_argument("--days", type=int, default=90, help="Nombre de jours d'historique")
    parser.add_argument("--capital", type=float, default=None, help="Capital initial en USDT")
    parser.add_argument("--config", type=str, default="config/config.yaml", help="Chemin config")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.capital:
        config["capital_usdt"] = args.capital

    pairs = [args.pair] if args.pair else config["pairs"]

    from backtest.report import BacktestReport

    for pair in pairs:
        engine = BacktestEngine(config)
        result = engine.run(pair, days=args.days)

        report = BacktestReport(result, config, pair)
        report.print_summary()
        csv_path = report.export_csv()
        png_path = report.plot_equity()

        logger.info(f"CSV: {csv_path}")
        logger.info(f"PNG: {png_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify syntax**

Run: `python -c "import ast; ast.parse(open('backtest/engine.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add backtest/engine.py
git commit -m "feat: implement backtest engine with candle-by-candle simulation"
```

---

## Task 5: Backtest Report

**Files:**
- Create: `backtest/report.py`

- [ ] **Step 1: Implement backtest/report.py**

```python
import csv
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from loguru import logger


class BacktestReport:
    def __init__(self, result, config: dict, pair: str):
        self.result = result
        self.config = config
        self.pair = pair
        self.output_dir = Path("data/backtest_results")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def print_summary(self) -> None:
        stats = self.result.stats
        print("\n" + "=" * 60)
        print(f"  BACKTEST REPORT — {self.pair}")
        print("=" * 60)
        print(f"  Capital initial    : {self.config['capital_usdt']} USDT")
        print(f"  Periode            : {len(self.result.equity_curve)} bougies")
        print("-" * 60)
        print(f"  Total trades       : {stats['total_trades']}")
        print(f"  Win rate           : {stats['win_rate']:.1f}%")
        print(f"  Profit factor      : {stats['profit_factor']:.2f}")
        print(f"  PnL total          : {stats['total_pnl_usdt']:+.2f} USDT ({stats['total_pnl_percent']:+.2f}%)")
        print(f"  Max drawdown       : {stats['max_drawdown_percent']:.2f}%")
        print(f"  Sharpe ratio       : {stats['sharpe_ratio']:.2f}")
        print(f"  Duree moy. trade   : {stats['avg_duration_s']:.0f}s")
        print(f"  Meilleur trade     : {stats['best_trade']:+.2f} USDT")
        print(f"  Pire trade         : {stats['worst_trade']:+.2f} USDT")
        print("=" * 60 + "\n")

    def export_csv(self) -> Path:
        pair_sanitized = self.pair.replace("/", "_")
        filepath = self.output_dir / f"{pair_sanitized}_{self._timestamp}.csv"

        if not self.result.trades:
            logger.warning("Aucun trade a exporter")
            return filepath

        fieldnames = ["pair", "side", "entry_price", "exit_price", "size", "pnl_usdt", "pnl_percent", "duration_s", "reason"]
        with open(filepath, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for trade in self.result.trades:
                writer.writerow({k: trade.get(k, "") for k in fieldnames})

        logger.info(f"CSV exporte: {filepath}")
        return filepath

    def plot_equity(self) -> Path:
        pair_sanitized = self.pair.replace("/", "_")
        filepath = self.output_dir / f"{pair_sanitized}_{self._timestamp}_equity.png"

        equity = self.result.equity_curve

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[3, 1], sharex=True)

        # Equity curve
        ax1.plot(equity, color="steelblue", linewidth=1.2)
        ax1.axhline(y=0, color="gray", linestyle="--", linewidth=0.5)
        ax1.set_ylabel("PnL (USDT)")
        ax1.set_title(f"Equity Curve — {self.pair}")
        ax1.grid(True, alpha=0.3)

        # Drawdown
        peak = 0.0
        drawdowns = []
        for eq in equity:
            if eq > peak:
                peak = eq
            dd = ((peak - eq) / peak * 100) if peak > 0 else 0.0
            drawdowns.append(dd)

        ax2.fill_between(range(len(drawdowns)), drawdowns, color="indianred", alpha=0.5)
        ax2.set_ylabel("Drawdown (%)")
        ax2.set_xlabel("Trade #")
        ax2.grid(True, alpha=0.3)
        ax2.invert_yaxis()

        plt.tight_layout()
        plt.savefig(filepath, dpi=100, bbox_inches="tight")
        plt.close()

        logger.info(f"Graphique exporte: {filepath}")
        return filepath
```

- [ ] **Step 2: Verify import**

Run: `python -c "from backtest.report import BacktestReport; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backtest/report.py
git commit -m "feat: implement backtest report with terminal stats, CSV export, and equity curve PNG"
```

---

## Task 6: Integration Test

**Files:**
- Create: `tests/test_backtest_engine.py`

- [ ] **Step 1: Create integration test using fake data**

```python
import pytest
import pandas as pd
import numpy as np
from pathlib import Path

from backtest.engine import BacktestEngine, BacktestResult


def generate_test_data(n_candles: int = 500) -> pd.DataFrame:
    """Generate synthetic OHLCV data with trends that trigger signals."""
    np.random.seed(42)
    timestamps = [1700000000000 + i * 60000 for i in range(n_candles)]
    price = 50000.0
    data = []

    for i in range(n_candles):
        # Create some trends and mean-reversion patterns
        if i % 50 < 10:
            change = -0.002  # downtrend (will create RSI oversold)
        elif i % 50 < 20:
            change = 0.003   # sharp bounce (RSI rising from oversold)
        elif i % 50 > 40:
            change = 0.002   # uptrend (will create RSI overbought)
        else:
            change = np.random.normal(0, 0.001)

        price *= (1 + change + np.random.normal(0, 0.0005))
        high = price * (1 + abs(np.random.normal(0, 0.001)))
        low = price * (1 - abs(np.random.normal(0, 0.001)))
        volume = np.random.uniform(50, 300)

        # Create volume spikes during trend changes
        if i % 50 in [10, 11, 12, 40, 41, 42]:
            volume *= 3

        data.append([timestamps[i], price * 0.999, high, low, price, volume])

    return pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])


class TestBacktestEngine:
    def setup_method(self):
        self.config = {
            "exchange": "binance",
            "testnet": False,
            "capital_usdt": 1000,
            "risk_per_trade_percent": 1.0,
            "max_drawdown_percent": 15.0,
            "daily_drawdown_limit": 5.0,
            "max_open_positions": 3,
            "leverage": 5,
            "stop_loss_percent": 0.15,
            "take_profit_percent": 0.3,
            "fees_percent": 0.04,
            "slippage_percent": 0.01,
            "timeout_seconds": 300,
            "trailing_activation_percent": 0.2,
            "timeframe": "1m",
        }

    def test_backtest_runs_without_crash(self):
        """Backtest completes without error on synthetic data."""
        engine = BacktestEngine(self.config)
        # Monkey-patch the data loader to return synthetic data
        test_data = generate_test_data(500)
        engine.data_loader.load = lambda pair, timeframe, days: test_data

        result = engine.run("BTC/USDT", days=1)
        assert isinstance(result, BacktestResult)
        assert isinstance(result.trades, list)
        assert isinstance(result.equity_curve, list)
        assert len(result.equity_curve) >= 1

    def test_backtest_generates_trades(self):
        """Backtest generates at least some trades on trending data."""
        engine = BacktestEngine(self.config)
        test_data = generate_test_data(1000)
        engine.data_loader.load = lambda pair, timeframe, days: test_data

        result = engine.run("BTC/USDT", days=1)
        # With 1000 candles of trending data, we should get some trades
        assert result.stats["total_trades"] > 0

    def test_backtest_stats_are_valid(self):
        """Stats have correct ranges and types."""
        engine = BacktestEngine(self.config)
        test_data = generate_test_data(1000)
        engine.data_loader.load = lambda pair, timeframe, days: test_data

        result = engine.run("BTC/USDT", days=1)
        stats = result.stats

        assert 0 <= stats["win_rate"] <= 100
        assert stats["max_drawdown_percent"] >= 0
        assert stats["total_trades"] >= 0
        assert stats["avg_duration_s"] >= 0

    def test_backtest_reproducible(self):
        """Same data produces same results."""
        test_data = generate_test_data(500)

        engine1 = BacktestEngine(self.config)
        engine1.data_loader.load = lambda pair, timeframe, days: test_data.copy()
        result1 = engine1.run("BTC/USDT", days=1)

        engine2 = BacktestEngine(self.config)
        engine2.data_loader.load = lambda pair, timeframe, days: test_data.copy()
        result2 = engine2.run("BTC/USDT", days=1)

        assert result1.stats["total_trades"] == result2.stats["total_trades"]
        assert result1.stats["total_pnl_usdt"] == result2.stats["total_pnl_usdt"]
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_backtest_engine.py -v`
Expected: All 4 tests PASS

- [ ] **Step 3: Run all tests together**

Run: `pytest tests/ -v`
Expected: All tests PASS (25 from Phase 1 + 9 simulator + 4 integration = 38)

- [ ] **Step 4: Commit**

```bash
git add tests/test_backtest_engine.py
git commit -m "test: add backtest engine integration tests with synthetic data"
```

---

## Task 7: End-to-End Verification

- [ ] **Step 1: Run the backtest CLI with synthetic data**

Since we may not have real exchange data cached, create a quick test script:

Run:
```bash
python -c "
from backtest.engine import BacktestEngine
from backtest.report import BacktestReport
from tests.test_backtest_engine import generate_test_data
import yaml

config = yaml.safe_load(open('config/config.yaml'))
engine = BacktestEngine(config)
test_data = generate_test_data(2000)
engine.data_loader.load = lambda pair, timeframe, days: test_data

result = engine.run('BTC/USDT', days=1)
report = BacktestReport(result, config, 'BTC/USDT')
report.print_summary()
csv_path = report.export_csv()
png_path = report.plot_equity()
print(f'CSV: {csv_path}')
print(f'PNG: {png_path}')
"
```

Expected: Stats printed, CSV and PNG files created in `data/backtest_results/`

- [ ] **Step 2: Verify output files exist**

Run: `ls data/backtest_results/`
Expected: At least one `.csv` and one `_equity.png` file

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: backtest end-to-end verification fixes"
```

---

## Summary of Commits

| # | Message | Key Files |
|---|---------|-----------|
| 1 | `feat: add backtest package and matplotlib dependency` | pyproject.toml, backtest/__init__.py |
| 2 | `feat: add historical data loader with CSV cache` | backtest/data_loader.py |
| 3 | `feat: implement simulated executor with intra-candle TP/SL` | backtest/simulator.py, tests/test_simulator.py |
| 4 | `feat: implement backtest engine with candle-by-candle simulation` | backtest/engine.py |
| 5 | `feat: implement backtest report (terminal, CSV, PNG)` | backtest/report.py |
| 6 | `test: add backtest engine integration tests` | tests/test_backtest_engine.py |
| 7 | `fix: end-to-end verification fixes` | (various if needed) |

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import numpy as np
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
            last_ts = last_candle["timestamp"] / 1000.0 if last_candle["timestamp"] > 1e12 else last_candle["timestamp"]
            for pos in open_positions:
                trade = self.executor._close(pos, last_candle["close"], "TIMEOUT", last_ts)
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

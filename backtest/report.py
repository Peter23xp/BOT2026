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

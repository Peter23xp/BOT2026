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

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

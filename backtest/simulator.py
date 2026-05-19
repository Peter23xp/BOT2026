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
        sl = position["stop_loss"]
        tp = position["take_profit"]

        # SL check (priority 1)
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
        fill_price = position["fill_price"]
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

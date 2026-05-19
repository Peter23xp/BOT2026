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

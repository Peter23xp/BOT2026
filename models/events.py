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

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

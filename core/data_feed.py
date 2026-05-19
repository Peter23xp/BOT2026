import asyncio
import csv
import time
from pathlib import Path
from typing import Literal

import pandas as pd
from loguru import logger
from ta.momentum import RSIIndicator
from ta.trend import EMAIndicator

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

    def _futures_symbol(self, pair: str) -> str:
        """Convertit BTC/USDT en BTC/USDT:USDT pour Futures."""
        if ":" not in pair:
            quote = pair.split("/")[1] if "/" in pair else "USDT"
            return f"{pair}:{quote}"
        return pair

    async def _run_live(self, output_queue: asyncio.Queue) -> None:
        logger.info(f"DataFeed live demarre pour {self.pairs} ({self.timeframe})")

        # Pre-charger le buffer avec des données historiques REST
        for pair in self.pairs:
            try:
                symbol = self._futures_symbol(pair)
                candles = await self.exchange.fetch_ohlcv(symbol, self.timeframe, limit=self._buffer_size)
                if candles:
                    self._candle_buffer[pair] = candles
                    logger.info(f"Buffer initial {pair}: {len(candles)} bougies chargees")
            except Exception as e:
                logger.warning(f"Impossible de pre-charger {pair}: {e}")

        while not self._shutdown:
            try:
                for pair in self.pairs:
                    symbol = self._futures_symbol(pair)
                    ohlcv = await self.exchange.watch_ohlcv(symbol, self.timeframe)
                    order_book = await self.exchange.watch_order_book(symbol, limit=5)

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

        rsi_indicator = RSIIndicator(close=df["close"], window=7)
        rsi_series = rsi_indicator.rsi()

        ema_indicator = EMAIndicator(close=df["close"], window=20)
        ema_series = ema_indicator.ema_indicator()

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

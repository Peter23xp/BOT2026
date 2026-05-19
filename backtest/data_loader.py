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

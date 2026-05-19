import pytest
from models.events import MarketData, Signal
from core.strategy import ScalpingStrategy


def make_market_data(
    pair="BTC/USDT",
    close=50000.0,
    rsi=30.0,
    rsi_prev=28.0,
    ema=49900.0,
    volume_ratio=1.8,
    bid=49999.0,
    ask=50001.0,
) -> MarketData:
    return MarketData(
        timestamp=1000.0,
        pair=pair,
        open=49950.0,
        high=50050.0,
        low=49900.0,
        close=close,
        volume=100.0,
        bid=bid,
        ask=ask,
        rsi=rsi,
        rsi_prev=rsi_prev,
        ema=ema,
        volume_ratio=volume_ratio,
    )


class TestLongSignal:
    def setup_method(self):
        self.strategy = ScalpingStrategy()

    def test_long_signal_all_conditions_met(self):
        """Signal LONG emis quand toutes les 5 conditions sont vraies."""
        data = make_market_data(
            rsi=33.0, rsi_prev=30.0, close=50000.0, ema=49900.0,
            volume_ratio=1.8, bid=49999.0, ask=50001.0
        )
        signal = self.strategy.evaluate(data)
        assert signal is not None
        assert signal.side == "LONG"
        assert signal.pair == "BTC/USDT"

    def test_no_signal_rsi_too_high(self):
        """Pas de signal si RSI >= 35."""
        data = make_market_data(rsi=40.0, rsi_prev=38.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_rsi_not_rising(self):
        """Pas de signal si RSI ne remonte pas."""
        data = make_market_data(rsi=30.0, rsi_prev=32.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_price_below_ema(self):
        """Pas de signal si prix < EMA."""
        data = make_market_data(close=49800.0, ema=49900.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_low_volume(self):
        """Pas de signal si volume_ratio < 1.5."""
        data = make_market_data(volume_ratio=1.2)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_high_spread(self):
        """Pas de signal si spread > 0.05%."""
        data = make_market_data(bid=49900.0, ask=49950.0)
        signal = self.strategy.evaluate(data)
        assert signal is None

    def test_no_signal_position_already_open(self):
        """Pas de signal si position deja ouverte sur la paire."""
        data = make_market_data()
        self.strategy.open_positions.add("BTC/USDT")
        signal = self.strategy.evaluate(data)
        assert signal is None


class TestShortSignal:
    def setup_method(self):
        self.strategy = ScalpingStrategy()

    def test_short_signal_all_conditions_met(self):
        """Signal SHORT emis avec conditions symetriques."""
        data = make_market_data(
            rsi=68.0, rsi_prev=70.0, close=49800.0, ema=49900.0,
            volume_ratio=1.8, bid=49799.0, ask=49801.0
        )
        signal = self.strategy.evaluate(data)
        assert signal is not None
        assert signal.side == "SHORT"

    def test_no_short_signal_rsi_too_low(self):
        """Pas de signal SHORT si RSI <= 65."""
        data = make_market_data(
            rsi=60.0, rsi_prev=62.0, close=49800.0, ema=49900.0,
            volume_ratio=1.8, bid=49799.0, ask=49801.0
        )
        signal = self.strategy.evaluate(data)
        assert signal is None

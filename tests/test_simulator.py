import pytest
from models.events import Signal
from backtest.simulator import SimulatedExecutor


def make_signal(pair="BTC/USDT", side="LONG", entry_price=50000.0) -> Signal:
    return Signal(
        timestamp=1000.0,
        pair=pair,
        side=side,
        entry_price=entry_price,
        rsi=30.0,
        ema_distance=0.2,
        volume_ratio=1.8,
        spread=0.003,
    )


class TestOpenPosition:
    def setup_method(self):
        self.executor = SimulatedExecutor(fees_percent=0.04, slippage_percent=0.01)

    def test_open_long_with_slippage(self):
        signal = make_signal(side="LONG", entry_price=50000.0)
        pos = self.executor.open_position(signal, size=0.1, stop_loss=49925.0, take_profit=50150.0)
        assert abs(pos["fill_price"] - 50005.0) < 0.01
        assert pos["side"] == "LONG"
        assert pos["size"] == 0.1

    def test_open_short_with_slippage(self):
        signal = make_signal(side="SHORT", entry_price=50000.0)
        pos = self.executor.open_position(signal, size=0.1, stop_loss=50075.0, take_profit=49850.0)
        assert abs(pos["fill_price"] - 49995.0) < 0.01
        assert pos["side"] == "SHORT"


class TestCheckExit:
    def setup_method(self):
        self.executor = SimulatedExecutor(fees_percent=0.04, slippage_percent=0.01)

    def _make_long_position(self):
        signal = make_signal(side="LONG", entry_price=50000.0)
        return self.executor.open_position(signal, size=0.1, stop_loss=49925.0, take_profit=50150.0)

    def _make_short_position(self):
        signal = make_signal(side="SHORT", entry_price=50000.0)
        return self.executor.open_position(signal, size=0.1, stop_loss=50075.0, take_profit=49850.0)

    def test_long_stop_loss_hit(self):
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50050, "low": 49900, "close": 49950, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "SL"
        assert result["exit_price"] == 49925.0

    def test_long_take_profit_hit(self):
        pos = self._make_long_position()
        candle = {"open": 50100, "high": 50200, "low": 50050, "close": 50180, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "TP"
        assert result["exit_price"] == 50150.0

    def test_long_sl_priority_over_tp(self):
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50200, "low": 49900, "close": 50100, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "SL"

    def test_timeout(self):
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50050, "low": 49950, "close": 50010, "timestamp": 1300.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=5)
        assert result is not None
        assert result["reason"] == "TIMEOUT"
        assert result["exit_price"] == 50010

    def test_no_exit(self):
        pos = self._make_long_position()
        candle = {"open": 50000, "high": 50050, "low": 49950, "close": 50020, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is None

    def test_short_stop_loss_hit(self):
        pos = self._make_short_position()
        candle = {"open": 50000, "high": 50100, "low": 49950, "close": 50050, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "SL"
        assert result["exit_price"] == 50075.0

    def test_short_take_profit_hit(self):
        pos = self._make_short_position()
        candle = {"open": 49900, "high": 49950, "low": 49800, "close": 49850, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        assert result is not None
        assert result["reason"] == "TP"
        assert result["exit_price"] == 49850.0

    def test_pnl_calculation_long_profit(self):
        pos = self._make_long_position()
        candle = {"open": 50100, "high": 50200, "low": 50050, "close": 50180, "timestamp": 1060.0}
        result = self.executor.check_exit(pos, candle, elapsed_candles=1)
        # fill_price=50005, exit=50150, size=0.1
        # gross: (50150-50005)*0.1 = 14.5
        # fees: 50005*0.1*0.0004 + 50150*0.1*0.0004 = 2.0002 + 2.006 = 4.0062
        # net: 14.5 - 4.0062 = 10.4938
        assert abs(result["pnl_usdt"] - 10.4938) < 0.1

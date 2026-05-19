import pytest
from models.events import Signal, OrderRequest
from core.risk_manager import RiskManager


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


class TestPositionSizing:
    def setup_method(self):
        self.rm = RiskManager(
            capital=1000.0,
            risk_per_trade_percent=1.0,
            max_drawdown_percent=15.0,
            daily_drawdown_limit=5.0,
            max_open_positions=3,
            leverage=5,
            stop_loss_percent=0.15,
            take_profit_percent=0.3,
        )

    def test_calculate_size(self):
        """Taille = (capital * risk%) / (price * SL%)."""
        size = self.rm.calculate_size(50000.0)
        # (1000 * 0.01) / (50000 * 0.0015) = 10 / 75 = 0.1333...
        assert abs(size - 0.13333) < 0.001

    def test_approve_normal_conditions(self):
        """Approuve un signal dans des conditions normales."""
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is True
        assert reason == ""

    def test_reject_max_positions_reached(self):
        """Refuse si max positions atteint."""
        self.rm.open_position_count = 3
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is False
        assert "positions" in reason.lower()

    def test_reject_daily_drawdown_exceeded(self):
        """Refuse si drawdown journalier depasse 5%."""
        self.rm.daily_pnl = -51.0  # -5.1% of 1000
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is False
        assert "journalier" in reason.lower()

    def test_reject_total_drawdown_exceeded(self):
        """Refuse si drawdown total depasse 15%."""
        self.rm.total_pnl = -151.0  # -15.1% of 1000
        signal = make_signal()
        approved, reason = self.rm.approve(signal)
        assert approved is False
        assert "total" in reason.lower()

    def test_build_order_request(self):
        """Construit un OrderRequest avec les bons TP/SL."""
        signal = make_signal(entry_price=50000.0)
        order = self.rm.build_order_request(signal)
        assert order.entry_price == 50000.0
        # LONG: SL = entry * (1 - 0.0015) = 49925
        assert abs(order.stop_loss - 49925.0) < 0.01
        # LONG: TP = entry * (1 + 0.003) = 50150
        assert abs(order.take_profit - 50150.0) < 0.01
        assert order.size > 0

    def test_build_order_request_short(self):
        """TP/SL inverses pour SHORT."""
        signal = make_signal(side="SHORT", entry_price=50000.0)
        order = self.rm.build_order_request(signal)
        # SHORT: SL = entry * (1 + 0.0015) = 50075
        assert abs(order.stop_loss - 50075.0) < 0.01
        # SHORT: TP = entry * (1 - 0.003) = 49850
        assert abs(order.take_profit - 49850.0) < 0.01

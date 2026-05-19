import pytest
from core.pnl_tracker import PnLCalculator


class TestPnLCalculation:
    def setup_method(self):
        self.calc = PnLCalculator(fees_percent=0.04)

    def test_long_profit(self):
        """PnL correct pour un LONG gagnant."""
        pnl = self.calc.calculate_pnl(
            side="LONG", entry_price=50000.0, exit_price=50150.0, size=0.1
        )
        # Brut: (50150 - 50000) * 0.1 = 15.0
        # Frais: 50000*0.1*0.0004 + 50150*0.1*0.0004 = 2.0 + 2.006 = 4.006
        # Net: 15.0 - 4.006 = 10.994
        assert abs(pnl - 10.994) < 0.01

    def test_long_loss(self):
        """PnL correct pour un LONG perdant."""
        pnl = self.calc.calculate_pnl(
            side="LONG", entry_price=50000.0, exit_price=49925.0, size=0.1
        )
        # Brut: (49925 - 50000) * 0.1 = -7.5
        # Frais: 50000*0.1*0.0004 + 49925*0.1*0.0004 = 2.0 + 1.997 = 3.997
        # Net: -7.5 - 3.997 = -11.497
        assert abs(pnl - (-11.497)) < 0.01

    def test_short_profit(self):
        """PnL correct pour un SHORT gagnant."""
        pnl = self.calc.calculate_pnl(
            side="SHORT", entry_price=50000.0, exit_price=49850.0, size=0.1
        )
        # Brut: (50000 - 49850) * 0.1 = 15.0
        # Frais: 50000*0.1*0.0004 + 49850*0.1*0.0004 = 2.0 + 1.994 = 3.994
        # Net: 15.0 - 3.994 = 11.006
        assert abs(pnl - 11.006) < 0.01

    def test_short_loss(self):
        """PnL correct pour un SHORT perdant."""
        pnl = self.calc.calculate_pnl(
            side="SHORT", entry_price=50000.0, exit_price=50075.0, size=0.1
        )
        # Brut: (50000 - 50075) * 0.1 = -7.5
        # Frais: 50000*0.1*0.0004 + 50075*0.1*0.0004 = 2.0 + 2.003 = 4.003
        # Net: -7.5 - 4.003 = -11.503
        assert abs(pnl - (-11.503)) < 0.01


class TestWinRate:
    def setup_method(self):
        self.calc = PnLCalculator(fees_percent=0.04)

    def test_win_rate_all_wins(self):
        """Win rate = 100% si tous les trades sont gagnants."""
        self.calc.record_trade(5.0)
        self.calc.record_trade(3.0)
        self.calc.record_trade(7.0)
        assert self.calc.win_rate == 100.0

    def test_win_rate_mixed(self):
        """Win rate correct pour un mix."""
        self.calc.record_trade(5.0)
        self.calc.record_trade(-3.0)
        self.calc.record_trade(7.0)
        self.calc.record_trade(-2.0)
        assert self.calc.win_rate == 50.0

    def test_win_rate_no_trades(self):
        """Win rate = 0 si aucun trade."""
        assert self.calc.win_rate == 0.0


class TestDrawdown:
    def setup_method(self):
        self.calc = PnLCalculator(fees_percent=0.04)

    def test_max_drawdown(self):
        """Max drawdown calcule correctement."""
        self.calc.record_trade(10.0)   # equity: 10
        self.calc.record_trade(5.0)    # equity: 15 (peak)
        self.calc.record_trade(-8.0)   # equity: 7, dd = 8/15 = 53.3%
        self.calc.record_trade(3.0)    # equity: 10
        assert abs(self.calc.max_drawdown_percent - 53.33) < 0.1

    def test_no_drawdown_only_profits(self):
        """Pas de drawdown si que des profits."""
        self.calc.record_trade(5.0)
        self.calc.record_trade(3.0)
        assert self.calc.max_drawdown_percent == 0.0

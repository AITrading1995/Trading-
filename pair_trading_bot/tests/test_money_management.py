import unittest
import sys
import os

# Adjust path to import from src
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../tests
parent_dir = os.path.dirname(current_dir) # .../pair_trading_bot
sys.path.insert(0, parent_dir) # Add .../pair_trading_bot to path

from src.money_management import calculate_position_size, calculate_stop_loss_take_profit

class TestMoneyManagement(unittest.TestCase):

    def test_calculate_position_size_normal_conditions(self):
        size = calculate_position_size(
            account_balance=10000,
            risk_percentage=0.01, # 1% risk -> $100
            stop_loss_pips=50,
            pips_per_unit=0, # Added to match function signature, value based on previous test cases
            price_per_pip_leg1=10.0, # Risk $10 per pip for 1 lot. $100 / (50 * $10) = $100 / $500 = 0.2 lots
            is_spread_trade=False
        )
        self.assertEqual(size, 0.20)

    def test_calculate_position_size_spread_trade(self):
        # Using simplified spread trade logic where price_per_pip_leg1 is for the spread instrument
        size = calculate_position_size(
            account_balance=5000,
            risk_percentage=0.02, # 2% risk -> $100
            stop_loss_pips=100,
            pips_per_unit=0, # Added
            price_per_pip_leg1=2.0, # Risk $2 per pip for 1 lot of spread. $100 / (100 * $2) = $100 / $200 = 0.5 lots
            is_spread_trade=True
        )
        self.assertEqual(size, 0.50)

    def test_calculate_position_size_zero_sl_pips(self):
        size = calculate_position_size(10000, 0.01, 0, 0, 10.0) # Added pips_per_unit
        self.assertEqual(size, 0.0)

    def test_calculate_position_size_zero_price_per_pip(self):
        size = calculate_position_size(10000, 0.01, 50, 0, 0) # Added pips_per_unit
        self.assertEqual(size, 0.0)

    def test_calculate_position_size_zero_balance_or_risk(self):
        size1 = calculate_position_size(0, 0.01, 50, 0, 10.0) # Added pips_per_unit
        self.assertEqual(size1, 0.0)
        size2 = calculate_position_size(10000, 0, 50, 0, 10.0) # Added pips_per_unit
        self.assertEqual(size2, 0.0)

    def test_calculate_stop_loss_take_profit_long_spread(self):
        # Long spread: entered at low Z (e.g., -2.0), expect Z to rise.
        # SL if Z goes lower (e.g., -3.0). TP if Z reaches target (e.g., 0.0 or -0.5).
        entry_price = 10.0 # Spread value at entry
        z_score_entry = -2.0
        mean_spread = 11.5 # Mean of the spread
        std_spread = 0.75  # (10.0 - 11.5) / -2.0 = -1.5 / -2.0 = 0.75

        stop_loss_z_level_config = 3.0 # Absolute SL Z-level -> -3.0 for long
        take_profit_z_target_config = 0.0 # Target Z for TP

        sl_price, tp_price = calculate_stop_loss_take_profit(
            entry_price=entry_price,
            z_score=z_score_entry,
            mean_spread=mean_spread,
            std_spread=std_spread,
            stop_loss_z_multiplier=stop_loss_z_level_config,
            take_profit_z_target=take_profit_z_target_config,
            is_long_spread=True
        )
        # Expected SL: mean + (-3.0 * std) = 11.5 + (-3.0 * 0.75) = 11.5 - 2.25 = 9.25
        # Expected TP: mean + (0.0 * std) = 11.5
        self.assertAlmostEqual(sl_price, 9.25)
        self.assertAlmostEqual(tp_price, 11.5)

    def test_calculate_stop_loss_take_profit_short_spread(self):
        # Short spread: entered at high Z (e.g., +2.0), expect Z to fall.
        # SL if Z goes higher (e.g., +3.0). TP if Z reaches target (e.g., 0.0 or +0.5).
        entry_price = 13.0 # Spread value at entry
        z_score_entry = 2.0
        mean_spread = 11.5 # Mean of the spread
        std_spread = 0.75  # (13.0 - 11.5) / 2.0 = 1.5 / 2.0 = 0.75

        stop_loss_z_level_config = 3.0 # Absolute SL Z-level -> +3.0 for short
        take_profit_z_target_config = 0.0 # Target Z for TP

        sl_price, tp_price = calculate_stop_loss_take_profit(
            entry_price=entry_price,
            z_score=z_score_entry,
            mean_spread=mean_spread,
            std_spread=std_spread,
            stop_loss_z_multiplier=stop_loss_z_level_config,
            take_profit_z_target=take_profit_z_target_config,
            is_long_spread=False
        )
        # Expected SL: mean + (3.0 * std) = 11.5 + (3.0 * 0.75) = 11.5 + 2.25 = 13.75
        # Expected TP: mean + (0.0 * std) = 11.5
        self.assertAlmostEqual(sl_price, 13.75)
        self.assertAlmostEqual(tp_price, 11.5)

    def test_calculate_stop_loss_take_profit_zero_std_dev(self):
        sl_price, tp_price = calculate_stop_loss_take_profit(
            entry_price=10, z_score=-2.0, mean_spread=10, std_spread=0,
            stop_loss_z_multiplier=3.0, take_profit_z_target=0, is_long_spread=True
        )
        # Should return entry_price if std_dev is zero as fallback
        self.assertEqual(sl_price, 10)
        self.assertEqual(tp_price, 10)

    def test_calculate_sl_tp_long_spread_alternative_tp(self):
        entry_price = 10.0
        z_score_entry = -2.0
        mean_spread = 11.5
        std_spread = 0.75
        stop_loss_z_level_config = 3.0
        take_profit_z_target_config = -0.5 # TP if Z reaches -0.5

        sl_price, tp_price = calculate_stop_loss_take_profit(
            entry_price=entry_price,
            z_score=z_score_entry,
            mean_spread=mean_spread,
            std_spread=std_spread,
            stop_loss_z_multiplier=stop_loss_z_level_config,
            take_profit_z_target=take_profit_z_target_config,
            is_long_spread=True
        )
        # Expected SL: 9.25
        # Expected TP: mean + (-0.5 * std) = 11.5 + (-0.5 * 0.75) = 11.5 - 0.375 = 11.125
        self.assertAlmostEqual(sl_price, 9.25)
        self.assertAlmostEqual(tp_price, 11.125)

if __name__ == '__main__':
    unittest.main()

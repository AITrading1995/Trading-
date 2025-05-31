import unittest
from unittest.mock import patch, MagicMock, PropertyMock
import pandas as pd
import numpy as np
import sys
import os
import time

# Adjust path to import from src
current_dir = os.path.dirname(os.path.abspath(__file__)) # .../tests
parent_dir = os.path.dirname(current_dir) # .../pair_trading_bot
sys.path.insert(0, parent_dir) # Add .../pair_trading_bot to path

from src.trading_bot import PairTradingBot
# Need to import the actual modules to mock their functions effectively
import src.utils as utils_module
import src.money_management as mm_module

# Default configuration for the bot during tests
DEFAULT_CONFIG = {
    "symbol1": "SYM1",
    "symbol2": "SYM2",
    "timeframe": "H1",
    "lookback_period": 60, # Shorter for faster tests
    "entry_z_threshold": 2.0,
    "exit_z_threshold": 0.5,
    "stop_loss_z_multiplier": 3.0,
    "account_balance": 10000,
    "risk_percentage": 0.01,
    "pip_value_leg1": 10.0, # Pip value for SYM1 or spread
    "pip_value_leg2": 9.0,  # Pip value for SYM2
    "min_trade_interval_seconds": 10
}

class TestPairTradingBot(unittest.TestCase):

    def setUp(self):
        # Create a bot instance with default config for each test
        # We will use patch decorators or context managers for specific mocks per test method
        self.bot_config = DEFAULT_CONFIG.copy()

        # Mock the mt5 object that trading_bot.py imports from src.utils
        # This ensures that the bot uses a controlled MT5 interface.
        self.mt5_mock_patcher = patch('src.trading_bot.mt5', MagicMock())
        self.mock_mt5 = self.mt5_mock_patcher.start()
        self.mock_mt5.initialize.return_value = True # Default successful init
        self.mock_mt5.TIMEFRAME_H1 = "H1" # Define constants used by bot

        # It's often cleaner to mock the functions within utils and money_management directly
        # when testing the bot's logic, rather than just MT5.
        self.download_patcher = patch('src.trading_bot.download_price_data')
        self.coint_patcher = patch('src.trading_bot.calculate_cointegration')
        self.spread_patcher = patch('src.trading_bot.calculate_spread')
        self.zscore_patcher = patch('src.trading_bot.calculate_zscore')
        self.pos_size_patcher = patch('src.trading_bot.calculate_position_size')
        self.sl_tp_patcher = patch('src.trading_bot.calculate_stop_loss_take_profit')

        self.mock_download = self.download_patcher.start()
        self.mock_coint = self.coint_patcher.start()
        self.mock_spread = self.spread_patcher.start()
        self.mock_zscore = self.zscore_patcher.start()
        self.mock_pos_size = self.pos_size_patcher.start()
        self.mock_sl_tp = self.sl_tp_patcher.start()

        # Default mock behaviors
        self.mock_download.return_value = self._create_dummy_series(self.bot_config["lookback_period"])
        self.mock_coint.return_value = (True, 0.9) # Cointegrated, hedge_ratio = 0.9
        self.mock_spread.return_value = self._create_dummy_series(self.bot_config["lookback_period"], name='spread')
        self.mock_zscore.return_value = self._create_dummy_series(self.bot_config["lookback_period"], name='zscore', mean=0, std=1)
        self.mock_pos_size.return_value = 0.1 # Default position size
        self.mock_sl_tp.return_value = (1.0, 2.0) # (sl_price, tp_price)

        self.bot = PairTradingBot(**self.bot_config)
        # Ensure bot's internal mt5 is the one we mocked via trading_bot's import scope
        self.bot.is_mt5_initialized = True # Assume successful init after mocks

    def tearDown(self):
        self.mt5_mock_patcher.stop()
        self.download_patcher.stop()
        self.coint_patcher.stop()
        self.spread_patcher.stop()
        self.zscore_patcher.stop()
        self.pos_size_patcher.stop()
        self.sl_tp_patcher.stop()
        # Ensure MT5 shutdown is called if bot was initialized
        if hasattr(self.bot, 'shutdown_mt5'):
             self.bot.shutdown_mt5()


    def _create_dummy_series(self, n_points, name=None, mean=100, std=1): # Corrected: self is first argument
        return pd.Series(np.random.normal(mean, std, n_points), name=name)

    def test_bot_initialization(self):
        self.assertEqual(self.bot.symbol1, self.bot_config["symbol1"])
        self.assertEqual(self.bot.account_balance, self.bot_config["account_balance"])
        self.assertTrue(self.bot.is_mt5_initialized) # Due to mock

    def test_update_market_data_success(self):
        # Default mocks should lead to success
        result = self.bot._update_market_data_and_parameters()
        self.assertTrue(result)
        self.assertIsNotNone(self.bot.hedge_ratio)
        self.assertFalse(self.bot.current_spread.empty)
        self.assertIsNotNone(self.bot.current_zscore)
        self.mock_download.assert_any_call(self.bot_config["symbol1"], self.bot_config["lookback_period"])
        self.mock_download.assert_any_call(self.bot_config["symbol2"], self.bot_config["lookback_period"])
        self.mock_coint.assert_called_once()
        self.mock_spread.assert_called_once()
        self.mock_zscore.assert_called_once()

    def test_update_market_data_fetch_fails(self):
        self.mock_download.return_value = pd.Series(dtype=np.float64) # Empty series
        result = self.bot._update_market_data_and_parameters()
        self.assertFalse(result)

    def test_update_market_data_not_coint(self):
        self.mock_coint.return_value = (False, 0.0) # Not cointegrated
        result = self.bot._update_market_data_and_parameters()
        self.assertFalse(result)
        self.assertIsNone(self.bot.hedge_ratio)

    def test_signal_generation_no_open_pos_buy_signal(self):
        # Make z-score low enough to trigger buy
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        z_series.iloc[-1] = - (self.bot_config["entry_z_threshold"] + 0.1)
        self.mock_zscore.return_value = z_series

        self.bot._update_market_data_and_parameters() # To set the zscore
        signal = self.bot._generate_signals()
        self.assertEqual(signal, 'BUY_SPREAD')

    def test_signal_generation_no_open_pos_sell_signal(self):
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        z_series.iloc[-1] = self.bot_config["entry_z_threshold"] + 0.1
        self.mock_zscore.return_value = z_series

        self.bot._update_market_data_and_parameters()
        signal = self.bot._generate_signals()
        self.assertEqual(signal, 'SELL_SPREAD')

    def test_signal_generation_no_signal_within_threshold(self):
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        z_series.iloc[-1] = 0.0 # Within thresholds
        self.mock_zscore.return_value = z_series

        self.bot._update_market_data_and_parameters()
        signal = self.bot._generate_signals()
        self.assertIsNone(signal)

    def test_signal_generation_exit_long_signal(self):
        self.bot.open_position = {'type': 'BUY_SPREAD'} # Simulate open long position
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        # Z-score rises above negative exit threshold (e.g. -0.5, if exit_z is 0.5)
        z_series.iloc[-1] = -self.bot_config["exit_z_threshold"] + 0.1
        self.mock_zscore.return_value = z_series

        self.bot._update_market_data_and_parameters()
        signal = self.bot._generate_signals()
        self.assertEqual(signal, 'EXIT_LONG')

    def test_signal_generation_exit_short_signal(self):
        self.bot.open_position = {'type': 'SELL_SPREAD'} # Simulate open short position
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        # Z-score falls below positive exit threshold (e.g. 0.5, if exit_z is 0.5)
        z_series.iloc[-1] = self.bot_config["exit_z_threshold"] - 0.1
        self.mock_zscore.return_value = z_series

        self.bot._update_market_data_and_parameters()
        signal = self.bot._generate_signals()
        self.assertEqual(signal, 'EXIT_SHORT')

    def test_execute_trade_buy_spread(self):
        # Setup for BUY_SPREAD
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        z_series.iloc[-1] = -(self.bot_config["entry_z_threshold"] + 0.1)
        self.mock_zscore.return_value = z_series
        self.mock_spread.return_value = self._create_dummy_series(self.bot_config["lookback_period"], mean=10, std=1) # ensure std > 0

        self.bot._update_market_data_and_parameters() # Populate spread and z-score
        self.bot._execute_trade('BUY_SPREAD')

        self.assertIsNotNone(self.bot.open_position)
        self.assertEqual(self.bot.open_position['type'], 'BUY_SPREAD')
        self.mock_pos_size.assert_called_once()
        self.mock_sl_tp.assert_called_once()
        # self.mock_mt5.order_send.assert_any_call(...) # If testing actual MT5 calls

    def test_execute_trade_sell_spread(self):
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        z_series.iloc[-1] = self.bot_config["entry_z_threshold"] + 0.1
        self.mock_zscore.return_value = z_series
        self.mock_spread.return_value = self._create_dummy_series(self.bot_config["lookback_period"], mean=10, std=1)

        self.bot._update_market_data_and_parameters()
        self.bot._execute_trade('SELL_SPREAD')

        self.assertIsNotNone(self.bot.open_position)
        self.assertEqual(self.bot.open_position['type'], 'SELL_SPREAD')

    def test_execute_trade_position_size_zero(self):
        self.mock_pos_size.return_value = 0.0 # Simulate zero position size
        self.bot._update_market_data_and_parameters() # Needed for spread stats
        self.bot._execute_trade('BUY_SPREAD')
        self.assertIsNone(self.bot.open_position)

    def test_execute_trade_close_position(self):
        # First, open a position
        self.bot.open_position = {
            'type': 'BUY_SPREAD', 'entry_price_spread': 1.0, 'size': 0.1,
            'sl_price_spread': 0.5, 'tp_price_spread': 1.5,
            'symbol1': 'SYM1', 'symbol2': 'SYM2', 'hedge_ratio': 0.9
        }
        self.bot.account_balance = 10000 # Reset for P/L check

        # Mock current spread for P/L calculation
        current_spread_series = self._create_dummy_series(self.bot_config["lookback_period"])
        current_spread_series.iloc[-1] = 1.2 # Exit price for BUY_SPREAD
        # self.mock_spread.return_value = current_spread_series # This was correctly mocked but _update needs to be called
        # self.bot._update_market_data_and_parameters() # Update current_spread

        # Instead of full _update, just set current_spread as it's directly used by _close_position_logic via _execute_trade
        self.bot.current_spread = current_spread_series
        # Also need to set current_zscore as _close_position_logic logs it.
        self.bot.current_zscore = self._create_dummy_series(self.bot_config["lookback_period"], name='zscore')


        self.bot._execute_trade('EXIT_LONG')

        self.assertIsNone(self.bot.open_position)
        # P/L = (1.2 - 1.0) * 0.1 * 10.0 (pip_value_leg1) = 0.2 * 0.1 * 10 = 0.02 * 10 = 0.2
        # New balance = 10000 + 0.2 = 10000.2
        self.assertAlmostEqual(self.bot.account_balance, 10000.2)


    def test_check_stop_loss_hit_long(self):
        self.bot.open_position = {
            'type': 'BUY_SPREAD', 'entry_price_spread': 1.0, 'size': 0.1,
            'sl_price_spread': 0.8, 'tp_price_spread': 1.2, # SL at 0.8
            'symbol1': 'SYM1', 'symbol2': 'SYM2', 'hedge_ratio': 0.9
        }
        # Current spread drops below SL
        current_spread_series = self._create_dummy_series(self.bot_config["lookback_period"])
        current_spread_series.iloc[-1] = 0.7
        self.bot.current_spread = current_spread_series # Manually set for this test
        # Also need to set current_zscore as _close_position_logic (called by SL) logs it.
        self.bot.current_zscore = self._create_dummy_series(self.bot_config["lookback_period"], name='zscore')


        self.bot._check_stop_loss_take_profit()
        self.assertIsNone(self.bot.open_position) # Position should be closed

    def test_check_take_profit_hit_short(self):
        self.bot.open_position = {
            'type': 'SELL_SPREAD', 'entry_price_spread': 1.0, 'size': 0.1,
            'sl_price_spread': 1.2, 'tp_price_spread': 0.8, # TP at 0.8
            'symbol1': 'SYM1', 'symbol2': 'SYM2', 'hedge_ratio': 0.9
        }
        current_spread_series = self._create_dummy_series(self.bot_config["lookback_period"])
        current_spread_series.iloc[-1] = 0.7 # Current spread drops below TP
        self.bot.current_spread = current_spread_series
        self.bot.current_zscore = self._create_dummy_series(self.bot_config["lookback_period"], name='zscore')


        self.bot._check_stop_loss_take_profit()
        self.assertIsNone(self.bot.open_position)

    def test_run_check_full_cycle_opens_trade(self):
        # Configure mocks to ensure a trade is opened
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        z_series.iloc[-1] = -(self.bot_config["entry_z_threshold"] + 0.1) # Trigger BUY
        self.mock_zscore.return_value = z_series
        self.mock_spread.return_value = self._create_dummy_series(self.bot_config["lookback_period"], mean=10, std=1) # Ensure std > 0 for SL/TP calc

        self.bot.run_check() # This calls _update_market_data, _generate_signals, _execute_trade

        self.mock_coint.assert_called()
        self.mock_zscore.assert_called()
        self.mock_pos_size.assert_called()
        self.assertIsNotNone(self.bot.open_position)
        self.assertEqual(self.bot.open_position['type'], 'BUY_SPREAD')

    def test_run_check_closes_trade_on_exit_signal(self):
        # Setup an open position
        self.bot.open_position = {
            'type': 'BUY_SPREAD', 'entry_price_spread': 1.0, 'size': 0.1,
            'sl_price_spread': 0.5, 'tp_price_spread': 1.5,
            'symbol1': 'SYM1', 'symbol2': 'SYM2', 'hedge_ratio': 0.9
        }
        # Configure mocks for exit signal
        z_series = self._create_dummy_series(self.bot_config["lookback_period"])
        z_series.iloc[-1] = -self.bot_config["exit_z_threshold"] + 0.1 # Trigger EXIT_LONG
        self.mock_zscore.return_value = z_series
        # Mock spread for P/L calc
        current_spread_series = self._create_dummy_series(self.bot_config["lookback_period"])
        current_spread_series.iloc[-1] = 1.2
        self.mock_spread.return_value = current_spread_series

        self.bot.run_check()

        self.assertIsNone(self.bot.open_position)


if __name__ == '__main__':
    # Important: If run directly, ensure that the paths are set up correctly
    # typically by running `python -m unittest pair_trading_bot/tests/test_trading_bot.py`
    # from the project root directory.
    unittest.main()

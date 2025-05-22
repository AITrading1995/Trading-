import unittest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np

# Attempt to import Bot and SimpleMACrossoverStrategy from bot.py
# This assumes bot.py is in the same directory or accessible via PYTHONPATH
try:
    from bot import Bot, SimpleMACrossoverStrategy, Interval 
except ImportError:
    print("Ensure bot.py is in the same directory or PYTHONPATH is set for tests.")
    # Define dummy versions if import fails, so tests can be outlined (though they might not fully run)
    class Interval: # Dummy for definition
        in_1_hour = "1h"
        in_15_minute = "15m"

    class Bot: # Dummy
        def __init__(self,symbol, exchange): pass
        def download(self, timeframe, bars): pass
        def backtest(self, timeframe, strategy_logic, initial_capital, bars, commission_bps): pass
        def generate_summary_report(self, backtest_results): pass
        def plot_results(self, backtest_results): pass

    class SimpleMACrossoverStrategy: # Dummy
         def __init__(self, short_window, long_window): pass
         def generate_signals(self, df): pass


class TestSimpleMACrossoverStrategy(unittest.TestCase):
    def test_strategy_signal_generation(self):
        strategy = SimpleMACrossoverStrategy(short_window=2, long_window=4)
        # Create sample data: short MA should cross above long MA, then below
        data = {
            'close': [10, 11, 12, 13, 14, 13, 12, 11, 10], # Price goes up, then down
            'open':  [10, 11, 12, 13, 14, 13, 12, 11, 10],
            'high':  [10, 11, 12, 13, 14, 13, 12, 11, 10],
            'low':   [10, 11, 12, 13, 14, 13, 12, 11, 10],
        }
        sample_df = pd.DataFrame(data, index=pd.to_datetime([f'2023-01-01 0{i}:00:00' for i in range(1,10)]))
        
        signals_df = strategy.generate_signals(sample_df)

        self.assertIn('signal', signals_df.columns)
        # Expected signals (approximate, depends on exact MA calculation and window effects):
        # Prices: 10, 11, 12, 13, 14, 13, 12, 11, 10
        # ShortMA(2): -, 10.5, 11.5, 12.5, 13.5, 13.5, 12.5, 11.5, 10.5
        # LongMA(4):  -, -, -, 11.5, 12.5, 13, 12.75, 12, 11.25
        # Signal (after long_window=4):
        # Bar 4 (idx 3): short 12.5 > long 11.5 -> BUY (1)
        # Bar 5 (idx 4): short 13.5 > long 12.5 -> BUY (1) (or hold if already in)
        # Bar 6 (idx 5): short 13.5 == long 13 -> BUY (1) (or hold)
        # Bar 7 (idx 6): short 12.5 < long 12.75 -> SELL (-1)
        # Bar 8 (idx 7): short 11.5 < long 12 -> SELL (-1)
        # Bar 9 (idx 8): short 10.5 < long 11.25 -> SELL (-1)
        
        # Check a few specific points after long_window stabilization period
        # Exact signal points depend on how strategy handles signal persistence vs. new crossover events
        # This strategy generates 1 if short > long, -1 if short < long, else uses previous signal state if not 0
        # Let's check based on the provided strategy logic:
        # np.where(short > long, 1, 0) then np.where(short < long, -1, previous_signal)

        # After long_window (index 3 onwards for 0-indexed df of length 9)
        self.assertEqual(signals_df['signal'].iloc[3], 1.0) # Index 3 (4th bar): 12.5 > 11.5
        self.assertEqual(signals_df['signal'].iloc[4], 1.0) # Index 4 (5th bar): 13.5 > 12.5
        # self.assertEqual(signals_df['signal'].iloc[5], 1.0) # Index 5 (6th bar): 13.5 > 13.0
        self.assertEqual(signals_df['signal'].iloc[6], -1.0) # Index 6 (7th bar): 12.5 < 12.75

class TestBot(unittest.TestCase):
    def setUp(self):
        # Bot instantiation can be done here if it doesn't make external calls in __init__
        # If TvDatafeed() in Bot.__init__ makes calls, we might need to mock it too.
        # For now, assume TvDatafeed() is light or mock it if tests fail/hang.
        with patch('bot.TvDatafeed') as mock_tv_datafeed:
            mock_tv_datafeed.return_value = MagicMock() # Mock instance
            self.bot = Bot(symbol='TEST/SYMBOL', exchange='TESTEX')

    @patch('bot.Bot.download') # Mock the download method within the Bot class
    def test_backtest_simple_buy_hold_sell(self, mock_download):
        # 1. Prepare Mock Data and Strategy
        strategy_mock = MagicMock()
        
        # Create sample price data for the mock download
        data = {
            'open':  [100, 101, 102, 103, 104, 105, 103, 102],
            'high':  [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 103.5, 102.5],
            'low':   [99.5, 100.5, 101.5, 102.5, 103.5, 104.5, 102.5, 101.5],
            'close': [100, 101, 102, 103, 104, 105, 103, 102],
            'volume':[1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000]
        }
        idx = pd.to_datetime([f'2023-01-01 0{i}:00:00' for i in range(1, 9)])
        mock_price_df = pd.DataFrame(data, index=idx)
        mock_download.return_value = mock_price_df

        # Define signals from the mock strategy: Buy at bar 1, Sell at bar 5
        # Signal at bar i, executes at open of bar i+1
        signals_data = {'signal': [0, 1, 0, 0, 0, -1, 0, 0]} # Signal at index 1 (Buy), index 5 (Sell)
        mock_signals_df = pd.DataFrame(signals_data, index=idx)
        strategy_mock.generate_signals.return_value = mock_signals_df

        # 2. Run Backtest
        results = self.bot.backtest(
            timeframe=Interval.in_1_hour, 
            strategy_logic=strategy_mock,
            initial_capital=10000,
            bars=len(mock_price_df), # Use length of our mock data
            commission_bps=0 # No commission for simplicity in this test
        )

        # 3. Assertions
        self.assertIsNotNone(results)
        self.assertEqual(len(results['trade_log']), 1) # One completed trade

        trade = results['trade_log'][0]
        # Entry: Signal at index 1 (price 101), executes at open of index 2 (price 102)
        # Exit: Signal at index 5 (price 105), executes at open of index 6 (price 103)
        self.assertEqual(trade['entry_price'], 102) # Executed at open of bar after signal
        self.assertEqual(trade['exit_price'], 103)  # Executed at open of bar after signal
        
        # PnL = (exit_price - entry_price) * shares
        # Shares = initial_capital / entry_price = 10000 / 102 = 98.039...
        expected_pnl = (103 - 102) * (10000 / 102)
        self.assertAlmostEqual(trade['pnl'], expected_pnl, places=2)
        
        self.assertAlmostEqual(results['performance_metrics']['final_equity'], 10000 + expected_pnl, places=2)
        self.assertEqual(results['performance_metrics']['total_trades'], 1)

    def test_generate_summary_report_basic(self):
        # Create a dummy backtest_results structure
        initial_capital = 10000
        final_equity = 11000
        pnl_trade1 = 500
        pnl_trade2 = 500
        
        dummy_results = {
            'performance_metrics': {
                'initial_capital': initial_capital,
                'final_equity': final_equity,
                'total_pnl': final_equity - initial_capital,
                'total_trades': 2,
            },
            'trade_log': [
                {'pnl': pnl_trade1, 'entry_price': 100, 'exit_price': 105, 'shares': 100, 'type':'long', 'entry_time': pd.Timestamp('20230101'), 'exit_time': pd.Timestamp('20230102')},
                {'pnl': pnl_trade2, 'entry_price': 110, 'exit_price': 115, 'shares': 100, 'type':'long', 'entry_time': pd.Timestamp('20230103'), 'exit_time': pd.Timestamp('20230104')}
            ],
            'equity_curve': pd.Series([10000, 10500, 11000], index=pd.to_datetime(['20230101','20230102','20230104']))
        }
        
        summary = self.bot.generate_summary_report(dummy_results)
        self.assertIsNotNone(summary)
        self.assertEqual(summary['total_pnl'], 1000)
        self.assertEqual(summary['total_trades'], 2)
        self.assertEqual(summary['total_winning_trades'], 2)
        self.assertEqual(summary['total_losing_trades'], 0)
        self.assertAlmostEqual(summary['win_rate_percentage'], 100.0)
        self.assertAlmostEqual(summary['average_win_pnl'], 500)
        self.assertEqual(summary['average_loss_pnl'], 0) # No losing trades
        self.assertEqual(summary['profit_factor'], float('inf')) # No losses
        # Max drawdown: peak 10000, then 10500, then 11000. No drawdown.
        self.assertAlmostEqual(summary['max_drawdown_percentage'], 0.0, places=2)


    def test_generate_summary_report_with_losses(self):
        initial_capital = 10000
        trade1_pnl = 1000 # Win
        trade2_pnl = -200 # Loss
        final_equity = initial_capital + trade1_pnl + trade2_pnl

        dummy_results_loss = {
            'performance_metrics': {
                'initial_capital': initial_capital,
                'final_equity': final_equity,
                'total_pnl': final_equity - initial_capital,
                'total_trades': 2,
            },
            'trade_log': [
                {'pnl': trade1_pnl, 'type':'long', 'entry_time': pd.Timestamp('20230101'), 'exit_time': pd.Timestamp('20230102')},
                {'pnl': trade2_pnl, 'type':'long', 'entry_time': pd.Timestamp('20230103'), 'exit_time': pd.Timestamp('20230104')}
            ],
            'equity_curve': pd.Series([10000, 11000, 10800], index=pd.to_datetime(['20230101','20230102','20230104']))
        }
        summary = self.bot.generate_summary_report(dummy_results_loss)
        self.assertIsNotNone(summary)
        self.assertEqual(summary['total_winning_trades'], 1)
        self.assertEqual(summary['total_losing_trades'], 1)
        self.assertAlmostEqual(summary['win_rate_percentage'], 50.0)
        self.assertAlmostEqual(summary['average_win_pnl'], 1000)
        self.assertAlmostEqual(summary['average_loss_pnl'], -200)
        self.assertAlmostEqual(summary['risk_reward_ratio'], 5.0) # 1000 / 200
        self.assertAlmostEqual(summary['profit_factor'], 5.0) # 1000 / 200
        # Max drawdown: peak 11000, valley 10800. Drawdown = (10800-11000)/11000 = -200/11000
        self.assertAlmostEqual(summary['max_drawdown_percentage'], (-200/11000)*100, places=2)

    @patch('bot.Bot.generate_summary_report')
    @patch('bot.Bot.backtest')
    def test_grid_search_optimize(self, mock_backtest, mock_generate_summary_report):
        # 1. Define a simple strategy class for testing (or use SimpleMACrossoverStrategy if its __init__ is simple)
        class MockStrategy:
            def __init__(self, param1=None, param2=None):
                self.param1 = param1
                self.param2 = param2
                # print(f"MockStrategy instantiated with param1={param1}, param2={param2}") # For debugging test

            def generate_signals(self, df):
                # Not actually called if backtest is properly mocked, but good practice to have it.
                return pd.DataFrame({'signal': [0] * len(df)}, index=df.index)

        # 2. Define parameter grid and metric
        parameter_grid = {
            'param1': [1, 2],
            'param2': ['a', 'b']
        }
        metric_to_optimize = 'total_pnl'

        # 3. Define side effects for mock_backtest and mock_generate_summary_report
        def summary_report_side_effect(backtest_results_arg):
            params_from_backtest = backtest_results_arg.get('params_for_score', {})
            p1 = params_from_backtest.get('param1')
            p2 = params_from_backtest.get('param2')

            if p1 == 1 and p2 == 'a':
                return {'total_pnl': 100, 'sharpe_ratio_period': 1.0}
            elif p1 == 1 and p2 == 'b':
                return {'total_pnl': 150, 'sharpe_ratio_period': 1.2} # This should be the best for total_pnl
            elif p1 == 2 and p2 == 'a':
                return {'total_pnl': 120, 'sharpe_ratio_period': 0.8}
            elif p1 == 2 and p2 == 'b':
                return {'total_pnl': 80, 'sharpe_ratio_period': 0.5}
            return {'total_pnl': 0, 'sharpe_ratio_period': 0} 

        mock_generate_summary_report.side_effect = summary_report_side_effect
        
        def backtest_side_effect(timeframe, strategy_logic, initial_capital, bars, commission_bps):
            return {
                'performance_metrics': {}, 
                'trade_log': [], 
                'equity_curve': pd.Series(dtype=float), 
                'params_for_score': {'param1': strategy_logic.param1, 'param2': strategy_logic.param2}
            }
        mock_backtest.side_effect = backtest_side_effect
        
        # 4. Run grid_search_optimize
        best_params, best_score, all_results = self.bot.grid_search_optimize(
            timeframe=Interval.in_1_hour, 
            strategy_class=MockStrategy,
            parameter_grid=parameter_grid,
            metric_to_optimize=metric_to_optimize,
            initial_capital=10000, 
            bars=100, 
            commission_bps=0 
        )

        # 5. Assertions
        self.assertIsNotNone(best_params)
        self.assertEqual(best_params, {'param1': 1, 'param2': 'b'})
        self.assertEqual(best_score, 150)
        self.assertEqual(len(all_results), 4) 

        best_result_in_all = next(r for r in all_results if r['params'] == best_params)
        self.assertEqual(best_result_in_all['summary']['sharpe_ratio_period'], 1.2)


    @patch('bot.Bot.generate_summary_report')
    @patch('bot.Bot.backtest')
    def test_grid_search_optimize_metric_not_found(self, mock_backtest, mock_generate_summary_report):
        class MockStrategy:
            def __init__(self, param1=None): self.param1 = param1
            def generate_signals(self, df): return pd.DataFrame({'signal': [0]*len(df)}, index=df.index)

        parameter_grid = {'param1': [1]}
        metric_to_optimize = 'non_existent_metric' 

        mock_backtest.return_value = {'params_for_score': {'param1': 1}} 
        mock_generate_summary_report.return_value = {'total_pnl': 100} 

        best_params, best_score, all_results = self.bot.grid_search_optimize(
            timeframe=Interval.in_1_hour,
            strategy_class=MockStrategy,
            parameter_grid=parameter_grid,
            metric_to_optimize=metric_to_optimize,
        )
        
        self.assertIsNone(best_params) 
        self.assertEqual(best_score, -float('inf')) 
        self.assertEqual(len(all_results), 1)
        self.assertTrue('error' in all_results[0])
        self.assertIn(f'Metric {metric_to_optimize} not found', all_results[0]['error'])

    @patch('bot.Bot.download')
    def test_backtest_sl_triggered(self, mock_download):
        # Test scenario where Stop Loss is triggered for a long trade
        strategy_mock = MagicMock()
        # Price data: Open high enough, then drops to hit SL
        # Entry on bar 1 (open=101 based on idx[0] signal), SL set relative to 101.
        # Bar 2 (idx=2) low goes to 97. SL expected: 101 * (1-0.02) = 98.98.
        data = { 
            'open':  [100, 101, 98,  97], 
            'high':  [102, 102, 99,  98],
            'low':   [99,  100, 97,  96], # SL hit at 97 on bar index 2 (data_df['low'].iloc[i+1] where i+1 = 2)
            'close': [101, 100, 97.5, 97],
            'volume':[1000,1000,1000,1000]
        }
        idx = pd.to_datetime([f'2023-01-01 0{i}:00:00' for i in range(len(data['open']))])
        mock_price_df = pd.DataFrame(data, index=idx)
        mock_download.return_value = mock_price_df

        # Signal: Buy at index 0, executes at open of index 1 (price 101)
        signals_data = {'signal': [1, 0, 0, 0]} 
        mock_signals_df = pd.DataFrame(signals_data, index=idx)
        strategy_mock.generate_signals.return_value = mock_signals_df

        sl_percentage = 0.02 
        entry_price_expected = 101 
        sl_price_expected = entry_price_expected * (1 - sl_percentage) 

        results = self.bot.backtest(
            timeframe=Interval.in_1_hour, 
            strategy_logic=strategy_mock,
            initial_capital=10000,
            bars=len(mock_price_df),
            commission_bps=0,
            sl_percentage=sl_percentage,
            tp_percentage=None 
        )

        self.assertIsNotNone(results)
        self.assertEqual(len(results['trade_log']), 1)
        trade = results['trade_log'][0]
        
        self.assertEqual(trade['entry_price'], entry_price_expected)
        self.assertEqual(trade['exit_reason'], 'SL')
        # SL is triggered when low <= sl_price. Assumed execution at sl_price.
        self.assertAlmostEqual(trade['exit_price'], sl_price_expected) 
        
        expected_shares = 10000 / entry_price_expected
        expected_pnl = (sl_price_expected - entry_price_expected) * expected_shares
        self.assertAlmostEqual(trade['pnl'], expected_pnl, places=2)
        self.assertAlmostEqual(results['performance_metrics']['final_equity'], 10000 + expected_pnl, places=2)

    @patch('bot.Bot.download')
    def test_backtest_tp_triggered(self, mock_download):
        strategy_mock = MagicMock()
        # Entry at open of index 1 (price 99). TP expected: 99 * (1+0.02) = 100.98.
        # Bar 2 (idx=2) high goes to 103.
        data = { 
            'open':  [100, 99,  101, 100], 
            'high':  [101, 100, 103, 101], # TP hit at 103 on bar index 2
            'low':   [99,  98,  100, 99],
            'close': [100, 99.5,102, 100.5],
            'volume':[1000,1000,1000,1000]
        }
        idx = pd.to_datetime([f'2023-01-01 0{i}:00:00' for i in range(len(data['open']))])
        mock_price_df = pd.DataFrame(data, index=idx)
        mock_download.return_value = mock_price_df

        signals_data = {'signal': [1, 0, 0, 0]} 
        mock_signals_df = pd.DataFrame(signals_data, index=idx)
        strategy_mock.generate_signals.return_value = mock_signals_df

        tp_percentage = 0.02 
        entry_price_expected = 99 
        tp_price_expected = entry_price_expected * (1 + tp_percentage)

        results = self.bot.backtest(
            timeframe=Interval.in_1_hour, 
            strategy_logic=strategy_mock,
            initial_capital=10000,
            bars=len(mock_price_df),
            commission_bps=0,
            sl_percentage=None, 
            tp_percentage=tp_percentage
        )

        self.assertIsNotNone(results)
        self.assertEqual(len(results['trade_log']), 1)
        trade = results['trade_log'][0]

        self.assertEqual(trade['entry_price'], entry_price_expected)
        self.assertEqual(trade['exit_reason'], 'TP')
        self.assertAlmostEqual(trade['exit_price'], tp_price_expected)

        expected_shares = 10000 / entry_price_expected
        expected_pnl = (tp_price_expected - entry_price_expected) * expected_shares
        self.assertAlmostEqual(trade['pnl'], expected_pnl, places=2)
        self.assertAlmostEqual(results['performance_metrics']['final_equity'], 10000 + expected_pnl, places=2)

    @patch('bot.Bot.download')
    def test_backtest_sl_takes_precedence_over_tp_on_same_bar(self, mock_download):
        strategy_mock = MagicMock()
        # Entry at open of index 1 (price 101). SL: 98.98. TP: 103.02.
        # Bar 2 (idx=2) low is 97 (hits SL), high is 104 (hits TP). SL should take precedence.
        data = { 
            'open':  [100, 101, 98], 
            'high':  [102, 102, 104], # Bar index 2 high (104)
            'low':   [99,  100, 97],  # Bar index 2 low (97)
            'close': [101, 100, 99],
            'volume':[1000,1000,1000]
        }
        idx = pd.to_datetime([f'2023-01-01 0{i}:00:00' for i in range(len(data['open']))])
        mock_price_df = pd.DataFrame(data, index=idx)
        mock_download.return_value = mock_price_df

        signals_data = {'signal': [1, 0, 0]} 
        mock_signals_df = pd.DataFrame(signals_data, index=idx)
        strategy_mock.generate_signals.return_value = mock_signals_df

        sl_percentage = 0.02 
        tp_percentage = 0.02
        entry_price_expected = 101
        sl_price_expected = entry_price_expected * (1 - sl_percentage)

        results = self.bot.backtest(
            timeframe=Interval.in_1_hour, 
            strategy_logic=strategy_mock,
            initial_capital=10000,
            bars=len(mock_price_df),
            commission_bps=0,
            sl_percentage=sl_percentage,
            tp_percentage=tp_percentage
        )
        self.assertEqual(len(results['trade_log']), 1)
        trade = results['trade_log'][0]
        self.assertEqual(trade['exit_reason'], 'SL') 
        self.assertAlmostEqual(trade['exit_price'], sl_price_expected)

    @patch('bot.Bot.download')
    def test_backtest_sl_tp_takes_precedence_over_signal_exit(self, mock_download):
        strategy_mock = MagicMock()
        # Entry at open of index 1 (price 101). SL: 98.98.
        # Bar 2 (idx=2) low is 97 (hits SL). Strategy also signals SELL at index 1 (for execution on open of index 2).
        data = { 
            'open':  [100, 101, 98], 
            'high':  [102, 102, 99], 
            'low':   [99,  100, 97],  
            'close': [101, 100, 99],
            'volume':[1000,1000,1000]
        }
        idx = pd.to_datetime([f'2023-01-01 0{i}:00:00' for i in range(len(data['open']))])
        mock_price_df = pd.DataFrame(data, index=idx)
        mock_download.return_value = mock_price_df
        
        signals_data = {'signal': [1, -1, 0]} # Buy at idx 0 (exec idx 1), Sell signal at idx 1 (exec idx 2)
        mock_signals_df = pd.DataFrame(signals_data, index=idx)
        strategy_mock.generate_signals.return_value = mock_signals_df

        sl_percentage = 0.02 
        entry_price_expected = 101
        sl_price_expected = entry_price_expected * (1 - sl_percentage)

        results = self.bot.backtest(
            timeframe=Interval.in_1_hour, 
            strategy_logic=strategy_mock,
            initial_capital=10000,
            bars=len(mock_price_df),
            commission_bps=0,
            sl_percentage=sl_percentage,
            tp_percentage=None # No TP for this specific test
        )
        self.assertEqual(len(results['trade_log']), 1)
        trade = results['trade_log'][0]
        self.assertEqual(trade['exit_reason'], 'SL') 
        self.assertAlmostEqual(trade['exit_price'], sl_price_expected)


if __name__ == '__main__':
    unittest.main(argv=['first-arg-is-ignored'], exit=False)

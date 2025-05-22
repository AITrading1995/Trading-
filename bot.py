from tvdatafeed import TvDatafeed, Interval # Assuming Interval is needed based on original code's multi_symbol
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
import itertools
# We will add matplotlib.pyplot later when implementing plotting features

class Bot:
    def __init__(self, symbol, exchange):
        self.symbol = symbol
        self.exchange = exchange
        # Create a TvDatafeed instance once, assuming it's okay to share it.
        # If TvDatafeed has issues with shared instances or different user credentials per call,
        # this might need to be instantiated within each method that uses it, as in the original multi_symbol.
        # For now, let's stick to the __init__ instantiation as in the original `download` method.
        self.tv = TvDatafeed()

    def download(self, timeframe, bars=20000):
        """ดึงข้อมูลจาก timeframe เดียว"""
        # Assuming tv.get_hist arguments are: symbol, exchange, interval, n_bars
        # The original code had 'timeframe' for interval. Let's ensure consistency.
        # If 'timeframe' is meant to be an Interval enum, it should be passed as such.
        df = self.tv.get_hist(self.symbol, self.exchange, interval=timeframe, n_bars=bars)
        if df is not None and 'symbol' in df.columns:
            df.drop(columns='symbol', inplace=True)
        return df

    def download_multi(self, timeframes, bars=20000):
        """ดึงข้อมูลจากหลายๆ Timeframe
           timeframes: list ของ Timeframe เช่น [Interval.in_15_minute, Interval.in_1_hour]
           returns: dict ที่ key เป็น Timeframe, value เป็น DataFrame ที่ได้
        """
        data = {}
        for tf in timeframes:
            df = self.download(tf, bars)
            data[tf] = df
        return data

    def multi_symbol(self, symbols, exchanges, bars=20000):
        """
        ดึงข้อมูล close price จากหลายๆ symbols และ exchanges สำหรับ Interval.in_15_minute.
        หมายเหตุ: โค้ดดั้งเดิมสร้าง instance TvDatafeed ใหม่ทุกครั้งที่เรียก method นี้
        และดึงเฉพาะ Interval.in_15_minute และราคา 'close' เท่านั้น
        การออกแบบนี้อาจแตกต่างจาก method อื่นๆ ที่ใช้ instance self.tv
        หากต้องการความสอดคล้อง อาจจะต้องปรับปรุง
        """
        data = {}
        # Consider whether to use self.tv or a new TvDatafeed() instance as in the original.
        # Using a new instance here as per original code for this specific method.
        tv_local = TvDatafeed()
        for sym in symbols:
            for ex in exchanges: # Original code iterates through exchanges for each symbol
                # Assuming Interval.in_15_minute is the fixed interval for this method as per original.
                df = tv_local.get_hist(symbol=sym, exchange=ex, interval=Interval.in_15_minute, n_bars=bars)
                if df is not None and 'close' in df.columns:
                    # Stores the 'close' series, keyed by symbol.
                    # If multiple exchanges provide the same symbol, the last one will overwrite previous ones.
                    # Consider a more robust key like f'{sym}_{ex}' if needed.
                    data[f'{sym}'] = df['close']
                elif df is not None:
                    # Handle cases where 'close' column might be missing but df is not None
                    print(f"Warning: 'close' column not found for {sym} on {ex}. DataFrame columns: {df.columns}")
                    data[f'{sym}'] = pd.Series(dtype='float64') # Store empty series
                else:
                    print(f"Warning: No data returned for {sym} on {ex}.")
                    data[f'{sym}'] = pd.Series(dtype='float64') # Store empty series for consistency
        return data

    def generate_summary_report(self, backtest_results):
        """
        Generates a summary report from backtest results.

        Args:
            backtest_results (dict): The dictionary returned by the `backtest` method.

        Returns:
            A dictionary containing key performance indicators (KPIs).
            Returns None if backtest_results is None or missing essential data.
        """
        if backtest_results is None or 'performance_metrics' not in backtest_results or 'trade_log' not in backtest_results or 'equity_curve' not in backtest_results:
            print("Error: Invalid or incomplete backtest_results provided to generate_summary_report.")
            return None

        metrics = backtest_results['performance_metrics']
        trade_log = backtest_results['trade_log']
        equity_curve = backtest_results['equity_curve']

        summary = metrics.copy() # Start with basic metrics (initial_capital, final_equity, total_pnl, total_trades)

        winning_trades = [t for t in trade_log if t['pnl'] > 0]
        losing_trades = [t for t in trade_log if t['pnl'] <= 0] # Includes zero PnL as non-winning

        summary['total_winning_trades'] = len(winning_trades)
        summary['total_losing_trades'] = len(losing_trades)

        if summary['total_trades'] > 0:
            summary['win_rate_percentage'] = (summary['total_winning_trades'] / summary['total_trades']) * 100
        else:
            summary['win_rate_percentage'] = 0.0

        total_profit_from_winners = sum(t['pnl'] for t in winning_trades)
        total_loss_from_losers = sum(t['pnl'] for t in losing_trades) # Sum of negative PnLs

        if summary['total_winning_trades'] > 0:
            summary['average_win_pnl'] = total_profit_from_winners / summary['total_winning_trades']
        else:
            summary['average_win_pnl'] = 0.0

        if summary['total_losing_trades'] > 0:
            summary['average_loss_pnl'] = total_loss_from_losers / summary['total_losing_trades']
        else:
            summary['average_loss_pnl'] = 0.0
        
        if summary['average_loss_pnl'] != 0: # Avoid division by zero
            summary['risk_reward_ratio'] = abs(summary['average_win_pnl'] / summary['average_loss_pnl']) if summary['average_loss_pnl'] !=0 else float('inf')
        else: # No losing trades or average loss is zero
            summary['risk_reward_ratio'] = float('inf') if summary['average_win_pnl'] > 0 else 0 # If avg win is also 0, then 0, else infinite


        if total_loss_from_losers != 0:
            summary['profit_factor'] = abs(total_profit_from_winners / total_loss_from_losers) if total_loss_from_losers !=0 else float('inf')

        else: # No losses
            summary['profit_factor'] = float('inf') if total_profit_from_winners > 0 else 0 # If also no profits, then 0

        # Max Drawdown calculation
        if not equity_curve.empty:
            peak = equity_curve.expanding(min_periods=1).max()
            drawdown = (equity_curve - peak) / peak
            summary['max_drawdown_percentage'] = drawdown.min() * 100 if not drawdown.empty else 0.0
            summary['max_drawdown_absolute'] = (equity_curve - peak).min() if not drawdown.empty else 0.0

        else:
            summary['max_drawdown_percentage'] = 0.0
            summary['max_drawdown_absolute'] = 0.0
            
        # Optional: Sharpe Ratio (annualized, assuming daily data and 0 risk-free rate for simplicity)
        # This is a simplified version. A more robust version would need daily returns and risk-free rate.
        if not equity_curve.empty and len(equity_curve) > 1:
            returns = equity_curve.pct_change().dropna()
            if not returns.empty and returns.std() != 0:
                # Assuming 252 trading days in a year for annualization
                # This part is highly dependent on data frequency (daily, hourly, etc.)
                # For a generic report, it might be better to report non-annualized Sharpe or specify assumptions.
                # Here, we calculate a simple Sharpe based on observed returns.
                sharpe_ratio = returns.mean() / returns.std()
                # To annualize (example for daily returns): sharpe_ratio_annualized = sharpe_ratio * np.sqrt(252)
                # For this generic version, let's stick to the non-annualized Sharpe of the period.
                summary['sharpe_ratio_period'] = sharpe_ratio
            else:
                summary['sharpe_ratio_period'] = 0.0
        else:
            summary['sharpe_ratio_period'] = 0.0


        print("--- Summary Report ---")
        for key, value in summary.items():
            if isinstance(value, float):
                print(f"{key.replace('_', ' ').title()}: {value:.2f}")
            else:
                print(f"{key.replace('_', ' ').title()}: {value}")
        print("----------------------")

        return summary

    def plot_results(self, backtest_results):
        """
        Generates plots for backtest results.

        Args:
            backtest_results (dict): The dictionary returned by the `backtest` method.
                                     Expected to contain 'equity_curve', 'trade_log', 
                                     and 'price_data_for_plotting'.
        
        Returns:
            None. Displays the plots.
        """
        if backtest_results is None:
            print("Error: No backtest results provided to plot.")
            return

        equity_curve = backtest_results.get('equity_curve')
        trade_log = backtest_results.get('trade_log', [])
        price_data = backtest_results.get('price_data_for_plotting')

        if equity_curve is None or price_data is None:
            print("Error: Equity curve or price data missing in backtest_results.")
            return

        # Ensure price_data index is DatetimeIndex if it's not already
        if not isinstance(price_data.index, pd.DatetimeIndex):
            try:
                price_data.index = pd.to_datetime(price_data.index)
            except Exception as e:
                print(f"Could not convert price_data index to DatetimeIndex: {e}")
                # Fallback: try to plot with original index if conversion fails
        
        # Ensure equity_curve index is DatetimeIndex if it's not already
        if not isinstance(equity_curve.index, pd.DatetimeIndex):
            try:
                equity_curve.index = pd.to_datetime(equity_curve.index)
            except Exception as e:
                print(f"Could not convert equity_curve index to DatetimeIndex: {e}")
                # Fallback: try to plot with original index if conversion fails

        # Plot 1: Equity Curve
        plt.figure(figsize=(12, 6))
        plt.plot(equity_curve.index, equity_curve, label='Equity Curve', color='blue')
        plt.title('Equity Curve Over Time')
        plt.xlabel('Time')
        plt.ylabel('Equity')
        plt.legend()
        plt.grid(True)
        plt.show(block=False) # Use block=False to allow multiple plots to be shown

        # Plot 2: Price Chart with Buy/Sell Markers
        plt.figure(figsize=(12, 8))
        
        # Plotting close price
        if 'close' in price_data.columns:
            plt.plot(price_data.index, price_data['close'], label='Close Price', color='black', alpha=0.7)
        else:
            print("Warning: 'close' column not found in price_data. Cannot plot price chart.")
            # If only equity curve can be shown, we might not want to proceed with this plot.
            # However, let's try to plot markers if trades exist.

        buy_signals = [pd.to_datetime(trade['entry_time']) for trade in trade_log if trade['type'] == 'long']
        sell_signals = [pd.to_datetime(trade['exit_time']) for trade in trade_log if trade['type'] == 'long' and trade.get('exit_time')]

        # Ensure signals are within the price_data index range if possible
        if 'close' in price_data.columns and not price_data.empty:
            min_time, max_time = price_data.index.min(), price_data.index.max()
            
            # Filter buy signals and get corresponding prices
            valid_buy_signals_time = [t for t in buy_signals if min_time <= t <= max_time]
            buy_prices = [price_data.loc[price_data.index.asof(t), 'close'] if price_data.index.asof(t) in price_data.index else np.nan for t in valid_buy_signals_time]
            
            # Filter sell signals and get corresponding prices
            valid_sell_signals_time = [t for t in sell_signals if min_time <= t <= max_time]
            sell_prices = [price_data.loc[price_data.index.asof(t), 'close'] if price_data.index.asof(t) in price_data.index else np.nan for t in valid_sell_signals_time]

            plt.scatter(valid_buy_signals_time, buy_prices, label='Buy Signal', marker='^', color='green', s=100, zorder=5)
            plt.scatter(valid_sell_signals_time, sell_prices, label='Sell Signal', marker='v', color='red', s=100, zorder=5)

        elif not trade_log: # No trades, just show price
             pass # Already plotted price or warned if no 'close'
        else: # Trades exist but no price data to align them with (e.g. 'close' was missing)
            print("Warning: Cannot accurately plot trade markers as 'close' price data is unavailable or index mismatch.")


        plt.title(f'{self.symbol} Price Chart with Trading Signals')
        plt.xlabel('Time')
        plt.ylabel('Price')
        plt.legend()
        plt.grid(True)
        plt.show(block=True) # block=True for the last plot, or manage windows if preferred

    def backtest(self, timeframe, strategy_logic, initial_capital=100000, bars=2000, commission_bps=0):
        """
        Performs a backtest of a given strategy.

        Args:
            timeframe: The timeframe for the historical data (e.g., Interval.in_15_minute).
            strategy_logic: An object with a method `generate_signals(self, df)` which returns a DataFrame
                            with a 'signal' column (1 for Buy, -1 for Sell, 0 for Hold).
            initial_capital (float): The starting capital for the backtest.
            bars (int): The number of historical bars to download.
            commission_bps (float): Commission in basis points (e.g., 2 bps = 0.02% = 0.0002).

        Returns:
            A dictionary containing the backtest results (trade log, equity curve, performance metrics),
            or None if data download fails or data is insufficient.
        """
        print(f"Starting backtest for {self.symbol} on {timeframe}...")
        data_df = self.download(timeframe, bars)

        if data_df is None or data_df.empty:
            print(f"Failed to download data or data is empty for {self.symbol}, {timeframe}.")
            return None

        if not all(col in data_df.columns for col in ['open', 'high', 'low', 'close']):
            print(f"Data for {self.symbol}, {timeframe} is missing required OHLC columns. Present: {data_df.columns}")
            return None
        
        if len(data_df) < 2: # Need at least 2 bars for signal and execution
            print(f"Insufficient data for backtest after download for {self.symbol}, {timeframe}. Need at least 2 bars, got {len(data_df)}.")
            return None

        signals_df = strategy_logic.generate_signals(data_df)
        # Ensure signals_df has the same index as data_df and the 'signal' column
        if 'signal' not in signals_df.columns or not signals_df.index.equals(data_df.index):
            print("Strategy did not return signals correctly. 'signal' column missing or index mismatch.")
            return None
            
        signals = signals_df['signal']

        capital = float(initial_capital)
        position_shares = 0.0
        equity = pd.Series(index=data_df.index, dtype=float)
        equity.iloc[0] = initial_capital
        trade_log = []
        active_trade = None

        print(f"Data downloaded. Columns: {data_df.columns}. Length: {len(data_df)}. Starting simulation...")

        # Loop from the first bar up to len(data_df) - 2 to allow execution on data_df['open'].iloc[i+1]
        for i in range(len(data_df) - 1): # Iterate up to second to last bar
            current_signal = signals.iloc[i]
            
            # Determine execution price: open of NEXT bar. If last signal, no next bar for execution.
            if i + 1 >= len(data_df):
                if position_shares > 0 and active_trade is not None: # If holding shares, try to liquidate
                    last_close_price = data_df['close'].iloc[i]
                    price_after_commission = last_close_price * (1 - commission_bps / 10000.0)
                    capital += position_shares * price_after_commission
                    active_trade['exit_time'] = data_df.index[i]
                    active_trade['exit_price'] = last_close_price
                    active_trade['pnl'] = (active_trade['exit_price'] - active_trade['entry_price']) * active_trade['shares'] - \
                                           (active_trade['entry_price'] * active_trade['shares'] * commission_bps / 10000.0) - \
                                           (active_trade['exit_price'] * active_trade['shares'] * commission_bps / 10000.0)
                    trade_log.append(active_trade)
                    print(f"Liquidated open position at end of data (bar {i}): {active_trade['shares']} shares at {last_close_price}")
                    position_shares = 0
                    active_trade = None
                equity.iloc[i] = capital # Update final equity point based on last capital
                break # Exit loop as no further bars to process or execute on

            execution_price = data_df['open'].iloc[i+1] # Execute on next bar's open

            # Buy Signal
            if current_signal == 1 and position_shares == 0:
                cost_per_share = execution_price * (1 + commission_bps / 10000.0)
                if cost_per_share <= 0: # Avoid division by zero or negative price
                    print(f"Warning: Invalid execution price or commission for buy at bar {i+1}: {cost_per_share}")
                    equity.iloc[i+1] = capital # No trade, equity is current capital
                    continue 
                shares_to_buy = capital / cost_per_share
                position_shares = shares_to_buy
                capital -= position_shares * execution_price # Actual capital deduction before commission for PnL calc later
                
                active_trade = {
                    'entry_time': data_df.index[i+1], 
                    'entry_price': execution_price, 
                    'shares': position_shares, 
                    'type': 'long',
                    'commission_entry_cost': position_shares * execution_price * (commission_bps / 10000.0)
                }
                print(f"Trade opened at {data_df.index[i+1]}: BUY {shares_to_buy:.2f} shares at {execution_price:.2f}")

            # Sell Signal (to close long position)
            elif current_signal == -1 and position_shares > 0 and active_trade is not None:
                proceeds_per_share = execution_price * (1 - commission_bps / 10000.0)
                capital += position_shares * execution_price # Actual capital addition before commission for PnL calc

                commission_exit_cost = position_shares * execution_price * (commission_bps / 10000.0)
                active_trade['exit_time'] = data_df.index[i+1]
                active_trade['exit_price'] = execution_price
                active_trade['pnl'] = ((active_trade['exit_price'] - active_trade['entry_price']) * active_trade['shares']) - \
                                       active_trade['commission_entry_cost'] - commission_exit_cost
                
                trade_log.append(active_trade)
                print(f"Trade closed at {data_df.index[i+1]}: SELL {active_trade['shares']:.2f} shares at {execution_price:.2f}, PnL: {active_trade['pnl']:.2f}")
                position_shares = 0
                active_trade = None
            
            # Update equity
            if i + 1 < len(data_df): # Ensure index is within bounds
                if position_shares > 0:
                    equity.iloc[i+1] = capital + position_shares * data_df['close'].iloc[i+1] # Mark-to-market
                else:
                    equity.iloc[i+1] = capital
            elif i < len(equity): # last point if loop ends due to i+1 out of bounds
                 equity.iloc[i] = capital


        # Fill any NaNs in equity curve (e.g., if loop didn't run fully or first bar)
        equity = equity.ffill().bfill() # Forward fill then backward fill for safety
        if equity.iloc[0] != initial_capital and pd.isna(equity.iloc[0]): # if first is still NaN
             equity.iloc[0] = initial_capital


        # Final liquidation if position is still open after the loop
        if position_shares > 0 and active_trade is not None:
            last_close_price = data_df['close'].iloc[-1] # Use the very last close price
            # Simulate commission for liquidation
            commission_exit_cost = position_shares * last_close_price * (commission_bps / 10000.0)
            capital += position_shares * last_close_price # Add proceeds to capital

            active_trade['exit_time'] = data_df.index[-1]
            active_trade['exit_price'] = last_close_price
            active_trade['pnl'] = ((active_trade['exit_price'] - active_trade['entry_price']) * active_trade['shares']) - \
                                   active_trade['commission_entry_cost'] - commission_exit_cost
            trade_log.append(active_trade)
            print(f"Position liquidated at end of data: SELL {active_trade['shares']:.2f} shares at {last_close_price:.2f}, PnL: {active_trade['pnl']:.2f}")
            position_shares = 0 # Reset position
            active_trade = None
            equity.iloc[-1] = capital # Update last equity point


        final_equity = equity.iloc[-1] if not equity.empty else initial_capital
        total_pnl = final_equity - initial_capital
        number_of_trades = len(trade_log)

        print(f"Backtest finished. Initial Capital: {initial_capital:.2f}, Final Equity: {final_equity:.2f}, PnL: {total_pnl:.2f}, Trades: {number_of_trades}")

        return {
            'trade_log': trade_log,
            'equity_curve': equity,
            'performance_metrics': {
                'initial_capital': initial_capital,
                'final_equity': final_equity,
                'total_pnl': total_pnl,
                'total_trades': number_of_trades,
            },
            'price_data_for_plotting': data_df.copy()
        }

# Placeholder for Interval enum if not directly available from tvdatafeed for type hinting
# This is just for structure; the actual Interval should come from tvdatafeed library
# from enum import Enum
# class Interval(Enum):
#     in_1_minute = "1m"
#     in_5_minute = "5m"
#     in_15_minute = "15m"
#     in_30_minute = "30m"
#     in_1_hour = "1H"
#     in_4_hour = "4H"
#     in_1_day = "1D"
#     in_1_week = "1W"
#     in_1_month = "1M"

# Example Strategy: Simple Moving Average Crossover
class SimpleMACrossoverStrategy:
    def __init__(self, short_window=20, long_window=50):
        self.short_window = short_window
        self.long_window = long_window
        if short_window >= long_window:
            raise ValueError("Short window must be less than long window for MA crossover.")

    def generate_signals(self, df):
        """
        Generates trading signals based on a moving average crossover.
        Args:
            df (pd.DataFrame): DataFrame with historical price data, must include 'close'.
        Returns:
            pd.DataFrame: DataFrame with a 'signal' column (1 for buy, -1 for sell, 0 for hold).
        """
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0.0 # Default to hold

        if 'close' not in df.columns:
            print("Error: 'close' column not in DataFrame for generating signals.")
            return signals # Return empty signals or handle error as appropriate

        # Calculate short and long moving averages
        signals['short_mavg'] = df['close'].rolling(window=self.short_window, min_periods=1, center=False).mean()
        signals['long_mavg'] = df['close'].rolling(window=self.long_window, min_periods=1, center=False).mean()

        # Generate signals
        # Buy signal: short MAVG crosses above long MAVG
        signals['signal'][self.long_window:] = np.where(signals['short_mavg'][self.long_window:] > signals['long_mavg'][self.long_window:], 1.0, 0.0)   
        
        # Sell signal: short MAVG crosses below long MAVG (to close a long position)
        # This generates an exit signal. The backtester handles position logic (only sell if holding).
        signals['signal'][self.long_window:] = np.where(signals['short_mavg'][self.long_window:] < signals['long_mavg'][self.long_window:], -1.0, signals['signal'][self.long_window:])
        
        # To avoid issues with initial NaNs in MAVGs, signals are typically generated after long_window periods.
        # The slices [self.long_window:] ensure we only assign signals where both MAVGs are more likely to be valid.
        
        print("Signals generated by SimpleMACrossoverStrategy.")
        # For debugging:
        # print(signals.tail())
        return signals

    def grid_search_optimize(self, timeframe, strategy_class, parameter_grid, metric_to_optimize, 
                             initial_capital=100000, bars=2000, commission_bps=0):
        """
        Performs a grid search to find the optimal parameters for a strategy.

        Args:
            timeframe: The timeframe for backtesting (e.g., Interval.in_1_hour).
            strategy_class: The class of the strategy to optimize (e.g., SimpleMACrossoverStrategy).
            parameter_grid (dict): A dictionary where keys are parameter names and values are lists of
                                   parameter values to test (e.g., {'short_window': [10, 20], 'long_window': [30, 40]}).
            metric_to_optimize (str): The key from the summary report to maximize (e.g., 'total_pnl', 'sharpe_ratio_period').
            initial_capital (float): Starting capital for each backtest.
            bars (int): Number of historical bars for each backtest.
            commission_bps (float): Commission in basis points.

        Returns:
            A tuple containing:
                - best_params (dict): The dictionary of parameters that yielded the best performance.
                - best_score (float): The score of the specified metric for the best parameters.
                - all_results (list): A list of dictionaries, each containing 'params' and 'score'.
                                      Returns None if no valid results were found.
        """
        if not parameter_grid:
            print("Error: Parameter grid is empty.")
            return None, -float('inf'), []

        param_names = list(parameter_grid.keys())
        param_values = list(parameter_grid.values())
        
        all_combinations = list(itertools.product(*param_values))
        
        if not all_combinations:
            print("Error: No parameter combinations generated from the grid.")
            return None, -float('inf'), []

        print(f"Starting grid search for {len(all_combinations)} parameter combinations...")
        print(f"Optimizing for metric: {metric_to_optimize}")

        best_params = None
        # Initialize best_score to negative infinity, as we want to maximize the metric.
        # If a metric could be negative (like PnL), this is appropriate.
        # If optimizing a metric that should always be positive (e.g. win rate), 0 might be an alternative start.
        best_score = -float('inf') 
        all_results = []

        for i, combo in enumerate(all_combinations):
            current_params = dict(zip(param_names, combo))
            print(f"\nRunning combination {i+1}/{len(all_combinations)}: {current_params}")

            try:
                # 1. Instantiate strategy with current parameters
                strategy_instance = strategy_class(**current_params)
                
                # 2. Run backtest
                backtest_results = self.backtest(
                    timeframe=timeframe,
                    strategy_logic=strategy_instance,
                    initial_capital=initial_capital,
                    bars=bars,
                    commission_bps=commission_bps
                )

                if backtest_results:
                    # 3. Generate summary report
                    summary_report = self.generate_summary_report(backtest_results)
                    
                    if summary_report and metric_to_optimize in summary_report:
                        current_score = summary_report[metric_to_optimize]
                        print(f"Params: {current_params}, Score ({metric_to_optimize}): {current_score:.4f}")
                        
                        result_entry = {'params': current_params.copy(), 'score': current_score, 'summary': summary_report}
                        all_results.append(result_entry)

                        if current_score > best_score:
                            best_score = current_score
                            best_params = current_params.copy()
                            print(f"*** New best score found: {best_score:.4f} with params: {best_params} ***")
                    else:
                        print(f"Warning: Metric '{metric_to_optimize}' not found in summary report for params {current_params} or report failed.")
                        all_results.append({'params': current_params.copy(), 'score': -float('inf'), 'summary': None, 'error': f'Metric {metric_to_optimize} not found or report failed'})

                else:
                    print(f"Warning: Backtest failed for params {current_params}. Skipping this combination.")
                    all_results.append({'params': current_params.copy(), 'score': -float('inf'), 'summary': None, 'error': 'Backtest failed'})

            except Exception as e:
                print(f"Exception during combination {current_params}: {e}")
                all_results.append({'params': current_params.copy(), 'score': -float('inf'), 'summary': None, 'error': str(e)})
        
        if best_params is None:
            print("\nGrid search completed. No valid results found or all backtests failed.")
        else:
            print(f"\nGrid search completed. Best parameters: {best_params} with {metric_to_optimize}: {best_score:.4f}")
            
        return best_params, best_score, all_results

if __name__ == '__main__':
    print("Starting Bot example execution...")

    # --- Configuration for the example ---
    # IMPORTANT: TvDatafeed often requires login. Ensure credentials are set up in your environment
    # or TvDatafeed is configured for guest mode if available and suitable for the chosen exchange.
    # For example, you might need to call `tv.login('your_username', 'your_password')`
    # This example will try to run and print guidance if it fails.

    example_symbol = 'AAPL' # Using a common stock symbol
    example_exchange = 'NASDAQ' 
    example_timeframe = Interval.in_1_hour # Using 1-hour timeframe
    # example_symbol = 'BTC/USD' # Alternative: Crypto pair
    # example_exchange = 'BITSTAMP'
    # example_timeframe = Interval.in_1_hour
    
    initial_capital_example = 100000.0
    commission_bps_example = 2.0 # e.g., 0.02%

    print(f"Attempting to run example for: {example_symbol}, {example_exchange}, {example_timeframe.value}")
    print(f"Initial capital: {initial_capital_example}, Commission: {commission_bps_example} bps")
    print("Note: Data download via TvDatafeed might require user login or specific setup.")
    print("If the script hangs or fails at data download, check your TvDatafeed configuration.")

    try:
        # 1. Instantiate the Bot
        # The Bot's __init__ instantiates TvDatafeed. This might be where login is needed.
        # If TvDatafeed() fails without login, this is the first point of failure.
        my_bot = Bot(symbol=example_symbol, exchange=example_exchange)
        
        # Optional: Explicit login if TvDatafeed instance `my_bot.tv` supports it and it's not done globally.
        # This depends on how TvDatafeed handles authentication.
        # E.g., if tv.login() is a method:
        # try:
        #     my_bot.tv.login('YOUR_TRADINGVIEW_USERNAME', 'YOUR_TRADINGVIEW_PASSWORD')
        #     print("TvDatafeed login successful (example).")
        # except Exception as e:
        #     print(f"TvDatafeed login failed (example): {e}. Guest mode might be used if available.")


        # 2. Define and Instantiate the Strategy
        # Using short_window=10, long_window=30 for H1 data as an example
        strategy = SimpleMACrossoverStrategy(short_window=10, long_window=30)
        print("SimpleMACrossoverStrategy instantiated.")

        # 3. Run the Backtest
        # Using fewer bars for the example to speed it up, e.g., 500 bars.
        # For H1 data, 500 bars is about 20 days.
        backtest_results = my_bot.backtest(
            timeframe=example_timeframe,
            strategy_logic=strategy,
            initial_capital=initial_capital_example,
            bars=500, # Number of bars for the backtest
            commission_bps=commission_bps_example
        )
        print("Backtest method called.")

        # 4. Process and Display Results
        if backtest_results:
            print("Backtest completed successfully. Generating report and plots...")
            
            # Generate Summary Report
            summary = my_bot.generate_summary_report(backtest_results)
            # The report is also printed inside the method.
            # if summary:
            #     print("\n--- Detailed Summary from Main ---")
            #     for key, value in summary.items():
            #         print(f"{key}: {value}")

            # Plot Results
            my_bot.plot_results(backtest_results)
            print("Plotting completed. Check for plot windows.")
        else:
            print("Backtest did not return results. Check logs for errors (e.g., data download issues).")

        # ... (keep existing single backtest example code here up to "Plotting completed.") ...
        # print("Plotting completed. Check for plot windows.") # From previous example part

        print("\n\n--- Starting Grid Search Optimization Example ---")
        # 5. Define Parameter Grid for Optimization
        # Using smaller ranges and fewer bars for a quicker example.
        # Ensure short_window < long_window in your grid to be logical for MACrossover.
        parameter_grid_example = {
            'short_window': [10, 15], # Example: test short windows 10 and 15
            'long_window': [25, 35]   # Example: test long windows 25 and 35
        }
        # This will result in 2x2 = 4 combinations: (10,25), (10,35), (15,25), (15,35)
        # We must ensure that for all combinations, short_window < long_window.
        # The SimpleMACrossoverStrategy constructor already raises ValueError if short_window >= long_window.
        # The grid_search_optimize method will catch this exception for invalid combos.

        metric_to_optimize_example = 'sharpe_ratio_period' # e.g., 'total_pnl', 'sharpe_ratio_period', 'profit_factor'
        
        print(f"Parameter grid for optimization: {parameter_grid_example}")
        print(f"Metric to optimize: {metric_to_optimize_example}")

        # 6. Run Grid Search Optimization
        # Using fewer bars (e.g., 300) for the optimization example to make it run faster.
        best_params, best_score, all_optimization_results = my_bot.grid_search_optimize(
            timeframe=example_timeframe,
            strategy_class=SimpleMACrossoverStrategy, # Pass the class itself
            parameter_grid=parameter_grid_example,
            metric_to_optimize=metric_to_optimize_example,
            initial_capital=initial_capital_example,
            bars=300, # Fewer bars for quicker optimization in example
            commission_bps=commission_bps_example
        )

        # 7. Print Optimization Results
        if best_params:
            print("\n--- Grid Search Optimization Results ---")
            print(f"Best parameters found: {best_params}")
            print(f"Best {metric_to_optimize_example}: {best_score:.4f}")
            
            # Optionally, print details of all combinations tested
            # print("\nDetails of all combinations tested in optimization:")
            # for res in all_optimization_results:
            #     print(f"Params: {res['params']}, Score: {res.get('score', 'N/A')}, Error: {res.get('error', 'None')}")
            #     # If you want to see the full summary for each:
            #     # if res.get('summary'):
            #     #     print("Summary:")
            #     #     for k, v in res['summary'].items():
            #     #         print(f"  {k}: {v}")
        else:
            print("\nGrid search optimization did not find any valid results or all combinations failed.")

    except ImportError as e:
        print(f"ImportError: {e}. Please ensure all required libraries (tvdatafeed, pandas, numpy, matplotlib) are installed.")
    except ValueError as e:
        print(f"ValueError in example: {e}")
    except Exception as e:
        # Catch-all for other exceptions, especially from TvDatafeed or during backtest logic
        print(f"An unexpected error occurred during the example execution: {e}")
        print("This could be due to TvDatafeed issues (login, network, symbol not found, exchange limits) or other runtime problems.")
        print("Please check your TvDatafeed setup, symbol/exchange validity, and internet connection.")

    print("Bot example execution finished.")

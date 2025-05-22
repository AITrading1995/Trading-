# Trading Bot with Backtesting Features

This Python script provides a `Bot` class designed for fetching historical market data, running backtests on trading strategies, generating performance reports, and plotting results.

## Features

*   **Data Download**:
    *   Download historical market data for a single symbol/exchange and timeframe.
    *   Download data for multiple timeframes.
    *   Download data for multiple symbols (fixed to 15-minute interval for 'close' prices).
*   **Backtesting Engine**:
    *   Test trading strategies on historical data.
    *   Supports commission calculations.
    *   Simulates trade execution (entry on next bar's open).
*   **Summary Reports**:
    *   Generate detailed performance reports including:
        *   Total P&L, initial/final equity.
        *   Number of trades, win/loss rates.
        *   Average win/loss PnL, risk-reward ratio.
        *   Profit factor.
        *   Max drawdown (percentage and absolute).
        *   Sharpe Ratio (period-based).
*   **Plotting**:
    *   Visualize equity curve over time.
    *   Plot price charts with buy/sell signals overlaid.

## Dependencies

*   Python 3.x
*   `tvdatafeed`: For downloading historical data from TradingView.
    *   Requires a TradingView account. You may need to provide your username and password.
*   `pandas`: For data manipulation and analysis.
*   `numpy`: For numerical operations, especially in strategy calculations and reporting.
*   `matplotlib`: For generating plots.

Install dependencies using pip:
```bash
pip install tvdatafeed pandas numpy matplotlib
```

## Setup - TvDatafeed Authentication

The `tvdatafeed` library requires authentication with your TradingView credentials to download data for most symbols/exchanges. The `Bot` class initializes `TvDatafeed()` upon instantiation.

**Important**: You need to ensure `TvDatafeed` can log in. This might involve:
1.  Setting environment variables that `TvDatafeed` recognizes (if it supports this).
2.  Modifying the script to explicitly call a login method if `TvDatafeed` provides one, e.g., `bot_instance.tv.login('your_username', 'your_password')` after `Bot` instantiation. The example in `bot.py` shows where this might be placed.
3.  Some exchanges/symbols might be accessible via a guest mode, but this is not guaranteed.

Refer to the `tvdatafeed` library's documentation for the most up-to-date authentication methods. If you encounter issues with data downloading, authentication is the most common cause.

## `Bot` Class Overview

### Initialization
```python
from bot import Bot, Interval # Assuming Interval is available from tvdatafeed or defined in bot.py

# For specific symbol and exchange
bot = Bot(symbol='AAPL', exchange='NASDAQ')

# For multi-symbol/exchange operations, these are passed to specific methods
```

### Data Download Methods
```python
# Download data for a single timeframe
df_hourly = bot.download(timeframe=Interval.in_1_hour, bars=500)

# Download for multiple timeframes
multi_tf_data = bot.download_multi(
    timeframes=[Interval.in_1_hour, Interval.in_4_hour],
    bars=500
)
# multi_tf_data will be a dict: {Interval.in_1_hour: DataFrame, Interval.in_4_hour: DataFrame}

# Download 'close' prices for multiple symbols (fixed to 15-min interval)
# Note: This method instantiates its own TvDatafeed object internally.
multi_sym_data = bot.multi_symbol(
    symbols=['AAPL', 'MSFT'],
    exchanges=['NASDAQ', 'NASDAQ'], # Corresponding exchanges
    bars=100
)
# multi_sym_data will be a dict: {'AAPL': Series_close, 'MSFT': Series_close}
```

### Backtesting Workflow
To perform a backtest, you need a strategy class that has a `generate_signals(self, df)` method. This method should take a pandas DataFrame of price data and return a DataFrame with a 'signal' column (1 for buy, -1 for sell, 0 for hold).

```python
# 1. Define your Strategy Class (Example: SimpleMACrossoverStrategy is in bot.py)
class MyStrategy:
    def __init__(self, ...): # Your strategy parameters
        # ...
        pass

    def generate_signals(self, df):
        signals = pd.DataFrame(index=df.index)
        signals['signal'] = 0.0
        # ... your logic to populate signals['signal'] ...
        # Example: signals based on 'close' prices in df
        # signals['signal'][condition_for_buy] = 1.0
        # signals['signal'][condition_for_sell] = -1.0
        return signals

# 2. Instantiate Bot and Strategy
bot = Bot(symbol='BTC/USD', exchange='BITSTAMP')
my_strategy = MyStrategy(...) # Initialize with your strategy's parameters

# 3. Run Backtest
backtest_results = bot.backtest(
    timeframe=Interval.in_1_hour,
    strategy_logic=my_strategy,
    initial_capital=10000.0,
    bars=1000,
    commission_bps=2.0 # 0.02% commission
)

# 4. Get Report and Plots (if backtest was successful)
if backtest_results:
    summary = bot.generate_summary_report(backtest_results)
    # The summary is printed to console by the method.
    # You can also use the returned 'summary' dictionary.

    bot.plot_results(backtest_results)
    # This will display the equity curve and price chart with trades.
```

### Grid Search Optimization for Strategies

The `Bot` class includes a `grid_search_optimize` method to help find the best parameters for your trading strategy based on a chosen performance metric.

```python
# Method signature:
# bot.grid_search_optimize(timeframe, strategy_class, parameter_grid, metric_to_optimize, 
#                          initial_capital=100000, bars=2000, commission_bps=0)
```

**How it Works:**

1.  **Define a Parameter Grid**: You provide a dictionary (`parameter_grid`) where keys are the names of the parameters in your strategy's `__init__` method, and values are lists of the values you want to test for those parameters.
2.  **Choose a Metric**: Specify which metric from the backtest summary report you want to maximize (e.g., `'total_pnl'`, `'sharpe_ratio_period'`, `'profit_factor'`).
3.  **Iteration**: The method iterates through all possible combinations of the parameters in your grid.
4.  **Backtesting**: For each combination, it instantiates your strategy with those parameters and runs a full backtest.
5.  **Evaluation**: It records the chosen performance metric for each parameter set.
6.  **Results**: It returns the parameter combination that yielded the highest score for your chosen metric, along with the score itself and a list containing results for all tested combinations.

**Example of `parameter_grid` and Usage:**

Let's assume you have a `SimpleMACrossoverStrategy` (like the one in `bot.py`) that takes `short_window` and `long_window` as parameters.

```python
# 1. (Bot and Strategy already instantiated or defined)
# bot = Bot(symbol='ETH/USD', exchange='COINBASE')
# strategy_class = SimpleMACrossoverStrategy # Pass the class, not an instance

# 2. Define the parameter grid
param_grid = {
    'short_window': [10, 15, 20],
    'long_window': [30, 40, 50] 
}
# This grid will test 3x3 = 9 combinations.
# Ensure that parameter constraints (e.g., short_window < long_window) are handled
# either by careful grid definition or within the strategy's __init__.
# The SimpleMACrossoverStrategy in bot.py checks this.

# 3. Choose the metric to optimize
metric = 'sharpe_ratio_period'

# 4. Run optimization
best_params, best_score, all_results = bot.grid_search_optimize(
    timeframe=Interval.in_1_hour,
    strategy_class=SimpleMACrossoverStrategy,
    parameter_grid=param_grid,
    metric_to_optimize=metric,
    initial_capital=10000.0,
    bars=500, # Use a reasonable number of bars for optimization speed
    commission_bps=2.0
)

# 5. Review results
if best_params:
    print(f"Best parameters found: {best_params}")
    print(f"Best {metric}: {best_score:.4f}")
    # all_results contains a list of dicts with {'params': ..., 'score': ..., 'summary': ...} for each combo
else:
    print("Grid search did not yield any valid results.")

```
**Important Considerations for Grid Search:**
*   **Computational Cost**: Grid search can be computationally expensive, as it runs a full backtest for every parameter combination. Be mindful of the size of your parameter grid and the number of bars used for backtesting.
*   **Overfitting**: Optimizing parameters too closely to historical data can lead to overfitting, where the strategy performs well on past data but poorly on new, unseen data. It's good practice to validate optimized parameters on out-of-sample data.
*   **Parameter Constraints**: Ensure logical constraints between parameters (e.g., `short_window` < `long_window`) are either managed by your grid definition or handled within your strategy's initialization to avoid errors or illogical tests.

## Example Usage

The `bot.py` script includes a runnable example in its `if __name__ == '__main__':` block. This example uses a `SimpleMACrossoverStrategy` (also defined in `bot.py`) to demonstrate the full workflow:

1.  Instantiating the `Bot`.
2.  Instantiating the `SimpleMACrossoverStrategy`.
3.  Running `bot.backtest()`.
4.  Calling `bot.generate_summary_report()` to print metrics.
5.  Calling `bot.plot_results()` to show charts.

To run the example:
```bash
python bot.py
```
**Note**: Ensure you have configured `TvDatafeed` authentication as mentioned in the Setup section, or the example may fail during data download.

## Running Unit Tests
Unit tests are provided in `test_bot.py`. To run them:
```bash
python -m unittest test_bot.py
```

This will help verify the core logic of the strategy evaluation, backtesting engine (with mocked data), and report calculations.

```

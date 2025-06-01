import MetaTrader5 as mt5

# MetaTrader 5 Connection Parameters
# Add any specific server, login, or password details if necessary.
# For now, we assume MT5 is running and accessible.

# Trading Pair Symbols
SYMBOL_1 = "EURUSD"  # Example: Euro vs US Dollar
SYMBOL_2 = "GBPUSD"  # Example: British Pound vs US Dollar
# Ensure these symbols are available in your MetaTrader 5 terminal

# Trading Parameters
MAGIC = 20240315  # Unique magic number for this EA
# Initial thought for volume: Aim for a roughly equivalent USD value for each leg of the pair.
# This will be refined in the `calculate_lot_size` function.
DESIRED_USD_VALUE_PER_LEG = 1000  # Target USD value for one leg of the trade
STOP_LOSS_PIPS = 50  # Stop loss in pips (e.g., 50 pips)
TAKE_PROFIT_PIPS = 100  # Take profit in pips (e.g., 100 pips)
PRICE_DEVIATION = 5  # Allowed price deviation for order execution (in points)

# Cointegration Test Parameters
COINTEGRATION_TIMEFRAME = mt5.TIMEFRAME_H1  # Timeframe for cointegration analysis (e.g., H1)
COINTEGRATION_LOOKBACK_PERIOD = 100  # Number of candles for regression and ADF test

# Spread Parameters
SPREAD_ENTRY_STD_DEV_THRESHOLD = 2.0  # Enter trade if spread is 2.0 std devs from mean
SPREAD_EXIT_STD_DEV_THRESHOLD = 0.5   # Exit trade if spread is 0.5 std devs from mean (or crosses mean)
EXTREME_SPREAD_STD_DEV_THRESHOLD = 3.5 # SL for the pair based on spread deviation

# Main Loop Cycle Time
CYCLE_TIME = 60  # Time in seconds between each loop iteration (e.g., 1 minute)

# Logging Configuration (Optional - for more advanced logging)
LOG_LEVEL = "INFO"
LOG_FILE = "cointegration_bot.log"

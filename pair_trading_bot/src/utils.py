import numpy as np
import pandas as pd
from statsmodels.tsa.vector_ar.vecm import coint_johansen
import logging

# Configure logging FIRST
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Attempt to import MetaTrader5, otherwise use a mock
try:
    import MetaTrader5 as mt5
except ImportError:
    logging.warning("MetaTrader5 module not found. Using a mock object for mt5.")
    # Create a mock mt5 object that allows the code to run without MetaTrader5
    class MockMT5:
        TIMEFRAME_D1 = "D1" # Example, add other timeframes if used directly
        # Add any other constants that might be accessed directly

        def initialize(self):
            logging.info("MockMT5: initialize called")
            return False # Simulate failure to initialize

        def shutdown(self):
            logging.info("MockMT5: shutdown called")
            pass

        def copy_rates_range(self, symbol, timeframe, start_date, end_date):
            logging.info(f"MockMT5: copy_rates_range called for {symbol}")
            return None # Simulate no data returned

        def terminal_info(self):
            logging.info("MockMT5: terminal_info called")
            return None # Simulate not initialized

    mt5 = MockMT5()

# Removed the second basicConfig call, it's now at the top.

def download_price_data(symbol, timeframe, start_date, end_date):
    """
    Downloads historical price data from MetaTrader 5.
    Note: This function assumes MT5 is initialized and logged in.
    """
    logging.info(f"Attempting to download data for {symbol} from {start_date} to {end_date} on timeframe {timeframe}.")
    try:
        # Ensure MT5 is initialized (this might be done in the main bot script)
        if not mt5.initialize():
            logging.error("Failed to initialize MetaTrader5.")
            # In a real scenario, you might raise an exception or handle this more robustly.
            # For now, returning an empty DataFrame to allow other parts to be tested.
            return pd.DataFrame()

        # Convert timeframe string to MT5 constant if necessary (e.g., 'D1' to mt5.TIMEFRAME_D1)
        # This is a simplified example; a more robust solution would map various timeframe strings.
        mt5_timeframe = getattr(mt5, f"TIMEFRAME_{timeframe.upper()}", mt5.TIMEFRAME_D1)

        rates = mt5.copy_rates_range(symbol, mt5_timeframe, pd.to_datetime(start_date), pd.to_datetime(end_date))
        mt5.shutdown() # Shutdown after use, or manage connection lifecycle elsewhere

        if rates is None:
            logging.warning(f"No data returned from MT5 for {symbol}.")
            return pd.DataFrame()

        data = pd.DataFrame(rates)
        data['time'] = pd.to_datetime(data['time'], unit='s')
        data.set_index('time', inplace=True)
        logging.info(f"Successfully downloaded {len(data)} data points for {symbol}.")
        return data
    except Exception as e:
        logging.error(f"Error downloading price data for {symbol}: {e}")
        # Ensure MT5 is shutdown in case of error during operations
        if mt5.terminal_info() is not None: # Check if initialized before trying to shutdown
            mt5.shutdown()
        return pd.DataFrame()

def calculate_cointegration(series1, series2, significance_level=0.05):
    """
    Calculates cointegration between two series using the Johansen test.
    Returns True if cointegrated, False otherwise.
    """
    if not isinstance(series1, pd.Series):
        series1 = pd.Series(series1)
    if not isinstance(series2, pd.Series):
        series2 = pd.Series(series2)

    df = pd.concat([series1, series2], axis=1).dropna()
    df.columns = ['series1', 'series2']

    if len(df) < 20: # Not enough data points for a reliable test
        logging.warning("Not enough data points to perform cointegration test.")
        return False, 0.0

    # The Johansen test requires non-stationarity of individual series.
    # This is a simplification; a full check for I(1) would be more robust.

    # Perform the Johansen cointegration test
    # det_order = -1 (no intercept), 0 (intercept), 1 (trend)
    # k_ar_diff = number of lags (p-1 where p is VAR order)
    try:
        result = coint_johansen(df, det_order=0, k_ar_diff=1)
    except Exception as e:
        logging.error(f"Error during Johansen test: {e}")
        return False, 0.0

    # Check trace statistic against critical values
    # We are looking for at most 1 cointegrating vector (r <= 1) for two series
    trace_stat = result.lr1
    crit_vals = result.cvt  # Critical values (90%, 95%, 99%) for r=0, r<=1, ...

    # For two series, we test hypothesis H0: r=0 against H1: r=1
    # If trace_stat[0] > crit_vals[0, 1] (95% significance), we reject r=0.
    # This means there is at least one cointegrating relationship.
    # For a pair, this implies they are cointegrated.

    # The result.cvt has shape (n_series, 3) for critical values at 90, 95, 99%
    # We are interested in the test for r=0 (first row of trace_stat and cvt)
    # and typically use 95% significance level (index 1 in cvt's second dimension)
    if trace_stat[0] > crit_vals[0, 1]: # Compare trace statistic for r=0 with 95% critical value
        logging.info("Series are likely cointegrated based on Johansen test (trace statistic).")
        # Hedge ratio can be estimated from the eigenvectors (result.evec)
        # The first eigenvector corresponds to the cointegrating vector [1, -beta]
        # So, hedge_ratio = result.evec[1,0] / result.evec[0,0] if normalized, or simply result.evec[1,0] if evec[0,0] is 1.
        # Or more directly, the first column of evec is the cointegrating vector.
        hedge_ratio = -result.evec[1,0] / result.evec[0,0] # Ensure it's series2 relative to series1
        logging.info(f"Estimated hedge ratio: {hedge_ratio}")
        return True, hedge_ratio
    else:
        logging.info("Series are not likely cointegrated based on Johansen test (trace statistic).")
        return False, 0.0

def calculate_spread(series1, series2, hedge_ratio):
    """
    Calculates the spread between two cointegrated series.
    Spread = series1 - hedge_ratio * series2
    """
    if not isinstance(series1, pd.Series):
        series1 = pd.Series(series1)
    if not isinstance(series2, pd.Series):
        series2 = pd.Series(series2)

    # Ensure series are aligned by index
    aligned_s1, aligned_s2 = series1.align(series2, join='inner')

    if aligned_s1.empty or aligned_s2.empty:
        logging.warning("Cannot calculate spread on empty or misaligned series.")
        return pd.Series(dtype=np.float64)

    spread = aligned_s1 - hedge_ratio * aligned_s2
    logging.info(f"Spread calculated with {len(spread)} points.")
    return spread

def calculate_zscore(series, window=None):
    """
    Calculates the z-score of a series.
    If window is None, calculates z-score based on the entire series.
    If window is an integer, calculates rolling z-score.
    """
    if not isinstance(series, pd.Series):
        series = pd.Series(series)

    if series.empty:
        logging.warning("Cannot calculate z-score on an empty series.")
        return pd.Series(dtype=np.float64)

    if window:
        # Rolling z-score
        mean = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        zscore = (series - mean) / std
    else:
        # Z-score for the entire series
        mean = series.mean()
        std = series.std()
        if std == 0: # Avoid division by zero if series is constant
            logging.warning("Standard deviation is zero, cannot calculate z-score. Returning series of zeros.")
            return pd.Series(np.zeros(len(series)), index=series.index)
        zscore = (series - mean) / std

    logging.info(f"Z-score calculated. Rolling window: {window if window else 'None'}")
    return zscore

if __name__ == '__main__':
    # Example Usage (for testing purposes, assuming MT5 is not available here)

    # Mock data for testing cointegration, spread, and z-score
    np.random.seed(42)
    n_points = 200
    s1 = pd.Series(np.random.randn(n_points).cumsum() + 100) # Random walk
    s2 = pd.Series(s1 + np.random.randn(n_points) * 0.5 + 5) # s2 is cointegrated with s1 by construction
    s3 = pd.Series(np.random.randn(n_points).cumsum() + 50) # Another random walk, likely not cointegrated with s1

    s1.index = pd.date_range(start='2023-01-01', periods=n_points, freq='D')
    s2.index = pd.date_range(start='2023-01-01', periods=n_points, freq='D')
    s3.index = pd.date_range(start='2023-01-01', periods=n_points, freq='D')

    logging.info("\n--- Testing Cointegration S1 and S2 ---")
    is_coint_s1_s2, hedge_ratio_s1_s2 = calculate_cointegration(s1, s2)
    logging.info(f"S1 and S2 Cointegrated: {is_coint_s1_s2}, Hedge Ratio: {hedge_ratio_s1_s2}")

    logging.info("\n--- Testing Cointegration S1 and S3 ---")
    is_coint_s1_s3, hedge_ratio_s1_s3 = calculate_cointegration(s1, s3)
    logging.info(f"S1 and S3 Cointegrated: {is_coint_s1_s3}, Hedge Ratio: {hedge_ratio_s1_s3}")

    if is_coint_s1_s2:
        logging.info("\n--- Testing Spread Calculation (S1, S2) ---")
        spread_s1_s2 = calculate_spread(s1, s2, hedge_ratio_s1_s2)
        # logging.info(f"Spread (S1, S2):\n{spread_s1_s2.head()}")

        logging.info("\n--- Testing Z-score Calculation (Spread S1, S2) ---")
        zscore_s1_s2 = calculate_zscore(spread_s1_s2)
        # logging.info(f"Z-score (Spread S1, S2):\n{zscore_s1_s2.head()}")

        logging.info("\n--- Testing Rolling Z-score Calculation (Spread S1, S2) ---")
        rolling_zscore_s1_s2 = calculate_zscore(spread_s1_s2, window=20)
        # logging.info(f"Rolling Z-score (Spread S1, S2, window=20):\n{rolling_zscore_s1_s2.tail()}")

    # Example for MT5 data download (will likely fail if MT5 is not set up)
    # logging.info("\n--- Testing MT5 Download Function (will likely return empty if MT5 not configured) ---")
    # test_symbol = "EURUSD"
    # test_timeframe = "D1"
    # test_start_date = "2023-01-01"
    # test_end_date = "2023-03-31"
    # price_data = download_price_data(test_symbol, test_timeframe, test_start_date, test_end_date)
    # if not price_data.empty:
    #     logging.info(f"Downloaded data for {test_symbol}:\n{price_data.head()}")
    # else:
    #     logging.info(f"No data downloaded for {test_symbol}, as expected if MT5 is not available/mocked.")

import pandas as pd
import numpy as np
import time
import logging

# Attempt to import from local src package, adjust path if necessary for execution context
try:
    from .utils import download_price_data, calculate_cointegration, calculate_spread, calculate_zscore, mt5
    from .money_management import calculate_position_size, calculate_stop_loss_take_profit
except ImportError: # Fallback for running script directly or if src path not set up
    from utils import download_price_data, calculate_cointegration, calculate_spread, calculate_zscore, mt5
    from money_management import calculate_position_size, calculate_stop_loss_take_profit


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__)

class PairTradingBot:
    def __init__(self, symbol1, symbol2, timeframe, lookback_period,
                 entry_z_threshold, exit_z_threshold, stop_loss_z_multiplier,
                 account_balance, risk_percentage, pip_value_leg1, pip_value_leg2,
                 min_trade_interval_seconds=60):
        """
        Initializes the Pair Trading Bot.

        Parameters:
        - symbol1 (str): The first symbol of the pair (e.g., "AUDCAD").
        - symbol2 (str): The second symbol of the pair (e.g., "NZDCAD").
        - timeframe (str): Timeframe for data (e.g., "H1", "D1"). MT5 format.
        - lookback_period (int): Number of candles for cointegration and z-score calculation.
        - entry_z_threshold (float): Z-score threshold to enter a trade (e.g., 2.0).
        - exit_z_threshold (float): Z-score threshold to exit a trade (e.g., 0.5, for mean reversion).
        - stop_loss_z_multiplier (float): Z-score level for stop loss (e.g., 3.0).
        - account_balance (float): Initial account balance for position sizing.
        - risk_percentage (float): Risk per trade (e.g., 0.01 for 1%).
        - pip_value_leg1 (float): Monetary value of 1 pip for 1 lot of symbol1.
        - pip_value_leg2 (float): Monetary value of 1 pip for 1 lot of symbol2.
        - min_trade_interval_seconds (int): Minimum time between trades to avoid over-trading.
        """
        self.symbol1 = symbol1
        self.symbol2 = symbol2
        self.timeframe = timeframe
        self.lookback_period = lookback_period # For historical data fetching and initial calculations
        self.entry_z_threshold = abs(entry_z_threshold)
        self.exit_z_threshold = abs(exit_z_threshold)
        self.stop_loss_z_multiplier = abs(stop_loss_z_multiplier)

        self.account_balance = account_balance
        self.risk_percentage = risk_percentage
        self.pip_value_leg1 = pip_value_leg1 # This will be used as proxy for spread pip value
        self.pip_value_leg2 = pip_value_leg2 # Not directly used in simplified position sizing yet

        self.min_trade_interval_seconds = min_trade_interval_seconds
        self.last_trade_time = 0

        self.hedge_ratio = None
        self.current_spread = pd.Series(dtype=np.float64)
        self.current_zscore = None

        self.is_mt5_initialized = False
        self.open_position = None # To store details of the current open trade {'type': 'long'/'short', 'entry_price': float, 'size': float, 'sl': float, 'tp': float}

        self._connect_mt5()

    def _connect_mt5(self):
        """Initializes connection to MetaTrader 5."""
        # This will use the mock from utils if the real MetaTrader5 is not installed
        # or if mt5.initialize() fails.
        try:
            if mt5.initialize():
                logger.info("MetaTrader 5 initialized successfully.")
                self.is_mt5_initialized = True
                # Login if needed - credentials should be handled securely, not hardcoded
                # account_info = mt5.account_info()
                # if account_info:
                #     logger.info(f"Logged into account: {account_info.login}")
                # else:
                #     logger.error("Failed to get account info. Check login and connection.")
                #     self.is_mt5_initialized = False # Force check later
            else:
                logger.error("Failed to initialize MetaTrader 5. Using mock or limited functionality.")
                self.is_mt5_initialized = False
        except Exception as e: # Catch if mt5 itself is the mock object and initialize is not robust
            logger.warning(f"MetaTrader 5 connection attempt resulted in an error: {e}. Assuming mock environment.")
            self.is_mt5_initialized = False # Ensure it's false if any error

    def _fetch_data(self, symbol, count):
        """Fetches historical data for a symbol."""
        # For simplicity, using a fixed start date far enough in the past.
        # A more robust approach would calculate start_date based on count and timeframe.
        end_dt = pd.Timestamp.now()
        # This is an approximation for count; MT5 copy_rates_from_pos is better for exact counts
        # For now, download_price_data expects date ranges.
        # Estimate start date (very roughly, depends on timeframe)
        if self.timeframe == "D1":
            start_dt = end_dt - pd.Timedelta(days=count * 1.5)
        elif self.timeframe == "H1":
            start_dt = end_dt - pd.Timedelta(hours=count * 1.5)
        else: # Default fallback, may not be accurate
            start_dt = end_dt - pd.Timedelta(days=count * 2)

        logger.info(f"Fetching {count} bars for {symbol} up to {end_dt.strftime('%Y-%m-%d %H:%M')} on {self.timeframe}")

        # Use the utility function which handles actual MT5 call or mock
        data = download_price_data(symbol, self.timeframe.upper(), start_dt, end_dt)
        if data is not None and not data.empty:
            # Ensure we have enough data, and take the latest 'count' records
            return data['close'].iloc[-count:] if len(data) >= count else data['close']
        logger.warning(f"Could not fetch sufficient data for {symbol}.")
        return pd.Series(dtype=np.float64)

    def _update_market_data_and_parameters(self):
        """Fetches latest data, re-calculates cointegration, spread, and z-score."""
        logger.info("Updating market data and parameters...")
        series1 = self._fetch_data(self.symbol1, self.lookback_period)
        series2 = self._fetch_data(self.symbol2, self.lookback_period)

        if series1.empty or series2.empty or len(series1) < self.lookback_period or len(series2) < self.lookback_period:
            logger.warning("Insufficient data for one or both symbols. Skipping calculations.")
            return False

        # Align series by index (time) before further processing
        # This is crucial if data points don't perfectly align
        aligned_s1, aligned_s2 = series1.align(series2, join='inner')
        if len(aligned_s1) < self.lookback_period * 0.8: # Ensure substantial overlap
            logger.warning(f"After alignment, insufficient data overlap ({len(aligned_s1)} points). Skipping.")
            return False

        is_coint, hr = calculate_cointegration(aligned_s1, aligned_s2)
        if not is_coint:
            logger.warning(f"{self.symbol1} and {self.symbol2} are not currently cointegrated. Halting strategy for now.")
            self.hedge_ratio = None # Invalidate hedge ratio
            # Consider closing any open positions if cointegration is lost
            if self.open_position:
                logger.info("Cointegration lost, closing open position.")
                self._close_position_logic("Cointegration lost")
            return False

        self.hedge_ratio = hr
        logger.info(f"Cointegration found. Hedge Ratio: {self.hedge_ratio:.4f}")

        self.current_spread = calculate_spread(aligned_s1, aligned_s2, self.hedge_ratio)
        if self.current_spread.empty:
            logger.warning("Spread calculation resulted in empty series.")
            return False

        # Use a rolling window for Z-score for adaptability, or full series if preferred
        # Rolling window should be same as lookback_period for consistency, or a bit shorter
        self.current_zscore = calculate_zscore(self.current_spread, window=self.lookback_period)
        if self.current_zscore.empty or pd.isna(self.current_zscore.iloc[-1]):
            logger.warning("Z-score calculation resulted in empty or NaN series.")
            self.current_zscore = None # Invalidate z-score
            return False

        logger.info(f"Latest spread: {self.current_spread.iloc[-1]:.4f}, Latest Z-score: {self.current_zscore.iloc[-1]:.2f}")
        return True

    def _generate_signals(self):
        """Generates trading signals based on the current z-score."""
        if self.current_zscore is None or pd.isna(self.current_zscore.iloc[-1]):
            logger.info("No valid Z-score available. No signal.")
            return None

        latest_z = self.current_zscore.iloc[-1]
        signal = None

        if self.open_position is None: # No open position, look for entry
            if latest_z > self.entry_z_threshold:
                signal = 'SELL_SPREAD' # Spread is too high, sell it (sell S1, buy S2*HR)
                logger.info(f"Signal: SELL SPREAD (Z-score: {latest_z:.2f} > {self.entry_z_threshold})")
            elif latest_z < -self.entry_z_threshold:
                signal = 'BUY_SPREAD'  # Spread is too low, buy it (buy S1, sell S2*HR)
                logger.info(f"Signal: BUY SPREAD (Z-score: {latest_z:.2f} < {-self.entry_z_threshold})")
        else: # Has an open position, look for exit
            if self.open_position['type'] == 'BUY_SPREAD': # Was long spread
                if latest_z >= -self.exit_z_threshold: # or latest_z >= self.open_position['tp_z_target']
                    signal = 'EXIT_LONG'
                    logger.info(f"Signal: EXIT LONG SPREAD (Z-score: {latest_z:.2f} >= {-self.exit_z_threshold})")
            elif self.open_position['type'] == 'SELL_SPREAD': # Was short spread
                if latest_z <= self.exit_z_threshold: # or latest_z <= self.open_position['tp_z_target']
                    signal = 'EXIT_SHORT'
                    logger.info(f"Signal: EXIT SHORT SPREAD (Z-score: {latest_z:.2f} <= {self.exit_z_threshold})")
        return signal

    def _execute_trade(self, signal):
        """
        Executes a trade based on the signal.
        This is a placeholder for actual MT5 order execution.
        """
        if not self.is_mt5_initialized:
            logger.warning("MT5 not initialized. Cannot execute trades. (Simulating for now)")
            # Allow simulation even if MT5 is not live
            # return

        current_time = time.time()
        if current_time - self.last_trade_time < self.min_trade_interval_seconds and self.open_position is None : # Check interval only for new entries
             logger.info(f"Trade attempt too soon. Min interval: {self.min_trade_interval_seconds}s. Skipping.")
             return

        if signal in ['BUY_SPREAD', 'SELL_SPREAD'] and self.open_position is None:
            self.last_trade_time = current_time

            # Calculate position size
            # For spread, SL pips needs to be on the spread value.
            # Let's assume SL for the spread is defined by the stop_loss_z_multiplier from the mean.
            # Spread_SL_Price = Mean_Spread + (Z_entry_sign * SL_Z_Multiplier) * Std_Dev_Spread
            # Spread_Entry_Price = self.current_spread.iloc[-1]
            # Pips_SL_Spread = abs(Spread_Entry_Price - Spread_SL_Price) / Pip_Value_of_Spread_Point
            # This is complex. Simplify: Assume a fixed pip SL for sizing calculation, or derive from Z-score.

            # Simplified SL pips for sizing: let's use a fixed arbitrary value for now e.g. 100 pips on the "spread instrument"
            # A better way: calculate SL price from Z-score, then pips from entry price to SL price.
            # Spread_Mean = self.current_spread.rolling(window=self.lookback_period).mean().iloc[-1]
            # Spread_Std = self.current_spread.rolling(window=self.lookback_period).std().iloc[-1]

            # Ensure spread stats are available
            if pd.isna(self.current_spread.mean()) or pd.isna(self.current_spread.std()) or self.current_spread.std() == 0:
                logger.error("Spread mean/std is NaN or std is zero. Cannot calculate SL/TP for trade.")
                return

            is_long = True if signal == 'BUY_SPREAD' else False
            entry_z = self.current_zscore.iloc[-1]

            sl_price, tp_price = calculate_stop_loss_take_profit(
                entry_price=self.current_spread.iloc[-1],
                z_score=entry_z,
                mean_spread=self.current_spread.mean(), # Or rolling mean
                std_spread=self.current_spread.std(),   # Or rolling std
                stop_loss_z_multiplier=self.stop_loss_z_multiplier,
                take_profit_z_target= -self.exit_z_threshold if is_long else self.exit_z_threshold, # Target opposite side of mean for TP
                is_long_spread=is_long
            )

            # Calculate SL pips from entry to SL price.
            # This assumes the spread itself has a "pip value".
            # For now, use a proxy: self.pip_value_leg1 for the "spread instrument"
            # This part is highly conceptual without a tradable spread instrument or defined pip value for spread.
            # Let's assume spread points are like pips for simplicity of sizing.
            stop_loss_points = abs(self.current_spread.iloc[-1] - sl_price)
            if stop_loss_points == 0: # Avoid division by zero if SL is too close or error
                logger.warning("Calculated stop loss points is zero. Using a minimum default (e.g. 10 points) for sizing.")
                stop_loss_points = 10 # Arbitrary minimum

            # Use pip_value_leg1 as a proxy for the value of 1 point change in spread for 1 lot.
            # This is a BIG assumption.
            pos_size = calculate_position_size(
                account_balance=self.account_balance,
                risk_percentage=self.risk_percentage,
                stop_loss_pips=stop_loss_points, # Using points as pips
                pips_per_unit=0, # Added: Consistent with money_management.py test, as it's not used there when price_per_pip_leg1 is for lot value
                price_per_pip_leg1=self.pip_value_leg1, # Proxy for spread's point value
                is_spread_trade=True # Use the simplified spread trade logic
            )

            if pos_size <= 0:
                logger.warning(f"Calculated position size is {pos_size}. Cannot open trade.")
                return

            self.open_position = {
                'type': signal,
                'entry_price_spread': self.current_spread.iloc[-1],
                'entry_z': entry_z,
                'size': pos_size,
                'sl_price_spread': sl_price,
                'tp_price_spread': tp_price,
                'symbol1': self.symbol1,
                'symbol2': self.symbol2,
                'hedge_ratio': self.hedge_ratio
            }
            logger.info(f"SIMULATING TRADE: {signal} | Size: {pos_size} lots | Entry Spread: {self.open_position['entry_price_spread']:.4f} (Z={entry_z:.2f}) | SL Spread: {sl_price:.4f} | TP Spread: {tp_price:.4f}")
            # Actual MT5 order placement for two legs would go here
            # e.g., mt5.order_send for symbol1 and symbol2 with appropriate sizes & directions

        elif signal in ['EXIT_LONG', 'EXIT_SHORT'] and self.open_position is not None:
            self._close_position_logic(f"Exit signal: {signal}")

    def _close_position_logic(self, reason):
        """ Encapsulates logic for closing a position (simulation). """
        logger.info(f"SIMULATING CLOSE POSITION: {self.open_position['type']} due to {reason} at current spread Z={self.current_zscore.iloc[-1]:.2f} / Spread={self.current_spread.iloc[-1]:.4f}")
        # Actual MT5 close orders would go here

        # Simulate P/L (very roughly, not accounting for transaction costs, exact fill prices)
        exit_price_spread = self.current_spread.iloc[-1]
        entry_price_spread = self.open_position['entry_price_spread']
        size = self.open_position['size']

        profit_points = 0
        if self.open_position['type'] == 'BUY_SPREAD':
            profit_points = exit_price_spread - entry_price_spread
        elif self.open_position['type'] == 'SELL_SPREAD':
            profit_points = entry_price_spread - exit_price_spread

        # Using pip_value_leg1 as proxy for spread point value per lot
        estimated_profit = profit_points * size * self.pip_value_leg1
        self.account_balance += estimated_profit # Update balance (simulation)

        logger.info(f"Estimated P/L for closed trade: {estimated_profit:.2f}. New Account Balance (simulated): {self.account_balance:.2f}")

        self.open_position = None
        self.last_trade_time = time.time() # Update last trade time after closing

    def _check_stop_loss_take_profit(self):
        """Checks if SL or TP levels for the open position have been hit."""
        if self.open_position is None or self.current_spread.empty:
            return

        latest_spread_price = self.current_spread.iloc[-1]
        sl_hit = False
        tp_hit = False

        if self.open_position['type'] == 'BUY_SPREAD': # Long spread
            if latest_spread_price <= self.open_position['sl_price_spread']:
                sl_hit = True
                logger.info("Stop Loss hit for BUY_SPREAD position.")
            elif latest_spread_price >= self.open_position['tp_price_spread']:
                tp_hit = True
                logger.info("Take Profit hit for BUY_SPREAD position.")
        elif self.open_position['type'] == 'SELL_SPREAD': # Short spread
            if latest_spread_price >= self.open_position['sl_price_spread']:
                sl_hit = True
                logger.info("Stop Loss hit for SELL_SPREAD position.")
            elif latest_spread_price <= self.open_position['tp_price_spread']:
                tp_hit = True
                logger.info("Take Profit hit for SELL_SPREAD position.")

        if sl_hit:
            self._close_position_logic("Stop Loss")
        elif tp_hit:
            self._close_position_logic("Take Profit")

    def run_check(self):
        """Runs a single check cycle of the bot."""
        logger.info("--- Running Bot Check Cycle ---")
        if not self.is_mt5_initialized:
            # Try to connect again if not initialized (e.g. if MT5 terminal was restarted)
            # self._connect_mt5() # Be careful with frequent reconnection attempts
            if not self.is_mt5_initialized: # Check again after attempt
                 logger.warning("MT5 still not initialized. Cannot proceed with check cycle that requires live data/trading.")
                 # Depending on strategy, some parts might run with historical/mock data
                 # For now, we mostly halt if no live connection for trading actions.
                 # return # Exit if no MT5 connection for live operations.

        if not self._update_market_data_and_parameters():
            logger.warning("Failed to update market data or parameters. Skipping this cycle.")
            return

        if self.open_position:
            self._check_stop_loss_take_profit()
            # If position was closed by SL/TP, self.open_position will be None
            if self.open_position is None:
                return # Don't try to generate new signals immediately after SL/TP

        # Generate and execute signals only if no position was closed by SL/TP in this check
        if self.open_position is None or (self.open_position is not None and self.current_zscore is not None): # Allow exit signals if position is open
            signal = self._generate_signals()
            if signal:
                self._execute_trade(signal)
        logger.info("--- Bot Check Cycle Complete ---")

    def shutdown_mt5(self):
        if self.is_mt5_initialized and hasattr(mt5, 'shutdown'):
            logger.info("Shutting down MetaTrader 5 connection.")
            mt5.shutdown()
            self.is_mt5_initialized = False

# Example Usage (for testing the bot logic)
if __name__ == '__main__':
    logger.info("--- Initializing Pair Trading Bot (Example) ---")

    # Parameters for the bot
    # These pip values are highly dependent on the broker and pair's quote currency.
    # For AUDCAD/NZDCAD, if quoted in USD and mini lots, pip value might be ~$0.10 for 0.01 lots.
    # For 1 lot, it would be ~$10. Assuming direct USD quote for simplicity.
    # This needs to be accurate for real trading.
    example_pip_value_audcad = 7.3  # Approx USD value of 1 pip for 1 lot of AUDCAD
    example_pip_value_nzdcad = 6.8  # Approx USD value of 1 pip for 1 lot of NZDCAD

    # Using one of these as a proxy for the "spread instrument" pip value in position sizing
    # This is a simplification. True spread pip value is complex.
    proxy_spread_pip_value = example_pip_value_audcad

    bot = PairTradingBot(
        symbol1="AUDCAD", # Example pair
        symbol2="NZDCAD", # Example pair
        timeframe="H1",     # Use H1 for more frequent data for testing
        lookback_period=100,# Number of candles for calculation
        entry_z_threshold=2.0,
        exit_z_threshold=0.5, # Exit when Z comes back towards 0.5
        stop_loss_z_multiplier=3.0, # SL if Z goes to 3.0 (against us)
        account_balance=10000,
        risk_percentage=0.01, # 1% risk per trade
        pip_value_leg1=proxy_spread_pip_value,
        pip_value_leg2=example_pip_value_nzdcad, # Not directly used in current simple sizing
        min_trade_interval_seconds=5 # Low for testing
    )

    # Simulate a few cycles
    # In a real scenario, this would be in a loop with a sleep timer
    for i in range(5): # Run 5 cycles for testing
        logger.info(f"--- Simulation Cycle {i+1} ---")
        # In a real bot, you might want to mock series1 and series2 data updates here
        # to test different scenarios. The _fetch_data will try to use MT5 (mocked or real).
        # If using the MT5 mock from utils.py, it will return empty data unless the mock is enhanced.

        # To make this test runnable without live MT5 and see logic:
        # We can manually set some data if MT5 is mocked and returns empty.
        if not bot.is_mt5_initialized or bot._fetch_data(bot.symbol1, bot.lookback_period).empty:
            logger.info("MT5 not available or returned empty. Using dummy data for simulation.")
            # Create some dummy data that might show cointegration and z-score dynamics
            idx = pd.date_range(start=pd.Timestamp.now() - pd.Timedelta(hours=bot.lookback_period*1.2), periods=bot.lookback_period + i*5, freq='h') # Growing data, changed 'H' to 'h'

            # Construct cointegrated series for testing
            base_series = np.random.randn(len(idx)).cumsum() * 0.1
            noise1 = np.random.randn(len(idx)) * 0.05
            noise2 = np.random.randn(len(idx)) * 0.05

            s1_data = pd.Series(base_series + noise1 + (i*0.01), index=idx) # s1 slightly trends up over cycles
            # s2 related to s1 with some noise, and a slight divergence controlled by 'i' to trigger trades
            s2_data = pd.Series(base_series * 0.8 + noise2 - (i*0.02) + np.sin(np.linspace(0, (i+1)*np.pi, len(idx)))*0.1, index=idx)

            # Monkey patch _fetch_data to return these dummy series
            def mock_fetch_data(symbol, count):
                if symbol == bot.symbol1:
                    return s1_data.iloc[-count:]
                elif symbol == bot.symbol2:
                    return s2_data.iloc[-count:]
                return pd.Series(dtype=np.float64)
            bot._fetch_data = mock_fetch_data
            logger.info(f"Patched _fetch_data with dummy data for cycle {i+1}.")

        bot.run_check()
        logger.info(f"Bot state after cycle {i+1}: Open Position: {bot.open_position is not None}, Z-score: {bot.current_zscore.iloc[-1] if bot.current_zscore is not None and not bot.current_zscore.empty else 'N/A'}")
        time.sleep(1) # Simulate time passing between checks

    bot.shutdown_mt5()
    logger.info("--- Pair Trading Bot Example Finished ---")

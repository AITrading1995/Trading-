import logging
import MetaTrader5 as mt5
import time
import pandas as pd
import numpy as np
import statsmodels.api as sm
from statsmodels.tsa.stattools import adfuller
import config  # Our configuration file

# --- Logger Setup ---
logger = logging.getLogger(__name__) # Use module name or a custom name
logger.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))

# Console Handler
ch = logging.StreamHandler()
ch.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

# File Handler (optional, if LOG_FILE is set in config)
if hasattr(config, 'LOG_FILE') and config.LOG_FILE:
    fh = logging.FileHandler(config.LOG_FILE)
    fh.setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.INFO))
    fh.setFormatter(formatter)
    logger.addHandler(fh)
# --- End Logger Setup ---

# Global variable to keep track of MT5 initialization status
mt5_initialized = False

def Init():
    """Initializes the MetaTrader 5 connection and selects symbols."""
    global mt5_initialized
    if not mt5.initialize():
        logger.error(f"MT5 initialize failed, error code: {mt5.last_error()}")
        mt5_initialized = False
        return False
    logger.info("MetaTrader 5 initialized successfully.")

    # Select symbol 1
    if not mt5.symbol_select(config.SYMBOL_1, True):
        logger.error(f"Failed to select symbol {config.SYMBOL_1}, error: {mt5.last_error()}")
        mt5.shutdown()
        mt5_initialized = False
        return False
    logger.info(f"Symbol {config.SYMBOL_1} selected successfully.")

    # Select symbol 2
    if not mt5.symbol_select(config.SYMBOL_2, True):
        logger.error(f"Failed to select symbol {config.SYMBOL_2}, error: {mt5.last_error()}")
        mt5.shutdown()
        mt5_initialized = False
        return False
    logger.info(f"Symbol {config.SYMBOL_2} selected successfully.")

    mt5_initialized = True
    return True

def get_historical_data(symbol, timeframe, count):
    """Fetches historical close prices for a given symbol.

    Args:
        symbol (str): The symbol to fetch data for (e.g., "EURUSD").
        timeframe (int): MT5 timeframe constant (e.g., mt5.TIMEFRAME_H1).
        count (int): The number of candles to retrieve.

    Returns:
        pd.Series: A Pandas Series of close prices, indexed by time,
                   or None if data retrieval fails.
    """
    if not mt5_initialized:
        logger.warning("MT5 not initialized. Cannot fetch historical data.")
        return None

    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)

    if rates is None:
        logger.error(f"Failed to get rates for {symbol}, error: {mt5.last_error()}")
        return None

    if len(rates) < count:
        logger.warning(f"Could not retrieve enough data for {symbol}. Requested {count}, got {len(rates)}.")
        return None

    # Convert to DataFrame
    rates_frame = pd.DataFrame(rates)
    # Convert time in seconds to datetime objects
    rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')
    # Set time as index
    rates_frame.set_index('time', inplace=True)

    logger.info(f"Successfully fetched {len(rates_frame)} data points for {symbol} on {timeframe} timeframe.")
    return rates_frame['close']

def check_cointegration(series1, series2):
    """Checks for cointegration between two price series.

    Args:
        series1 (pd.Series): Price series of the first symbol (dependent variable).
        series2 (pd.Series): Price series of the second symbol (independent variable).

    Returns:
        tuple: (is_cointegrated (bool), spread (pd.Series), hedge_ratio (float))
               Returns (False, None, None) if not cointegrated or an error occurs.
    """
    if series1 is None or series2 is None:
        logger.warning("One or both series are None. Cannot check cointegration.")
        return False, None, None

    if len(series1) != len(series2):
        logger.warning("Series lengths do not match. Cannot perform regression.")
        return False, None, None

    if series1.isnull().any() or series2.isnull().any():
        logger.warning("One or both series contain NaN values. Cannot check cointegration.")
        return False, None, None

    try:
        series2_with_const = sm.add_constant(series2)
        model = sm.OLS(series1, series2_with_const)
        results = model.fit()
        hedge_ratio = results.params.iloc[1]
        spread = series1 - hedge_ratio * series2
        adf_test_result = adfuller(spread)

        adf_statistic = adf_test_result[0]
        p_value = adf_test_result[1]
        critical_values = adf_test_result[4]

        logger.debug(f"Cointegration Test Results:") # Changed to debug for less verbosity
        logger.debug(f"  Hedge Ratio: {hedge_ratio:.4f}")
        logger.debug(f"  ADF Statistic: {adf_statistic:.4f}")
        logger.debug(f"  P-value: {p_value:.4f}")
        logger.debug(f"  Critical Values:")
        for key, value in critical_values.items():
            logger.debug(f"    {key}: {value:.4f}")

        if adf_statistic < critical_values['5%']:
            logger.info("  Result: Series are likely cointegrated (ADF < 5% critical value).")
            return True, spread, hedge_ratio
        else:
            logger.info("  Result: Series are likely NOT cointegrated (ADF >= 5% critical value).")
            return False, spread, hedge_ratio

    except Exception as e:
        logger.error(f"Error during cointegration check: {e}", exc_info=True)
        return False, None, None

def calculate_lot_size(symbol, desired_usd_value, current_price):
    """Calculates the trading volume (lot size) for a symbol
    to achieve a desired USD value for the position, respecting symbol constraints.
    """
    if not mt5_initialized:
        logger.warning("MT5 not initialized. Cannot calculate lot size.")
        return 0.0

    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        logger.error(f"Failed to get symbol info for {symbol}, error: {mt5.last_error()}")
        return 0.0

    contract_size = symbol_info.contract_size
    volume_min = symbol_info.volume_min
    volume_max = symbol_info.volume_max
    volume_step = symbol_info.volume_step

    if current_price <= 0:
        logger.warning(f"Invalid current_price ({current_price}) for lot calculation.")
        return 0.0

    if contract_size <= 0:
        logger.warning(f"Invalid contract_size ({contract_size}) for {symbol}.")
        return 0.0

    value_of_one_lot = contract_size * current_price
    if value_of_one_lot <= 0:
        logger.warning(f"Calculated value of one lot is invalid ({value_of_one_lot}) for {symbol}.")
        return 0.0

    calculated_volume = desired_usd_value / value_of_one_lot

    if volume_step > 0:
        calculated_volume = round(calculated_volume / volume_step) * volume_step
    else:
        logger.warning(f"volume_step for {symbol} is {volume_step}. Volume may not be precise.")

    calculated_volume = max(volume_min, calculated_volume)
    calculated_volume = min(volume_max, calculated_volume)

    if calculated_volume < volume_min:
        logger.warning(f"Calculated volume {calculated_volume} is less than min_volume {volume_min} for {symbol}. "
                       f"This might occur if desired_usd_value is too small or price is too high.")
        return 0.0

    calculated_volume = round(calculated_volume, 2)

    if calculated_volume < volume_min:
         logger.warning(f"Volume {calculated_volume} (after rounding) is less than min_volume {volume_min} for {symbol}.")
         return 0.0

    logger.info(f"Calculated lot size for {symbol}: {calculated_volume:.2f} "
                f"(target USD value: {desired_usd_value}, price: {current_price})")
    return calculated_volume

def get_open_pair_positions_count(symbol1, symbol2, magic_number):
    """Checks if there are any open positions for the given pair and magic number."""
    if not mt5_initialized:
        logger.warning("MT5 not initialized. Cannot get open positions count.")
        return -1

    count = 0
    try:
        positions1 = mt5.positions_get(symbol=symbol1, magic=magic_number)
        if positions1 is None:
            if mt5.last_error()[0] != mt5.RES_S_OK_EMPTY:
                 logger.error(f"Failed to get positions for {symbol1}, error: {mt5.last_error()}")
                 return -1
        elif len(positions1) > 0:
            count += len(positions1)

        positions2 = mt5.positions_get(symbol=symbol2, magic=magic_number)
        if positions2 is None:
            if mt5.last_error()[0] != mt5.RES_S_OK_EMPTY:
                logger.error(f"Failed to get positions for {symbol2}, error: {mt5.last_error()}")
                return -1
        elif len(positions2) > 0:
            count += len(positions2)

    except Exception as e:
        logger.error(f"Exception in get_open_pair_positions_count: {e}", exc_info=True)
        return -1
    return count

def open_pair_position(symbol1, order_type1, volume1,
                       symbol2, order_type2, volume2,
                       stop_loss_pips, take_profit_pips, magic_number):
    """Opens two positions for a pair trade."""
    if not mt5_initialized:
        logger.warning("MT5 not initialized. Cannot open pair position.")
        return False

    if volume1 <= 0 or volume2 <= 0:
        logger.warning(f"Invalid volumes for opening pair position: {symbol1} vol={volume1}, {symbol2} vol={volume2}")
        return False

    legs_opened_successfully = 0
    for i, (symbol, order_type, volume) in enumerate([(symbol1, order_type1, volume1),
                                                      (symbol2, order_type2, volume2)]):
        price_info = mt5.symbol_info_tick(symbol)
        if price_info is None:
            logger.error(f"Failed to get price info for {symbol}, error: {mt5.last_error()}")
            continue

        price = 0
        sl_price = 0
        tp_price = 0
        point = mt5.symbol_info(symbol).point

        if order_type == mt5.ORDER_TYPE_BUY:
            price = price_info.ask
            sl_price = price - stop_loss_pips * point if stop_loss_pips > 0 else 0.0
            tp_price = price + take_profit_pips * point if take_profit_pips > 0 else 0.0
        elif order_type == mt5.ORDER_TYPE_SELL:
            price = price_info.bid
            sl_price = price + stop_loss_pips * point if stop_loss_pips > 0 else 0.0
            tp_price = price - take_profit_pips * point if take_profit_pips > 0 else 0.0
        else:
            logger.error(f"Invalid order type {order_type} for {symbol}")
            continue

        if stop_loss_pips <= 0: sl_price = 0.0
        if take_profit_pips <= 0: tp_price = 0.0

        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": float(volume),
            "type": order_type, "price": price,
            "sl": round(sl_price, 5 if "JPY" not in symbol else 3),
            "tp": round(tp_price, 5 if "JPY" not in symbol else 3),
            "deviation": config.PRICE_DEVIATION, "magic": magic_number,
            "comment": f"PairTrade Leg {i+1} {'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'}",
            "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
        }

        logger.info(f"Attempting to open leg {i+1}: {request['comment']} {symbol} Vol:{volume} Price:{price} SL:{sl_price} TP:{tp_price}")
        result = mt5.order_send(request)

        if result is None:
            logger.error(f"Order send failed for {symbol}, MT5 returned None. Error: {mt5.last_error()}")
        elif result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order send failed for {symbol}, retcode: {result.retcode} - {result.comment} (MT5 error: {mt5.last_error()})")
        else:
            logger.info(f"Order sent successfully for {symbol}, order ID: {result.order}")
            legs_opened_successfully +=1

    if legs_opened_successfully == 2:
        logger.info("Both legs of the pair trade were sent successfully.")
        return True
    else:
        logger.warning(f"Failed to send one or both legs of the pair trade. Successes: {legs_opened_successfully}/2.")
        return False

def close_positions_for_pair(symbol1, symbol2, magic_number, comment="Close PairTrade"):
    """Closes all open positions for the given symbols and magic number."""
    if not mt5_initialized:
        logger.warning("MT5 not initialized. Cannot close positions.")
        return False

    closed_successfully_count = 0
    positions_found_count = 0

    for symbol in [symbol1, symbol2]:
        positions = mt5.positions_get(symbol=symbol, magic=magic_number)

        if positions is None:
            if mt5.last_error()[0] != mt5.RES_S_OK_EMPTY:
                logger.error(f"Failed to get positions for {symbol} to close, error: {mt5.last_error()}")
            continue

        if len(positions) == 0:
            continue

        positions_found_count += len(positions)

        for pos in positions:
            order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price_info = mt5.symbol_info_tick(symbol)

            if price_info is None:
                logger.error(f"Failed to get price info for {symbol} to close position {pos.ticket}, error: {mt5.last_error()}")
                continue

            price = price_info.bid if order_type == mt5.ORDER_TYPE_SELL else price_info.ask

            request = {
                "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": pos.volume,
                "type": order_type, "position": pos.ticket, "price": price,
                "deviation": config.PRICE_DEVIATION, "magic": magic_number,
                "comment": comment, "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            logger.info(f"Attempting to close position ticket {pos.ticket} for {symbol} ({'SELL' if order_type == mt5.ORDER_TYPE_SELL else 'BUY'} {pos.volume} @ {price})")
            result = mt5.order_send(request)

            if result is None:
                logger.error(f"Close order send failed for ticket {pos.ticket} ({symbol}), MT5 returned None. Error: {mt5.last_error()}")
            elif result.retcode != mt5.TRADE_RETCODE_DONE:
                logger.error(f"Close order send failed for ticket {pos.ticket} ({symbol}), retcode: {result.retcode} - {result.comment}")
            else:
                logger.info(f"Close order sent successfully for ticket {pos.ticket} ({symbol}), order ID: {result.order}")
                closed_successfully_count +=1

    if positions_found_count == 0:
        logger.info(f"No open positions found for pair {symbol1}-{symbol2} with magic {magic_number} to close.")
        return True

    logger.info(f"Attempted to close {closed_successfully_count}/{positions_found_count} positions for pair {symbol1}-{symbol2}.")
    return True

def Deinit():
    """Shuts down the MetaTrader 5 connection."""
    global mt5_initialized
    if mt5_initialized:
        mt5.shutdown()
        logger.info("MetaTrader 5 shutdown.")
        mt5_initialized = False
    return

def Loop():
    """Main trading loop for the cointegration strategy."""
    if not mt5_initialized:
        logger.error("MT5 not initialized. Cannot proceed with loop.")
        return False

    logger.info(f"Loop iteration started at {time.strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        open_positions_count = get_open_pair_positions_count(config.SYMBOL_1, config.SYMBOL_2, config.MAGIC)
        if open_positions_count == -1:
            logger.warning("Error getting open positions count. Skipping this cycle.")
            return True

        logger.info(f"Currently {open_positions_count} leg(s) open for pair {config.SYMBOL_1}-{config.SYMBOL_2} with magic {config.MAGIC}.")

        series1 = get_historical_data(config.SYMBOL_1, config.COINTEGRATION_TIMEFRAME, config.COINTEGRATION_LOOKBACK_PERIOD)
        series2 = get_historical_data(config.SYMBOL_2, config.COINTEGRATION_TIMEFRAME, config.COINTEGRATION_LOOKBACK_PERIOD)

        if series1 is None or series2 is None:
            logger.warning("Failed to fetch historical data for one or both symbols. Skipping this cycle.")
            return True

        if len(series1) < config.COINTEGRATION_LOOKBACK_PERIOD or len(series2) < config.COINTEGRATION_LOOKBACK_PERIOD:
            logger.warning(f"Not enough historical data. S1 got {len(series1)}, S2 got {len(series2)}. Need {config.COINTEGRATION_LOOKBACK_PERIOD}. Skipping cycle.")
            return True

        aligned_s1, aligned_s2 = series1.align(series2, join='inner')
        if len(aligned_s1) < config.COINTEGRATION_LOOKBACK_PERIOD * 0.8:
            logger.warning(f"Not enough aligned data points ({len(aligned_s1)}). Skipping cycle.")
            return True

        is_cointegrated, historical_spread, hedge_ratio = check_cointegration(aligned_s1, aligned_s2)

        if historical_spread is None:
             logger.warning("Error occurred during cointegration check. Skipping cycle.")
             return True

        if is_cointegrated:
            logger.info(f"Symbols {config.SYMBOL_1} and {config.SYMBOL_2} are cointegrated. Hedge Ratio: {hedge_ratio:.4f}")

            spread_mean = historical_spread.mean()
            spread_std_dev = historical_spread.std()

            if spread_std_dev == 0:
                logger.warning("Spread standard deviation is zero. Cannot calculate z-score. Skipping cycle.")
                return True

            tick1 = mt5.symbol_info_tick(config.SYMBOL_1)
            tick2 = mt5.symbol_info_tick(config.SYMBOL_2)

            if tick1 is None or tick2 is None:
                logger.warning("Failed to get current ticks for spread calculation. Skipping cycle.")
                return True

            current_price1 = (tick1.bid + tick1.ask) / 2
            current_price2 = (tick2.bid + tick2.ask) / 2
            current_spread = current_price1 - hedge_ratio * current_price2
            current_zscore = (current_spread - spread_mean) / spread_std_dev

            logger.info(f"Spread: Current={current_spread:.5f}, Mean={spread_mean:.5f}, StdDev={spread_std_dev:.5f}, Z-Score={current_zscore:.2f}")

            entry_threshold_long_spread = config.SPREAD_ENTRY_STD_DEV_THRESHOLD
            entry_threshold_short_spread = -config.SPREAD_ENTRY_STD_DEV_THRESHOLD
            exit_threshold_long_spread = config.SPREAD_EXIT_STD_DEV_THRESHOLD
            exit_threshold_short_spread = -config.SPREAD_EXIT_STD_DEV_THRESHOLD
            extreme_sl_threshold_long = config.EXTREME_SPREAD_STD_DEV_THRESHOLD
            extreme_sl_threshold_short = -config.EXTREME_SPREAD_STD_DEV_THRESHOLD

            if open_positions_count == 0:
                if current_zscore > entry_threshold_long_spread:
                    logger.info(f"ENTRY SIGNAL: Z-score ({current_zscore:.2f}) > {entry_threshold_long_spread}. Planning to SELL SPREAD (SELL {config.SYMBOL_1}, BUY {config.SYMBOL_2}).")
                    lot1 = calculate_lot_size(config.SYMBOL_1, config.DESIRED_USD_VALUE_PER_LEG, tick1.bid)
                    lot2 = calculate_lot_size(config.SYMBOL_2, config.DESIRED_USD_VALUE_PER_LEG * abs(hedge_ratio), tick2.ask)

                    if lot1 > 0 and lot2 > 0:
                        open_pair_position(
                            config.SYMBOL_1, mt5.ORDER_TYPE_SELL, lot1,
                            config.SYMBOL_2, mt5.ORDER_TYPE_BUY, lot2,
                            config.STOP_LOSS_PIPS, config.TAKE_PROFIT_PIPS,
                            config.MAGIC
                        )
                    else:
                        logger.warning(f"Lot calculation failed. Lot1: {lot1}, Lot2: {lot2}. No trade placed.")

                elif current_zscore < entry_threshold_short_spread:
                    logger.info(f"ENTRY SIGNAL: Z-score ({current_zscore:.2f}) < {entry_threshold_short_spread}. Planning to BUY SPREAD (BUY {config.SYMBOL_1}, SELL {config.SYMBOL_2}).")
                    lot1 = calculate_lot_size(config.SYMBOL_1, config.DESIRED_USD_VALUE_PER_LEG, tick1.ask)
                    lot2 = calculate_lot_size(config.SYMBOL_2, config.DESIRED_USD_VALUE_PER_LEG * abs(hedge_ratio), tick2.bid)

                    if lot1 > 0 and lot2 > 0:
                        open_pair_position(
                            config.SYMBOL_1, mt5.ORDER_TYPE_BUY, lot1,
                            config.SYMBOL_2, mt5.ORDER_TYPE_SELL, lot2,
                            config.STOP_LOSS_PIPS, config.TAKE_PROFIT_PIPS,
                            config.MAGIC
                        )
                    else:
                        logger.warning(f"Lot calculation failed. Lot1: {lot1}, Lot2: {lot2}. No trade placed.")
                else:
                    logger.info("No entry signal based on Z-score.")

            elif open_positions_count > 0:
                if (current_zscore < exit_threshold_long_spread and current_zscore > exit_threshold_short_spread):
                     logger.info(f"EXIT SIGNAL: Z-score ({current_zscore:.2f}) has reverted towards mean. Closing pair trade.")
                     close_positions_for_pair(config.SYMBOL_1, config.SYMBOL_2, config.MAGIC, comment="PairTrade Exit Reversion")

                elif current_zscore > extreme_sl_threshold_long or current_zscore < extreme_sl_threshold_short:
                    logger.warning(f"EXTREME SPREAD SL: Z-score ({current_zscore:.2f}) exceeded extreme threshold "
                                   f"({extreme_sl_threshold_short} / {extreme_sl_threshold_long}). Closing pair trade.")
                    close_positions_for_pair(config.SYMBOL_1, config.SYMBOL_2, config.MAGIC, comment="PairTrade Extreme Spread SL")
                else:
                    logger.info(f"Positions open. Z-score ({current_zscore:.2f}) not meeting exit or SL criteria. Holding.")

        else:
            logger.info(f"Symbols {config.SYMBOL_1} and {config.SYMBOL_2} are NOT currently cointegrated based on lookback period.")
            if open_positions_count > 0:
                logger.warning("WARNING: Positions are open but symbols no longer appear cointegrated. Consider manual review or forced close.")

    except Exception as e:
        logger.error(f"An error occurred in the main loop: {e}", exc_info=True)

    logger.info("Loop iteration finished. Waiting for next cycle...")
    return True

def main():
    """Main function to run the bot."""
    if Init():
        try:
            while Loop():
                time.sleep(config.CYCLE_TIME)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (KeyboardInterrupt).")
        finally:
            Deinit()
    else:
        logger.error("Failed to initialize the bot. Exiting.")
    logger.info("Bot has finished execution.")

if __name__ == '__main__':
    main()

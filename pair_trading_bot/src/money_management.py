import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def calculate_position_size(account_balance, risk_percentage, stop_loss_pips, pips_per_unit, price_per_pip_leg1, price_per_pip_leg2=0, is_spread_trade=False):
    """
    Calculates the position size for a trade.

    Parameters:
    - account_balance (float): Current account balance.
    - risk_percentage (float): Desired risk per trade (e.g., 0.01 for 1%).
    - stop_loss_pips (float): Stop-loss distance in pips for the trade/instrument.
    - pips_per_unit (float): The value of 1 pip movement for 1 unit of the instrument
                             (e.g., for EURUSD, 1 lot = 100,000 units, pip value might be $10 for 1 pip if 1 lot is traded).
                             This needs to be carefully determined based on the instrument's contract size and quote currency.
                             For pairs trading, this can be complex. We might simplify or use a combined risk.
    - price_per_pip_leg1 (float): The value of one pip for one standard unit (e.g. 1 lot) of the first leg.
    - price_per_pip_leg2 (float, optional): The value of one pip for one standard unit of the second leg. Required if is_spread_trade is True.
    - is_spread_trade (bool): If True, assumes stop_loss_pips applies to the spread and risk is distributed.
                              This is a simplified model; true pair trading position sizing can be complex.

    Returns:
    - float: The calculated position size (e.g., in lots or units).
    """
    if account_balance <= 0 or risk_percentage <= 0 or stop_loss_pips <= 0:
        logging.warning("Account balance, risk percentage, and stop loss pips must be positive.")
        return 0.0

    risk_amount = account_balance * risk_percentage

    if is_spread_trade:
        # Simplified: Assume stop loss pips is on the spread value itself.
        # Risk per pip for the spread needs to be estimated.
        # This is a challenging part for pairs trading as pip values for the spread are not direct.
        # For simplicity, let's assume the stop_loss_pips is for the primary leg or a combined entity.
        # A more advanced model would consider the volatility and correlation of the two legs.
        # Here, we assume price_per_pip_leg1 represents the risk of the combined position per pip.
        # This is a placeholder for a more sophisticated calculation.
        if price_per_pip_leg1 <= 0:
            logging.warning("Price per pip for leg1 must be positive for spread trade sizing.")
            return 0.0
        total_risk_per_pip = price_per_pip_leg1 # Simplified: This would be more complex in reality

        # If we consider both legs, a simple sum might be too conservative or too aggressive.
        # For now, we will base it on leg1's pip value as a proxy or combined value.
        # A better approach might involve calculating the dollar volatility of the spread.
        # For now, let's assume the provided price_per_pip_leg1 is for the 'net' spread risk per pip.

    else: # Single instrument trade
        if price_per_pip_leg1 <= 0:
            logging.warning("Price per pip must be positive for position sizing.")
            return 0.0
        total_risk_per_pip = price_per_pip_leg1

    if total_risk_per_pip == 0: # Should be caught by price_per_pip_leg1 <= 0
        logging.warning("Total risk per pip is zero, cannot calculate position size.")
        return 0.0

    # Position size = Risk Amount / (Stop Loss Pips * Value per Pip per Unit)
    # This formula assumes 'pips_per_unit' is the value of 1 pip for 1 unit of the instrument.
    # More commonly, brokers provide pip value per lot.
    # Let's redefine price_per_pip_leg1 as "dollar value of 1 pip movement for 1 lot"

    # Risk Amount / (Stop Loss Pips * Dollar Value of 1 Pip for 1 Lot) = Size in Lots
    position_size_lots = risk_amount / (stop_loss_pips * total_risk_per_pip)

    logging.info(f"Calculated position size: {position_size_lots:.2f} lots. "
                 f"Account: {account_balance}, Risk %: {risk_percentage*100}%, "
                 f"SL pips: {stop_loss_pips}, Risk per pip (1 lot): {total_risk_per_pip}")

    # Ensure minimum position size if applicable (e.g. 0.01 lots) - broker specific
    # For now, just return the calculated size. Broker interaction layer would handle rounding/min/max.
    return round(position_size_lots, 2) # Standard rounding for lots

def calculate_stop_loss_take_profit(entry_price, z_score, mean_spread, std_spread, stop_loss_z_multiplier, take_profit_z_target, is_long_spread):
    """
    Calculates stop-loss and take-profit levels for a spread trade based on z-score.

    Parameters:
    - entry_price (float): The price (spread value) at which the trade was entered.
    - z_score (float): The current z-score of the spread. (Can be entry z-score)
    - mean_spread (float): The mean of the spread.
    - std_spread (float): The standard deviation of the spread.
    - stop_loss_z_multiplier (float): Multiplier for std_spread to set stop-loss beyond entry z_score
                                      (e.g., if z_score entry is 2, SL could be at 3 or -1 if mean reverting).
                                      This needs careful definition. Let's assume it's an absolute Z level.
    - take_profit_z_target (float): The z-score level at which to take profit (e.g., 0 for mean reversion).
    - is_long_spread (bool): True if the trade is long the spread (buy series1, sell series2), False otherwise.

    Returns:
    - tuple: (stop_loss_price, take_profit_price)
    """
    if std_spread == 0:
        logging.warning("Spread standard deviation is zero. Cannot calculate SL/TP based on Z-score levels.")
        # Fallback: could be a fixed pip SL/TP, but this function focuses on Z-score based.
        # For now, returning entry_price, implying no Z-based SL/TP can be set.
        return entry_price, entry_price

    # Stop Loss: Set at a Z-score level that indicates the trade is likely wrong.
    # If long spread (expecting z-score to decrease towards mean from positive, or increase from negative)
    # If short spread (expecting z-score to increase towards mean from negative, or decrease from positive)

    # Let's define stop_loss_z_multiplier as an absolute Z-score level for SL.
    # Example: If entry is at Z=2 (long spread), SL could be at Z=3.
    # If entry is at Z=-2 (short spread), SL could be at Z=-3.

    # Alternative: SL is a fixed distance in Z-score units from entry Z
    # e.g., stop_loss_z_distance = 1.0. If entry_z = 2.0 (long), SL_z = 3.0. If entry_z = -2.0 (short), SL_z = -3.0

    # Let's use the absolute Z level for stop_loss_z_multiplier for clarity.
    # E.g. if stop_loss_z_multiplier is 3.0:
    if is_long_spread: # Entered when spread was low (negative Z), expecting it to rise. Or entered high Z, expecting mean reversion (sell spread)
        # This logic depends on how "long spread" is defined.
        # Assume: Long spread = buy S1, sell S2. Entered when spread was "cheap" (e.g. Z < -threshold_entry)
        # OR Long spread = sell S1, buy S2. Entered when spread was "dear" (e.g. Z > threshold_entry) - this is effectively shorting the spread.
        # Let's assume:
        # is_long_spread = True means we bought the spread (e.g. S1 - ratio*S2) because Z was low (e.g. -2.0)
        # We expect Z to rise towards 0 (TP) or further positive. SL if Z falls further (e.g. to -3.0).
        # is_long_spread = False means we sold the spread because Z was high (e.g. +2.0)
        # We expect Z to fall towards 0 (TP) or further negative. SL if Z rises further (e.g. to +3.0).

        if z_score < 0: # Entered long spread at negative Z
            stop_loss_z = -abs(stop_loss_z_multiplier)
        else: # Entered short spread at positive Z (is_long_spread = False)
            stop_loss_z = abs(stop_loss_z_multiplier)
    else: # Shorting the spread
        if z_score > 0: # Entered short spread at positive Z
            stop_loss_z = abs(stop_loss_z_multiplier)
        else: # Entered long spread at negative Z (is_long_spread = True)
            stop_loss_z = -abs(stop_loss_z_multiplier)

    # Ensure SL is further away from mean than entry Z, in the adverse direction.
    if is_long_spread: # Expecting Z to increase
        # If entered at Z=-2, SL_Z should be < -2 (e.g. -3).
        # If entered at Z=2 (this case is selling spread, so is_long_spread=False)
        actual_stop_loss_z = min(z_score - 0.5, -abs(stop_loss_z_multiplier)) if z_score < 0 else max(z_score + 0.5, abs(stop_loss_z_multiplier))
        if z_score < take_profit_z_target: # e.g. z_score = -2, tp_target = 0. SL should be more negative.
             actual_stop_loss_z = -abs(stop_loss_z_multiplier)
        else: # This case (z_score > take_profit_z_target while is_long_spread) is ambiguous for typical pair trading.
              # Assuming if is_long_spread, we entered because z < target (e.g. z=-2, target=0)
              # Or if is_long_spread means we are betting on divergence (z keeps increasing from positive)
              # For classic mean reversion:
              # If long spread (entered at low Z, e.g. -2), SL is Z = -3, TP is Z = 0
              # If short spread (entered at high Z, e.g. +2), SL is Z = +3, TP is Z = 0
            actual_stop_loss_z = -abs(stop_loss_z_multiplier) # Default if logic is unclear for this scenario

    else: # Short spread, expecting Z to decrease
        actual_stop_loss_z = max(z_score + 0.5, abs(stop_loss_z_multiplier)) if z_score > 0 else min(z_score - 0.5, -abs(stop_loss_z_multiplier))
        if z_score > take_profit_z_target: # e.g. z_score = 2, tp_target = 0. SL should be more positive.
            actual_stop_loss_z = abs(stop_loss_z_multiplier)
        else:
            actual_stop_loss_z = abs(stop_loss_z_multiplier) # Default

    # Refined SL logic:
    # If long spread (entered on low Z, e.g., Z < -entry_z_thresh, betting on Z increasing to `take_profit_z_target` (e.g. 0 or -0.5)):
    #   Stop loss if Z goes even lower (e.g., Z < -stop_loss_z_level).
    # If short spread (entered on high Z, e.g., Z > entry_z_thresh, betting on Z decreasing to `take_profit_z_target` (e.g. 0 or 0.5)):
    #   Stop loss if Z goes even higher (e.g., Z > stop_loss_z_level).

    if is_long_spread: # Expecting Z to rise
        sl_z_level = -abs(stop_loss_z_multiplier) # e.g. -3.0
        tp_z_level = take_profit_z_target       # e.g. 0.0 or -0.5
    else: # Expecting Z to fall
        sl_z_level = abs(stop_loss_z_multiplier)  # e.g. 3.0
        tp_z_level = take_profit_z_target       # e.g. 0.0 or 0.5

    stop_loss_price = mean_spread + sl_z_level * std_spread
    take_profit_price = mean_spread + tp_z_level * std_spread

    logging.info(f"Calculated SL/TP. Entry Z: {z_score:.2f}, Is Long: {is_long_spread}")
    logging.info(f"SL Z-level: {sl_z_level:.2f} -> SL Price: {stop_loss_price:.5f}")
    logging.info(f"TP Z-level: {tp_z_level:.2f} -> TP Price: {take_profit_price:.5f}")

    return stop_loss_price, take_profit_price


if __name__ == '__main__':
    logging.info("--- Testing Money Management ---")

    acc_balance = 10000
    risk_perc = 0.01 # 1%
    sl_pips = 50 # Stop loss in pips for the instrument/spread

    # For a single instrument like EURUSD, 1 pip for 1 lot (100,000 units) is often $10
    # This is context-dependent (quote currency, pair)
    price_per_pip_one_lot_eurusd = 10.0

    logging.info("\n--- Test 1: Position Sizing (Single Instrument) ---")
    position_size_eurusd = calculate_position_size(
        account_balance=acc_balance,
        risk_percentage=risk_perc,
        stop_loss_pips=sl_pips,
        pips_per_unit=0, # Not used in this version, relying on price_per_pip_leg1 for lot value
        price_per_pip_leg1=price_per_pip_one_lot_eurusd
    )
    logging.info(f"EURUSD Position Size for SL {sl_pips} pips, {risk_perc*100}% risk: {position_size_eurusd} lots")

    logging.info("\n--- Test 2: Position Sizing (Spread Trade - Simplified) ---")
    # Assuming 'price_per_pip_leg1' now represents the net pip value of the spread for 1 unit of spread trade
    # This is a major simplification.
    price_per_pip_one_unit_spread = 12.0 # Hypothetical value for 1 unit of spread trade
    position_size_spread = calculate_position_size(
        account_balance=acc_balance,
        risk_percentage=risk_perc,
        stop_loss_pips=sl_pips, # Assuming SL pips is on the spread value
        pips_per_unit=0,
        price_per_pip_leg1=price_per_pip_one_unit_spread, # Pip value for 1 lot of the "spread instrument"
        is_spread_trade=True
    )
    logging.info(f"Spread Position Size for SL {sl_pips} pips, {risk_perc*100}% risk: {position_size_spread} lots/units")


    logging.info("\n--- Test 3: SL/TP Calculation ---")
    entry_spread_price = 10.5
    current_z = -2.0 # Entered when Z-score was -2.0 (longing the spread)
    spread_mean = 12.0
    spread_std_dev = 1.0 # Makes Z = (Price - Mean) / StdDev -> Price = Mean + Z * StdDev
                         # Entry Price 10.0 = 12.0 + (-2.0) * 1.0 -- this seems off.
                         # Let's adjust: Entry Z = (Entry Price - Mean) / StdDev
                         # -2.0 = (10.5 - 12.0) / StdDev => -2.0 = -1.5 / StdDev => StdDev = 0.75
    spread_std_dev_adj = 0.75

    # We are long the spread (bought S1, sold S2, or bought the spread instrument)
    # expecting the spread value (and Z-score) to rise.
    # Entry Z = -2.0. Target Z for TP = 0.0. Stop Loss Z = -3.0.

    sl_z_multiplier_config = 3.0 # Absolute Z-level for SL (e.g., -3.0 if long, +3.0 if short)
    tp_z_target_config = 0.0   # Target Z for mean reversion

    logging.info("Scenario: Long Spread (entered at Z=-2.0, expecting Z to rise to 0.0)")
    sl_price_long, tp_price_long = calculate_stop_loss_take_profit(
        entry_price=entry_spread_price, # Spread value at entry
        z_score=current_z, # Z-score at entry
        mean_spread=spread_mean,
        std_spread=spread_std_dev_adj,
        stop_loss_z_multiplier=sl_z_multiplier_config, # SL if Z reaches -3.0
        take_profit_z_target=tp_z_target_config,       # TP if Z reaches 0.0
        is_long_spread=True
    )
    # Expected SL price: 12.0 + (-3.0 * 0.75) = 12.0 - 2.25 = 9.75
    # Expected TP price: 12.0 + (0.0 * 0.75) = 12.0
    logging.info(f"Long Spread: Entry Price={entry_spread_price}, SL Price={sl_price_long:.4f}, TP Price={tp_price_long:.4f}")

    logging.info("Scenario: Short Spread (entered at Z=2.0, expecting Z to fall to 0.0)")
    entry_spread_price_short = 13.5 # Mean 12.0, StdDev 0.75. Z = (13.5-12.0)/0.75 = 1.5/0.75 = 2.0
    current_z_short = 2.0
    sl_price_short, tp_price_short = calculate_stop_loss_take_profit(
        entry_price=entry_spread_price_short,
        z_score=current_z_short,
        mean_spread=spread_mean,
        std_spread=spread_std_dev_adj,
        stop_loss_z_multiplier=sl_z_multiplier_config, # SL if Z reaches +3.0
        take_profit_z_target=tp_z_target_config,       # TP if Z reaches 0.0
        is_long_spread=False
    )
    # Expected SL price: 12.0 + (3.0 * 0.75) = 12.0 + 2.25 = 14.25
    # Expected TP price: 12.0 + (0.0 * 0.75) = 12.0
    logging.info(f"Short Spread: Entry Price={entry_spread_price_short}, SL Price={sl_price_short:.4f}, TP Price={tp_price_short:.4f}")

    logging.info("\n--- Test 4: SL/TP Calculation - Alternative TP target ---")
    # TP if Z reaches -0.5 (for long spread that started at -2.0)
    tp_z_target_alt = -0.5
    logging.info(f"Scenario: Long Spread (Z=-2.0 to {tp_z_target_alt})")
    sl_price_long_alt, tp_price_long_alt = calculate_stop_loss_take_profit(
        entry_price=entry_spread_price,
        z_score=current_z,
        mean_spread=spread_mean,
        std_spread=spread_std_dev_adj,
        stop_loss_z_multiplier=sl_z_multiplier_config,
        take_profit_z_target=tp_z_target_alt,
        is_long_spread=True
    )
    # Expected SL price: 9.75
    # Expected TP price: 12.0 + (-0.5 * 0.75) = 12.0 - 0.375 = 11.625
    logging.info(f"Long Spread (Alt TP): SL Price={sl_price_long_alt:.4f}, TP Price={tp_price_long_alt:.4f}")

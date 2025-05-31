print("MAIN.PY SCRIPT EXECUTION STARTED", flush=True)
import time
import logging
import signal # For graceful shutdown

# Assuming src is in the same parent directory or PYTHONPATH is set up
# If running from pair_trading_bot directory, `from src.trading_bot import PairTradingBot`
# If running from parent of pair_trading_bot, `from pair_trading_bot.src.trading_bot import PairTradingBot`
# For simplicity, assuming execution from within pair_trading_bot directory or src is discoverable
try:
    from src.trading_bot import PairTradingBot
    from src.utils import download_price_data, mt5 # To potentially pre-test MT5 connection via utils and get mt5 object
except ImportError as e:
    print(f"Import Error: {e}. Ensure you are in the 'pair_trading_bot' directory or your PYTHONPATH is set correctly.")
    print("Attempting to adjust path for common project structures...")
    import sys
    import os
    # Add parent directory of 'pair_trading_bot' to path, assuming 'pair_trading_bot' is a subdir
    # And current file is 'pair_trading_bot/main.py'
    # So, parent of current file's dir is the project root for 'from src...'
    current_dir = os.path.dirname(os.path.abspath(__file__)) # Should be /path/to/pair_trading_bot
    project_root = os.path.dirname(current_dir) # Should be /path/to
    # If 'src' is directly under 'pair_trading_bot'
    sys.path.insert(0, current_dir) # Add 'pair_trading_bot' to path to find 'src'

    # Try imports again
    from src.trading_bot import PairTradingBot
    from src.utils import download_price_data, mt5


# Configure basic logging for the main application
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger("main")

# Global variable to control the main loop
running = True

def shutdown_handler(signum, frame):
    """Handles shutdown signals for graceful exit."""
    global running
    logger.info(f"Shutdown signal received ({signal.Signals(signum).name}). Terminating bot...")
    running = False

# Register signal handlers for SIGINT (Ctrl+C) and SIGTERM
signal.signal(signal.SIGINT, shutdown_handler)
signal.signal(signal.SIGTERM, shutdown_handler)

def main():
    global running
    logger.info("--- Starting Pair Trading Bot Application ---")

    # Configuration (ideally from a config file or environment variables)
    # Ensure these pip values are accurate for your broker and account currency.
    # These are placeholders.
    # For AUDCAD/NZDCAD, if account is in USD, 1 pip for 1 lot might be around 7-8 USD.
    config = {
        "symbol1": "AUDCAD",  # Primary symbol
        "symbol2": "NZDCAD",  # Cointegrated symbol
        "timeframe": "H1",    # Timeframe for analysis
        "lookback_period": 100, # Candles for coint/z-score
        "entry_z_threshold": 2.0,
        "exit_z_threshold": 0.5, # Target for mean reversion
        "stop_loss_z_multiplier": 3.0, # Absolute Z-level for SL
        "account_balance": 10000, # Initial virtual balance
        "risk_percentage": 0.01,  # 1% risk per trade
        "pip_value_leg1": 7.50,   # Approx. value of 1 pip for 1 lot of symbol1 (e.g., AUDCAD in USD)
        "pip_value_leg2": 7.20,   # Approx. value of 1 pip for 1 lot of symbol2 (e.g., NZDCAD in USD)
                                  # Note: pip_value_leg1 is used as proxy for spread pip value in bot's current simple sizing.
        "run_interval_seconds": 5 # TEMP: Reduced for testing. Original: 300
    }

    logger.info(f"Configuration: {config}")

    # Initialize the bot
    bot = None
    try:
        bot = PairTradingBot(
            symbol1=config["symbol1"],
            symbol2=config["symbol2"],
            timeframe=config["timeframe"],
            lookback_period=config["lookback_period"],
            entry_z_threshold=config["entry_z_threshold"],
            exit_z_threshold=config["exit_z_threshold"],
            stop_loss_z_multiplier=config["stop_loss_z_multiplier"],
            account_balance=config["account_balance"],
            risk_percentage=config["risk_percentage"],
            pip_value_leg1=config["pip_value_leg1"],
            pip_value_leg2=config["pip_value_leg2"],
            min_trade_interval_seconds=config["run_interval_seconds"] / 2 # Avoid rapid trades
        )
        logger.info("PairTradingBot initialized successfully.")

        # Optional: Test MT5 connection here if needed, or rely on bot's internal check
        # if not bot.is_mt5_initialized:
        #    logger.warning("MT5 connection could not be established by the bot during init. Bot may run in simulation mode or fail on live actions.")

    except Exception as e:
        logger.exception("Failed to initialize PairTradingBot. Exiting.")
        return

    # Main loop
    logger.info("Starting main trading loop... Press Ctrl+C to stop.")
    cycle_count = 0
    while running:
        cycle_count += 1
        logger.info(f"--- Main Loop: Starting cycle {cycle_count} ---")
        try:
            bot.run_check()
            logger.info(f"--- Main Loop: bot.run_check() completed for cycle {cycle_count} ---")

            # Wait for the next interval
            # Check running flag frequently if interval is long
            logger.info(f"--- Main Loop: Entering sleep for {config['run_interval_seconds']} seconds (cycle {cycle_count}) ---")
            for i in range(config["run_interval_seconds"]):
                if not running:
                    logger.info(f"--- Main Loop: Shutdown signal detected during sleep (cycle {cycle_count}, iteration {i+1}) ---")
                    break
                time.sleep(1)
            logger.info(f"--- Main Loop: Sleep completed (cycle {cycle_count}) ---")

        except KeyboardInterrupt: # Should be caught by signal handler, but as a fallback
            logger.info("KeyboardInterrupt caught in main loop. Shutting down...")
            running = False
        except Exception as e:
            logger.exception("An error occurred in the main trading loop. Continuing...")
            # Potentially add a longer sleep here to prevent rapid error loops
            time.sleep(config["run_interval_seconds"])

    # Cleanup
    if bot:
        logger.info("Shutting down bot resources...")
        bot.shutdown_mt5() # Ensure MT5 connection is closed

    logger.info("--- Pair Trading Bot Application Terminated ---")

if __name__ == "__main__":
    # This structure helps if pair_trading_bot is a package and main.py is run as a script
    # For example, python -m pair_trading_bot.main if structure supports it
    # Or simply python pair_trading_bot/main.py

    # Simple check for mock MT5 availability from utils
    # This is just for quick feedback during development if MT5 is the mock.
    try:
        if mt5.initialize(): # Try to init
            if mt5.terminal_info() is None : # A characteristic of the current mock
                 logger.info("MetaTrader5 mock appears to be active (based on terminal_info).")
            mt5.shutdown()
        else:
            logger.warning("MetaTrader5 failed to initialize via utils.download_price_data's mt5 instance.")
    except Exception as e:
        logger.info(f"MT5 check generated an exception (likely using mock): {e}")

    main()

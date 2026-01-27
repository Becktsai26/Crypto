from src.monitor.ws_manager import BybitMonitor
from src.utils.logger import log
from src.config import settings
import time
import threading

def run_account_monitor(account_config):
    """
    Runs the monitor for a specific account with a persistent restart loop.
    """
    name = account_config["name"]
    api_key = account_config["api_key"]
    api_secret = account_config["api_secret"]

    log.info(f"--- Initializing Monitor for Account: {name} ---")

    while True:
        try:
            # Initialize Monitor (WebSocket + Sync + Webhook)
            monitor = BybitMonitor(
                api_key=api_key,
                api_secret=api_secret,
                account_name=name
            )
            monitor.start()
        except KeyboardInterrupt:
            log.info(f"Monitor [{name}] stopped by user.")
            break
        except Exception as e:
            log.error(f"Monitor [{name}] crashed: {e}")
            log.info(f"Restarting monitor [{name}] in 5 seconds...")
            time.sleep(5)

def start_monitor():
    log.info("--- Starting Multi-Account Bybit Monitor ---")

    accounts = settings.get("bybit_accounts", [])
    threads = []

    for acc in accounts:
        t = threading.Thread(target=run_account_monitor, args=(acc,), daemon=False)
        t.start()
        threads.append(t)
        log.info(f"Started thread for account: {acc['name']}")

    # Keep main thread alive (though threads are not daemon, so this isn't strictly necessary,
    # but good for catching KeyboardInterrupt at the top level to shut everything down gracefully-ish)
    try:
        for t in threads:
            t.join()
    except KeyboardInterrupt:
        log.info("Global shutdown signal received.")

if __name__ == "__main__":
    start_monitor()

from src.monitor.ws_manager import BybitMonitor
from src.utils.logger import log
import time

def start_monitor():
    log.info("--- Starting Bybit Real-time Monitor ---")
    
    while True:
        try:
            # Initialize Monitor (WebSocket + Sync + Webhook)
            monitor = BybitMonitor()
            monitor.start()
        except KeyboardInterrupt:
            log.info("Monitor stopped by user.")
            break
        except Exception as e:
            log.error(f"Monitor crashed: {e}")
            log.info("Restarting monitor in 5 seconds...")
            time.sleep(5) # Prevent tight loop on crash

if __name__ == "__main__":
    start_monitor()

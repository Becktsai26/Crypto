from src.monitor.ws_manager import BybitMonitor
from src.utils.logger import log
import time

def start_monitor():
    log.info("--- Starting Bybit Real-time Monitor ---")
    
    # Initialize Monitor (WebSocket + Sync + Webhook)
    monitor = BybitMonitor()
    
    try:
        monitor.start()
    except KeyboardInterrupt:
        log.info("Monitor stopped by user.")
    except Exception as e:
        log.error(f"Monitor crashed: {e}")
        time.sleep(5) # Prevent tight loop on crash

if __name__ == "__main__":
    start_monitor()

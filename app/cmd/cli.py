import time
import argparse
import sys
from app.config.settings import settings
from app.config.logging import logger
from app.services.syncer import SyncService

def run_sync_loop():
    """持續運行的監控迴圈 (用於 Docker)"""
    service = SyncService()
    interval = settings.SYNC_INTERVAL_SECONDS
    
    logger.info(f"Starting sync loop. Interval: {interval} seconds")
    
    while True:
        try:
            service.run_full_sync()
        except Exception as e:
            logger.error(f"Error during sync cycle: {e}")
        
        logger.info(f"Sleeping for {interval} seconds...")
        time.sleep(interval)

def main():
    parser = argparse.ArgumentParser(description="Crypto Sync CLI")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: sync (只跑一次)
    sync_parser = subparsers.add_parser("sync", help="Run a single sync operation")
    
    # Command: monitor (持續跑)
    monitor_parser = subparsers.add_parser("monitor", help="Run in continuous monitor mode")
    
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "sync":
        logger.info("Running single sync...")
        SyncService().run_full_sync()
    
    elif args.command == "monitor":
        run_sync_loop()

if __name__ == "__main__":
    main()

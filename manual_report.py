import argparse
from src.adapters.bybit import BybitAdapter
from src.services.stats import StatsService
from src.monitor.notifier import DiscordNotifier
from src.config import settings
from src.utils.logger import log

def main():
    parser = argparse.ArgumentParser(description='Generate Manual PnL Report')
    parser.add_argument('--days', type=int, help='Number of days for multi-day stats', default=None)
    args = parser.parse_args()

    log.info("--- Generating Manual PnL Report ---")
    
    try:
        # Initialize Dependencies
        api_key = settings["bybit_api_key"]
        api_secret = settings["bybit_api_secret"]
        
        adapter = BybitAdapter(api_key, api_secret)
        stats = StatsService(adapter)
        notifier = DiscordNotifier()
        
        # Fetch Data
        log.info("Fetching account data from Bybit...")
        report_data = stats.get_daily_report_data()
        
        multi_day_stats = None
        if args.days:
            log.info(f"Fetching multi-day stats for {args.days} days...")
            multi_day_stats = stats.get_multi_day_stats(days=args.days)
        
        # Fetch Open Positions for Unrealized PnL
        log.info("Fetching open positions...")
        open_positions = adapter.get_positions(category="linear")
        
        # Send PnL Dashboard (Realized + Unrealized)
        log.info("Sending PnL Dashboard to Discord...")
        notifier.send_pnl_dashboard(report_data, open_positions, multi_day_stats=multi_day_stats)
        
        log.info("Reports sent successfully!")
        
    except Exception as e:
        log.error(f"Failed to generate report: {e}")

if __name__ == "__main__":
    main()

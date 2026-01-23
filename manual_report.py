
from src.adapters.bybit import BybitAdapter
from src.services.stats import StatsService
from src.monitor.notifier import DiscordNotifier
from src.config import settings
from src.utils.logger import log

def main():
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
        
        # Send to Discord (Daily Report)
        log.info("Sending Daily Report to Discord...")
        notifier.send_daily_report(report_data)
        
        # Fetch Last Closed Trade (User Request: "Show recent trade record")
        log.info("Fetching last closed position stats...")
        last_trade = stats.get_last_closed_position_stats()
        
        if last_trade:
             # Construct data similar to execution update for notifier
             # Map Aggregated Record to Notifier format
             pnl = float(last_trade.get("closedPnl", 0))
             trade_data = {
                 "symbol": last_trade.get("symbol"),
                 "side": last_trade.get("side"), # Buy or Sell
                 "execPrice": last_trade.get("avgExitPrice"), 
                 "execQty": last_trade.get("qty")
             }
             
             log.info(f"Sending Last Position Result: {trade_data['symbol']} PnL: {pnl} (Aggregated {last_trade.get('record_count')} fills)")
             notifier.send_order_filled(trade_data, pnl=pnl)
        
        log.info("✅ Reports sent successfully!")
        
    except Exception as e:
        log.error(f"Failed to generate report: {e}")

if __name__ == "__main__":
    main()

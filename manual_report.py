
from datetime import datetime, timedelta
import pandas as pd
from src.adapters.bybit import BybitAdapter
from src.services.stats import StatsService
from src.monitor.notifier import DiscordNotifier
from src.config import settings
from src.utils.logger import log

def generate_fee_stats(adapter, account_name="Main"):
    log.info(f"Calculating Fee Statistics for [{account_name}] (Last 30 Days)...")

    end_time = datetime.now()
    start_time = end_time - timedelta(days=30)

    start_ts = int(start_time.timestamp() * 1000)
    end_ts = int(end_time.timestamp() * 1000)

    # Fetch all transaction logs for the period
    all_transactions = []
    current_start = start_ts
    
    try:
        while current_start < end_ts:
            current_end = min(current_start + (7 * 24 * 60 * 60 * 1000) - 1, end_ts)
            chunk_txs = adapter.fetch_transaction_log(
                account_type="UNIFIED",
                category="linear",
                start_time=int(current_start),
                end_time=int(current_end)
            )
            all_transactions.extend(chunk_txs)
            current_start = current_end + 1

    except Exception as e:
        log.error(f"Failed to fetch transactions for fee stats: {e}")
        return None

    if not all_transactions:
        log.info("No transactions found for fee calculation.")
        return None

    df = pd.DataFrame(all_transactions)

    # Ensure fee is numeric
    if "fee" not in df.columns:
        return None
        
    df["fee"] = pd.to_numeric(df["fee"], errors='coerce').fillna(0.0)

    total_fees = df["fee"].sum()
    funding_fees = df[df["execType"] == "Funding"]["fee"].sum()
    trading_fees = total_fees - funding_fees

    stats = {
        "Total Fees": total_fees,
        "Funding Fees": funding_fees,
        "Trading Fees": trading_fees,
        "Transaction Count": len(df)
    }

    return stats

def main():
    log.info("--- Generating Manual PnL & Fee Report ---")

    accounts = settings.get("bybit_accounts", [])

    for acc in accounts:
        name = acc["name"]
        log.info(f"\n>>> Processing Account: {name} <<<")
        
        try:
            # Initialize Dependencies
            adapter = BybitAdapter(acc["api_key"], acc["api_secret"])
            stats_service = StatsService(adapter)
            notifier = DiscordNotifier()

            # 1. PnL Dashboard
            log.info("Fetching daily PnL data...")
            report_data = stats_service.get_daily_report_data()

            log.info("Fetching open positions...")
            open_positions = adapter.get_positions(category="linear")

            log.info(f"Sending PnL Dashboard for {name} to Discord...")
            # Note: Notifier currently sends to the same webhook.
            # Ideally, we might want to prefix the message with the Account Name,
            # but standard Notifier methods don't take account name.
            # We rely on the console output for now, and the Notifier will send as is.
            notifier.send_pnl_dashboard(report_data, open_positions)

            # 2. Fee Statistics
            fee_stats = generate_fee_stats(adapter, account_name=name)
            if fee_stats:
                print("\n" + "="*40)
                print(f" FEE STATISTICS (Last 30 Days) - {name}")
                print("="*40)
                print(f" Total Fees   : {fee_stats['Total Fees']:.4f} USDT")
                print(f" Trading Fees : {fee_stats['Trading Fees']:.4f} USDT")
                print(f" Funding Fees : {fee_stats['Funding Fees']:.4f} USDT")
                print(f" Transactions : {fee_stats['Transaction Count']}")
                print("="*40 + "\n")

            log.info(f"✅ Reports for {name} completed!")

        except Exception as e:
            log.error(f"Failed to generate report for {name}: {e}")

if __name__ == "__main__":
    main()

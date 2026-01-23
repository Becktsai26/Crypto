# src/services/sync.py
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from ..adapters.base import BaseExchangeAdapter
from ..clients.notion import NotionClient
from ..utils.logger import log

class SyncService:
    """
    Orchestrates the synchronization process between an exchange and Notion.
    """

    def __init__(self, exchange_adapter: BaseExchangeAdapter, notion_client: NotionClient):
        self.exchange = exchange_adapter
        self.notion = notion_client

    def run_sync(self):
        """
        Runs the main synchronization logic with support for multi-window fetching.
        """
        log.info("Starting synchronization process...")
        
        # 1. Determine the time window
        last_sync_ms = self.notion.get_last_sync_timestamp()
        
        # Default start date (e.g., for backfill)
        backfill_start_ms = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
        
        if last_sync_ms:
            # Start from the second after the last sync to avoid duplicates
            start_time_ms = max(last_sync_ms + 1, backfill_start_ms)
            log.info(f"Last sync found at {datetime.fromtimestamp(last_sync_ms/1000, tz=timezone.utc)}. Starting from {datetime.fromtimestamp(start_time_ms/1000, tz=timezone.utc)}")
        else:
            start_time_ms = backfill_start_ms
            log.info(f"No previous sync found. Forcing start date to: {datetime.fromtimestamp(start_time_ms/1000, tz=timezone.utc)}")
        
        end_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 2. Skip subaccount notice for brevity
        log.warning("Note: Syncing main account only.")

        # 3. Fetch data from Bybit in 7-day chunks (API limit)
        all_transactions = []
        current_start = start_time_ms
        
        while current_start < end_time_ms:
            # 7 days max per request
            current_end = min(current_start + (7 * 24 * 60 * 60 * 1000) - 1, end_time_ms)
            
            log.info(f"Fetching chunk from {datetime.fromtimestamp(current_start/1000, tz=timezone.utc)} to {datetime.fromtimestamp(current_end/1000, tz=timezone.utc)}")
            
            try:
                chunk_txs = self.exchange.fetch_transaction_log(
                    account_type="UNIFIED", 
                    category="linear", 
                    start_time=int(current_start), 
                    end_time=int(current_end)
                )
                all_transactions.extend(chunk_txs)
            except Exception as e:
                log.error(f"Error fetching chunk: {e}")
                break
                
            current_start = current_end + 1

        log.info(f"Total transactions retrieved: {len(all_transactions)}")

        # 4. Process and Aggregation
        # Group by (symbol, side, tradeId_prefix) or just tradeId if available to merge split fills.
        # Bybit Transaction Log 'tradeId' is unique for each fill. 'orderId' is unique for the order.
        # However, a single closing order might have multiple fills.
        # We want to aggregate fills that belong to the same "Closing Event".
        # Simplest approach: Aggregate by 'orderId' if it exists and side/symbol match.
        
        aggregated_data = {}

        for tx_record in all_transactions:
            if tx_record.get("type") != "TRADE":
                continue
                
            change = float(tx_record.get("change", 0.0))
            fee = float(tx_record.get("fee", 0.0))
            pnl = change + fee
            
            # Filter non-zero and above threshold at the individual level? 
            # Or aggregate first then filter? Usually better to aggregate first to catch split fills that sum up to > threshold.
            
            order_id = tx_record.get("orderId")
            symbol = tx_record.get("symbol")
            side = tx_record.get("side")
            
            # Key for aggregation: Order ID + Symbol + Side
            key = f"{order_id}_{symbol}_{side}"
            
            if key not in aggregated_data:
                aggregated_data[key] = {
                    "symbol": symbol,
                    "side": side,
                    "size": 0.0,
                    "total_value": 0.0, # for weighted avg price
                    "fee": 0.0,
                    "pnl": 0.0,
                    "timestamp": int(tx_record.get("transactionTime")),
                    "id": order_id, # Use Order ID as the unique ID for Notion
                    "count": 0
                }
            
            agg = aggregated_data[key]
            qty = float(tx_record.get("qty", 0.0))
            price = float(tx_record.get("tradePrice", 0.0))
            
            agg["size"] += qty
            agg["total_value"] += (qty * price)
            agg["fee"] += fee
            agg["pnl"] += pnl
            # Update timestamp to the latest one in the group
            agg["timestamp"] = max(agg["timestamp"], int(tx_record.get("transactionTime")))
            agg["count"] += 1

        notion_records = []
        pnl_threshold = 0.5 

        for key, agg in aggregated_data.items():
            final_pnl = agg["pnl"]
            
            # Apply threshold filter on the AGGREGATED PnL
            if abs(final_pnl) < pnl_threshold:
                continue
                
            avg_price = agg["total_value"] / agg["size"] if agg["size"] > 0 else 0.0
            
            record = {
                "symbol": agg["symbol"],
                "side": agg["side"],
                "size": agg["size"],
                "price": avg_price,
                "fee": agg["fee"],
                "pnl": final_pnl,
                "timestamp": agg["timestamp"],
                "subaccount": "Main Account",
                "id": agg["id"] 
            }
            notion_records.append(record)

        # Sort all records by timestamp
        notion_records.sort(key=lambda r: r['timestamp'])
        
        if not notion_records:
            log.info("No records matching the filter were found.")
            return

        log.info(f"Processed {len(notion_records)} records (PnL > {pnl_threshold}) to be written to Notion.")
        
        # 5. Write to Notion
        self.notion.create_records(notion_records)
        log.info("Synchronization process completed successfully.")

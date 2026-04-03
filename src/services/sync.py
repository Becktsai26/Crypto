# src/services/sync.py
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..adapters.base import BaseExchangeAdapter
from ..clients.notion import NotionClient
from ..utils.logger import log

class SyncService:
    """
    Orchestrates the synchronization process between an exchange and Notion.
    """

    def __init__(
        self,
        exchange_adapter: BaseExchangeAdapter,
        notion_client: NotionClient,
        exchange_name: str = "bybit",
        journal_db_id: Optional[str] = None,
        pnl_threshold: float = 0,
    ):
        self.exchange = exchange_adapter
        self.notion = notion_client
        self.exchange_name = exchange_name
        self.journal_db_id = journal_db_id
        self.pnl_threshold = pnl_threshold

    def run_sync(self, silent: bool = False) -> Dict[str, Any]:
        """
        Runs the main synchronization logic with support for multi-window fetching.
        :param silent: If True, suppresses external notifications
        :returns: Dict with sync results: created_records (list), total_fetched (int)
        """
        log.info(f"Starting synchronization process... (Silent Mode: {silent})")
        sync_result = {"created_records": [], "total_fetched": 0}
        
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

        # 3. Fetch data in chunks (window size depends on exchange)
        all_transactions = []
        current_start = start_time_ms
        window_ms = self.exchange.max_query_window_ms

        while current_start < end_time_ms:
            current_end = min(current_start + window_ms - 1, end_time_ms) if window_ms > 0 else end_time_ms

            log.info(f"[{self.exchange.exchange_name}] Fetching chunk from {datetime.fromtimestamp(current_start/1000, tz=timezone.utc)} to {datetime.fromtimestamp(current_end/1000, tz=timezone.utc)}")

            try:
                chunk_txs = self.exchange.fetch_transaction_log(
                    account_type=self.exchange.default_account_type,
                    category=self.exchange.default_category,
                    start_time=int(current_start),
                    end_time=int(current_end)
                )
                all_transactions.extend(chunk_txs)
            except Exception as e:
                log.error(f"Error fetching chunk: {e}")
                break
                
            current_start = current_end + 1

        log.info(f"Total transactions retrieved: {len(all_transactions)}")
        sync_result["total_fetched"] = len(all_transactions)

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

        for key, agg in aggregated_data.items():
            gross_pnl = agg["pnl"]  # change + fee (used for opening trade detection)

            # Skip opening trades (gross PnL=0 means change=-fee, no realized PnL)
            if gross_pnl == 0:
                continue

            # Net PnL = gross - fee = sum(change) = actual wallet impact
            net_pnl = gross_pnl - agg["fee"]

            # Apply threshold on net PnL
            if abs(net_pnl) < self.pnl_threshold:
                continue

            avg_price = agg["total_value"] / agg["size"] if agg["size"] > 0 else 0.0

            # Determine Result based on net PnL
            if net_pnl > 0:
                result = "Win"
            elif net_pnl < 0:
                result = "Loss"
            else:
                result = "BE"

            record = {
                "symbol": agg["symbol"],
                "side": agg["side"],
                "size": agg["size"],
                "price": avg_price,
                "fee": agg["fee"],
                "pnl": net_pnl,
                "timestamp": agg["timestamp"],
                "subaccount": "Main Account",
                "id": agg["id"],
                "exchange": self.exchange_name,
                "result": result,
            }
            notion_records.append(record)

        # Sort all records by timestamp
        notion_records.sort(key=lambda r: r['timestamp'])
        
        if not notion_records:
            log.info("No records matching the filter were found.")
            return sync_result

        log.info(f"Processed {len(notion_records)} records (PnL > {self.pnl_threshold}) to be written to Notion.")

        # 5. Write to Main_Account
        created_pages = self.notion.create_records(notion_records)
        log.info("Main_Account synchronization completed.")

        # 6. Create Trade_Journal stubs (non-fatal)
        if self.journal_db_id and created_pages:
            try:
                log.info(f"Creating {len(created_pages)} journal stubs...")
                self.notion.create_journal_stubs(self.journal_db_id, created_pages)
                log.info("Journal stubs created.")
            except Exception as e:
                log.error(f"Journal stub creation failed (non-fatal): {e}")

        # Build result: only include records that were actually created (not duplicates)
        created_txids = set(p["transaction_id"] for p in created_pages) if created_pages else set()
        sync_result["created_records"] = [r for r in notion_records if r["id"] in created_txids]

        # Find the page_id of the latest created trade (for Account Balance update)
        if created_pages and sync_result["created_records"]:
            latest_record = max(
                sync_result["created_records"],
                key=lambda r: r["timestamp"],
            )
            for p in created_pages:
                if p["transaction_id"] == latest_record["id"]:
                    sync_result["last_page_id"] = p["page_id"]
                    break

        log.info("Synchronization process completed successfully.")
        return sync_result

# src/clients/notion.py
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from notion_client import Client
from notion_client.errors import APIResponseError

from ..utils.exceptions import NotionApiException
from ..utils.logger import log

# Notion API has a rate limit of an average of 3 requests per second.
NOTION_REQUEST_DELAY = 0.4  # seconds, slightly more than 1/3

import requests

class NotionClient:
    """
    A client for interacting with the Notion API.
    Handles querying the database for the last sync time and creating new records.
    """

    def __init__(self, token: str, database_id: str):
        """
        Initializes the Notion client.

        Args:
            token: The Notion integration token.
            database_id: The ID of the Notion database to sync with.
        """
        self.client = Client(auth=token)
        self.token = token
        self.database_id = database_id

    def _query_database(self, **kwargs):
        """
        Helper method to query the database using direct requests to bypass
        client library issues on Windows.
        """
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.post(url, headers=headers, json=kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            # Wrap as APIResponseError or NotionApiException so callers handle it
            raise NotionApiException(f"Direct query failed: {e}")

    def _query_database_by_id(self, database_id: str, **kwargs):
        """
        Helper method to query a specific database by ID (for journal/monthly DBs).
        Same logic as _query_database but accepts an arbitrary database_id.
        """
        url = f"https://api.notion.com/v1/databases/{database_id}/query"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json"
        }
        try:
            response = requests.post(url, headers=headers, json=kwargs)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            raise NotionApiException(f"Direct query failed: {e}")

    def get_last_sync_timestamp(self, timestamp_col_name: str = "Timestamp") -> Optional[int]:
        """
        Retrieves the timestamp of the most recent entry in the Notion database.

        Args:
            timestamp_col_name: The name of the 'Date' column in Notion.

        Returns:
            The timestamp of the last record in milliseconds, or None if the DB is empty.
        """
        try:
            response = self._query_database(
                sorts=[{"property": timestamp_col_name, "direction": "descending"}],
                page_size=1,
            )
            if not response["results"]:
                return None
            
            date_prop = response["results"][0]["properties"][timestamp_col_name].get("date")
            if not date_prop or not date_prop.get("start"):
                return None
            
            last_entry_date_str = date_prop["start"]
            # Convert ISO 8601 string to datetime object, then to UTC timestamp
            dt = datetime.fromisoformat(last_entry_date_str)
            return int(dt.timestamp() * 1000)

        except APIResponseError as e:
            raise NotionApiException(f"Failed to query Notion database: {e}")

    def query_all_records(self) -> List[Dict[str, Any]]:
        """
        Queries and returns all records from the Notion database, handling pagination.

        Returns:
            A list of all records (pages) from the database.
        """
        all_results = []
        has_more = True
        start_cursor = None
        
        while has_more:
            try:
                response = self._query_database(
                    start_cursor=start_cursor,
                    page_size=100  # Max page size
                )
                
                all_results.extend(response["results"])
                has_more = response["has_more"]
                start_cursor = response.get("next_cursor")
                
                time.sleep(NOTION_REQUEST_DELAY)

            except APIResponseError as e:
                raise NotionApiException(f"Failed to query Notion database: {e}")
        
        log.info(f"Queried and retrieved {len(all_results)} total records from Notion.")
        return all_results

    def create_records(self, records: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """
        Creates new pages in the Notion database for each record.
        Includes deduplication based on 'Transaction ID'.

        Args:
            records: A list of dictionaries, where each dict represents a trade/transaction.

        Returns:
            A list of dicts with 'page_id' and 'transaction_id' for each created page.
        """
        if not records:
            return []

        # Deduplication Step 1: Check specifically for the IDs we are about to write.
        # We process this in chunks to avoid hitting filter size limits (Notion limit is ~100 filters, we stay safe with 50).
        
        candidate_ids = [r.get("id") for r in records if r.get("id")]
        # Remove duplicates within the batch itself
        candidate_ids = list(set(candidate_ids))
        
        existing_ids = set()
        
        # Helper to chunk list
        def chunk_list(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i:i + n]
                
        # Query matching IDs from Notion
        for id_chunk in chunk_list(candidate_ids, 50):
            if not id_chunk:
                continue
                
            try:
                # Construct OR filter for this chunk
                or_filters = []
                for tid in id_chunk:
                    or_filters.append({
                        "property": "Transaction ID",
                        "rich_text": {
                            "equals": tid
                        }
                    })
                
                # Query Notion
                response = self._query_database(
                    filter={"or": or_filters},
                    page_size=100  # Should be enough for the chunk size
                )
                
                # Collect found IDs
                for page in response.get("results", []):
                    try:
                        # Extract Transaction ID
                        id_prop = page["properties"].get("Transaction ID", {}).get("rich_text", [])
                        if id_prop:
                            found_id = id_prop[0]["plain_text"]
                            existing_ids.add(found_id)
                    except (KeyError, IndexError):
                        continue
                        
                # Rate limit respect
                time.sleep(NOTION_REQUEST_DELAY)
                
            except APIResponseError as e:
                log.warning(f"Failed to query existing IDs matching chunk: {e}. Duplicates may occur.")

        
        # Deduplication Step 2: Filter input records
        unique_records = [r for r in records if r.get("id") and r.get("id") not in existing_ids]
        
        duplicates_count = len(records) - len(unique_records)
        if duplicates_count > 0:
            log.info(f"Skipped {duplicates_count} duplicate records found in Notion.")
        
        if not unique_records:
            log.info("No new unique records to create.")
            return []

        created_pages = []
        for record in unique_records:
            properties = self._map_to_notion_properties(record)
            try:
                result = self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                )
                created_pages.append({
                    "page_id": result["id"],
                    "transaction_id": record.get("id", ""),
                })
                log.info(f"Successfully created record in Notion for symbol: {record.get('symbol')}")
                # Adhere to rate limits
                time.sleep(NOTION_REQUEST_DELAY)

            except APIResponseError as e:
                # Handle rate limit error
                if e.code == "rate_limited":
                    log.warning("Notion rate limit hit. Sleeping for 60 seconds...")
                    time.sleep(60)
                    # Retry the same record
                    result = self.client.pages.create(
                        parent={"database_id": self.database_id},
                        properties=properties,
                    )
                    created_pages.append({
                        "page_id": result["id"],
                        "transaction_id": record.get("id", ""),
                    })
                else:
                    raise NotionApiException(f"Failed to create Notion page for record {record}: {e}")

        return created_pages

    @staticmethod
    def _map_to_notion_properties(record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps a standard record dictionary to the Notion API's property format.
        This must be customized to match your database schema precisely.

        Schema: Symbol(Select), Side(Select), Size(Num), Entry/Exit Price(Num), 
                Fee(Num), PnL(Num), Timestamp(Date), Subaccount(Text).
        """
        # Convert timestamp (ms) to ISO 8601 string
        timestamp_iso = datetime.fromtimestamp(record.get("timestamp", 0) / 1000, tz=timezone.utc).isoformat()

        properties = {
            "Symbol": {"select": {"name": record.get("symbol")}},
            "Side": {"select": {"name": record.get("side")}},
            "Size": {"number": record.get("size")},
            "Entry/Exit Price": {"number": record.get("price")},
            "Fee": {"number": record.get("fee")},
            "PnL": {"number": record.get("pnl")},
            "Timestamp": {"date": {"start": timestamp_iso}},
            "Subaccount": {
                "rich_text": [{"type": "text", "text": {"content": record.get("subaccount", "Main Account")}}]
            },
            "Transaction ID": {
                "rich_text": [{"type": "text", "text": {"content": record.get("id", "")}}]
            },
            "Trade": {
                "title": [{"type": "text", "text": {"content": f"{record.get('symbol')} {record.get('side')}"}}]
            }
        }

        # Phase 1: Add Exchange and Result if present in record
        if record.get("exchange"):
            properties["Exchange"] = {"select": {"name": record["exchange"]}}
        if record.get("result"):
            properties["Result"] = {"select": {"name": record["result"]}}

        # Notion API does not accept None for number fields.
        # We filter out any properties where the number value is None.
        return {k: v for k, v in properties.items() if not (isinstance(v.get('number'), float) and v.get('number') is None)}

    # ── Phase 1: Trade Journal ──────────────────────────────────────

    def create_journal_stubs(self, journal_db_id: str, created_pages: List[Dict[str, str]]) -> None:
        """
        Creates stub rows in Trade_Journal for newly created Main_Account pages.
        Deduplicates by Transaction ID to avoid overwriting human-filled fields.

        Args:
            journal_db_id: The Notion database ID for Trade_Journal.
            created_pages: List of dicts with 'page_id' and 'transaction_id'.
        """
        if not created_pages:
            return

        # Dedup: check which Transaction IDs already exist in journal
        candidate_ids = list(set(p["transaction_id"] for p in created_pages if p.get("transaction_id")))
        existing_ids = set()

        def chunk_list(lst, n):
            for i in range(0, len(lst), n):
                yield lst[i:i + n]

        for id_chunk in chunk_list(candidate_ids, 50):
            if not id_chunk:
                continue
            try:
                or_filters = [
                    {"property": "Transaction ID", "rich_text": {"equals": tid}}
                    for tid in id_chunk
                ]
                response = self._query_database_by_id(
                    journal_db_id,
                    filter={"or": or_filters},
                    page_size=100,
                )
                for page in response.get("results", []):
                    try:
                        id_prop = page["properties"].get("Transaction ID", {}).get("rich_text", [])
                        if id_prop:
                            existing_ids.add(id_prop[0]["plain_text"])
                    except (KeyError, IndexError):
                        continue
                time.sleep(NOTION_REQUEST_DELAY)
            except Exception as e:
                log.warning(f"Failed to query journal existing IDs: {e}")

        # Create stubs for new entries only
        new_pages = [p for p in created_pages if p.get("transaction_id") and p["transaction_id"] not in existing_ids]

        skipped = len(created_pages) - len(new_pages)
        if skipped > 0:
            log.info(f"Skipped {skipped} journal stubs (already exist).")

        for page_info in new_pages:
            tid = page_info["transaction_id"]
            pid = page_info["page_id"]
            properties = {
                "Journal Entry": {
                    "title": [{"type": "text", "text": {"content": tid}}]
                },
                "Transaction ID": {
                    "rich_text": [{"type": "text", "text": {"content": tid}}]
                },
                "Trade Link": {
                    "relation": [{"id": pid}]
                },
            }
            try:
                self.client.pages.create(
                    parent={"database_id": journal_db_id},
                    properties=properties,
                )
                log.info(f"Created journal stub for Transaction ID: {tid}")
                time.sleep(NOTION_REQUEST_DELAY)
            except APIResponseError as e:
                if e.code == "rate_limited":
                    log.warning("Notion rate limit hit during journal creation. Sleeping 60s...")
                    time.sleep(60)
                    self.client.pages.create(
                        parent={"database_id": journal_db_id},
                        properties=properties,
                    )
                else:
                    raise NotionApiException(f"Failed to create journal stub for {tid}: {e}")

    # ── Phase 1: Monthly Summary ────────────────────────────────────

    def query_current_month_trades(self, month_start_iso: str, month_end_iso: str) -> List[Dict[str, Any]]:
        """
        Queries Main_Account (self.database_id) for all trades within a date range.

        Args:
            month_start_iso: ISO 8601 start date (inclusive).
            month_end_iso: ISO 8601 end date (exclusive).

        Returns:
            A list of all matching Notion page objects.
        """
        date_filter = {
            "and": [
                {"property": "Timestamp", "date": {"on_or_after": month_start_iso}},
                {"property": "Timestamp", "date": {"before": month_end_iso}},
            ]
        }

        all_results = []
        has_more = True
        start_cursor = None

        while has_more:
            try:
                query_params = {"filter": date_filter, "page_size": 100}
                if start_cursor:
                    query_params["start_cursor"] = start_cursor
                response = self._query_database(**query_params)
                all_results.extend(response["results"])
                has_more = response["has_more"]
                start_cursor = response.get("next_cursor")
                time.sleep(NOTION_REQUEST_DELAY)
            except Exception as e:
                raise NotionApiException(f"Failed to query current month trades: {e}")

        log.info(f"Queried {len(all_results)} trades for monthly summary.")
        return all_results

    def upsert_monthly_summary(self, monthly_db_id: str, month_key: str, stats: Dict[str, float]) -> None:
        """
        Upserts a row in the monthly summary DB (資產成長追蹤).
        Only writes number fields; does not touch formula or manual fields.

        Args:
            monthly_db_id: The Notion database ID for the monthly summary.
            month_key: Month identifier, e.g. "2026-04".
            stats: Dict with keys: total_pnl, total_fees, wins, losses, max_single_win, max_single_loss.
        """
        # Query for existing row matching this month
        try:
            response = self._query_database_by_id(
                monthly_db_id,
                filter={"property": "Month", "title": {"equals": month_key}},
                page_size=1,
            )
        except Exception as e:
            raise NotionApiException(f"Failed to query monthly summary for {month_key}: {e}")

        properties = {
            "Total PnL": {"number": stats["total_pnl"]},
            "Total Fees": {"number": stats["total_fees"]},
            "Wins": {"number": stats["wins"]},
            "Losses": {"number": stats["losses"]},
            "Max Single Win": {"number": stats["max_single_win"]},
            "Max Single Loss": {"number": stats["max_single_loss"]},
        }

        existing_pages = response.get("results", [])

        try:
            if existing_pages:
                # Update existing row
                page_id = existing_pages[0]["id"]
                self.client.pages.update(page_id=page_id, properties=properties)
                log.info(f"Updated monthly summary for {month_key}.")
            else:
                # Create new row
                properties["Month"] = {
                    "title": [{"type": "text", "text": {"content": month_key}}]
                }
                self.client.pages.create(
                    parent={"database_id": monthly_db_id},
                    properties=properties,
                )
                log.info(f"Created monthly summary for {month_key}.")
            time.sleep(NOTION_REQUEST_DELAY)
        except APIResponseError as e:
            raise NotionApiException(f"Failed to upsert monthly summary for {month_key}: {e}")

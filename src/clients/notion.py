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

    def create_records(self, records: List[Dict[str, Any]]):
        """
        Creates new pages in the Notion database for each record.
        Includes deduplication based on 'Transaction ID'.

        Args:
            records: A list of dictionaries, where each dict represents a trade/transaction.
        """
        if not records:
            return

        # Deduplication Step 1: Fetch recent IDs from Notion to avoid duplicates
        # We fetch the last 100 records (enough for most overlapping sync windows)
        existing_ids = set()
        try:
            response = self._query_database(
                sorts=[{"property": "Timestamp", "direction": "descending"}],
                page_size=100
            )
            for page in response.get("results", []):
                try:
                    # Extract Rich Text content safely
                    id_prop = page["properties"].get("Transaction ID", {}).get("rich_text", [])
                    if id_prop:
                        existing_ids.add(id_prop[0]["plain_text"])
                except (KeyError, IndexError):
                    continue
        except APIResponseError as e:
            log.warning(f"Failed to fetch existing IDs for deduplication: {e}. Proceeding without deduplication.")
        
        # Deduplication Step 2: Filter input records
        unique_records = [r for r in records if r.get("id") and r.get("id") not in existing_ids]
        
        duplicates_count = len(records) - len(unique_records)
        if duplicates_count > 0:
            log.info(f"Skipped {duplicates_count} duplicate records found in Notion.")
        
        if not unique_records:
            log.info("No new unique records to create.")
            return

        for record in unique_records:
            properties = self._map_to_notion_properties(record)
            try:
                self.client.pages.create(
                    parent={"database_id": self.database_id},
                    properties=properties,
                )
                log.info(f"Successfully created record in Notion for symbol: {record.get('symbol')}")
                # Adhere to rate limits
                time.sleep(NOTION_REQUEST_DELAY)

            except APIResponseError as e:
                # Handle rate limit error
                if e.code == "rate_limited":
                    log.warning("Notion rate limit hit. Sleeping for 60 seconds...")
                    time.sleep(60)
                    # Retry the same record
                    self.client.pages.create(
                        parent={"database_id": self.database_id},
                        properties=properties,
                    )
                else:
                    raise NotionApiException(f"Failed to create Notion page for record {record}: {e}")

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
        }
        # Notion API does not accept None for number fields.
        # We filter out any properties where the number value is None.
        return {k: v for k, v in properties.items() if not (isinstance(v.get('number'), float) and v.get('number') is None)}

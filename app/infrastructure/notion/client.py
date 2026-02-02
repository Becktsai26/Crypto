from notion_client import Client
from app.config.settings import settings
from app.config.logging import logger
from app.core.exceptions import DataDestinationError
from app.core.models import Trade, BalanceSnapshot
from .mapper import NotionMapper

class NotionClient:
    """
    Notion API 封裝客戶端。
    """
    
    def __init__(self):
        if not settings.NOTION_TOKEN:
            raise DataDestinationError("NOTION_TOKEN is not set")
        self.client = Client(auth=settings.NOTION_TOKEN)
        self.trade_db_id = settings.NOTION_DB_ID
        self.snapshot_db_id = settings.NOTION_SNAPSHOT_DB_ID

    def save_trade(self, trade: Trade):
        """將單筆交易寫入 Notion"""
        try:
            properties = NotionMapper.trade_to_props(trade)
            self.client.pages.create(
                parent={"database_id": self.trade_db_id},
                properties=properties
            )
            logger.info(f"Successfully saved trade {trade.trade_id} to Notion.")
        except Exception as e:
            logger.error(f"Failed to save trade to Notion: {e}")
            raise DataDestinationError(f"Notion save error: {e}")

    def query_last_trade_id(self) -> str:
        """
        查詢資料庫中最後一筆交易的 ID，用於增量同步。
        這是一個簡單的實現，實際可能需要更複雜的排序。
        """
        try:
            response = self.client.databases.query(
                database_id=self.trade_db_id,
                sorts=[{"property": "Timestamp", "direction": "descending"}],
                page_size=1
            )
            results = response.get("results", [])
            if not results:
                return ""
            
            # 從 rich_text 欄位中提取 OrderID
            props = results[0].get("properties", {})
            order_id_list = props.get("OrderID", {}).get("rich_text", [])
            if order_id_list:
                return order_id_list[0].get("text", {}).get("content", "")
            return ""
        except Exception as e:
            logger.error(f"Failed to query Notion for last trade ID: {e}")
            return ""

    def save_balance_snapshot(self, snapshot: BalanceSnapshot):
        """將資產快照寫入 Notion"""
        if not self.snapshot_db_id:
            logger.warning("NOTION_SNAPSHOT_DB_ID not set, skipping snapshot save.")
            return

        try:
            properties = NotionMapper.balance_to_props(snapshot)
            self.client.pages.create(
                parent={"database_id": self.snapshot_db_id},
                properties=properties
            )
            logger.info("Successfully saved balance snapshot to Notion.")
        except Exception as e:
            logger.error(f"Failed to save snapshot to Notion: {e}")
            # 快照失敗通常不影響主同步，所以我們只記錄 log，不拋出致命錯誤

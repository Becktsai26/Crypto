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

    def query_daily_trades(self, target_date: str) -> list[dict]:
        """
        查詢特定日期的交易紀錄。
        target_date: ISO date string YYYY-MM-DD
        """
        try:
            # Filter by Date
            response = self.client.databases.query(
                database_id=self.trade_db_id,
                filter={
                    "property": settings.NOTION_FIELD_DATE,
                    "date": {
                        "equals": target_date
                    }
                }
            )
            results = response.get("results", [])
            trades = []
            for page in results:
                props = page.get("properties", {})

                # Helper to extract value safely
                def get_prop(name):
                    p = props.get(name, {})
                    p_type = p.get("type")
                    if not p_type:
                        return None

                    if p_type == "date":
                        return p.get("date", {}).get("start")
                    elif p_type == "select":
                        return p.get("select", {}).get("name")
                    elif p_type == "number":
                        return p.get("number")
                    elif p_type == "rich_text":
                        t = p.get("rich_text", [])
                        return t[0].get("plain_text") if t else ""
                    elif p_type == "title":
                         t = p.get("title", [])
                         return t[0].get("plain_text") if t else ""
                    return None

                trade = {
                    "date": get_prop(settings.NOTION_FIELD_DATE),
                    "pair": get_prop(settings.NOTION_FIELD_PAIR),
                    "direction": get_prop(settings.NOTION_FIELD_DIRECTION),
                    "r": get_prop(settings.NOTION_FIELD_RESULT_R),
                    "note": get_prop(settings.NOTION_FIELD_NOTE),
                }

                # Basic validation: r is required for stats
                if trade["r"] is not None:
                     trades.append(trade)

            return trades

        except Exception as e:
            logger.error(f"Failed to query daily trades: {e}")
            return []

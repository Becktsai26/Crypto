from typing import Any, Dict
from app.core.models import Trade, BalanceSnapshot

class NotionMapper:
    """
    負責將 Domain Models 轉換為 Notion API 所需的 JSON 格式 (Properties)。
    """
    
    @staticmethod
    def trade_to_props(trade: Trade) -> Dict[str, Any]:
        """
        將 Trade 物件轉為 Notion Database Properties。
        注意：欄位名稱必須與 Notion Database 一致。
        """
        return {
            "Symbol": {"select": {"name": trade.symbol}},
            "Side": {"select": {"name": trade.side}},
            "Size": {"number": float(trade.qty)},
            "Entry Price": {"number": float(trade.entry_price or 0)},
            "Exit Price": {"number": float(trade.exit_price or 0)},
            "PnL": {"number": float(trade.pnl)},
            "Fee": {"number": float(trade.fee)},
            "Timestamp": {"date": {"start": trade.timestamp.isoformat()}},
            "OrderID": {"rich_text": [{"text": {"content": trade.trade_id}}]}
        }

    @staticmethod
    def balance_to_props(snapshot: BalanceSnapshot) -> Dict[str, Any]:
        """
        將 BalanceSnapshot 物件轉為快照資料庫的格式。
        """
        return {
            "Date": {"date": {"start": snapshot.timestamp.isoformat()}},
            "Equity": {"number": float(snapshot.wallet_balance)},
            "Unrealized PnL": {"number": float(snapshot.unrealized_pnl)},
            "Exposure": {"number": float(snapshot.total_position_size)}
        }

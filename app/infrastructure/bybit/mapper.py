from datetime import datetime
from decimal import Decimal
from typing import Any, Dict
from app.core.models import Trade, BalanceSnapshot

class BybitMapper:
    """
    負責將 Bybit API 的原始 JSON 資料轉換為核心 Domain Models。
    """
    
    @staticmethod
    def to_trade(raw: Dict[str, Any], category: str = "linear") -> Trade:
        """
        將 closed-pnl 或 execution 紀錄轉為 Trade 物件。
        """
        # 以 Bybit V5 closed-pnl 為例
        return Trade(
            trade_id=str(raw.get("orderId", raw.get("execId", ""))),
            symbol=raw.get("symbol", ""),
            side=raw.get("side", ""),
            order_type="Trade",
            qty=Decimal(str(raw.get("closedSize", raw.get("execQty", 0)))),
            price=Decimal(str(raw.get("avgExitPrice", raw.get("execPrice", 0)))),
            fee=Decimal(str(raw.get("fillFee", 0))),
            pnl=Decimal(str(raw.get("closedPnl", 0))),
            timestamp=datetime.fromtimestamp(int(raw.get("updatedTime", raw.get("execTime", 0))) / 1000),
            entry_price=Decimal(str(raw.get("avgEntryPrice", 0))),
            exit_price=Decimal(str(raw.get("avgExitPrice", 0)))
        )

    @staticmethod
    def to_balance_snapshot(raw: Dict[str, Any]) -> BalanceSnapshot:
        """
        將 wallet-balance 紀錄轉為 BalanceSnapshot 物件。
        """
        # Bybit V5 wallet-balance 'list' contains account info
        account_info = raw.get("list", [{}])[0]
        return BalanceSnapshot(
            timestamp=datetime.now(), # Bybit 回傳通常只有秒級，我們取當下
            wallet_balance=Decimal(str(account_info.get("totalEquity", 0))),
            unrealized_pnl=Decimal(str(account_info.get("totalUnrealizedProfit", 0))),
            total_position_size=Decimal(str(account_info.get("totalMarginBalance", 0))) # 這裡可依需求調整定義
        )

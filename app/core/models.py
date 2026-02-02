from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

@dataclass(frozen=True)
class Trade:
    """
    核心交易模型 (Domain Model)。
    代表一筆已完成的交易或資金費率紀錄。
    此模型獨立於任何交易所 API 或資料庫格式。
    """
    trade_id: str          # 唯一識別碼 (交易所端的 OrderID 或 TransactionID)
    symbol: str            # 交易對 (e.g., "BTCUSDT")
    side: str              # 方向 (Buy, Sell, None)
    order_type: str        # 類型 (Trade, Funding, Fee, etc.)
    qty: Decimal           # 數量
    price: Decimal         # 價格 (若是 Funding 則可能為 0 或 Funding Rate)
    fee: Decimal           # 手續費
    pnl: Decimal           # 已實現損益 (Realized PnL)
    timestamp: datetime    # 交易時間 (UTC)
    
    # 選填欄位，視交易所 API 是否提供
    entry_price: Optional[Decimal] = None
    exit_price: Optional[Decimal] = None
    
    def is_profit(self) -> bool:
        return self.pnl > 0

@dataclass(frozen=True)
class BalanceSnapshot:
    """
    資產快照模型。
    用於紀錄特定時間點的帳戶總值。
    """
    timestamp: datetime
    wallet_balance: Decimal      # 錢包權益 (Equity)
    unrealized_pnl: Decimal      # 未實現損益
    total_position_size: Decimal # 總持倉價值 (名目價值)

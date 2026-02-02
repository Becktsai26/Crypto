from typing import List
from app.config.logging import logger
from app.infrastructure.bybit.client import BybitClient
from app.infrastructure.notion.client import NotionClient
from app.core.models import Trade

class SyncService:
    """
    負責協調 Bybit 與 Notion 之間的資料同步流程。
    """
    def __init__(self):
        # 依賴注入 (Dependency Injection) 的概念，但這裡為了簡化直接實例化
        # 在更嚴謹的架構中，這些 Client 應該由外部傳入
        self.source = BybitClient()
        self.destination = NotionClient()

    def run_once(self):
        """執行一次完整的同步週期"""
        logger.info("Starting sync process...")
        
        # 1. 獲取最後同步的狀態 (Checkpoint)
        last_trade_id = self.destination.query_last_trade_id()
        logger.info(f"Last synced Trade ID in Notion: {last_trade_id or 'None'}")

        # 2. 從交易所獲取最近的交易紀錄
        # 這裡預設抓 50 筆，如果交易量大，可能需要 Loop Fetch
        recent_trades = self.source.get_closed_pnl(limit=50)
        if not recent_trades:
            logger.info("No trades returned from Bybit.")
            return

        # 3. 業務邏輯：過濾新交易
        # Bybit API 通常回傳最新的在前 (Index 0 is latest)
        # 為了依序寫入，我們可能需要反轉順序，或是由後往前找
        
        new_trades: List[Trade] = []
        found_checkpoint = False

        if not last_trade_id:
            # 如果是第一次執行 (Notion 空的)，全部視為新交易
            new_trades = recent_trades
        else:
            for trade in recent_trades:
                if trade.trade_id == last_trade_id:
                    found_checkpoint = True
                    break
                new_trades.append(trade)
            
            if not found_checkpoint:
                logger.warning(
                    f"Checkpoint ID {last_trade_id} not found in recent 50 trades. "
                    "Potentially missing gap data. Consider increasing fetch limit."
                )

        if not new_trades:
            logger.info("No new trades to sync.")
            return

        # 4. 將新交易寫入 Notion (反轉順序，讓舊的先寫入)
        logger.info(f"Found {len(new_trades)} new trades. Syncing...")
        for trade in reversed(new_trades):
            self.destination.save_trade(trade)
        
        logger.info("Trade sync completed.")

    def run_snapshot(self):
        """執行資產快照同步"""
        logger.info("Taking wallet balance snapshot...")
        try:
            snapshot = self.source.get_balance()
            self.destination.save_balance_snapshot(snapshot)
            logger.info(f"Snapshot saved. Equity: {snapshot.wallet_balance}")
        except Exception as e:
            logger.error(f"Snapshot failed: {e}")

    def run_full_sync(self):
        """同時執行交易同步與快照"""
        self.run_once()
        self.run_snapshot()

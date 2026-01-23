
from datetime import datetime, timedelta
import time
from typing import Dict, Any, Tuple
from ..adapters.bybit import BybitAdapter
from ..utils.logger import log

class StatsService:
    def __init__(self, exchange_adapter: BybitAdapter):
        self.adapter = exchange_adapter

    def get_start_of_day_timestamp(self) -> int:
        now = datetime.now()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return int(start_of_day.timestamp() * 1000)

    def get_start_of_month_timestamp(self) -> int:
        now = datetime.now()
        start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return int(start_of_month.timestamp() * 1000)

    def calculate_pnl_stats(self, pnl_records: list) -> Dict[str, Any]:
        """
        Calculates detailed PnL statistics from a list of records.
        """
        total_pnl = 0.0
        wins = 0
        losses = 0
        max_win = 0.0
        max_loss = 0.0
        
        for record in pnl_records:
            pnl = float(record.get("closedPnl", 0))
            total_pnl += pnl
            
            if pnl > 0:
                wins += 1
                if pnl > max_win:
                    max_win = pnl
            elif pnl < 0:
                losses += 1
                if pnl < max_loss: # pnl is negative, so smaller is "bigger loss"
                    max_loss = pnl
                
        return {
            "pnl": total_pnl,
            "wins": wins,
            "losses": losses,
            "max_win": max_win,
            "max_loss": max_loss
        }

    def get_daily_report_data(self) -> Dict[str, Any]:
        try:
            # User requested to REMOVE Equity and Monthly stats.
            # 1. Get Daily PnL
            start_today = self.get_start_of_day_timestamp()
            daily_records = self.adapter.get_closed_pnl(category="linear", start_time=start_today)
            
            stats = self.calculate_pnl_stats(daily_records)

            return {
                "daily_pnl": stats["pnl"],
                "daily_wins": stats["wins"],
                "daily_losses": stats["losses"],
                "daily_max_win": stats["max_win"],
                "daily_max_loss": stats["max_loss"]
            }

        except Exception as e:
            log.error(f"Error fetching report data: {e}")
            return {}

        except Exception as e:
            log.error(f"Error fetching report data: {e}")
            return {}

    def get_closed_pnl_by_order(self, symbol: str, order_id: str) -> float:
        """
        Fetches the closed PnL for a specific order ID.
        Returns None if not found (e.g. opening trade).
        """
        try:
            # Fetch recent closed PnL for the symbol (default last 7 days is fine, we just need recent)
            # We assume the PnL is generated within the buffer time (3s)
            records = self.adapter.get_closed_pnl(category="linear", limit=20) # No symbol filter in adapter yet? check logic
            # Adapter get_closed_pnl takes category, start_time, end_time, limit. 
            # We might need to handle symbol filtering in the loop or adding symbol arg to adapter if supported.
            # Bybit V5 closed-pnl supports 'symbol' param. Let's update adapter call if needed or just filter.
            
            # Note: Adapter implementation of get_closed_pnl:
            # def get_closed_pnl(self, category: str, start_time: int = None, end_time: int = None, limit: int = 50)
            # It doesn't expose symbol! We should rely on standard loop or update adapter.
            # Updating adapter is cleaner, but for now let's just fetch recent global PnL 
            # (as user likely only trades one symbol at a time or low freq).
            # Better: Filter by matching orderId.
            
            for record in records:
                if record.get("orderId") == order_id:
                    return float(record.get("closedPnl", 0))
            
            return None
            
        except Exception as e:
            log.error(f"Error fetching PnL for order {order_id}: {e}")
            return None

    def get_last_closed_position_stats(self) -> Dict[str, Any]:
        """
        Fetches and aggregates the most recent closed position.
        Uses 'Same Average Entry Price' clustering to identify records belonging to the same position cycle.
        This handles partial TPs (TP1, TP2) even if they are hours apart, as long as AvgEntry didn't change (or is close).
        """
        try:
            # Fetch recent records
            records = self.adapter.get_closed_pnl(category="linear", limit=50)
            if not records:
                return None
                
            # 1. Identify the latest closing action target
            last_record = records[0]
            target_symbol = last_record.get("symbol")
            target_side = last_record.get("side")
            target_avg_entry = float(last_record.get("avgEntryPrice", 0))
            
            # 2. Filter records to only this Symbol and Side (ignore other pairs traded in between)
            # We keep order preserved (newest first)
            relevant_records = [
                r for r in records 
                if r.get("symbol") == target_symbol and r.get("side") == target_side
            ]
            
            total_pnl = 0.0
            total_qty = 0.0
            weighted_price_sum = 0.0
            count = 0
            
            # 3. Aggregate backwards until AvgEntryPrice mismatch
            for rec in relevant_records:
                current_entry_price = float(rec.get("avgEntryPrice", 0))
                
                # Check for Match (with slight tolerance for float precision)
                if abs(current_entry_price - target_avg_entry) < 0.0001:  # Epsilon match
                     qty = float(rec.get("qty", 0) or rec.get("closedSize", 0))
                     pnl = float(rec.get("closedPnl", 0))
                     price = float(rec.get("avgExitPrice", 0))
                     
                     total_pnl += pnl
                     total_qty += qty
                     weighted_price_sum += (price * qty)
                     count += 1
                else:
                    # Found a record with different Entry Price -> Previous Position Cycle
                    break
            
            avg_exit_price = (weighted_price_sum / total_qty) if total_qty > 0 else 0
            
            return {
                "symbol": target_symbol,
                "side": target_side,
                "closedPnl": total_pnl,
                "qty": total_qty,
                "avgExitPrice": avg_exit_price,
                "avgEntryPrice": target_avg_entry,
                "record_count": count
            }
            
        except Exception as e:
            log.error(f"Error fetching last closed position: {e}")
            return None

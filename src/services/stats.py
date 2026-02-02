
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

    def get_multi_day_stats(self, days: int = 5) -> Dict[str, Any]:
        """
        Fetches PnL records for the last N days and groups them by date.
        """
        try:
            now = datetime.now()
            # Calculate start time (N days ago at 00:00)
            start_date = (now - timedelta(days=days-1)).replace(hour=0, minute=0, second=0, microsecond=0)
            start_timestamp = int(start_date.timestamp() * 1000)
            
            log.info(f"Fetching PnL records since {start_date.strftime('%Y-%m-%d %H:%M:%S')}")
            records = self.adapter.get_closed_pnl(category="linear", start_time=start_timestamp)
            log.info(f"Fetched {len(records)} records for multi-day stats.")
            
            # Group by date
            daily_groups = {}
            for day_offset in range(days):
                target_date = (start_date + timedelta(days=day_offset)).strftime("%m-%d")
                daily_groups[target_date] = 0.0
                
            total_period_pnl = 0.0
            for record in records:
                pnl = float(record.get("closedPnl", 0))
                # Bybit v5 closedPnl record updatedTime is in ms
                updated_time = int(record.get("updatedTime", 0))
                date_str = datetime.fromtimestamp(updated_time / 1000).strftime("%m-%d")
                
                if date_str in daily_groups:
                    daily_groups[date_str] += pnl
                    total_period_pnl += pnl
            
            log.info(f"Multi-day stats calculated: {daily_groups}, Total: {total_period_pnl}")
            return {
                "daily_groups": daily_groups,
                "total_period_pnl": total_period_pnl,
                "days": days
            }
            
        except Exception as e:
            log.error(f"Error calculating multi-day stats: {e}")
            return {}

    def get_closed_pnl_by_order(self, symbol: str, order_id: str) -> float:
        """
        Fetches the closed PnL for a specific order ID.
        Returns None if not found (e.g. opening trade).
        """
        try:
            records = self.adapter.get_closed_pnl(category="linear", limit=20)
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
        """
        try:
            records = self.adapter.get_closed_pnl(category="linear", limit=50)
            if not records:
                return None
                
            last_record = records[0]
            target_symbol = last_record.get("symbol")
            target_side = last_record.get("side")
            target_avg_entry = float(last_record.get("avgEntryPrice", 0))
            
            relevant_records = [
                r for r in records 
                if r.get("symbol") == target_symbol and r.get("side") == target_side
            ]
            
            total_pnl = 0.0
            total_qty = 0.0
            weighted_price_sum = 0.0
            count = 0
            
            for rec in relevant_records:
                current_entry_price = float(rec.get("avgEntryPrice", 0))
                if abs(current_entry_price - target_avg_entry) < 0.0001:
                     qty = float(rec.get("qty", 0) or rec.get("closedSize", 0))
                     pnl = float(rec.get("closedPnl", 0))
                     price = float(rec.get("avgExitPrice", 0))
                     
                     total_pnl += pnl
                     total_qty += qty
                     weighted_price_sum += (price * qty)
                     count += 1
                else:
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

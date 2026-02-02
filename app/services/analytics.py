from typing import List, Dict

class AnalyticsService:
    @staticmethod
    def calculate_stats(trades: List[Dict]) -> Dict:
        """
        Calculate trading performance statistics from a list of trades.
        Each trade dict must have an 'r' key with a float value.
        """
        if not trades:
            return {
                "total_r": 0.0,
                "avg_r": 0.0,
                "win_rate": 0.0,
                "max_consecutive_loss": 0,
                "max_drawdown": 0.0,
                "count": 0
            }

        # Filter trades that have R value
        rs = [float(t.get("r")) for t in trades if t.get("r") is not None]

        if not rs:
             return {
                "total_r": 0.0,
                "avg_r": 0.0,
                "win_rate": 0.0,
                "max_consecutive_loss": 0,
                "max_drawdown": 0.0,
                "count": 0
            }

        count = len(rs)
        total_r = sum(rs)
        avg_r = total_r / count

        # Win Rate: R > 0 is a win.
        wins = sum(1 for r in rs if r > 0)
        win_rate = (wins / count) * 100

        # Max Consecutive Loss
        max_loss_streak = 0
        current_loss_streak = 0
        for r in rs:
            if r < 0:
                current_loss_streak += 1
            else:
                max_loss_streak = max(max_loss_streak, current_loss_streak)
                current_loss_streak = 0
        # Check last streak
        max_loss_streak = max(max_loss_streak, current_loss_streak)

        # Max Drawdown Calculation
        # We assume trades are ordered chronologically.
        # Drawdown is the decline from a historical peak in cumulative profit.

        current_equity = 0.0
        equity_curve = [0.0] # Start at 0
        for r in rs:
            current_equity += r
            equity_curve.append(current_equity)

        peak = -9999999.0
        max_dd = 0.0

        for val in equity_curve:
            if val > peak:
                peak = val
            dd = peak - val
            if dd > max_dd:
                max_dd = dd

        return {
            "total_r": round(total_r, 2),
            "avg_r": round(avg_r, 2),
            "win_rate": round(win_rate, 1),
            "max_consecutive_loss": max_loss_streak,
            "max_drawdown": round(-max_dd, 2), # Return as negative value for display
            "count": count
        }

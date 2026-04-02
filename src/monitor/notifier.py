import requests
import json
from datetime import datetime
from ..clients.notion import NotionClient
from ..config import settings
from ..utils.goal_progress import (
    build_monthly_goal_progress,
    format_currency,
    format_signed_currency,
)
from ..utils.logger import log

class DiscordNotifier:
    def __init__(self):
        self.webhook_url = settings["discord_webhook_url"]
        self.pnl_webhook_url = settings.get("discord_pnl_webhook_url") or self.webhook_url

    def _get_goal_progress_for_dashboard(self):
        monthly_db_id = settings.get("notion_monthly_db_id")
        target_pnl = settings.get("monthly_pnl_target", 0)
        notion_token = settings.get("notion_token")

        if not monthly_db_id or target_pnl <= 0 or not notion_token:
            return None

        database_id = settings.get("notion_db_id")
        if not database_id:
            first_exchange = next(iter(settings.get("exchanges", {}).values()), None)
            if first_exchange:
                database_id = first_exchange.get("notion_db_id")

        if not database_id:
            return None

        now = datetime.now()
        month_key = now.strftime("%Y-%m %B")

        try:
            notion_client = NotionClient(token=notion_token, database_id=database_id)
            current_pnl = notion_client.get_monthly_total_pnl(monthly_db_id, month_key)
            if current_pnl is None:
                return None
            return build_monthly_goal_progress(current_pnl, target_pnl, now)
        except Exception as e:
            log.warning(f"Failed to build monthly goal progress for PnL dashboard: {e}")
            return None

    def _send(self, payload, webhook_url=None):
        """
        Internal send method.
        """
        url = webhook_url or self.webhook_url
        
        try:
            response = requests.post(
                url, 
                data=json.dumps(payload),
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code not in [200, 201, 204]:
                log.error(f"Failed to send notification: {response.status_code} {response.text}")
                return False
            return True
        except Exception as e:
            log.error(f"Error sending notification: {e}")
            return False

    def _format_all_positions_footer(self, positions_cache: dict):
        """
        Helper to format ALL active positions in the account.
        """
        header = f"----------------------------------------------------\n"
        header += f"**當前持倉狀態 (Account Positions)**"
        
        if not positions_cache:
            return f"{header}\n無 (Empty)"
            
        active_positions = []
        for symbol, pos in positions_cache.items():
            size = float(pos.get("size", 0))
            if size > 0:
                active_positions.append(pos)
        
        if not active_positions:
            return f"{header}\n無 (Empty)"
            
        lines = [header]
        for pos in active_positions:
            symbol = pos.get("symbol", "UNKNOWN")
            side = pos.get("side", "None")
            entry_price = pos.get("avgPrice") or pos.get("entryPrice") or "0"
            size = pos.get("size")
            
            tp = pos.get("takeProfit") or "無"
            sl = pos.get("stopLoss") or "無"
            if str(tp) == "0" or str(tp) == "": tp = "無"
            if str(sl) == "0" or str(sl) == "": sl = "無"
                
            unrealized_pnl = float(pos.get("unrealisedPnl", 0))
            pnl_str = f"{unrealized_pnl:+.2f} U"
            
            side_emoji = "🟢" if side == "Buy" else "🔴"
            
            p_line = f"\n**{symbol} {side} {side_emoji}** (Size: {size})\n"
            p_line += f"Price: `{entry_price}`  TP: `{tp}`  SL: `{sl}`\n"
            p_line += f"PnL: `{pnl_str}`"
            lines.append(p_line)
            
        return "".join(lines)

    def send_order_modified(self, order_data: dict, positions: dict = None):
        symbol = order_data.get("symbol")
        side = order_data.get("side")
        order_type = order_data.get("orderType")
        
        # New simplified logic: Entry (from position check?), New TP, New SL
        # We need to find the entry price from the positions if possible, or use order price if relevant.
        # But for TP/SL modification on a position, the entry price is in the position data.
        
        entry_price = "N/A"
        if positions and symbol in positions:
            pos = positions[symbol]
            entry_price = pos.get("avgPrice") or pos.get("entryPrice") or "N/A"
        elif order_data.get("price"):
             entry_price = order_data.get("price")

        tp = order_data.get("takeProfit", "")
        sl = order_data.get("stopLoss", "")
        
        color = 0xFFA500 
        direction = "做多 LONG" if side == "Buy" else "做空 SHORT"

        embed = {
            "title": f"📝 訂單/TP-SL 修改: {symbol}",
            "description": f"**{direction}** {order_type}",
            "color": color,
            "fields": [
                {"name": "入場價格 (Entry)", "value": f"`{entry_price}`", "inline": True},
                {"name": "最新止盈 (New TP)", "value": f"`{tp}`" if tp else "未設定", "inline": True},
                {"name": "最新止損 (New SL)", "value": f"`{sl}`" if sl else "未設定", "inline": True},
            ]
        }
        
        # User requested NO footer for modification
        self._send({"embeds": [embed]})

    def send_order_new(self, order_data: dict, positions: dict = None):
        symbol = order_data.get("symbol")
        side = order_data.get("side")
        order_type = order_data.get("orderType")
        price = order_data.get("price")
        
        tp = order_data.get("takeProfit", "")
        sl = order_data.get("stopLoss", "")
        
        if order_type == "Market" or float(price or 0) == 0:
            display_price = "市價 (Market)"
        else:
            display_price = f"`{price}`"
        
        color = 0x00FF00 if side == "Buy" else 0xFF0000 
        direction = "做多 LONG 🟢" if side == "Buy" else "做空 SHORT 🔴"
        order_type_cn = "限價單" if order_type == "Limit" else "市價單"

        embed = {
            "title": f"📢 交易訊號發布: {symbol}",
            "description": f"**{direction}** ({order_type_cn})",
            "color": color,
            "fields": [
                {"name": "入場價格 (Entry)", "value": display_price, "inline": True},
                {"name": "止盈目標 (TP)", "value": f"`{tp}`" if tp else "未設定", "inline": True},
                {"name": "止損價格 (SL)", "value": f"`{sl}`" if sl else "未設定", "inline": True},
            ]
        }
        
        footer_text = self._format_all_positions_footer(positions)
        if footer_text:
             embed["fields"].append({"name": "Status", "value": footer_text, "inline": False})
        
        self._send({"embeds": [embed]})

    def send_order_filled(self, order_data: dict, pnl: float = None, positions: dict = None, close_type: str = None):
        symbol = order_data.get("symbol")
        side = order_data.get("side")
        price = order_data.get("execPrice")
        qty = order_data.get("execQty")
        
        if pnl is not None:
            if close_type == "TakeProfit":
                action = "止盈出場 (Take Profit)"
                emoji = "💰"
            elif close_type == "StopLoss":
                action = "止損出場 (Stop Loss)"
                emoji = "🛑"
            elif close_type == "TrailingStop":
                action = "追蹤止損 (Trailing Stop)"
                emoji = "📉"
            elif close_type == "Liquidation":
                action = "強制平倉 (Liquidation)"
                emoji = "🌊"
            else:
                action = "平倉離場 (Closed)"
                emoji = "💰" if pnl >= 0 else "💸"
                
            color = 0x00FF00 if pnl >= 0 else 0xFF0000
            pnl_str = f"**{pnl:+.2f} U**"
        else:
            action = "訊號成交 (Open)" if "Open" in str(side) or float(qty) > 0 else "平倉出場"
            emoji = "🚀"
            color = 0x00FF00 if side == "Buy" else 0xFF0000
            pnl_str = None
            
        embed = {
            "title": f"{emoji} {action}: {symbol}",
            "color": color,
            "fields": [
                {"name": "成交價格", "value": f"`{price}`", "inline": True},
            ]
        }
        
        if pnl_str:
             embed["fields"].append({"name": "已實現盈虧", "value": pnl_str, "inline": True})
             
        footer_text = self._format_all_positions_footer(positions)
        if footer_text:
             embed["fields"].append({"name": "Status", "value": footer_text, "inline": False})
        
        self._send({"embeds": [embed]})

    def send_order_cancel(self, order_data: dict, positions: dict = None):
        symbol = order_data.get("symbol")
        side = order_data.get("side")
        price = order_data.get("price", "N/A")
        
        direction = "做多 LONG" if side == "Buy" else "做空 SHORT"
        
        embed = {
            "title": f"⚠️ 掛單取消: {symbol}",
            "color": 0x95a5a6, 
            "fields": [
                {"name": "方向 (Side)", "value": direction, "inline": True},
                {"name": "掛單價格 (Price)", "value": f"`{price}`", "inline": True}
            ]
        }
        
        # User requested NO footer for Cancel
        self._send({"embeds": [embed]})

    def send_position_update(self, pos_data: dict):
        symbol = pos_data.get("symbol")
        side = pos_data.get("side")
        size = pos_data.get("size")
        entry_price = pos_data.get("avgPrice") or pos_data.get("entryPrice") or "Unknown"
        unrealized_pnl = float(pos_data.get("unrealisedPnl", 0))
        
        if float(size) == 0:
            return 
            
        emoji = "💰" if unrealized_pnl >= 0 else "🔻"
        color = 0x00FF00 if unrealized_pnl >= 0 else 0xFF0000
        direction = "由於持倉" if side == "Buy" else "空頭持倉"
        
        embed = {
            "title": f"{emoji} 盈虧更新: {symbol}",
            "color": color,
            "fields": [
                {"name": "方向", "value": side, "inline": True},
                {"name": "入場均價", "value": str(entry_price), "inline": True},
                {"name": "未實現盈虧", "value": f"**{unrealized_pnl:.2f} U**", "inline": False},
            ]
        }
        
        target_url = self.pnl_webhook_url
        self._send({"embeds": [embed]}, webhook_url=target_url)

    def send_daily_report(self, report_data: dict):
        daily_pnl = report_data.get("daily_pnl", 0)
        daily_wins = report_data.get("daily_wins", 0)
        daily_losses = report_data.get("daily_losses", 0)
        max_win = report_data.get("daily_max_win", 0)
        max_loss = report_data.get("daily_max_loss", 0)
        
        daily_total = daily_wins + daily_losses
        daily_win_rate = (daily_wins / daily_total * 100) if daily_total > 0 else 0.0
        
        color = 0xFFD700 if daily_pnl >= 0 else 0x95a5a6
        d_emoji = "🔥" if daily_pnl >= 0 else "❄️"
        
        embed = {
            "title": f"📅 日報統計 (Daily Report)",
            "description": f"截至 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "color": color,
            "fields": [
                {"name": "⬇️ **今日戰績 (Today)**", "value": "----------------", "inline": False},
                {"name": f"{d_emoji} 今日盈虧 (PnL)", "value": f"**{daily_pnl:+.2f} U**", "inline": True},
                {"name": "📊 今日勝率 (Win Rate)", "value": f"{daily_win_rate:.1f}% ({daily_wins}W - {daily_losses}L)", "inline": True},
                {"name": "🚀 今日最大獲利", "value": f"+{max_win:.2f} U", "inline": True},
                {"name": "💸 今日最大虧損", "value": f"{max_loss:.2f} U", "inline": True},
            ],
            "footer": {"text": "Bybit 訊號群 • 日報統計"}
        }
        
        target_url = self.pnl_webhook_url
        self._send({"embeds": [embed]}, webhook_url=target_url)

    def send_pnl_dashboard(self, realized_data: dict, open_positions: list, multi_day_stats: dict = None):
        """
        Sends a comprehensive PnL Dashboard (Realized + Unrealized).
        """
        daily_pnl = realized_data.get("daily_pnl", 0)
        daily_wins = realized_data.get("daily_wins", 0)
        daily_losses = realized_data.get("daily_losses", 0)
        
        total_unrealized = 0
        pos_lines = []
        
        for pos in open_positions:
            symbol = pos.get("symbol")
            u_pnl = float(pos.get("unrealisedPnl", 0))
            size = float(pos.get("size", 0))
            side = pos.get("side")
            
            if size > 0:
                total_unrealized += u_pnl
                icon = "🟢" if u_pnl >= 0 else "🔴"
                pos_lines.append(f"{icon} **{symbol}** ({side}): `{u_pnl:+.2f} U`")
        
        total_equity_change = daily_pnl + total_unrealized
        color = 0xFFD700 if total_equity_change >= 0 else 0xFF0000
        
        fields = [
            {"name": "💰 今日已實現 (Realized)", "value": f"**{daily_pnl:+.2f} U**", "inline": True},
            {"name": "📉 當前未實現 (Unrealized)", "value": f"**{total_unrealized:+.2f} U**", "inline": True},
            {"name": "🏆 今日總結 (Total Change)", "value": f"**{total_equity_change:+.2f} U**", "inline": True},
        ]

        goal_progress = self._get_goal_progress_for_dashboard()
        if goal_progress:
            fields.append({"name": "----------------", "value": "----------------", "inline": False})
            fields.append({
                "name": f"🎯 {goal_progress['month_label']}目標 PnL",
                "value": "\n".join([
                    f"{format_signed_currency(goal_progress['current'])} / {format_currency(goal_progress['target'])}",
                    f"{goal_progress['bar']} {goal_progress['display_pct']:.1f}%",
                    (
                        f"已超標 {format_signed_currency(goal_progress['surplus'])} 👑"
                        if goal_progress["achieved"]
                        else f"還差 {format_currency(goal_progress['remaining'])} 💪"
                    ),
                ]),
                "inline": False
            })

        if multi_day_stats and "daily_groups" in multi_day_stats:
            stats_lines = []
            sorted_dates = sorted(multi_day_stats["daily_groups"].keys(), reverse=True)
            for date_str in sorted_dates:
                pnl = multi_day_stats["daily_groups"][date_str]
                icon = "🟢" if pnl >= 0 else "🔴"
                stats_lines.append(f"{icon} {date_str}: `{pnl:+.2f} U`")
            
            total_pnl = multi_day_stats.get("total_period_pnl", 0)
            total_icon = "💰" if total_pnl >= 0 else "💸"
            stats_lines.append(f"----------------\n{total_icon} **7日累計: {total_pnl:+.2f} U**")
            
            fields.append({"name": "----------------", "value": "----------------", "inline": False})
            fields.append({
                "name": "📅 近7日盈虧統計 (Last 7 Days)",
                "value": "\n".join(stats_lines),
                "inline": False
            })

        fields.append({"name": "----------------", "value": "----------------", "inline": False})
        
        embed = {
            "title": "📊 帳戶盈虧儀表板 (PnL Dashboard)",
            "description": f"截至 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "color": color,
            "fields": fields,
            "footer": {"text": "Bybit 訊號群 • 財務報表"}
        }
        
        if pos_lines:
            embed["fields"].append({
                "name": "📝 持倉明細 (Open Positions)",
                "value": "\n".join(pos_lines),
                "inline": False
            })
        else:
            embed["fields"].append({
                "name": "📝 持倉明細",
                "value": "無持倉 (No Open Positions)",
                "inline": False
            })

        target_url = self.pnl_webhook_url
        self._send({"embeds": [embed]}, webhook_url=target_url)

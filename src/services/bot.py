# src/services/bot.py
"""
Discord Trading Bot — Slash command interface for querying trading data.

Uses discord.py app_commands (slash commands) instead of prefix commands.
All existing services (BybitAdapter, NotionClient, StatsService) are synchronous,
so we use asyncio.to_thread() to avoid blocking the Discord event loop.
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import discord
from discord import app_commands

from ..config import settings
from ..adapters import ADAPTER_MAP
from ..clients.notion import NotionClient
from ..utils.exceptions import ApiException, NotionApiException
from ..utils.logger import log
from .stats import StatsService


class TradingBot(discord.Client):
    """Persistent Discord bot with slash command support for trading queries."""

    def __init__(self):
        intents = discord.Intents.default()
        # No message_content intent needed — we only use slash commands
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self._init_services()
        self._register_commands()

    # ── Service Initialization ──────────────────────────────────────

    def _init_services(self):
        """Initialize exchange adapters, Notion clients, and stats service."""
        configured_exchanges = settings.get("exchanges", {})
        self.adapters: Dict[str, Any] = {}
        self.notion_clients: Dict[str, NotionClient] = {}

        for name, ex_config in configured_exchanges.items():
            adapter_cls = ADAPTER_MAP.get(name)
            if not adapter_cls:
                continue
            kwargs = {
                "api_key": ex_config["api_key"],
                "api_secret": ex_config["api_secret"],
            }
            if ex_config.get("passphrase"):
                kwargs["passphrase"] = ex_config["passphrase"]
            self.adapters[name] = adapter_cls(**kwargs)
            self.notion_clients[name] = NotionClient(
                token=settings["notion_token"],
                database_id=ex_config["notion_db_id"],
            )

        # Primary adapter (prefer Bybit) for StatsService
        primary = self.adapters.get("bybit") or next(iter(self.adapters.values()), None)
        self.stats_service = StatsService(primary) if primary else None

        log.info(f"Bot services initialized: {list(self.adapters.keys())}")

    # ── Lifecycle ───────────────────────────────────────────────────

    async def setup_hook(self):
        """Sync slash commands to Discord on startup."""
        guild_id = settings.get("discord_bot_guild_id")
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info(f"Slash commands synced to guild {guild_id}")
        else:
            await self.tree.sync()
            log.info("Slash commands synced globally (may take up to 1 hour)")

    async def on_ready(self):
        log.info(f"Discord Bot logged in as {self.user} (ID: {self.user.id})")

    # ── Command Registration ────────────────────────────────────────

    def _register_commands(self):
        """Register all slash commands on the command tree."""

        # ── /mgoal ──────────────────────────────────────────────
        @self.tree.command(name="mgoal", description="\U0001f3af \u6708\u76ee\u6a19\u9032\u5ea6 \u2014 Monthly goal progress")
        async def mgoal_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_mgoal_data)
                embed = self._build_mgoal_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /balance ────────────────────────────────────────────
        @self.tree.command(name="balance", description="\U0001f4b0 \u5e33\u6236\u9918\u984d \u2014 Account balance")
        async def balance_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_balance_data)
                embed = self._build_balance_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /today ──────────────────────────────────────────────
        @self.tree.command(name="today", description="\U0001f4c5 \u4eca\u65e5\u6230\u7e3e \u2014 Today\u2019s realized PnL")
        async def today_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_today_data)
                embed = self._build_today_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /positions ──────────────────────────────────────────
        @self.tree.command(name="positions", description="\U0001f4ca \u7576\u524d\u6301\u5009 \u2014 Open positions")
        async def positions_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_positions_data)
                embed = self._build_positions_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /week ───────────────────────────────────────────────
        @self.tree.command(name="week", description="\U0001f4c8 \u8fd17\u65e5\u76c8\u8667 \u2014 Last 7 days PnL")
        async def week_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_week_data)
                embed = self._build_week_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /month ──────────────────────────────────────────────
        @self.tree.command(name="month", description="\U0001f4cb \u672c\u6708\u6458\u8981 \u2014 Monthly summary")
        async def month_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_month_data)
                embed = self._build_month_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /lasttrade ──────────────────────────────────────────
        @self.tree.command(name="lasttrade", description="\U0001f504 \u6700\u8fd1\u5e73\u5009 \u2014 Last closed trade")
        async def lasttrade_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_lasttrade_data)
                embed = self._build_lasttrade_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /orders ─────────────────────────────────────────────
        @self.tree.command(name="orders", description="\U0001f4dd \u639b\u55ae\u67e5\u8a62 \u2014 Active orders")
        async def orders_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                data = await asyncio.to_thread(self._fetch_orders_data)
                embed = self._build_orders_embed(data)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

        # ── /sync ───────────────────────────────────────────────
        @self.tree.command(name="sync", description="\U0001f504 \u624b\u52d5\u540c\u6b65 \u2014 Trigger Notion sync")
        async def sync_command(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                result = await asyncio.to_thread(self._run_sync)
                embed = self._build_sync_result_embed(result)
                await interaction.followup.send(embed=embed)
            except Exception as e:
                await self._send_error(interaction, e)

    # ── Data Fetching (synchronous, run in thread) ──────────────────

    def _fetch_mgoal_data(self) -> dict:
        """Fetch monthly goal progress from Notion."""
        monthly_db_id = settings.get("notion_monthly_db_id")
        if not monthly_db_id:
            return {"error": "NOTION_MONTHLY_DB_ID not configured"}

        now = datetime.now(timezone.utc)
        month_key = now.strftime("%Y-%m %B")

        # Use any NotionClient to query the monthly DB
        nc = next(iter(self.notion_clients.values()), None)
        if not nc:
            return {"error": "No Notion client available"}

        try:
            response = nc._query_database_by_id(
                monthly_db_id,
                filter={"property": "Month", "title": {"equals": month_key}},
                page_size=1,
            )
        except Exception as e:
            return {"error": f"Notion query failed: {e}"}

        results = response.get("results", [])
        if not results:
            return {"month_key": month_key, "no_data": True}

        props = results[0]["properties"]
        return {
            "month_key": month_key,
            "total_pnl": props.get("Total PnL", {}).get("number") or 0,
            "target_pnl": props.get("Target PnL", {}).get("number"),
            "wins": props.get("Wins", {}).get("number") or 0,
            "losses": props.get("Losses", {}).get("number") or 0,
            "total_fees": props.get("Total Fees", {}).get("number") or 0,
            "start_balance": props.get("Start Balance", {}).get("number"),
            "actual_end_balance": props.get("Actual End Balance", {}).get("number"),
            "max_single_win": props.get("Max Single Win", {}).get("number") or 0,
            "max_single_loss": props.get("Max Single Loss", {}).get("number") or 0,
        }

    def _fetch_balance_data(self) -> dict:
        """Fetch wallet balance from all configured exchanges."""
        balances = {}
        for name, adapter in self.adapters.items():
            try:
                result = adapter.get_wallet_balance(account_type="UNIFIED", coin="USDT")
                if result:
                    wallet_list = result.get("result", {}).get("list", [])
                    if wallet_list:
                        equity = round(float(wallet_list[0].get("totalWalletBalance", 0)), 2)
                        balances[name] = equity
            except Exception as e:
                balances[name] = f"Error: {e}"
        return balances

    def _fetch_today_data(self) -> dict:
        """Fetch today's PnL stats."""
        if not self.stats_service:
            return {"error": "StatsService not available"}
        data = self.stats_service.get_daily_report_data()
        # Also fetch current balance
        primary = self.adapters.get("bybit") or next(iter(self.adapters.values()), None)
        if primary:
            try:
                result = primary.get_wallet_balance(account_type="UNIFIED", coin="USDT")
                if result:
                    wallet_list = result.get("result", {}).get("list", [])
                    if wallet_list:
                        data["equity"] = round(float(wallet_list[0].get("totalWalletBalance", 0)), 2)
            except Exception:
                pass
        return data

    def _fetch_positions_data(self) -> dict:
        """Fetch open positions from all exchanges."""
        all_positions = {}
        for name, adapter in self.adapters.items():
            try:
                positions = adapter.get_positions(category="linear")
                active = [p for p in positions if float(p.get("size", 0)) > 0]
                if active:
                    all_positions[name] = active
            except Exception as e:
                all_positions[name] = f"Error: {e}"
        return all_positions

    def _fetch_week_data(self) -> dict:
        """Fetch last 7 days PnL breakdown."""
        if not self.stats_service:
            return {"error": "StatsService not available"}
        return self.stats_service.get_multi_day_stats(days=7)

    def _fetch_month_data(self) -> dict:
        """Fetch full monthly summary from Notion."""
        # Reuse mgoal data which already pulls everything
        return self._fetch_mgoal_data()

    def _fetch_lasttrade_data(self) -> dict:
        """Fetch last closed position details."""
        if not self.stats_service:
            return {"error": "StatsService not available"}
        result = self.stats_service.get_last_closed_position_stats()
        return result or {"empty": True}

    def _fetch_orders_data(self) -> dict:
        """Fetch active orders from all exchanges."""
        all_orders = {}
        for name, adapter in self.adapters.items():
            try:
                orders = adapter.get_active_orders(category="linear")
                if orders:
                    all_orders[name] = orders
            except Exception as e:
                all_orders[name] = f"Error: {e}"
        return all_orders

    def _run_sync(self) -> dict:
        """Run the full sync flow (same as main.py run_sync)."""
        from .sync import SyncService

        configured_exchanges = settings.get("exchanges", {})
        all_new_records = []
        total_fetched = 0

        for exchange_name, ex_config in configured_exchanges.items():
            adapter_cls = ADAPTER_MAP.get(exchange_name)
            if not adapter_cls:
                continue

            kwargs = {"api_key": ex_config["api_key"], "api_secret": ex_config["api_secret"]}
            if ex_config.get("passphrase"):
                kwargs["passphrase"] = ex_config["passphrase"]

            adapter = adapter_cls(**kwargs)
            notion_client = NotionClient(
                token=settings["notion_token"],
                database_id=ex_config["notion_db_id"],
            )
            sync_service = SyncService(
                exchange_adapter=adapter,
                notion_client=notion_client,
                exchange_name=exchange_name,
                journal_db_id=settings.get("notion_journal_db_id"),
                pnl_threshold=settings.get("pnl_threshold", 0),
            )
            result = sync_service.run_sync()
            if result:
                total_fetched += result.get("total_fetched", 0)
                if result.get("created_records"):
                    for r in result["created_records"]:
                        r["_exchange"] = exchange_name
                    all_new_records.extend(result["created_records"])

        return {
            "new_records": all_new_records,
            "total_fetched": total_fetched,
        }

    # ── Embed Builders ──────────────────────────────────────────────

    def _build_mgoal_embed(self, data: dict) -> discord.Embed:
        """Build embed for /mgoal command."""
        if data.get("error"):
            return discord.Embed(title="\u26a0\ufe0f \u932f\u8aa4", description=data["error"], color=0xFF0000)
        if data.get("no_data"):
            return discord.Embed(
                title=f"\U0001f3af {data['month_key']} \u6708\u76ee\u6a19\u9032\u5ea6",
                description="\u5c1a\u7121\u672c\u6708\u8cc7\u6599",
                color=0x95A5A6,
            )

        month_key = data["month_key"]
        total_pnl = data["total_pnl"]
        target_pnl = data.get("target_pnl")
        wins = data["wins"]
        losses = data["losses"]
        total_trades = wins + losses
        win_rate = f"{(wins / total_trades * 100):.0f}%" if total_trades > 0 else "N/A"
        start_balance = data.get("start_balance")
        end_balance = data.get("actual_end_balance")

        color = 0x00FF00 if total_pnl >= 0 else 0xFF0000

        embed = discord.Embed(
            title=f"\U0001f3af {month_key} \u6708\u76ee\u6a19\u9032\u5ea6",
            color=color,
        )

        embed.add_field(name="\U0001f4b0 \u7576\u6708 PnL", value=f"**{total_pnl:+,.2f} U**", inline=True)
        embed.add_field(name="\U0001f4ca \u52dd\u7387", value=f"{win_rate} ({wins}W / {losses}L)", inline=True)

        if start_balance is not None and end_balance is not None:
            roi = ((end_balance - start_balance) / start_balance * 100) if start_balance > 0 else 0
            embed.add_field(
                name="\U0001f4b5 \u9918\u984d\u8b8a\u5316",
                value=f"{start_balance:,.0f} \u2192 {end_balance:,.0f} U ({roi:+.1f}%)",
                inline=False,
            )
        elif end_balance is not None:
            embed.add_field(name="\U0001f4b0 \u7576\u524d\u9918\u984d", value=f"**{end_balance:,.2f} U**", inline=True)

        # Progress toward target
        if target_pnl is not None and target_pnl > 0:
            remaining = target_pnl - total_pnl
            progress_pct = (total_pnl / target_pnl * 100) if target_pnl > 0 else 0

            if remaining <= 0:
                excess = abs(remaining)
                msg = f"\U0001f3c6 **\u5df2\u9054\u6210\u6708\u76ee\u6a19\uff01** \u8d85\u984d **+{excess:,.2f} U**"
            elif progress_pct >= 75:
                msg = f"\U0001f525 \u9032\u5ea6 {progress_pct:.0f}%\uff01\u53ea\u5dee **{remaining:,.2f} U** \u5c31\u9054\u6a19\uff01\u885d\u523a\uff01"
            elif progress_pct >= 50:
                msg = f"\U0001f4aa \u9032\u5ea6 {progress_pct:.0f}%\uff0c\u9084\u5dee **{remaining:,.2f} U**\uff0c\u7a69\u624e\u7a69\u6253\uff01"
            elif progress_pct >= 25:
                msg = f"\U0001f4ca \u9032\u5ea6 {progress_pct:.0f}%\uff0c\u8ddd\u96e2\u76ee\u6a19\u9084\u6709 **{remaining:,.2f} U**\uff0c\u4fdd\u6301\u7bc0\u594f\uff01"
            else:
                msg = f"\U0001f680 \u9032\u5ea6 {progress_pct:.0f}%\uff0c\u8ddd\u96e2\u6708\u76ee\u6a19 **{target_pnl:,.2f} U** \u9084\u5dee **{remaining:,.2f} U**\uff0c\u52a0\u6cb9\uff01"

            # Progress bar
            filled = int(max(0, min(progress_pct, 100)) / 10)
            bar = "\u2588" * filled + "\u2591" * (10 - filled)
            msg += f"\n`[{bar}]` {progress_pct:.1f}%"

            embed.add_field(name="\U0001f3af \u76ee\u6a19\u9032\u5ea6", value=msg, inline=False)
        else:
            embed.add_field(
                name="\U0001f3af \u76ee\u6a19",
                value="\u672a\u8a2d\u5b9a Target PnL",
                inline=False,
            )

        embed.set_footer(text="Trading Bot \u2022 Monthly Goal")
        return embed

    def _build_balance_embed(self, data: dict) -> discord.Embed:
        """Build embed for /balance command."""
        total = 0.0
        lines = []
        for name, value in data.items():
            if isinstance(value, (int, float)):
                total += value
                lines.append(f"**{name.upper()}**: `{value:,.2f} U`")
            else:
                lines.append(f"**{name.upper()}**: \u26a0\ufe0f {value}")

        color = 0x00FF00 if total > 0 else 0x95A5A6

        embed = discord.Embed(
            title="\U0001f4b0 \u5e33\u6236\u9918\u984d",
            description=f"\u67e5\u8a62\u6642\u9593\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            color=color,
        )

        if lines:
            embed.add_field(name="\U0001f4b1 \u5404\u4ea4\u6613\u6240", value="\n".join(lines), inline=False)
        embed.add_field(name="\U0001f4b5 \u7d44\u5408\u7e3d\u984d", value=f"**{total:,.2f} USDT**", inline=False)
        embed.set_footer(text="Trading Bot \u2022 Balance")
        return embed

    def _build_today_embed(self, data: dict) -> discord.Embed:
        """Build embed for /today command."""
        if data.get("error"):
            return discord.Embed(title="\u26a0\ufe0f \u932f\u8aa4", description=data["error"], color=0xFF0000)

        daily_pnl = data.get("daily_pnl", 0)
        wins = data.get("daily_wins", 0)
        losses = data.get("daily_losses", 0)
        total = wins + losses
        win_rate = f"{(wins / total * 100):.0f}%" if total > 0 else "N/A"
        max_win = data.get("daily_max_win", 0)
        max_loss = data.get("daily_max_loss", 0)
        equity = data.get("equity")

        color = 0x00FF00 if daily_pnl >= 0 else 0xFF0000
        emoji = "\U0001f525" if daily_pnl >= 0 else "\u2744\ufe0f"

        embed = discord.Embed(
            title=f"\U0001f4c5 \u4eca\u65e5\u6230\u7e3e ({datetime.now().strftime('%m/%d')})",
            color=color,
        )

        embed.add_field(name=f"{emoji} \u4eca\u65e5\u76c8\u8667", value=f"**{daily_pnl:+,.2f} U**", inline=True)
        embed.add_field(name="\U0001f4ca \u52dd\u7387", value=f"{win_rate} ({wins}W / {losses}L)", inline=True)

        if total > 0:
            embed.add_field(name="\u2705 \u6700\u5927\u7372\u5229", value=f"`{max_win:+,.2f} U`", inline=True)
            embed.add_field(name="\u274c \u6700\u5927\u8667\u640d", value=f"`{max_loss:+,.2f} U`", inline=True)

        if equity is not None:
            embed.add_field(name="\U0001f4b0 \u5e33\u6236\u9918\u984d", value=f"**{equity:,.2f} U**", inline=True)

        if total == 0:
            embed.add_field(name="\U0001f4dd \u72c0\u614b", value="\u4eca\u65e5\u5c1a\u7121\u4ea4\u6613", inline=False)

        embed.set_footer(text="Trading Bot \u2022 Daily Report")
        return embed

    def _build_positions_embed(self, data: dict) -> discord.Embed:
        """Build embed for /positions command."""
        has_positions = False
        embed = discord.Embed(
            title="\U0001f4ca \u7576\u524d\u6301\u5009",
            description=f"\u67e5\u8a62\u6642\u9593\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            color=0x3498DB,
        )

        for ex_name, positions in data.items():
            if isinstance(positions, str):
                embed.add_field(name=f"\u26a0\ufe0f {ex_name.upper()}", value=positions, inline=False)
                continue

            lines = []
            for pos in positions:
                symbol = pos.get("symbol", "UNKNOWN")
                side = pos.get("side", "")
                size = pos.get("size", "0")
                entry = pos.get("avgPrice") or pos.get("entryPrice") or "0"
                mark_price = pos.get("markPrice", "0")
                unrealized = float(pos.get("unrealisedPnl", 0))
                tp = pos.get("takeProfit") or "\u7121"
                sl = pos.get("stopLoss") or "\u7121"
                if str(tp) in ("0", ""):
                    tp = "\u7121"
                if str(sl) in ("0", ""):
                    sl = "\u7121"

                side_emoji = "\U0001f7e2" if side == "Buy" else "\U0001f534"
                pnl_emoji = "\u2705" if unrealized >= 0 else "\u274c"

                line = (
                    f"{side_emoji} **{symbol}** {side} (Size: {size})\n"
                    f"\u2003Entry: `{entry}` \u2003Mark: `{mark_price}`\n"
                    f"\u2003TP: `{tp}` \u2003SL: `{sl}`\n"
                    f"\u2003{pnl_emoji} PnL: `{unrealized:+.2f} U`"
                )
                lines.append(line)
                has_positions = True

            if lines:
                embed.add_field(
                    name=f"\U0001f4b1 {ex_name.upper()}",
                    value="\n\n".join(lines),
                    inline=False,
                )

        if not has_positions:
            embed.add_field(name="\U0001f4ed \u72c0\u614b", value="\u7576\u524d\u7121\u6301\u5009", inline=False)
            embed.color = 0x95A5A6

        embed.set_footer(text="Trading Bot \u2022 Positions")
        return embed

    def _build_week_embed(self, data: dict) -> discord.Embed:
        """Build embed for /week command."""
        if data.get("error"):
            return discord.Embed(title="\u26a0\ufe0f \u932f\u8aa4", description=data["error"], color=0xFF0000)

        daily_groups = data.get("daily_groups", {})
        total_pnl = data.get("total_period_pnl", 0)

        color = 0x00FF00 if total_pnl >= 0 else 0xFF0000

        embed = discord.Embed(
            title=f"\U0001f4c8 \u8fd1 {data.get('days', 7)} \u65e5\u76c8\u8667",
            color=color,
        )

        if daily_groups:
            # Find max abs for bar scaling
            max_abs = max(abs(v) for v in daily_groups.values()) if any(daily_groups.values()) else 1
            lines = []
            for date_str, pnl in daily_groups.items():
                if max_abs > 0:
                    bar_len = int(abs(pnl) / max_abs * 8)
                else:
                    bar_len = 0
                if pnl >= 0:
                    bar = "\U0001f7e9" * bar_len if bar_len > 0 else "\u2796"
                else:
                    bar = "\U0001f7e5" * bar_len if bar_len > 0 else "\u2796"
                emoji = "\u2705" if pnl > 0 else ("\u274c" if pnl < 0 else "\u2796")
                lines.append(f"`{date_str}` {bar} {emoji} **{pnl:+,.2f}**")

            embed.add_field(name="\U0001f4c5 \u6bcf\u65e5 PnL", value="\n".join(lines), inline=False)
        else:
            embed.add_field(name="\U0001f4dd", value="\u7121\u8cc7\u6599", inline=False)

        total_emoji = "\U0001f4b0" if total_pnl >= 0 else "\U0001f4b8"
        embed.add_field(name=f"{total_emoji} \u7e3d\u8a08", value=f"**{total_pnl:+,.2f} U**", inline=False)
        embed.set_footer(text="Trading Bot \u2022 Weekly PnL")
        return embed

    def _build_month_embed(self, data: dict) -> discord.Embed:
        """Build embed for /month command — full monthly summary."""
        if data.get("error"):
            return discord.Embed(title="\u26a0\ufe0f \u932f\u8aa4", description=data["error"], color=0xFF0000)
        if data.get("no_data"):
            return discord.Embed(
                title=f"\U0001f4cb {data['month_key']} \u6708\u5ea6\u6458\u8981",
                description="\u5c1a\u7121\u672c\u6708\u8cc7\u6599",
                color=0x95A5A6,
            )

        month_key = data["month_key"]
        total_pnl = data["total_pnl"]
        wins = data["wins"]
        losses = data["losses"]
        total_trades = wins + losses
        win_rate = f"{(wins / total_trades * 100):.0f}%" if total_trades > 0 else "N/A"
        total_fees = data["total_fees"]
        max_win = data["max_single_win"]
        max_loss = data["max_single_loss"]
        start_balance = data.get("start_balance")
        end_balance = data.get("actual_end_balance")
        target_pnl = data.get("target_pnl")

        color = 0x00FF00 if total_pnl >= 0 else 0xFF0000
        emoji = "\U0001f4c8" if total_pnl >= 0 else "\U0001f4c9"

        embed = discord.Embed(
            title=f"{emoji} {month_key} \u6708\u5ea6\u6458\u8981",
            color=color,
        )

        embed.add_field(name="\U0001f4b0 \u7e3d PnL", value=f"**{total_pnl:+,.2f} U**", inline=True)
        embed.add_field(name="\U0001f3c6 \u52dd\u7387", value=f"{win_rate} ({wins}W / {losses}L)", inline=True)
        embed.add_field(name="\U0001f4ca \u7e3d\u4ea4\u6613\u6578", value=f"{total_trades}", inline=True)
        embed.add_field(name="\U0001f4b8 \u7e3d\u624b\u7e8c\u8cbb", value=f"{total_fees:,.2f} U", inline=True)
        embed.add_field(name="\u2705 \u6700\u5927\u7372\u5229", value=f"{max_win:+,.2f} U", inline=True)
        embed.add_field(name="\u274c \u6700\u5927\u8667\u640d", value=f"{max_loss:+,.2f} U", inline=True)

        if start_balance is not None and end_balance is not None:
            roi = ((end_balance - start_balance) / start_balance * 100) if start_balance > 0 else 0
            embed.add_field(
                name="\U0001f4b5 \u9918\u984d",
                value=f"{start_balance:,.0f} \u2192 {end_balance:,.0f} U ({roi:+.1f}%)",
                inline=False,
            )

        if target_pnl is not None and target_pnl > 0:
            progress = (total_pnl / target_pnl * 100)
            status = "\u2705 \u9054\u6a19" if total_pnl >= target_pnl else f"\u9032\u5ea6 {progress:.0f}%"
            embed.add_field(
                name="\U0001f3af \u76ee\u6a19",
                value=f"Target: {target_pnl:,.2f} U \u2014 {status}",
                inline=False,
            )

        embed.set_footer(text="Trading Bot \u2022 Monthly Summary")
        return embed

    def _build_lasttrade_embed(self, data: dict) -> discord.Embed:
        """Build embed for /lasttrade command."""
        if data.get("error"):
            return discord.Embed(title="\u26a0\ufe0f \u932f\u8aa4", description=data["error"], color=0xFF0000)
        if data.get("empty"):
            return discord.Embed(
                title="\U0001f504 \u6700\u8fd1\u5e73\u5009",
                description="\u7121\u6700\u8fd1\u5e73\u5009\u7d00\u9304",
                color=0x95A5A6,
            )

        symbol = data.get("symbol", "UNKNOWN")
        side = data.get("side", "")
        pnl = data.get("closedPnl", 0)
        qty = data.get("qty", 0)
        entry = data.get("avgEntryPrice", 0)
        exit_price = data.get("avgExitPrice", 0)
        fills = data.get("record_count", 1)

        color = 0x00FF00 if pnl >= 0 else 0xFF0000
        result_emoji = "\u2705" if pnl >= 0 else "\u274c"
        side_emoji = "\U0001f7e2" if side == "Buy" else "\U0001f534"

        embed = discord.Embed(
            title=f"\U0001f504 \u6700\u8fd1\u5e73\u5009 \u2014 {symbol}",
            color=color,
        )

        embed.add_field(name="\U0001f4cd \u65b9\u5411", value=f"{side_emoji} {side}", inline=True)
        embed.add_field(name="\U0001f4e6 \u6578\u91cf", value=f"{qty}", inline=True)
        embed.add_field(name="\U0001f4cb \u6210\u4ea4\u7b46\u6578", value=f"{fills}", inline=True)
        embed.add_field(name="\U0001f4b2 \u9032\u5834\u50f9", value=f"`{entry:,.2f}`", inline=True)
        embed.add_field(name="\U0001f4b2 \u51fa\u5834\u50f9", value=f"`{exit_price:,.2f}`", inline=True)
        embed.add_field(name=f"{result_emoji} PnL", value=f"**{pnl:+,.2f} U**", inline=True)

        embed.set_footer(text="Trading Bot \u2022 Last Trade")
        return embed

    def _build_orders_embed(self, data: dict) -> discord.Embed:
        """Build embed for /orders command."""
        has_orders = False
        embed = discord.Embed(
            title="\U0001f4dd \u639b\u55ae\u67e5\u8a62",
            description=f"\u67e5\u8a62\u6642\u9593\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M')}",
            color=0x3498DB,
        )

        for ex_name, orders in data.items():
            if isinstance(orders, str):
                embed.add_field(name=f"\u26a0\ufe0f {ex_name.upper()}", value=orders, inline=False)
                continue

            lines = []
            for order in orders:
                symbol = order.get("symbol", "UNKNOWN")
                side = order.get("side", "")
                price = order.get("price", "0")
                qty = order.get("qty", "0")
                order_type = order.get("orderType", "Limit")

                side_emoji = "\U0001f7e2" if side == "Buy" else "\U0001f534"
                lines.append(
                    f"{side_emoji} **{symbol}** {side} `{order_type}`\n"
                    f"\u2003Price: `{price}` \u2003Qty: `{qty}`"
                )
                has_orders = True

            if lines:
                embed.add_field(
                    name=f"\U0001f4b1 {ex_name.upper()}",
                    value="\n\n".join(lines),
                    inline=False,
                )

        if not has_orders:
            embed.add_field(name="\U0001f4ed \u72c0\u614b", value="\u7576\u524d\u7121\u639b\u55ae", inline=False)
            embed.color = 0x95A5A6

        embed.set_footer(text="Trading Bot \u2022 Orders")
        return embed

    def _build_sync_result_embed(self, data: dict) -> discord.Embed:
        """Build embed for /sync result."""
        new_records = data.get("new_records", [])
        total_fetched = data.get("total_fetched", 0)

        if new_records:
            total_pnl = sum(r.get("pnl", 0) for r in new_records)
            color = 0x00FF00 if total_pnl >= 0 else 0xFF0000

            trade_lines = []
            for r in new_records:
                icon = "\u2705" if r.get("pnl", 0) > 0 else "\u274c"
                ex = r.get("_exchange", "").upper()
                trade_lines.append(
                    f"{icon} **{r['symbol']}** {r['side']}  `{r['pnl']:+.2f} U`  ({ex})"
                )

            embed = discord.Embed(
                title="\U0001f504 \u540c\u6b65\u5b8c\u6210",
                description=f"\u65b0\u589e {len(new_records)} \u7b46\u4ea4\u6613",
                color=color,
            )
            embed.add_field(
                name="\U0001f4dd \u4ea4\u6613\u660e\u7d30",
                value="\n".join(trade_lines[:15]),  # Limit to 15 to avoid embed size limits
                inline=False,
            )
            embed.add_field(name="\U0001f4b0 PnL", value=f"**{total_pnl:+,.2f} U**", inline=True)
        else:
            embed = discord.Embed(
                title="\U0001f504 \u540c\u6b65\u5b8c\u6210",
                description=f"\u7121\u65b0\u4ea4\u6613\u9700\u540c\u6b65\uff08\u63c3\u63cf {total_fetched} \u7b46\uff09",
                color=0x95A5A6,
            )

        embed.set_footer(text="Trading Bot \u2022 Sync")
        return embed

    # ── Error Handling ──────────────────────────────────────────────

    async def _send_error(self, interaction: discord.Interaction, error: Exception):
        """Send a user-friendly error embed."""
        log.error(f"Command error: {error}", exc_info=True)

        if isinstance(error, ApiException):
            title = "\u26a0\ufe0f \u4ea4\u6613\u6240 API \u932f\u8aa4"
            desc = f"\u4ea4\u6613\u6240 API \u56de\u61c9\u7570\u5e38\uff1a{error}"
        elif isinstance(error, NotionApiException):
            title = "\u26a0\ufe0f Notion API \u932f\u8aa4"
            desc = f"Notion API \u56de\u61c9\u7570\u5e38\uff1a{error}"
        else:
            title = "\u26a0\ufe0f \u7cfb\u7d71\u932f\u8aa4"
            desc = "\u767c\u751f\u672a\u9810\u671f\u7684\u932f\u8aa4\uff0c\u8acb\u7a0d\u5f8c\u518d\u8a66\u3002"

        embed = discord.Embed(title=title, description=desc, color=0xFF0000)
        embed.set_footer(text="Trading Bot")

        try:
            await interaction.followup.send(embed=embed)
        except Exception:
            pass  # Interaction may have expired

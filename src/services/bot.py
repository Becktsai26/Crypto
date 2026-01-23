
import discord
from discord.ext import commands
import asyncio
from ..config import settings
from ..utils.logger import log
from .stats import StatsService

class DiscordBot:
    def __init__(self, stats_service: StatsService):
        self.stats_service = stats_service
        self.token = settings.get("discord_bot_token")
        
        # Intents are required for reading message content
        intents = discord.Intents.default()
        intents.message_content = True 
        
        self.bot = commands.Bot(command_prefix="", intents=intents)
        
        # Register events and commands
        self.bot.event(self.on_ready)
        self.bot.command(name="MONEY")(self.money_command)
        self.bot.command(name="money")(self.money_command) # case insensitive support

    async def on_ready(self):
        log.info(f"Discord Bot logged in as {self.bot.user}")

    async def money_command(self, ctx):
        """
        Handler for the 'MONEY' command.
        """
        log.info(f"Received MONEY command from {ctx.author}")
        
        if not self.stats_service:
            await ctx.send("⚠️ Stats Service not available.")
            return

        # Fetch Data
        report_data = self.stats_service.get_daily_report_data()
        
        # Re-use the formatting logic. 
        # Since Notifier logic is coupled with Webhook, we'll format it here or reuse logic.
        # To keep it DRY, we should ideally extract the formatting logic.
        # For now, I will inline the formatting here to ensure it works with the Bot's context.
        
        embed = self._create_report_embed(report_data)
        await ctx.send(embed=embed)

    def _create_report_embed(self, report_data: dict) -> discord.Embed:
        equity = report_data.get("total_equity", 0)
        daily_pnl = report_data.get("daily_pnl", 0)
        daily_wins = report_data.get("daily_wins", 0)
        daily_losses = report_data.get("daily_losses", 0)
        daily_total = daily_wins + daily_losses
        daily_win_rate = (daily_wins / daily_total * 100) if daily_total > 0 else 0
        
        monthly_pnl = report_data.get("monthly_pnl", 0)
        monthly_wins = report_data.get("monthly_wins", 0)
        monthly_losses = report_data.get("monthly_losses", 0)
        monthly_total = monthly_wins + monthly_losses
        monthly_win_rate = (monthly_wins / monthly_total * 100) if monthly_total > 0 else 0
        
        color = 0xFFD700 if daily_pnl >= 0 else 0x95a5a6
        d_emoji = "🔥" if daily_pnl >= 0 else "❄️"
        m_emoji = "👑" if monthly_pnl >= 0 else "📉"
        
        embed = discord.Embed(
            title="📅 日報與月報統計 (Daily & Monthly Report)",
            description=f"截至 {discord.utils.utcnow().strftime('%Y-%m-%d %H:%M')}",
            color=color
        )
        embed.add_field(name="💰 帳戶總資產 (Total Equity)", value=f"**${equity:,.2f} U**", inline=False)
        embed.add_field(name="--------------------------------", value="⬇️ **今日戰績 (Today)**", inline=False)
        embed.add_field(name=f"{d_emoji} 今日盈虧", value=f"**{daily_pnl:+.2f} U**", inline=True)
        embed.add_field(name="📊 今日勝率", value=f"{daily_win_rate:.1f}% ({daily_wins}W - {daily_losses}L)", inline=True)
        embed.add_field(name="--------------------------------", value="⬇️ **本月戰績 (Month)**", inline=False)
        embed.add_field(name=f"{m_emoji} 本月盈虧", value=f"**{monthly_pnl:+.2f} U**", inline=True)
        embed.add_field(name="🏆 本月勝率", value=f"{monthly_win_rate:.1f}% ({monthly_wins}W - {monthly_losses}L)", inline=True)
        embed.set_footer(text="Bybit 訊號群 • 資產統計 (Bot)")
        
        return embed

    async def start(self):
        if not self.token:
            log.error("No Discord Bot Token found!")
            return
        try:
            await self.bot.start(self.token)
        except Exception as e:
            log.error(f"Failed to start Discord Bot: {e}")

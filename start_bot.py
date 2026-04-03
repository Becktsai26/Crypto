# start_bot.py
"""
Entry point for the Discord Trading Bot.
Runs persistently — keep the terminal open or use a process manager.
"""
import sys
import os

# Adjust the Python path to include the project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.config import settings
from src.services.bot import TradingBot
from src.utils.logger import log


def main():
    log.info("-----------------------------------------")
    log.info("--- Trading Discord Bot Starting ---")
    log.info("-----------------------------------------")

    token = settings.get("discord_bot_token")
    if not token:
        log.critical("DISCORD_BOT_TOKEN is not set in .env! Cannot start bot.")
        sys.exit(1)

    bot = TradingBot()
    bot.run(token)


if __name__ == "__main__":
    main()

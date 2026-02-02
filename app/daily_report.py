import datetime
from zoneinfo import ZoneInfo
from app.config.settings import settings
from app.config.logging import logger
from app.infrastructure.notion.client import NotionClient
from app.infrastructure.gemini_client import GeminiClient
from app.infrastructure.line_client import LineNotifyClient
from app.services.analytics import AnalyticsService
from app.services.report_formatter import ReportFormatter

def main():
    logger.info("Starting Daily Trading Report task...")

    # 1. Determine Date
    try:
        tz = ZoneInfo(settings.TZ)
    except Exception:
        logger.warning(f"Invalid timezone {settings.TZ}, falling back to UTC")
        tz = datetime.timezone.utc

    today = datetime.datetime.now(tz).date()
    today_str = today.isoformat()
    logger.info(f"Target Date: {today_str}")

    # 2. Fetch Trades from Notion
    try:
        notion = NotionClient()
        trades = notion.query_daily_trades(today_str)
        logger.info(f"Retrieved {len(trades)} trades for {today_str}")
    except Exception as e:
        logger.error(f"Failed to fetch trades from Notion: {e}")
        # We might want to notify about this error?
        return

    # 3. Handle No Trades
    line_client = LineNotifyClient()

    if not trades:
        logger.info("No trades found. Sending 'No Trades' report.")
        message = ReportFormatter.format_no_trades(today_str)
        if not settings.DRY_RUN:
            line_client.send_message(message)
        else:
            logger.info(f"[DRY RUN] Message:\n{message}")
        return

    # 4. Calculate Stats (Local)
    stats = AnalyticsService.calculate_stats(trades)
    logger.info(f"Stats calculated: {stats}")

    # 5. Analyze with Gemini (AI)
    gemini = GeminiClient()
    analysis = gemini.analyze_trades(trades)
    logger.info("Gemini analysis completed.")

    # 6. Format Report
    report_message = ReportFormatter.format_daily_report(today_str, stats, analysis, trades)

    # 7. Send via Line Notify
    if not settings.DRY_RUN:
        line_client.send_message(report_message)
    else:
        logger.info(f"[DRY RUN] Message:\n{report_message}")

    logger.info("Daily Trading Report task completed.")

if __name__ == "__main__":
    main()

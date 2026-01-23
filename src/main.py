# src/main.py
import sys
import os

# Adjust the Python path to include the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import settings
from src.adapters.bybit import BybitAdapter
from src.clients.notion import NotionClient
from src.services.sync import SyncService
from src.services.reporter import ReporterService
from src.utils.exceptions import ApiException, NotionApiException
from src.utils.logger import log
from src.utils.alerter import send_discord_alert

def main():
    """
    Main function to run the synchronization or reporting service based on arguments.
    """
    # 1. Load Configuration
    if not settings:
        log.critical("Critical: Configuration could not be loaded. Exiting.")
        sys.exit(1)

    # 2. Argument parsing
    if len(sys.argv) > 1 and (sys.argv[1] == '--report' or sys.argv[1] == '--report-excel'):
        run_reporter(output_format='excel' if sys.argv[1] == '--report-excel' else 'csv')
    else:
        run_sync()

def run_sync():
    """Runs the data synchronization process."""
    log.info("-----------------------------------------")
    log.info("--- Bybit to Notion Sync Service ---")
    log.info("-----------------------------------------")
    try:
        log.info("Initializing Bybit and Notion clients for sync...")
        bybit_adapter = BybitAdapter(
            api_key=settings["bybit_api_key"],
            api_secret=settings["bybit_api_secret"]
        )
        notion_client = NotionClient(
            token=settings["notion_token"],
            database_id=settings["notion_db_id"]
        )
        sync_service = SyncService(
            exchange_adapter=bybit_adapter,
            notion_client=notion_client
        )
        sync_service.run_sync()
    except (ApiException, NotionApiException) as e:
        error_message = f"An API error occurred during synchronization: {e}"
        log.error(error_message)
        send_discord_alert(settings.get("discord_webhook_url"), error_message)
        sys.exit(1)
    except Exception as e:
        error_message = f"An unexpected error occurred: {e}"
        log.critical(error_message, exc_info=True)
        send_discord_alert(settings.get("discord_webhook_url"), error_message)
        sys.exit(1)

def run_reporter(output_format: str):
    """Runs the report generation process."""
    log.info("-----------------------------------------")
    log.info("--- Notion PnL Report Generator ---")
    log.info("-----------------------------------------")
    try:
        log.info("Initializing Notion client for reporting...")
        notion_client = NotionClient(
            token=settings["notion_token"],
            database_id=settings["notion_db_id"]
        )
        reporter_service = ReporterService(notion_client=notion_client)
        reporter_service.generate_pnl_report(output_format=output_format)
    except (NotionApiException) as e:
        log.error(f"An API error occurred during report generation: {e}")
        sys.exit(1)
    except Exception as e:
        log.critical(f"An unexpected error occurred during report generation: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()

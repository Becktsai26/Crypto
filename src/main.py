# src/main.py
import sys
import os

# Adjust the Python path to include the project root
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.config import settings
from src.adapters import ADAPTER_MAP
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
    """Runs the data synchronization process for all configured exchanges."""
    log.info("-----------------------------------------")
    log.info("--- Multi-Exchange to Notion Sync ---")
    log.info("-----------------------------------------")

    configured_exchanges = settings.get("exchanges", {})
    if not configured_exchanges:
        log.warning("No exchanges configured. Nothing to sync.")
        return

    has_error = False

    for exchange_name, ex_config in configured_exchanges.items():
        log.info(f"=== Syncing {exchange_name.upper()} ===")
        try:
            adapter_cls = ADAPTER_MAP.get(exchange_name)
            if not adapter_cls:
                log.warning(f"No adapter for exchange '{exchange_name}'. Skipping.")
                continue

            adapter_kwargs = {
                "api_key": ex_config["api_key"],
                "api_secret": ex_config["api_secret"],
            }
            if "passphrase" in ex_config and ex_config["passphrase"]:
                adapter_kwargs["passphrase"] = ex_config["passphrase"]

            adapter = adapter_cls(**adapter_kwargs)
            notion_client = NotionClient(
                token=settings["notion_token"],
                database_id=ex_config["notion_db_id"]
            )
            sync_service = SyncService(
                exchange_adapter=adapter,
                notion_client=notion_client
            )
            sync_service.run_sync()
            log.info(f"=== {exchange_name.upper()} sync complete ===")

        except (ApiException, NotionApiException) as e:
            error_message = f"API error during {exchange_name} sync: {e}"
            log.error(error_message)
            send_discord_alert(settings.get("discord_webhook_url"), error_message)
            has_error = True
            continue  # Don't let one exchange failure stop others
        except Exception as e:
            error_message = f"Unexpected error during {exchange_name} sync: {e}"
            log.critical(error_message, exc_info=True)
            send_discord_alert(settings.get("discord_webhook_url"), error_message)
            has_error = True
            continue

    if has_error:
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

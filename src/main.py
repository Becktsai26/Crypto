# src/main.py
import sys
import os
from datetime import datetime, timezone

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
                notion_client=notion_client,
                exchange_name=exchange_name,
                journal_db_id=settings.get("notion_journal_db_id"),
                pnl_threshold=settings.get("pnl_threshold", 0),
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

    # After all exchanges sync, update monthly summary once (portfolio-level)
    monthly_db_id = settings.get("notion_monthly_db_id")
    if monthly_db_id:
        try:
            _update_monthly_summary(configured_exchanges, monthly_db_id)
        except Exception as e:
            log.error(f"Monthly summary update failed (non-fatal): {e}")

    if has_error:
        sys.exit(1)


def _update_monthly_summary(configured_exchanges: dict, monthly_db_id: str):
    """
    Aggregates current month's trades across ALL exchange raw DBs
    and upserts a single portfolio-level row to the monthly summary DB.
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        month_end = month_start.replace(year=now.year + 1, month=1)
    else:
        month_end = month_start.replace(month=now.month + 1)

    month_key = now.strftime("%Y-%m")
    log.info(f"=== Aggregating portfolio monthly summary for {month_key} ===")

    total_pnl = 0.0
    total_fees = 0.0
    wins = 0
    losses = 0
    max_win = 0.0
    max_loss = 0.0

    # Query each exchange's raw DB and merge
    for exchange_name, ex_config in configured_exchanges.items():
        try:
            notion_client = NotionClient(
                token=settings["notion_token"],
                database_id=ex_config["notion_db_id"],
            )
            pages = notion_client.query_current_month_trades(
                month_start_iso=month_start.isoformat(),
                month_end_iso=month_end.isoformat(),
            )
            for page in pages:
                props = page["properties"]
                pnl = props.get("PnL", {}).get("number")
                fee = props.get("Fee", {}).get("number")
                if pnl is None:
                    continue
                total_pnl += pnl
                total_fees += (fee or 0.0)
                if pnl > 0:
                    wins += 1
                    max_win = max(max_win, pnl)
                elif pnl < 0:
                    losses += 1
                    max_loss = min(max_loss, pnl)

            log.info(f"  [{exchange_name}] queried {len(pages)} trades for {month_key}")
        except Exception as e:
            log.error(f"  [{exchange_name}] failed to query monthly trades: {e}")

    stats = {
        "total_pnl": round(total_pnl, 2),
        "total_fees": round(total_fees, 2),
        "wins": wins,
        "losses": losses,
        "max_single_win": round(max_win, 2),
        "max_single_loss": round(max_loss, 2),
    }

    log.info(f"Portfolio {month_key}: PnL={stats['total_pnl']}, W={wins}, L={losses}")

    # Use any NotionClient to call upsert (only needs token, not a specific DB)
    first_ex = next(iter(configured_exchanges.values()))
    notion_client = NotionClient(
        token=settings["notion_token"],
        database_id=first_ex["notion_db_id"],
    )
    notion_client.upsert_monthly_summary(monthly_db_id, month_key, stats)
    log.info(f"=== Monthly summary for {month_key} updated ===")


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

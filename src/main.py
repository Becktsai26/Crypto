# src/main.py
import sys
import os
import json
import requests
from datetime import datetime, timedelta, timezone

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
from src.utils.goal_progress import (
    build_monthly_goal_progress,
    format_currency,
    format_signed_currency,
    get_newly_crossed_milestones,
    load_goal_milestone_state,
    save_goal_milestone_state,
)


MILESTONE_EMBEDS = {
    25: {"title_prefix": "🏁", "description": "起步完成，繼續累積。", "color": 0x3498DB},
    50: {"title_prefix": "🏁", "description": "正式進入下半場，維持節奏。", "color": 0x2ECC71},
    75: {"title_prefix": "🏁", "description": "最後一段，先穩再推。", "color": 0xF1C40F},
    100: {"title_prefix": "👑", "description": "本月任務完成，接下來守成果。", "color": 0x9B59B6},
}


def _post_discord_embeds(webhook_url: str, embeds: list) -> bool:
    response = requests.post(
        webhook_url,
        data=json.dumps({"embeds": embeds}),
        headers={"Content-Type": "application/json"},
    )
    if response.status_code not in [200, 201, 204]:
        log.error(f"Failed to send Discord payload: {response.status_code} {response.text}")
        return False
    return True


def _build_goal_progress_from_monthly_stats(monthly_stats: dict, now: datetime = None):
    target_pnl = settings.get("monthly_pnl_target", 0)
    current_pnl = (monthly_stats or {}).get("total_pnl")
    if target_pnl <= 0 or current_pnl is None:
        return None

    progress_time = now or datetime.now()
    return build_monthly_goal_progress(current_pnl, target_pnl, progress_time)


def _send_goal_milestones(webhook_url: str, goal_progress: dict, now: datetime) -> None:
    month_key = now.strftime("%Y-%m")
    milestone_state = load_goal_milestone_state()
    newly_crossed = get_newly_crossed_milestones(goal_progress, month_key, milestone_state)
    if not newly_crossed:
        return
    sent_any = False

    for milestone in newly_crossed:
        milestone_spec = MILESTONE_EMBEDS.get(milestone)
        if not milestone_spec:
            continue

        title = (
            f"{milestone_spec['title_prefix']} {goal_progress['month_label']}目標達成"
            if milestone == 100
            else f"{milestone_spec['title_prefix']} {goal_progress['month_label']}目標已達 {milestone}%"
        )
        embed = {
            "title": title,
            "description": milestone_spec["description"],
            "color": milestone_spec["color"],
            "fields": [
                {
                    "name": "目前",
                    "value": f"{format_signed_currency(goal_progress['current'])} / {format_currency(goal_progress['target'])}",
                    "inline": False,
                },
                {
                    "name": "進度",
                    "value": f"{goal_progress['display_pct']:.1f}%",
                    "inline": False,
                },
            ],
            "footer": {"text": "Bybit-Notion Sync Bot"},
        }

        if _post_discord_embeds(webhook_url, [embed]):
            month_state = set(milestone_state.get(month_key, []))
            month_state.add(milestone)
            milestone_state[month_key] = sorted(month_state)
            sent_any = True

    if sent_any:
        save_goal_milestone_state(milestone_state)

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
    elif len(sys.argv) > 1 and sys.argv[1] == '--backfill-balance':
        run_backfill_balance()
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
    all_new_records = []  # collect newly created records across all exchanges

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
            result = sync_service.run_sync()
            if result and result.get("created_records"):
                for r in result["created_records"]:
                    r["_exchange"] = exchange_name
                all_new_records.extend(result["created_records"])

            # Fetch wallet balance and update last trade's Account Balance
            try:
                balance_data = adapter.get_wallet_balance(account_type="UNIFIED", coin="USDT")
                if balance_data:
                    wallet_list = balance_data.get("result", {}).get("list", [])
                    if wallet_list:
                        equity = round(float(wallet_list[0].get("totalWalletBalance", 0)), 2)
                        ex_config["_current_balance"] = equity
                        log.info(f"[{exchange_name}] Wallet balance: {equity} USDT")

                        # Update last created trade page with balance
                        last_page_id = result.get("last_page_id") if result else None
                        if last_page_id:
                            notion_client.update_page_balance(last_page_id, equity)
            except Exception as e:
                log.error(f"[{exchange_name}] Failed to fetch/update wallet balance (non-fatal): {e}")

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
    monthly_stats = None
    monthly_db_id = settings.get("notion_monthly_db_id")
    if monthly_db_id:
        try:
            monthly_stats = _update_monthly_summary(configured_exchanges, monthly_db_id)
        except Exception as e:
            log.error(f"Monthly summary update failed (non-fatal): {e}")

    # Send Discord summary
    _send_sync_discord_summary_v2(all_new_records, monthly_stats)

    if has_error:
        sys.exit(1)


def _update_monthly_summary(configured_exchanges: dict, monthly_db_id: str) -> dict:
    """
    Aggregates current month's trades across ALL exchange raw DBs
    and upserts a single portfolio-level row to the monthly summary DB.
    Returns the stats dict for Discord notification.
    """
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if now.month == 12:
        month_end = month_start.replace(year=now.year + 1, month=1)
    else:
        month_end = month_start.replace(month=now.month + 1)

    # Match existing Notion format: "2026-04 April"
    month_key = now.strftime("%Y-%m %B")
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

    # Phase 1.5: Add Actual End Balance (sum of all exchange balances)
    portfolio_balance = sum(
        ex.get("_current_balance", 0)
        for ex in configured_exchanges.values()
        if ex.get("_current_balance")
    )
    if portfolio_balance > 0:
        stats["actual_end_balance"] = portfolio_balance
        log.info(f"Portfolio balance: {portfolio_balance} USDT")

    log.info(f"Portfolio {month_key}: PnL={stats['total_pnl']}, W={wins}, L={losses}")

    # Use any NotionClient to call upsert (only needs token, not a specific DB)
    first_ex = next(iter(configured_exchanges.values()))
    notion_client = NotionClient(
        token=settings["notion_token"],
        database_id=first_ex["notion_db_id"],
    )

    # Phase 1.5: Auto-fill Start Balance from previous month's Actual End Balance
    prev_month = month_start - timedelta(days=1)
    prev_month_key = prev_month.strftime("%Y-%m %B")
    prev_end_balance = notion_client.get_monthly_actual_end_balance(monthly_db_id, prev_month_key)
    if prev_end_balance is not None:
        stats["start_balance"] = prev_end_balance
        log.info(f"Previous month ({prev_month_key}) Actual End Balance: {prev_end_balance}")

    notion_client.upsert_monthly_summary(monthly_db_id, month_key, stats)
    log.info(f"=== Monthly summary for {month_key} updated ===")

    stats["month_key"] = month_key
    return stats


def _send_sync_discord_summary(new_records: list, monthly_stats: dict = None):
    """
    Sends a Discord embed summarizing the sync results.
    Always sends — shows 'no new trades' if nothing was synced.
    """
    webhook_url = settings.get("discord_webhook_url")
    if not webhook_url:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Build trade lines ──
    if new_records:
        total_pnl = sum(r["pnl"] for r in new_records)
        wins = sum(1 for r in new_records if r["pnl"] > 0)
        losses = sum(1 for r in new_records if r["pnl"] < 0)
        color = 0x00FF00 if total_pnl >= 0 else 0xFF0000
        emoji = "🟢" if total_pnl >= 0 else "🔴"

        trade_lines = []
        for r in new_records:
            result_icon = "✅" if r["pnl"] > 0 else "❌"
            ex = r.get("_exchange", "").upper()
            trade_lines.append(
                f"{result_icon} **{r['symbol']}** {r['side']}  `{r['pnl']:+.2f} U`  ({ex})"
            )
        trades_text = "\n".join(trade_lines)

        fields = [
            {"name": f"📝 新同步 {len(new_records)} 筆交易", "value": trades_text, "inline": False},
            {"name": "💰 本次 PnL", "value": f"**{total_pnl:+.2f} U**", "inline": True},
            {"name": "📊 勝負", "value": f"{wins}W / {losses}L", "inline": True},
        ]
    else:
        color = 0x95A5A6
        emoji = "✔️"
        fields = [
            {"name": "📝 同步結果", "value": "無新交易需同步", "inline": False},
        ]

    # ── Monthly summary ──
    if monthly_stats:
        mk = monthly_stats.get("month_key", "")
        m_pnl = monthly_stats.get("total_pnl", 0)
        m_wins = monthly_stats.get("wins", 0)
        m_losses = monthly_stats.get("losses", 0)
        m_total = m_wins + m_losses
        m_wr = f"{(m_wins / m_total * 100):.0f}%" if m_total > 0 else "N/A"
        m_icon = "📈" if m_pnl >= 0 else "📉"

        fields.append({"name": "─────────────────────", "value": f"**{m_icon} {mk} 月度累計**", "inline": False})
        fields.append({"name": "月 PnL", "value": f"**{m_pnl:+.2f} U**", "inline": True})
        fields.append({"name": "月勝率", "value": f"{m_wr} ({m_wins}W / {m_losses}L)", "inline": True})

        # Show portfolio balance if available
        balance = monthly_stats.get("actual_end_balance")
        if balance:
            fields.append({"name": "💰 帳戶餘額", "value": f"**{balance:,.2f} U**", "inline": True})

    embed = {
        "title": f"{emoji} Notion Sync 完成",
        "description": f"同步時間：{now_str}",
        "color": color,
        "fields": fields,
        "footer": {"text": "Bybit-Notion Sync Bot"},
    }

    try:
        requests.post(
            webhook_url,
            data=json.dumps({"embeds": [embed]}),
            headers={"Content-Type": "application/json"},
        )
        log.info("Discord sync summary sent.")
    except Exception as e:
        log.error(f"Failed to send Discord summary: {e}")


def _send_sync_discord_summary_v2(new_records: list, monthly_stats: dict = None):
    """
    Sends a Discord embed summarizing the sync results.
    Always sends a summary, even when there are no new trades.
    """
    webhook_url = settings.get("discord_webhook_url")
    if not webhook_url:
        return

    now = datetime.now()
    now_str = now.strftime("%Y-%m-%d %H:%M")

    if new_records:
        total_pnl = sum(r["pnl"] for r in new_records)
        wins = sum(1 for r in new_records if r["pnl"] > 0)
        losses = sum(1 for r in new_records if r["pnl"] < 0)
        color = 0x00FF00 if total_pnl >= 0 else 0xFF0000
        emoji = "📈" if total_pnl >= 0 else "📉"

        trade_lines = []
        for record in new_records:
            result_icon = "🟢" if record["pnl"] > 0 else ("🔴" if record["pnl"] < 0 else "⚪")
            exchange_name = record.get("_exchange", "").upper()
            trade_lines.append(
                f"{result_icon} **{record['symbol']}** {record['side']}  `{record['pnl']:+.2f} U`  ({exchange_name})"
            )

        fields = [
            {"name": f"🧾 本次新增 {len(new_records)} 筆交易", "value": "\n".join(trade_lines), "inline": False},
            {"name": "💰 本次 PnL", "value": f"**{total_pnl:+.2f} U**", "inline": True},
            {"name": "🏁 勝負", "value": f"{wins}W / {losses}L", "inline": True},
        ]
    else:
        color = 0x95A5A6
        emoji = "🧭"
        fields = [
            {"name": "🧾 本次同步", "value": "本次沒有新交易。", "inline": False},
        ]

    if monthly_stats:
        month_key = monthly_stats.get("month_key", "")
        monthly_pnl = monthly_stats.get("total_pnl", 0)
        monthly_wins = monthly_stats.get("wins", 0)
        monthly_losses = monthly_stats.get("losses", 0)
        total_trades = monthly_wins + monthly_losses
        monthly_win_rate = f"{(monthly_wins / total_trades * 100):.0f}%" if total_trades > 0 else "N/A"
        month_icon = "📈" if monthly_pnl >= 0 else "📉"

        fields.append({"name": "----------------", "value": f"**{month_icon} {month_key} 月度摘要**", "inline": False})
        fields.append({"name": "📊 月 PnL", "value": f"**{monthly_pnl:+.2f} U**", "inline": True})
        fields.append({"name": "🏆 月勝率", "value": f"{monthly_win_rate} ({monthly_wins}W / {monthly_losses}L)", "inline": True})

        balance = monthly_stats.get("actual_end_balance")
        if balance is not None:
            fields.append({"name": "💼 帳戶餘額", "value": f"**{balance:,.2f} U**", "inline": True})

    goal_progress = _build_goal_progress_from_monthly_stats(monthly_stats, now=now)
    if goal_progress:
        fields.append({
            "name": "🎯 本月目標",
            "value": "\n".join([
                (
                    f"{format_signed_currency(goal_progress['current'])} / "
                    f"{format_currency(goal_progress['target'])} "
                    f"({goal_progress['display_pct']:.1f}%)"
                ),
                (
                    f"已超標 {format_signed_currency(goal_progress['surplus'])}"
                    if goal_progress["achieved"]
                    else f"還差 {format_currency(goal_progress['remaining'])}"
                ),
            ]),
            "inline": False,
        })

    embed = {
        "title": f"{emoji} Notion Sync 摘要",
        "description": f"同步時間：{now_str}",
        "color": color,
        "fields": fields,
        "footer": {"text": "Bybit-Notion Sync Bot"},
    }

    try:
        if not _post_discord_embeds(webhook_url, [embed]):
            return
        log.info("Discord sync summary sent.")
        if goal_progress:
            _send_goal_milestones(webhook_url, goal_progress, now)
    except Exception as e:
        log.error(f"Failed to send Discord summary: {e}")


def run_backfill_balance():
    """
    Backfills Monthly Performance Tracker Start Balance by chaining
    each month's Actual End Balance to the next month's Start Balance.
    Run this after manually filling in Actual End Balance values.
    """
    log.info("-----------------------------------------")
    log.info("--- Backfill Monthly Start Balance ---")
    log.info("-----------------------------------------")

    monthly_db_id = settings.get("notion_monthly_db_id")
    if not monthly_db_id:
        log.error("NOTION_MONTHLY_DB_ID not configured. Cannot backfill.")
        return

    first_ex = next(iter(settings.get("exchanges", {}).values()), None)
    if not first_ex:
        log.error("No exchange configured. Cannot backfill.")
        return

    notion_client = NotionClient(
        token=settings["notion_token"],
        database_id=first_ex["notion_db_id"],
    )

    # Define months to chain (Jan 2026 through current month)
    now = datetime.now(timezone.utc)
    months = []
    current = datetime(2026, 1, 1, tzinfo=timezone.utc)
    while current <= now:
        months.append(current.strftime("%Y-%m %B"))
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    log.info(f"Chaining Start Balance for {len(months)} months...")

    prev_end_balance = None
    for month_key in months:
        # Get this month's Actual End Balance
        actual_end = notion_client.get_monthly_actual_end_balance(monthly_db_id, month_key)

        if prev_end_balance is not None:
            # Set this month's Start Balance = previous month's Actual End Balance
            stats = {"start_balance": prev_end_balance}
            # We need to do a targeted update — use upsert with minimal stats
            try:
                response = notion_client._query_database_by_id(
                    monthly_db_id,
                    filter={"property": "Month", "title": {"equals": month_key}},
                    page_size=1,
                )
                results = response.get("results", [])
                if results:
                    existing_start = results[0]["properties"].get("Start Balance", {}).get("number")
                    if existing_start is None:
                        notion_client.client.pages.update(
                            page_id=results[0]["id"],
                            properties={"Start Balance": {"number": prev_end_balance}},
                        )
                        log.info(f"  {month_key}: Set Start Balance = {prev_end_balance}")
                    else:
                        log.info(f"  {month_key}: Start Balance already set ({existing_start}), skipping")
            except Exception as e:
                log.error(f"  {month_key}: Failed to update Start Balance: {e}")

        if actual_end is not None:
            log.info(f"  {month_key}: Actual End Balance = {actual_end}")
            prev_end_balance = actual_end
        else:
            log.info(f"  {month_key}: No Actual End Balance found")
            prev_end_balance = None

    log.info("Backfill complete.")


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

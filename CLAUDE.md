# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-exchange trading monitor and sync system. Fetches trade data from Bybit, Binance, OKX, MEXC, Bitget via REST API, syncs each to its own Notion database, monitors Bybit real-time positions via WebSocket, and sends Discord notifications. UI labels are in Traditional Chinese.

## Commands

```bash
# Setup
pip install -r requirements.txt
cp .env.example .env  # then fill in credentials

# Run sync (all configured exchanges → Notion)
python src/main.py

# Generate PnL reports
python src/main.py --report          # CSV
python src/main.py --report-excel    # Excel

# Start real-time WebSocket monitor (Bybit only)
python start_monitor.py

# Docker
docker-compose up -d                                    # monitor
docker-compose up pnl-report --profile manual           # one-off PnL report
```

No test suite exists. No linter is configured.

## Architecture

```
Exchanges (Bybit, Binance, OKX, MEXC, Bitget)
       │
       ├──→ Adapters (src/adapters/{exchange}.py)
       │       Each implements BaseExchangeAdapter (src/adapters/base.py)
       │       fetch_transaction_log() normalizes to standard format:
       │         {type, change, fee, orderId, symbol, side, qty, tradePrice, transactionTime}
       │
       ├──→ BybitMonitor (src/monitor/ws_manager.py)  ← Bybit-only runtime
       │       Private WebSocket stream, debounced TP/SL (5s),
       │       execution aggregation (3s buffer), PnL retry with backoff,
       │       triggers SyncService 3s after fills
       │
       └──→ DiscordNotifier (src/monitor/notifier.py)
               Embeds with position footer, emoji indicators

SyncService (src/services/sync.py)
       Iterates all configured exchanges, fetches transaction log in
       exchange-specific chunk sizes, aggregates split fills by orderId,
       PnL threshold 0.5 USDT
               │
               └──→ NotionClient (src/clients/notion.py)
                       One instance per exchange (different database_id),
                       deduplicates by Transaction ID, chunked queries
                       (50 IDs/batch), rate limited (0.4s/req),
                       uses direct HTTP (not SDK) for Windows compatibility
```

**Entry points**: `src/main.py` (sync/report CLI — all exchanges), `start_monitor.py` (WebSocket monitor — Bybit only)

**Config**: `src/config.py` loads from `.env`. Per-exchange: `{PREFIX}_API_KEY`, `{PREFIX}_API_SECRET`, `{PREFIX}_NOTION_DB_ID`, `{PREFIX}_API_PASSPHRASE` (OKX/Bitget). Global: `NOTION_TOKEN`, `DISCORD_WEBHOOK_URL`. Backward compatible with legacy `BYBIT_API_KEY` + `NOTION_DB_ID`.

**Adapter registry**: `src/adapters/__init__.py` exports `ADAPTER_MAP` dict mapping exchange names to adapter classes.

## Key Design Decisions

- **Adapter pattern** in `src/adapters/base.py` — `BaseExchangeAdapter` defines `exchange_name`, `default_account_type`, `default_category`, `max_query_window_ms` properties + abstract methods. Each exchange normalizes its API response to a common format.
- **Per-exchange Notion database** — each exchange writes to a separate Notion DB via its own `NotionClient` instance
- **NotionClient uses raw HTTP requests** instead of the `notion-client` SDK to work around Windows compatibility issues
- **Execution debouncing** in ws_manager.py — split fills are buffered for 3 seconds then sent as a single aggregated notification with weighted average price
- **TP/SL debounce** — 5-second window suppresses transient glitches (A→B→A reverts); also 60-minute cooldown on redundant PnL updates
- **Ghost signal prevention** — on WebSocket connect, active orders/positions are prefetched so reconnection doesn't generate false "new order" notifications
- **Error isolation** — one exchange sync failure doesn't block others

## Notion Database Schema

Each exchange needs its own Notion database with columns matching exactly: **Symbol** (Select), **Side** (Select), **Size** (Number), **Entry/Exit Price** (Number), **Fee** (Number), **PnL** (Number), **Timestamp** (Date), **Subaccount** (Text), **Transaction ID** (Rich Text), **Trade** (Title).

## Rate Limits

| Exchange | Rate Limit | Sleep Interval | Max Query Window |
|----------|-----------|----------------|------------------|
| Bybit | 120 req/min | 0.55s | 7 days |
| Binance | 1200 req/min | 0.1s | 7 days |
| OKX | 10 req/2s | 0.25s | 90 days |
| MEXC | 20 req/2s | 0.15s | 90 days |
| Bitget | 20 req/s | 0.1s | 90 days |
| Notion | 3 req/sec | 0.4s | — |

Notion filter: max 50 IDs per "or" condition → chunked deduplication queries.

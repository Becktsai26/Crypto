# Changelog

## [1.5.0] - 2026-04-02 — Account Balance 自動記錄 + 月度餘額串接

### 需求背景
Trade 首頁與月度摘要（資產成長追蹤）過去全靠手動維護。Phase 1 已完成 Exchange/Result 自動填入、Journal stub 建立、月度 PnL 聚合。Phase 1.5 補上帳戶餘額自動記錄，讓整條資料鏈從「交易 → 餘額 → 月度摘要」全自動化。

### 新增功能
- **Account Balance 自動寫入**：sync 完成後呼叫 Bybit `get_wallet_balance()` API，將 `totalWalletBalance`（已實現績效後的餘額，不含未實現浮盈虧）寫入 Main_Account 最新一筆交易的 `Account Balance` 欄位
- **Actual End Balance 自動寫入**：月度摘要（資產成長追蹤）新增寫入 `Actual End Balance`，值為所有交易所餘額加總
- **Start Balance 自動串接**：月度摘要自動查詢上月的 `Actual End Balance`，寫入當月 `Start Balance`（如果當月 Start Balance 已有手動填的值，不覆蓋）
- **Discord 通知加上帳戶餘額**：每次 sync 的 Discord embed 新增 `💰 帳戶餘額` 欄位
- **`--backfill-balance` CLI 指令**：一次性串接歷史月份的 Start Balance。手動填入各月 Actual End Balance 後，跑 `python src/main.py --backfill-balance` 即可自動串接

### 改動檔案
- `src/adapters/base.py` — 新增 `get_wallet_balance()` 預設方法（return None），Bybit 已有 override
- `src/clients/notion.py` — 新增 `update_page_balance()`、`get_monthly_actual_end_balance()`；property mapping 支援 `Account Balance`；`upsert_monthly_summary` 支援 `Actual End Balance` + `Start Balance`
- `src/services/sync.py` — `run_sync()` 回傳值新增 `last_page_id`
- `src/main.py` — sync 後取餘額更新交易頁；月度摘要寫入餘額並串接 Start Balance；Discord 通知加餘額；新增 `--backfill-balance` CLI

### 已知限制
- 只有 Bybit 支援 wallet balance API，其他交易所 adapter 尚未實作
- 批次 sync 多筆交易時，Account Balance 只寫在最新一筆（因為 API 只能取「現在」的餘額）
- Q1 歷史交易的 Account Balance 無法自動回填（Bybit API 不提供歷史餘額查詢）
- 需手動在 Notion 填入各月 Actual End Balance 後，再跑 `--backfill-balance` 串接 Start Balance

---

## [1.0.0] - 2026-04-02 — Phase 1 Trade Dashboard 自動化 + Journal 結構

### 需求背景
把 Trade 頁面從手動摘要頁改成由 Notion 資料庫驅動的 portfolio dashboard。採雙層架構：`Main_Account` 放系統自動寫入的 raw trade，新增 `Trade_Journal` 放人工分析欄位（Setup Type / Notes / R Multiple）。首頁與月度摘要不再手動維護，改由 sync 自動聚合。

### 核心設計
- **雙層分離**：raw trade（Main_Account）與交易日誌（Trade_Journal）用 Notion Relation 連結，系統欄位與人工欄位解耦
- **Portfolio-first 月度摘要**：所有交易所 sync 完成後才做一次跨交易所聚合，避免互相覆蓋
- **Non-fatal error handling**：Journal stub 和月度摘要失敗不阻斷主 sync
- **100% 向後相容**：新 env var 都是 optional，不設定就跳過

### 新增功能
- **Exchange 自動填入**：每筆 raw trade 寫入 `Exchange` select 欄位（Phase 1 固定 `bybit`）
- **Result 自動計算**：PnL > 0 → Win、< 0 → Loss、= 0 → BE
- **Trade Journal stub**：sync 寫入 Main_Account 後，自動在 Trade_Journal 建立 stub row（Relation 連結 + Transaction ID），人工欄位留空
- **月度摘要自動聚合**：跨交易所聚合 Total PnL / Total Fees / Wins / Losses / Max Single Win / Max Single Loss，upsert 到資產成長追蹤
- **PnL 門檻可配置**：`PNL_THRESHOLD` env var，預設 0（記錄所有已實現交易）
- **Discord sync 摘要通知**：每次 sync 發送 embed，含新交易明細 + 月度累計

### 新增環境變數
```
NOTION_JOURNAL_DB_ID=""    # Trade_Journal DB ID
NOTION_MONTHLY_DB_ID=""    # 資產成長追蹤 DB ID
PNL_THRESHOLD="0"          # PnL 過濾門檻（預設 0 = 全部記錄）
```

### Notion 部署前置作業（見 RELEASE_CHECKLIST.md）
1. Main_Account 新增 `Exchange` select 欄位（選項 `bybit`）
2. 新建 `Trade_Journal` DB（Journal Entry / Transaction ID / Trade Link / Setup Type / Risk Amount / R Multiple / Notes）
3. 確保 Notion integration 分享給三個 DB

### 改動檔案
- `src/config.py` — 新增 3 個 env var
- `src/clients/notion.py` — create_records 回傳 page ID；新增 journal stub / monthly upsert / 月份查詢方法；property mapping 加 Exchange + Result
- `src/services/sync.py` — constructor 擴充；record 加 exchange + result；可配置 threshold；journal stub 呼叫
- `src/main.py` — 傳遞新參數；跨交易所月度摘要；Discord sync 摘要通知
- `.env.example` — 文件化新 env var
- `RELEASE_CHECKLIST.md` — 部署前置作業 checklist

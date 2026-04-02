# HANDOFF — 2026-04-02

讀這份文件就能接續上個 session 的所有工作。

---

## 目前狀態

**Phase 1 + 1.5 程式碼已完成，尚未在部署機器上實際跑過。**

最新 commit：`7767f9d` — feat: Phase 1.5 — auto Account Balance, Actual End Balance, Start Balance chaining

---

## 這個 Session 做了什麼

### Phase 1 (commit `fb82216`)
- `Main_Account` 每筆交易自動填入 `Exchange`（bybit）和 `Result`（Win/Loss/BE）
- 新增 `Trade_Journal` stub 機制：sync 後自動建立 Relation 連結的 journal row，人工欄位（Setup Type / R Multiple / Notes）留空，不覆蓋
- 跨交易所月度摘要自動聚合（Total PnL / Fees / Wins / Losses）寫入 `資產成長追蹤`
- `PNL_THRESHOLD` 可配置，預設改為 `0`（記錄所有已實現交易）
- 多交易所月度不互蓋 bug 已修：改在 exchange loop 結束後統一聚合一次
- 新增 `RELEASE_CHECKLIST.md`

### Phase 1.5 (commit `7767f9d`)
- sync 後呼叫 Bybit `get_wallet_balance()` → 寫入最新一筆交易的 `Account Balance`（用 `totalWalletBalance`，不含未實現浮盈虧）
- 月度摘要新增寫入 `Actual End Balance`（所有交易所餘額加總）
- 月度摘要自動串接 `Start Balance`（從上月 `Actual End Balance` 來），不覆蓋手動已填的值
- Discord 通知新增 `💰 帳戶餘額` 欄位
- 新增 `--backfill-balance` CLI 指令（歷史月份 Start Balance 串接）
- 新增 `CHANGELOG.md`

---

## 部署前必做（Notion 手動設定）

詳見 `RELEASE_CHECKLIST.md`，摘要如下：

1. **Main_Account DB** — 新增 `Exchange` select 欄位，加選項 `bybit`（小寫）
   - `Result` 欄位已存在 ✓
   - `Account Balance` 欄位已存在 ✓

2. **Trade_Journal DB** — **全新建立**，欄位：
   | 名稱 | 類型 |
   |------|------|
   | Journal Entry | Title |
   | Transaction ID | Rich text |
   | Trade Link | Relation → Main_Account |
   | Setup Type | Select |
   | Risk Amount | Number |
   | R Multiple | Number |
   | Notes | Rich text |
   → 建好後複製 DB ID → 填入 `.env` 的 `NOTION_JOURNAL_DB_ID`

3. **資產成長追蹤** — 確認 integration 有分享，複製 DB ID → 填入 `.env` 的 `NOTION_MONTHLY_DB_ID`
   - `Actual End Balance` 欄位已存在 ✓
   - `Start Balance` 欄位已存在 ✓

4. **Notion integration** — 確保已分享給上述三個 DB

---

## 環境變數（.env 需新增）

```env
NOTION_JOURNAL_DB_ID="<Trade_Journal DB ID>"
NOTION_MONTHLY_DB_ID="<資產成長追蹤 DB ID>"
PNL_THRESHOLD="0"
```

---

## 使用方式

```bash
# 日常使用（雙擊即可）
run_all.bat

# 或等價的：
python src/main.py

# 一次性：串接歷史 Start Balance
python src/main.py --backfill-balance

# 產報表
python src/main.py --report
python src/main.py --report-excel
```

`run_all.bat` 單次執行會依序完成：
1. Sync trades → Main_Account（含 Exchange + Result）
2. Journal stubs → Trade_Journal
3. Wallet balance → 更新最後一筆交易 Account Balance
4. 月度摘要（Actual End Balance + Start Balance 串接）
5. Discord 通知

---

## 部署後驗證清單

1. Main_Account 新交易有 `Exchange=bybit`、`Result=Win/Loss/BE`
2. Main_Account 最新一筆交易有 `Account Balance` 值
3. Trade_Journal 有對應 stub row，Trade Link 指向 Main_Account，人工欄位為空
4. 資產成長追蹤當月 row 有 Total PnL / Wins / Losses / Actual End Balance
5. 當月 Start Balance 自動從上月串接（前提：上月有 Actual End Balance）
6. 再跑一次 sync（無新交易）→ 月度數字更新但不重複建 stub
7. Discord 通知含 💰 帳戶餘額

---

## 已知限制（Phase 1 scope 外）

| 限制 | 說明 |
|------|------|
| Journal 只補新交易 | 現有歷史交易不會自動補 stub，需後續 backfill script |
| Q1 Account Balance 無法回填 | Bybit API 不提供歷史餘額，需手動填入月底餘額 |
| 只有 Bybit 有餘額 | 其他交易所 adapter 尚未實作 get_wallet_balance |
| 首頁排版不動 | Phase 1 只做後端，Trade 首頁 callout 仍需手動維護 |
| Account Balance 只寫最後一筆 | 批次 sync 多筆時，只有最新的一筆寫入當前餘額 |

---

## 下一步建議（Phase 2 候選）

1. **Q1 Account Balance 手動回填** → 手動在 Notion 填入 1-3 月底的 Actual End Balance，然後跑 `--backfill-balance` 串接 Start Balance
2. **歷史 Journal backfill** → 寫一個 script 遍歷 Main_Account 所有頁面，對沒有對應 journal stub 的補建
3. **Trade 首頁改版** → 移除手動 callout，以 linked database 顯示當月 portfolio summary row
4. **多交易所 / 子帳戶** → Phase 2：Sync_State DB 管理各 source 的 cursor，Bybit subaccount 擴充

---

## 關鍵檔案位置

| 檔案 | 用途 |
|------|------|
| `src/main.py` | 入口點，sync 編排 + Discord 通知 + backfill CLI |
| `src/services/sync.py` | 同步邏輯（fetch → aggregate → dedup → write） |
| `src/clients/notion.py` | Notion API 客戶端（所有 DB 操作） |
| `src/config.py` | 設定載入（env var） |
| `src/adapters/bybit.py` | Bybit API（含 get_wallet_balance） |
| `RELEASE_CHECKLIST.md` | 部署前 Notion 手動設定清單 |
| `CHANGELOG.md` | 需求背景與版本記錄 |
| `.env.example` | 所有 env var 範本 |

# Phase 1 Release Checklist

> 部署 Phase 1（Trade Dashboard 自動化 + Journal）前，必須完成以下前置作業。
> 程式碼已就緒，但 Notion workspace 需要手動調整才能正確運作。

## Notion DB 設定

### 1. Main_Account — 新增 Exchange 欄位
- [ ] 開啟 Main_Account database
- [ ] 新增 property：`Exchange`，類型 `Select`
- [ ] 新增選項：`bybit`（小寫）
- [ ] 確認欄位名稱**完全一致**（含大小寫）

> 若未新增，sync 寫入時 Notion API 會回 400。

### 2. Trade_Journal — 新建 DB
- [ ] 在 Trade workspace 下新建一個 database，命名為 `Trade_Journal`
- [ ] 建立以下欄位：

| 欄位名稱 | 類型 | 說明 |
|----------|------|------|
| Journal Entry | Title | 程式自動填入 Transaction ID |
| Transaction ID | Rich text | 去重用，對應 Main_Account 的 Transaction ID |
| Trade Link | Relation → Main_Account | 一對一連結到 raw trade |
| Setup Type | Select | 選項：Trend Follow / Reversal / Breakout / Range / Scalp / Other |
| Risk Amount | Number | 手動填寫 |
| R Multiple | Number | 手動填寫 |
| Notes | Rich text | 手動填寫 |

- [ ] 複製 database ID（從 URL 取得）
- [ ] 寫入 `.env`：`NOTION_JOURNAL_DB_ID="<你的 DB ID>"`

> 這是**新建的 DB**，不是沿用現有的 Trading Journal。舊 Journal 的 schema 不相容。

### 3. 資產成長追蹤 — 取得 DB ID
- [ ] 開啟現有的「資產成長追蹤」database
- [ ] 確認 title 欄位名稱為 `Month`
- [ ] 確認以下 number 欄位存在且名稱一致：`Total PnL` / `Total Fees` / `Wins` / `Losses` / `Max Single Win` / `Max Single Loss`
- [ ] 複製 database ID
- [ ] 寫入 `.env`：`NOTION_MONTHLY_DB_ID="<你的 DB ID>"`

### 4. Integration 權限
- [ ] 確認 Notion integration 已分享給以下三個 DB：
  - Main_Account
  - Trade_Journal（新建的）
  - 資產成長追蹤

## 環境變數

- [ ] `.env` 新增：
  ```
  NOTION_JOURNAL_DB_ID="<Trade_Journal DB ID>"
  NOTION_MONTHLY_DB_ID="<資產成長追蹤 DB ID>"
  PNL_THRESHOLD="0"
  ```

## 已知限制（Phase 1）

- **歷史 journal 不補齊**：啟用後只有新 sync 進來的交易會自動建 journal stub。Main_Account 中已存在的歷史交易不會自動補 relation。需要後續 backfill script 處理。
- **單交易所路徑**：Phase 1 只驗證 `bybit:main`。多交易所架構已預留但未啟用 subaccount / 多帳戶。
- **首頁不動**：Trade 首頁排版維持現狀，Phase 1 只做後端自動化。

## 部署後驗證

1. 跑一次 sync → 確認 Main_Account 新交易有 `Exchange=bybit` 和 `Result=Win/Loss/BE`
2. 確認 Trade_Journal 有對應的 stub row，Trade Link 指向正確
3. 確認資產成長追蹤當月 row 被 upsert（Total PnL / Wins / Losses 等正確）
4. 再跑一次 sync（無新交易）→ 確認不重複建立 journal stub，monthly row 只更新不新增
5. 在 Trade_Journal 手動填寫 Setup Type → 再跑 sync → 確認不被覆蓋
6. 移除 `NOTION_JOURNAL_DB_ID` 和 `NOTION_MONTHLY_DB_ID` → 跑 sync → 確認向後相容正常

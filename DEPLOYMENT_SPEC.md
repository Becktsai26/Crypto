# 部署規劃書：Crypto 專案 Docker 容器化

**專案名稱**：Crypto (Bybit to Notion Sync)
**日期**：2026-02-02
**目標**：將 Python 自動化腳本容器化，實現環境隔離、依賴管理標準化，並確保 Windows/macOS 跨平台協作的穩定性。

---

## 1. 部署架構概述 (Architecture Overview)

本專案將採用 **Docker** 進行封裝，並使用 **Docker Compose** 進行服務編排。根據程式的兩種運作模式（背景同步、報表產出），將規劃兩個獨立的服務定義。

### 1.1 核心組件
*   **Base Image**: `python:3.10-slim` (基於 Debian 的輕量級映像檔，平衡體積與相容性)。
*   **Orchestration**: Docker Compose (V2)。
*   **Configuration**: 透過環境變數注入 (`.env` file)，嚴禁將機敏資訊 (API Keys) 打包進映像檔。

---

## 2. 映像檔規格 (Image Specification)

### 2.1 Dockerfile 定義
目標映像檔需滿足以下建置需求：

*   **基礎環境**：
    *   OS: Linux (Debian Bullseye/Bookworm slim variant)
    *   Runtime: Python 3.10+
*   **環境變數設定**：
    *   `PYTHONDONTWRITEBYTECODE=1` (避免產生 .pyc 垃圾檔)
    *   `PYTHONUNBUFFERED=1` (確保 Log 即時輸出至 Container stdout)
    *   `PYTHONPATH=/app` (修正 src 模組路徑問題，取代程式碼中的 `sys.path` hack)
*   **依賴安裝**：
    *   將 `requirements.txt` 複製並執行 `pip install`。
    *   利用 Docker Cache 機制優化建置速度（先 Copy requirements 再 Copy code）。
*   **檔案結構**：
    *   工作目錄：`/app`
    *   程式碼路徑：`/app/src`

### 2.2 忽略檔案 (.dockerignore)
為縮減映像檔體積並確保安全性，以下檔案**不可**包含在映像檔中：
*   `.git/` (版本控制檔)
*   `.env` (機敏設定檔)
*   `venv/`, `.conda/` (本地虛擬環境)
*   `__pycache__/`
*   `*.log`, `*.csv`, `*.xlsx` (本地產出的資料)

---

## 3. 跨平台協作規範 (Cross-Platform Collaboration) **[NEW]**

為解決 Windows (CRLF) 與 macOS/Linux (LF) 換行符號不一致，導致 Script 在 Docker 容器內無法執行的問題，必須強制規範 Git 的行為。

### 3.1 Git 屬性設定 (.gitattributes)
專案根目錄需新增 `.gitattributes` 檔案，強制特定檔案在 Repository 中始終保持 `LF` 格式。

**檔案內容規範**：
```text
# 預設行為：自動處理文字檔
* text=auto

# 強制核心程式碼與設定檔使用 LF (Linux 標準)
# 避免 Windows 開發者 commit CRLF 導致 Docker 執行錯誤
*.py text eol=lf
*.sh text eol=lf
*.md text eol=lf
Dockerfile text eol=lf
docker-compose.yml text eol=lf
requirements.txt text eol=lf
.env.example text eol=lf
```

---

## 4. 服務編排規格 (Docker Compose Specification)

系統需定義兩個服務 Profile，共用同一個 Docker Image，但執行指令與掛載設定不同。

### 4.1 服務 A：背景同步服務 (`crypto-sync`)
*   **用途**：長期運行，定期執行同步任務。
*   **執行策略**：
    *   由於程式本身為單次執行 (Run-once) 腳本，容器需透過 Shell Script 實作無窮迴圈 (Loop)。
    *   **週期**：預設每 3600 秒 (1小時) 喚醒一次。
*   **重啟策略 (Restart Policy)**：`unless-stopped` (確保伺服器重開機後自動啟動)。
*   **Volume 掛載**：
    *   (選填) 掛載 `./sync.log` 以便在 Host 端查看歷史紀錄。

### 4.2 服務 B：報表產出工具 (`crypto-report`)
*   **用途**：手動觸發，產出年度 PnL 報表 (Excel/CSV)。
*   **執行策略**：單次執行容器 (Ephemeral Container)，執行完畢後自動移除。
*   **Volume 掛載 (關鍵)**：
    *   必須將 Host 當前目錄 (`./`) 掛載至 Container 工作目錄 (`/app`)。
    *   **目的**：確保容器內生成的 `.xlsx` 或 `.csv` 檔案能寫回 Host 的 Windows 資料夾，而不是留在容器內隨容器消失。
*   **Profile 設定**：標記為 `profiles: ["tools"]`，避免使用 `docker-compose up` 時自動啟動此服務。

---

## 5. 環境與配置管理 (Configuration Management)

### 5.1 環境變數注入
所有機敏資訊由 `.env` 檔案管理，Docker Compose 需設定 `env_file` 屬性。

**必要變數清單**：
*   `BYBIT_API_KEY`
*   `BYBIT_API_SECRET`
*   `NOTION_TOKEN`
*   `NOTION_DB_ID`
*   `DISCORD_WEBHOOK_URL` (Optional)

### 5.2 程式碼相容性調整
*   **路徑處理**：確認 Python 程式碼中讀取 `.env` 的邏輯相容於 Docker 環境（目前的 `config.py` 邏輯已相容，因 Docker 會將變數注入為 System Environment Variables）。

---

## 6. 操作流程規範 (Operational Procedures)

### 6.1 部署與更新
*   **初次部署**：
    1.  建立 `.env` 檔案。
    2.  `docker-compose up -d crypto-sync`
*   **程式碼更新**：
    1.  `git pull`
    2.  `docker-compose build` (重新建置 Image)
    3.  `docker-compose up -d crypto-sync` (重建並重啟容器)

### 6.2 報表產出
使用者需在終端機執行以下指令來獲得 Excel 檔：
```bash
# 產出 Excel
docker-compose run --rm crypto-report python src/main.py --report-excel
```

### 6.3 監控與除錯
*   **查看即時 Log**：`docker-compose logs -f crypto-sync`
*   **檢查容器狀態**：`docker-compose ps`

---

## 7. 未來擴充建議 (Future Roadmap)

*   **CI/CD 整合**：建立 GitHub Actions，當 Master 分支更新時自動 Build Docker Image 並 Push 到 Docker Hub 或私有 Registry。
*   **排程優化**：若同步邏輯變複雜，建議將 Shell Loop 改為容器內的 Crond (Cron Daemon) 或改用外部排程器 (如 Airflow, Jenkins) 觸發。

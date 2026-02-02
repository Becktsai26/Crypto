import os
import sys
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """
    應用程式全域設定。
    自動從環境變數 (.env) 讀取並驗證型別。
    """
    # Bybit 設定
    BYBIT_API_KEY: str
    BYBIT_API_SECRET: str
    BYBIT_TESTNET: bool = False  # 預設為 False (Mainnet)

    # Notion 設定
    NOTION_TOKEN: str
    NOTION_DB_ID: str
    NOTION_SNAPSHOT_DB_ID: Optional[str] = None  # 新功能：資產快照 DB

    # Discord 設定 (Optional)
    DISCORD_WEBHOOK_URL: Optional[str] = None
    DISCORD_PNL_WEBHOOK_URL: Optional[str] = None

    # Gemini & Line Notify (Daily Report)
    GEMINI_API_KEY: Optional[str] = None
    LINE_NOTIFY_TOKEN: Optional[str] = None

    # Notion Field Mapping (Daily Report)
    NOTION_FIELD_DATE: str = "Date"
    NOTION_FIELD_PAIR: str = "pair"
    NOTION_FIELD_DIRECTION: str = "direction"
    NOTION_FIELD_RESULT_R: str = "result_r"
    NOTION_FIELD_NOTE: str = "note"

    # Environment
    TZ: str = "Asia/Taipei"
    DRY_RUN: bool = False
    
    # 應用程式行為
    LOG_LEVEL: str = "INFO"
    SYNC_INTERVAL_SECONDS: int = 3600

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True  # 區分大小寫，通常環境變數建議全大寫

# Singleton Instance
try:
    settings = Settings()
except Exception as e:
    # 這裡只做基本 print，因為 logging 模組可能依賴 settings，避免循環
    # 但為了讓使用者知道缺了什麼，我們把錯誤印出來
    # 注意：如果不符合條件，程式會在 import 時就報錯
    print(f"CRITICAL: Failed to load configuration. Missing env vars? {e}", file=sys.stderr)
    settings = None

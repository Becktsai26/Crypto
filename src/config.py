# src/config.py
import os
from dotenv import load_dotenv
# We can't use the logger here easily because it might not be configured yet
# and can cause circular dependencies. For config errors, printing to stderr is standard.

def load_config():
    """
    Loads configuration from environment variables or a .env file.
    It validates that all necessary variables are present.
    Supports multi-exchange configuration via {PREFIX}_API_KEY / {PREFIX}_API_SECRET / {PREFIX}_NOTION_DB_ID.
    """
    # Load environment variables from .env file if it exists
    # Useful for local development
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)

    config = {
        # Legacy Bybit keys (backward compatibility for ws_manager, manual_report, etc.)
        "bybit_api_key": os.getenv("BYBIT_API_KEY"),
        "bybit_api_secret": os.getenv("BYBIT_API_SECRET"),
        "notion_token": os.getenv("NOTION_TOKEN"),
        "notion_db_id": os.getenv("NOTION_DB_ID"),
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL"),
        "discord_pnl_webhook_url": os.getenv("DISCORD_PNL_WEBHOOK_URL"),
        "discord_bot_token": os.getenv("DISCORD_BOT_TOKEN"),
        "exchanges": {},
    }

    # Per-exchange configuration: (name, env_prefix, requires_passphrase)
    exchange_defs = [
        ("bybit",   "BYBIT",   False),
        ("binance", "BINANCE", False),
        ("okx",     "OKX",     True),
        ("mexc",    "MEXC",    False),
        ("bitget",  "BITGET",  True),
    ]

    for name, prefix, needs_passphrase in exchange_defs:
        api_key = os.getenv(f"{prefix}_API_KEY")
        api_secret = os.getenv(f"{prefix}_API_SECRET")
        notion_db_id = os.getenv(f"{prefix}_NOTION_DB_ID")

        if api_key and api_secret and notion_db_id:
            ex_config = {
                "api_key": api_key,
                "api_secret": api_secret,
                "notion_db_id": notion_db_id,
            }
            if needs_passphrase:
                ex_config["passphrase"] = os.getenv(f"{prefix}_API_PASSPHRASE")
            config["exchanges"][name] = ex_config

    # Backward compatibility: if legacy Bybit keys are set but BYBIT_NOTION_DB_ID is not,
    # auto-populate exchanges["bybit"] using the global NOTION_DB_ID
    if "bybit" not in config["exchanges"] and config["bybit_api_key"] and config["bybit_api_secret"] and config["notion_db_id"]:
        config["exchanges"]["bybit"] = {
            "api_key": config["bybit_api_key"],
            "api_secret": config["bybit_api_secret"],
            "notion_db_id": config["notion_db_id"],
        }

    # Validate: NOTION_TOKEN is always required
    if not config["notion_token"]:
        raise ValueError("Missing required environment variable: NOTION_TOKEN")

    # Validate: at least one exchange must be configured
    if not config["exchanges"]:
        raise ValueError("No exchange configured. Set at least BYBIT_API_KEY + BYBIT_API_SECRET + NOTION_DB_ID (or {PREFIX}_NOTION_DB_ID).")

    return config

# Load configuration once when the module is imported
try:
    settings = load_config()
except ValueError as e:
    # Using print here is intentional as logger might not be set up
    # and this is a critical startup failure.
    print(f"Configuration Error: {e}", file=os.sys.stderr)
    settings = {}

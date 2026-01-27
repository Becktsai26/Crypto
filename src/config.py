# src/config.py
import os
import json
from dotenv import load_dotenv

# We can't use the logger here easily because it might not be configured yet
# and can cause circular dependencies. For config errors, printing to stderr is standard.

def load_config():
    """
    Loads configuration from environment variables or a .env file.
    It validates that all necessary variables are present.
    """
    # Load environment variables from .env file if it exists
    # Useful for local development
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path=dotenv_path)

    config = {
        "notion_token": os.getenv("NOTION_TOKEN"),
        "notion_db_id": os.getenv("NOTION_DB_ID"),
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL"),
        "discord_pnl_webhook_url": os.getenv("DISCORD_PNL_WEBHOOK_URL"),
        "discord_bot_token": os.getenv("DISCORD_BOT_TOKEN"),
    }

    # Handle Multi-Account Config
    accounts_json = os.getenv("BYBIT_ACCOUNTS")
    accounts = []

    if accounts_json:
        try:
            accounts = json.loads(accounts_json)
            # Validate structure
            for acc in accounts:
                if not all(k in acc for k in ("name", "api_key", "api_secret")):
                     raise ValueError("Invalid BYBIT_ACCOUNTS structure. Each account must have 'name', 'api_key', and 'api_secret'.")
        except json.JSONDecodeError as e:
             raise ValueError(f"Invalid JSON in BYBIT_ACCOUNTS: {e}")
    else:
        # Fallback to single account legacy config
        api_key = os.getenv("BYBIT_API_KEY")
        api_secret = os.getenv("BYBIT_API_SECRET")
        if api_key and api_secret:
            accounts.append({
                "name": "Main",
                "api_key": api_key,
                "api_secret": api_secret
            })
            # Keep legacy keys in config for backward compatibility if needed elsewhere
            config["bybit_api_key"] = api_key
            config["bybit_api_secret"] = api_secret

    if not accounts:
        raise ValueError("No Bybit accounts configured. Set BYBIT_ACCOUNTS (JSON) or BYBIT_API_KEY/SECRET.")

    config["bybit_accounts"] = accounts

    # Validate that essential variables are set
    required_vars = ["notion_token", "notion_db_id"]
    missing_vars = [key for key, value in config.items() if key in required_vars and not value]

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    return config

# Load configuration once when the module is imported
try:
    settings = load_config()
except ValueError as e:
    # Using print here is intentional as logger might not be set up
    # and this is a critical startup failure.
    print(f"Configuration Error: {e}", file=os.sys.stderr)
    settings = {}

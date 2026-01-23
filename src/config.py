# src/config.py
import os
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
        "bybit_api_key": os.getenv("BYBIT_API_KEY"),
        "bybit_api_secret": os.getenv("BYBIT_API_SECRET"),
        "notion_token": os.getenv("NOTION_TOKEN"),
        "notion_db_id": os.getenv("NOTION_DB_ID"),
        "discord_webhook_url": os.getenv("DISCORD_WEBHOOK_URL"),
        "discord_pnl_webhook_url": os.getenv("DISCORD_PNL_WEBHOOK_URL"),
        "discord_bot_token": os.getenv("DISCORD_BOT_TOKEN"),
    }

    # Validate that essential variables are set
    required_vars = ["bybit_api_key", "bybit_api_secret", "notion_token", "notion_db_id"]
    missing_vars = [key for key, value in config.items() if key in required_vars and not value]

    if missing_vars:
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

    # The discord webhook is optional, so no validation for it.
    
    return config

# Load configuration once when the module is imported
try:
    settings = load_config()
except ValueError as e:
    # Using print here is intentional as logger might not be set up
    # and this is a critical startup failure.
    print(f"Configuration Error: {e}", file=os.sys.stderr)
    settings = {}

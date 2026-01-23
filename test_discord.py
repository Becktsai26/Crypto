
import os
from dotenv import load_dotenv
from src.utils.alerter import send_discord_alert

# Explicitly load from correct path
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(".env")

url = os.getenv("DISCORD_WEBHOOK_URL")
print(f"URL loaded: {url[:30]}..." if url else "URL NOT LOADED")

if url:
    print("Sending test message...")
    send_discord_alert(url, "✅ (Test Message) Bybit to Notion Sync is correctly configured and running!")
    print("Done.")
else:
    print("ERROR: DISCORD_WEBHOOK_URL not found in environment.")

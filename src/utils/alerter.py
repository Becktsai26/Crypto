# src/utils/alerter.py
import requests
from typing import Optional

def send_discord_alert(webhook_url: Optional[str], message: str):
    """
    Sends a message to a Discord webhook.

    Args:
        webhook_url: The Discord webhook URL.
        message: The message to send.
    """
    if not webhook_url:
        print("Discord webhook URL is not configured. Cannot send alert.")
        return

    data = {
        "content": message,
        "username": "Bybit-Notion Sync Bot"
    }
    
    try:
        response = requests.post(webhook_url, json=data)
        if response.status_code >= 300:
            print(f"Failed to send Discord alert. Status code: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord alert: {e}")


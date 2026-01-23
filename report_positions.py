from src.adapters.bybit import BybitAdapter
from src.config import settings
from src.monitor.notifier import DiscordNotifier
import json

def report_positions():
    # Initialize adapter and notifier
    adapter = BybitAdapter(
        api_key=settings["bybit_api_key"],
        api_secret=settings["bybit_api_secret"]
    )
    notifier = DiscordNotifier()
    
    # Fetch positions from Bybit
    print("Fetching positions...")
    positions = adapter.get_positions(category="linear", settleCoin="USDT")
    
    # Prepare message content
    active_positions = [p for p in positions if float(p.get("size", 0)) > 0]
    
    if not active_positions:
        print("No active positions found.")
        # Optional: Send a "No positions" message to Discord
        notifier._send({
            "embeds": [{
                "title": "📊 當前持倉快照",
                "description": "目前沒有任何持倉。",
                "color": 9807270
            }]
        })
        return

    print(f"Found {len(active_positions)} active positions.")
    
    # Send report for each position
    for pos in active_positions:
        notifier.send_position_update(pos)
        print(f"Reported: {pos['symbol']} {pos['side']} Size: {pos['size']}")

if __name__ == "__main__":
    report_positions()

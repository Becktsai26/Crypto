
import os
import sys
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Adjust path and import
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src.adapters.bybit import BybitAdapter

load_dotenv()

def main():
    api_key = os.getenv("BYBIT_API_KEY")
    api_secret = os.getenv("BYBIT_API_SECRET")
    adapter = BybitAdapter(api_key, api_secret)
    
    # Scan from 2.5 hours ago to NOW
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=150) # 2.5 hours
    
    now_ms = int(now.timestamp() * 1000)
    start_ms = int(start_time.timestamp() * 1000)
    
    sub_uid = "463099713"
    
    print(f"Current Time: {now}")
    print(f"Scanning from: {start_time}")
    
    with open("scan_2hours.txt", "w", encoding="utf-8") as f:
        # Check Master
        f.write("=== MASTER ACCOUNT (Linear) ===\n")
        try:
            txs = adapter.fetch_transaction_log("UNIFIED", "linear", start_ms, now_ms)
            f.write(f"Count: {len(txs)}\n")
            for t in txs:
                change = float(t.get('change',0))
                fee = float(t.get('fee',0))
                pnl = change + fee
                f.write(f"[TX] {t['transactionTime']} | {t['symbol']} | PnL: {pnl} | ID: {t['orderId']} | Type: {t.get('type')}\n")
        except Exception as e:
             f.write(f"Error: {e}\n")
             
        # Check Sub
        f.write(f"\n=== SUBACCOUNT {sub_uid} (Linear) ===\n")
        try:
            endpoint = "/v5/account/transaction-log"
            params = {
                "accountType": "UNIFIED",
                "category": "linear",
                "startTime": start_ms,
                "endTime": now_ms,
                "subMemberId": sub_uid
            }
            resp = adapter._request("GET", endpoint, params)
            sub_txs = resp.get("result", {}).get("list", [])
            f.write(f"Count: {len(sub_txs)}\n")
            for t in sub_txs:
                change = float(t.get('change',0))
                fee = float(t.get('fee',0))
                pnl = change + fee
                f.write(f"[TX] {t['transactionTime']} | {t['symbol']} | PnL: {pnl} | ID: {t['orderId']} | Type: {t.get('type')}\n")
        except Exception as e:
             f.write(f"Error: {e}\n")
             
    print("Scan results written to scan_2hours.txt")

if __name__ == "__main__":
    main()

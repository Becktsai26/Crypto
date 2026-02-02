
import websocket
import threading
import time
import json
import hmac
import hashlib
import os
from dotenv import load_dotenv

# Load env
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(".env")
api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")

def generate_signature(api_secret, expires):
    param_str = f"GET/realtime{expires}"
    return hmac.new(
        api_secret.encode("utf-8"), 
        param_str.encode("utf-8"), 
        hashlib.sha256
    ).hexdigest()

def on_message(ws, message):
    print(f"[RECV] {message}")

def on_error(ws, error):
    print(f"[ERROR] {error}")

def on_close(ws, close_status_code, close_msg):
    print(f"[CLOSED] {close_status_code} - {close_msg}")

def on_open(ws):
    print("[OPEN] Connected. Sending Auth...")
    
    # Auth
    expires = int(time.time() * 1000) + 10000
    signature = generate_signature(api_secret, expires)
    
    auth_msg = {
        "op": "auth",
        "args": [
            api_key,
            expires,
            signature
        ]
    }
    print(f"Sending Auth: {auth_msg}")
    ws.send(json.dumps(auth_msg))

    # Wait a bit then subscribe
    def subscribe():
        time.sleep(2)
        sub_msg = {
            "op": "subscribe",
            "args": [
                "position"
            ]
        }
        print(f"Sending Sub: {sub_msg}")
        ws.send(json.dumps(sub_msg))
    
    threading.Thread(target=subscribe).start()

if __name__ == "__main__":
    websocket.enableTrace(True)
    ws = websocket.WebSocketApp(
        "wss://stream.bybit.com/v5/private",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

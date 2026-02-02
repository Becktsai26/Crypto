from pybit.unified_trading import WebSocket, HTTP
from dotenv import load_dotenv
import os
import time
import logging

# Configure logging
logging.basicConfig(filename="ws_debug.log", level=logging.DEBUG, 
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

# Load env variables
os.chdir(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(".env")

api_key = os.getenv("BYBIT_API_KEY")
api_secret = os.getenv("BYBIT_API_SECRET")

print(f"Using Key: {api_key[:5]}...")

session = HTTP(api_key=api_key, api_secret=api_secret)
server_time = session.get_server_time()["time"]
server_time_s = int(server_time) / 1000
local_time_s = time.time()
diff = local_time_s - server_time_s

print(f"Server Time: {server_time_s}")
print(f"Local Time:  {local_time_s}")
print(f"Difference:  {diff:.4f} seconds")

print(f"Key repr: {repr(api_key)}")
print(f"Secret repr: {repr(api_secret)}")

if abs(diff) > 2:
    print("WARNING: large time drift detected! This implies Auth failure.")
else:
    print("Time drift is acceptable.")

try:
    print("Testing Privileged REST Call (Wallet Balance)...")
    wallet = session.get_wallet_balance(accountType="UNIFIED")
    print("REST Call Success! Account seems to be Unified.")
    # print(wallet) 
except Exception as e:
    print(f"REST Call Failed (UNIFIED): {e}")
    try:
        print("Retrying with CONTRACT account type...")
        wallet = session.get_wallet_balance(accountType="CONTRACT")
        print("REST Call Success! Account seems to be Classic/Contract.")
    except Exception as e2:
        print(f"REST Call Failed (CONTRACT): {e2}")
        print("CRITICAL: API Key might be invalid or missing permissions!")

def on_message(message):
    print("Received message:", message)

try:
    print("Connecting to Bybit WebSocket...")
    ws = WebSocket(
        testnet=False,
        channel_type="private",
        api_key=api_key,
        api_secret=api_secret,
        trace_logging=True,  # Enable internal debug logs
    )
    
    # Subscribe to wallet/position to test auth
    ws.position_stream(callback=on_message)
    
    print("Connected. Waiting for 10 seconds...")
    time.sleep(10)
    print("Done waiting.")

except Exception as e:
    print(f"Error: {e}")

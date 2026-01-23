from datetime import datetime
import json
import time
import hmac
import hashlib
import threading
import websocket
from .notifier import DiscordNotifier
from ..config import settings
from ..utils.logger import log
from ..adapters.bybit import BybitAdapter
from ..clients.notion import NotionClient
from ..services.sync import SyncService
from ..services.stats import StatsService

class BybitMonitor:
    def __init__(self):
        self.notifier = DiscordNotifier()
        self.api_key = settings["bybit_api_key"]
        self.api_secret = settings["bybit_api_secret"]
        self.ws_url = "wss://stream.bybit.com/v5/private"
        self.ws = None
        self.keep_running = True
        
        # Throttling state for position updates (Symbol -> Timestamp)
        self.last_position_update = {}
        # TRACKING STATE for TP/SL changes (Symbol -> {tp, sl})
        self.last_position_state = {} 
        self.UPDATE_COOLDOWN = 3600 # 60 minutes
        
        # POSITIONS CACHE (Symbol -> Position Data Dict)
        self.positions = {}
        
        # Buffer for aggregation
        self.execution_buffer = {}
        
        # Track active orders to distinguish New vs Modified
        self.active_orders = set()
        
        # Initialize Services
        try:
            self.bybit_adapter = BybitAdapter(
                api_key=self.api_key,
                api_secret=self.api_secret
            )
            self.notion_client = NotionClient(
                token=settings["notion_token"],
                database_id=settings["notion_db_id"]
            )
            self.sync_service = SyncService(
                exchange_adapter=self.bybit_adapter,
                notion_client=self.notion_client
            )
            self.stats_service = StatsService(exchange_adapter=self.bybit_adapter)
            log.info("Services (Sync, Stats) initialized successfully.")
        except Exception as e:
            log.error(f"Failed to initialize Services: {e}")
            self.sync_service = None
            self.stats_service = None

    def generate_signature(self, expires):
        param_str = f"GET/realtime{expires}"
        return hmac.new(
            self.api_secret.encode("utf-8"), 
            param_str.encode("utf-8"), 
            hashlib.sha256
        ).hexdigest()

    def on_open(self, ws):
        log.info("WebSocket Connected. Sending Auth...")
        
        # Authentication
        expires = int(time.time() * 1000) + 10000
        signature = self.generate_signature(expires)
        
        auth_msg = {
            "op": "auth",
            "args": [self.api_key, expires, signature]
        }
        ws.send(json.dumps(auth_msg))
        
        # Clear Active Orders on reconnect
        self.active_orders.clear()
        
        # DO NOT Clear Position State - We want to remember TP/SL across reconnects

        # Start Heartbeat Loop
        threading.Thread(target=self.heartbeat, daemon=True).start()

    def send_daily_report(self):
        if self.stats_service:
            try:
                report_data = self.stats_service.get_daily_report_data()
                self.notifier.send_daily_report(report_data)
                log.info("Daily/Monthly Report sent to Discord.")
            except Exception as e:
                log.error(f"Failed to send Daily Report: {e}")

    def on_message(self, ws, message):
        try:
            data = json.loads(message)
            op = data.get("op")
            
            if op == "auth":
                if data.get("success"):
                    log.info("WebSocket Authentication Successful!")
                    # Subscribe after auth
                    self.subscribe()
                else:
                    log.error(f"WebSocket Authentication Failed: {data}")
                    
            elif op == "subscribe":
                if data.get("success"):
                    log.info(f"Subscribed: {data.get('ret_msg')}")
                    
            elif "topic" in data:
                topic = data["topic"]
                if topic == "order":
                    self._on_order_update(data)
                elif topic == "execution":
                    self._on_execution_update(data)
                elif topic == "position":
                    self._on_position_update(data)
                    
        except Exception as e:
            log.error(f"Error processing message: {e}")

    def on_error(self, ws, error):
        log.error(f"WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        log.warning("WebSocket Connection Closed.")

    def subscribe(self):
        topics = ["order", "execution", "position"]
        sub_msg = {
            "op": "subscribe",
            "args": topics
        }
        self.ws.send(json.dumps(sub_msg))
        log.info(f"Subscribing to topics: {topics}")

    def heartbeat(self):
        while self.keep_running and self.ws and self.ws.sock and self.ws.sock.connected:
            try:
                self.ws.send(json.dumps({"op": "ping"}))
                time.sleep(20)
            except Exception:
                break

    def _on_order_update(self, message):
        """Callback for order stream."""
        data = message.get("data", [])
        for order in data:
            status = order.get("orderStatus") # Might be None in delta update
            order_id = order.get("orderId")
            symbol = order.get("symbol")
            stop_order_type = order.get("stopOrderType", "")
            
            # Retrieve cached position for footer
            current_position = self.positions.get(symbol)

            # Check for Closing Order Indicators
            is_reduce_only = order.get("reduceOnly", False)
            is_close_on_trigger = order.get("closeOnTrigger", False)
            is_conditional = stop_order_type in ["TakeProfit", "StopLoss", "TrailingStop"]
            
            # Identify if this is a modification (existing order or partial update)
            if status is None:
                self.notifier.send_order_modified(order, positions=self.positions)
                continue
            
            if status in ["New", "Untriggered"]:
                # Check for Closing/Conditional Orders (e.g., TP/SL set on position)
                if is_reduce_only or is_close_on_trigger or is_conditional:
                     self.notifier.send_order_modified(order, positions=self.positions)
                
                elif order_id not in self.active_orders:
                    # Truly New Opening Order
                    self.active_orders.add(order_id)
                    self.notifier.send_order_new(order, positions=self.positions)
                
                else:
                    # Existing Order Update -> Modification
                    self.notifier.send_order_modified(order, positions=self.positions)
                    
            elif status in ["Cancelled", "Deactivated", "Filled"]:
                if order_id in self.active_orders:
                    self.active_orders.remove(order_id)
                
                if status in ["Cancelled", "Deactivated"]:
                    self.notifier.send_order_cancel(order, positions=self.positions)

    def _on_execution_update(self, message):
        """Callback for execution stream (trades)."""
        data = message.get("data", [])
        has_valid_trade = False
        
        for trade in data:
            if trade.get("execType") == "Funding":
                continue
            has_valid_trade = True
            
            order_id = trade.get("orderId")
            if not order_id:
                symbol = trade.get("symbol")
                self.notifier.send_order_filled(trade, positions=self.positions)
                continue
                
            if order_id in self.execution_buffer:
                self.execution_buffer[order_id]["timer"].cancel()
                existing = self.execution_buffer[order_id]["data"]
                
                old_qty = float(existing["execQty"])
                new_qty = float(trade["execQty"])
                old_price = float(existing["execPrice"])
                new_price = float(trade["execPrice"])
                
                total_qty = old_qty + new_qty
                if total_qty > 0:
                    avg_price = (old_qty * old_price + new_qty * new_price) / total_qty
                else:
                    avg_price = new_price
                    
                existing["execQty"] = str(total_qty)
                existing["execPrice"] = str(avg_price)
            else:
                self.execution_buffer[order_id] = {
                    "data": trade.copy(), 
                    "timer": None
                }
            
            timer = threading.Timer(3.0, self._flush_execution_buffer, args=[order_id])
            self.execution_buffer[order_id]["timer"] = timer
            timer.start()
        
        if has_valid_trade and self.sync_service:
            threading.Thread(target=self._run_sync_delayed, daemon=True).start()

    def _flush_execution_buffer(self, order_id):
        """Called by timer to send aggregated execution."""
        if order_id in self.execution_buffer:
            trade_data = self.execution_buffer[order_id]["data"]
            del self.execution_buffer[order_id]
            
            symbol = trade_data.get("symbol")
            pnl = None
            if self.stats_service:
                pnl = self.stats_service.get_closed_pnl_by_order(symbol, order_id)
            
            self.notifier.send_order_filled(trade_data, pnl=pnl, positions=self.positions)

    def _run_sync_delayed(self):
        time.sleep(3) 
        try:
            self.sync_service.run_sync()
        except Exception as e:
            log.error(f"Auto-Sync failed: {e}")

    def _safe_float_compare(self, val1, val2):
        """Helper to compare two price strings/floats/nones."""
        try:
            v1 = float(val1) if val1 and val1 != "" else 0.0
            v2 = float(val2) if val2 and val2 != "" else 0.0
            return abs(v1 - v2) > 0.000001 # Epsilon for checks
        except:
             return val1 != val2 # Fallback to string

    def _on_position_update(self, message):
        """Callback for position stream."""
        data = message.get("data", [])
        now = time.time()
        
        for pos in data:
            symbol = pos.get("symbol")
            
            # Cache the latest position data (Merge to handle partial updates)
            if symbol not in self.positions:
                self.positions[symbol] = pos
            else:
                self.positions[symbol].update(pos)
            
            # Use the FULL merged state for logic checks
            current_pos_state = self.positions[symbol]
            
            current_tp = current_pos_state.get("takeProfit", "") or ""
            current_sl = current_pos_state.get("stopLoss", "") or ""
            
            last_state = self.last_position_state.get(symbol, {})
            last_tp = last_state.get("tp", "") or ""
            last_sl = last_state.get("sl", "") or ""
            
            # Initialize state if first run
            if symbol not in self.last_position_state:
                self.last_position_state[symbol] = {"tp": current_tp, "sl": current_sl}
            else:
                # Detect Change using Float Compare
                changed_tp = self._safe_float_compare(current_tp, last_tp)
                changed_sl = self._safe_float_compare(current_sl, last_sl)
                
                # Check Position Size (From merged state)
                size = float(current_pos_state.get("size", 0))
                
                if changed_tp or changed_sl:
                    log.info(f"Position TP/SL Changed for {symbol}: TP {last_tp}->{current_tp}, SL {last_sl}->{current_sl}")
                    
                    self.last_position_state[symbol] = {"tp": current_tp, "sl": current_sl}
                    
                    # Only alert if position is OPEN
                    if size > 0:
                        mod_data = {
                            "symbol": symbol,
                            "side": current_pos_state.get("side"),
                            "orderType": "Position Update",
                            "price": current_pos_state.get("entryPrice", "N/A"), 
                            "takeProfit": current_tp,
                            "stopLoss": current_sl,
                            "triggerPrice": f"{current_sl} (SL) / {current_tp} (TP)" 
                        }
                        # Pass ALL positions
                        self.notifier.send_order_modified(mod_data, positions=self.positions)
                    else:
                        log.info(f"Suppressed TP/SL Alert for {symbol} because position is closed (Size=0).")
            
            # PnL Throttling Logic
            last_time = self.last_position_update.get(symbol, 0)
            if now - last_time >= self.UPDATE_COOLDOWN:
                self.notifier.send_position_update(current_pos_state)
                self.last_position_update[symbol] = now

    def start(self):
        log.info("Starting Bybit Monitor (Custom WebSocket)...")
        
        # Prefetch Initial Positions via REST API to warm the cache
        try:
            log.info("Fetching initial open positions (Scanning Linear & Inverse)...")
            
            # 1. Fetch Linear (USDT/USDC Perps)
            positions_linear = self.bybit_adapter.get_positions(category="linear")
            
            # 2. Fetch Inverse (Coin-Margined)
            positions_inverse = self.bybit_adapter.get_positions(category="inverse")
            
            initial_positions = positions_linear + positions_inverse
            
            if not initial_positions:
                 log.info("No active positions found on startup.")
            
            for pos in initial_positions:
                symbol = pos.get("symbol")
                size = float(pos.get("size", 0))
                
                # Only cache legitimate positions (Size > 0)
                if size > 0:
                    log.info(f"Loaded Active Position: {symbol}, Size: {size}")
                    
                    # Store full position data
                    self.positions[symbol] = pos
                    
                    # Also Initialize Tracking State
                    self.last_position_state[symbol] = {
                        "tp": pos.get("takeProfit", "") or "", 
                        "sl": pos.get("stopLoss", "") or ""
                    }
            log.info(f"Total {len(self.positions)} active positions loaded.")
        except Exception as e:
            log.error(f"Failed to fetch initial positions: {e}")
            
        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        while self.keep_running:
            try:
                self.ws.run_forever()
                log.info("Reconnecting in 5 seconds...")
                time.sleep(5)
            except KeyboardInterrupt:
                self.keep_running = False
                break
            except Exception as e:
                log.error(f"WebSocket crashed: {e}")
                time.sleep(5)

if __name__ == "__main__":
    monitor = BybitMonitor()
    monitor.start()

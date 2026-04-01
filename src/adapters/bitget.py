# src/adapters/bitget.py
import time
import hmac
import hashlib
import base64
import json
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException

from .base import BaseExchangeAdapter
from ..utils.exceptions import ApiException
from ..utils.logger import log

# Bitget API v2
BITGET_BASE_URL = "https://api.bitget.com"
REQUEST_SLEEP_INTERVAL = 0.1  # Conservative: 20 req/s


class BitgetAdapter(BaseExchangeAdapter):
    """
    Bitget API v2 adapter for USDT-M futures.
    Fetches order fill history from /api/v2/mix/order/fills and normalizes
    to the standard transaction log format for SyncService.
    """

    @property
    def exchange_name(self) -> str:
        return "bitget"

    @property
    def default_category(self) -> str:
        return "USDT-FUTURES"

    @property
    def max_query_window_ms(self) -> int:
        return 90 * 24 * 60 * 60 * 1000  # 90 days

    def __init__(self, api_key: str, api_secret: str, passphrase: str = None):
        super().__init__(api_key, api_secret, passphrase=passphrase)
        self.last_request_time = 0

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """
        Generates Bitget signature: Base64(HMAC-SHA256(timestamp + method + requestPath + body))
        """
        prehash = timestamp + method.upper() + request_path + body
        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            prehash.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Sends a signed request to the Bitget API."""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_SLEEP_INTERVAL:
            time.sleep(REQUEST_SLEEP_INTERVAL - elapsed)

        self.last_request_time = time.time()
        timestamp = str(int(time.time() * 1000))

        body = ""
        request_path = endpoint
        if method.upper() == "GET" and params:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            request_path = f"{endpoint}?{query_string}"
        elif method.upper() == "POST" and params:
            body = json.dumps(params)

        signature = self._sign(timestamp, method.upper(), request_path, body)

        headers = {
            'ACCESS-KEY': self._api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': self._passphrase or "",
            'Content-Type': 'application/json',
            'locale': 'en-US',
        }

        url = f"{BITGET_BASE_URL}{request_path}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers)
            else:
                response = requests.post(url, headers=headers, data=body)

            response.raise_for_status()
            data = response.json()

            if data.get("code") != "00000":
                if data.get("code") == "40014":  # Rate limit
                    log.warning("Bitget rate limit hit. Retrying after delay...")
                    time.sleep(1)
                    return self._request(method, endpoint, params)
                raise ApiException(f"Bitget API Error: {data.get('msg')} (Code: {data.get('code')})")

            return data

        except RequestException as e:
            raise ApiException(f"Bitget HTTP Request failed: {e}")
        except json.JSONDecodeError:
            raise ApiException(f"Failed to decode JSON response from {url}")

    def fetch_executions(self, category: str, start_time: int, end_time: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetches raw fill records from Bitget."""
        endpoint = "/api/v2/mix/order/fills"
        all_results = []
        id_less_than = None

        while True:
            params = {
                "productType": "USDT-FUTURES",
                "startTime": str(start_time),
                "endTime": str(end_time),
                "limit": str(limit),
            }
            if id_less_than:
                params["idLessThan"] = id_less_than

            data = self._request("GET", endpoint, params)
            results = data.get("data", {}).get("fillList", [])

            if not results:
                break

            all_results.extend(results)

            if len(results) < limit:
                break

            id_less_than = results[-1].get("tradeId")

        return all_results

    def fetch_transaction_log(self, account_type: str, category: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """
        Fetches fill history and normalizes to the standard format.

        Returns records with: type, change, fee, orderId, symbol, side, qty, tradePrice, transactionTime
        """
        raw_fills = self.fetch_executions(category, start_time, end_time)

        normalized = []
        for fill in raw_fills:
            profit = float(fill.get("profit", 0))

            # Only include closing trades with PnL
            if profit == 0:
                continue

            # Normalize side: Bitget uses "open_long", "close_long", "open_short", "close_short"
            raw_side = fill.get("side", "").lower()
            if "close_long" in raw_side or "close_short" in raw_side:
                side = "Sell" if "close_long" in raw_side else "Buy"
            elif "buy" in raw_side:
                side = "Buy"
            elif "sell" in raw_side:
                side = "Sell"
            else:
                side = raw_side.capitalize()

            total_fee = float(fill.get("totalFee", fill.get("fee", 0)))

            normalized.append({
                "type": "TRADE",
                "change": profit,
                "fee": -abs(total_fee) if total_fee > 0 else total_fee,
                "orderId": fill.get("orderId", ""),
                "symbol": fill.get("symbol", ""),
                "side": side,
                "qty": fill.get("size", fill.get("fillSz", "0")),
                "tradePrice": fill.get("price", fill.get("fillPx", "0")),
                "transactionTime": fill.get("cTime", "0"),
            })

        return normalized

    def fetch_subaccounts(self) -> List[Dict[str, Any]]:
        """Bitget sub-account API. Returns empty for now."""
        return []

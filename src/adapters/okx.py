# src/adapters/okx.py
import time
import hmac
import hashlib
import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException

from .base import BaseExchangeAdapter
from ..utils.exceptions import ApiException
from ..utils.logger import log

# OKX API
OKX_BASE_URL = "https://www.okx.com"
REQUEST_SLEEP_INTERVAL = 0.25  # Conservative: 10 req/2s


class OKXAdapter(BaseExchangeAdapter):
    """
    OKX API v5 adapter.
    Fetches fill history from /api/v5/trade/fills-history and normalizes them
    to the standard transaction log format for SyncService.
    """

    @property
    def exchange_name(self) -> str:
        return "okx"

    @property
    def default_category(self) -> str:
        return "SWAP"

    @property
    def max_query_window_ms(self) -> int:
        return 90 * 24 * 60 * 60 * 1000  # 90 days

    def __init__(self, api_key: str, api_secret: str, passphrase: str = None):
        super().__init__(api_key, api_secret, passphrase=passphrase)
        self.last_request_time = 0

    def _sign(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """
        Generates OKX signature: Base64(HMAC-SHA256(timestamp + method + requestPath + body))
        """
        prehash = timestamp + method.upper() + request_path + body
        signature = hmac.new(
            self._api_secret.encode('utf-8'),
            prehash.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Sends a signed request to the OKX API."""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_SLEEP_INTERVAL:
            time.sleep(REQUEST_SLEEP_INTERVAL - elapsed)

        self.last_request_time = time.time()

        timestamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.') + \
                    f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"

        body = ""
        request_path = endpoint
        if method.upper() == "GET" and params:
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            request_path = f"{endpoint}?{query_string}"

        signature = self._sign(timestamp, method.upper(), request_path, body)

        headers = {
            'OK-ACCESS-KEY': self._api_key,
            'OK-ACCESS-SIGN': signature,
            'OK-ACCESS-TIMESTAMP': timestamp,
            'OK-ACCESS-PASSPHRASE': self._passphrase or "",
            'Content-Type': 'application/json',
        }

        url = f"{OKX_BASE_URL}{request_path}"

        try:
            response = requests.request(method.upper(), url, headers=headers)
            response.raise_for_status()
            data = response.json()

            if data.get("code") != "0":
                if data.get("code") == "50011":  # Rate limit
                    log.warning("OKX rate limit hit. Retrying after delay...")
                    time.sleep(2)
                    return self._request(method, endpoint, params)
                raise ApiException(f"OKX API Error: {data.get('msg')} (Code: {data.get('code')})")

            return data

        except RequestException as e:
            raise ApiException(f"OKX HTTP Request failed: {e}")
        except json.JSONDecodeError:
            raise ApiException(f"Failed to decode JSON response from {url}")

    def fetch_executions(self, category: str, start_time: int, end_time: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetches raw fill records from OKX."""
        endpoint = "/api/v5/trade/fills-history"
        all_results = []
        after_cursor = None

        while True:
            params = {
                "instType": category,  # "SWAP" for perpetual
                "begin": str(start_time),
                "end": str(end_time),
                "limit": str(limit),
            }
            if after_cursor:
                params["after"] = after_cursor

            data = self._request("GET", endpoint, params)
            results = data.get("data", [])

            if not results:
                break

            all_results.extend(results)

            if len(results) < limit:
                break

            after_cursor = results[-1].get("billId")

        return all_results

    def fetch_transaction_log(self, account_type: str, category: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """
        Fetches fill history and normalizes to the standard format.

        Returns records with: type, change, fee, orderId, symbol, side, qty, tradePrice, transactionTime
        """
        inst_type = "SWAP"  # USDT perpetual
        raw_fills = self.fetch_executions(inst_type, start_time, end_time)

        normalized = []
        for fill in raw_fills:
            pnl = float(fill.get("pnl", 0))

            # Only include fills with realized PnL (closing trades)
            if pnl == 0:
                continue

            # Normalize side: OKX uses "buy"/"sell"
            side = fill.get("side", "").capitalize()

            normalized.append({
                "type": "TRADE",
                "change": pnl,
                "fee": float(fill.get("fee", 0)),  # OKX fee is negative for charges
                "orderId": fill.get("ordId", ""),
                "symbol": fill.get("instId", ""),  # e.g., "BTC-USDT-SWAP"
                "side": side,
                "qty": fill.get("fillSz", "0"),
                "tradePrice": fill.get("fillPx", "0"),
                "transactionTime": fill.get("ts", "0"),
            })

        return normalized

    def fetch_subaccounts(self) -> List[Dict[str, Any]]:
        """OKX sub-account API. Returns empty for now."""
        return []

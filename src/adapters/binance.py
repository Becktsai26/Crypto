# src/adapters/binance.py
import time
import hmac
import hashlib
import json
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from requests.exceptions import RequestException

from .base import BaseExchangeAdapter
from ..utils.exceptions import ApiException
from ..utils.logger import log

# Binance USDT-M Futures API
BINANCE_BASE_URL = "https://fapi.binance.com"
REQUEST_SLEEP_INTERVAL = 0.1  # Conservative: 1200 req/min


class BinanceAdapter(BaseExchangeAdapter):
    """
    Binance USDT-M Futures API adapter.
    Fetches trade fills from /fapi/v1/userTrades and normalizes them
    to the standard transaction log format for SyncService.
    """

    @property
    def exchange_name(self) -> str:
        return "binance"

    @property
    def max_query_window_ms(self) -> int:
        return 7 * 24 * 60 * 60 * 1000  # 7 days

    def __init__(self, api_key: str, api_secret: str):
        super().__init__(api_key, api_secret)
        self.last_request_time = 0

    def _sign(self, query_string: str) -> str:
        """Generates HMAC-SHA256 signature for the query string."""
        return hmac.new(
            self._api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Sends a signed request to the Binance API."""
        # Rate limiting
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_SLEEP_INTERVAL:
            time.sleep(REQUEST_SLEEP_INTERVAL - elapsed)

        self.last_request_time = time.time()

        if params is None:
            params = {}
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 5000

        query_string = urlencode(params)
        params['signature'] = self._sign(query_string)

        headers = {
            'X-MBX-APIKEY': self._api_key,
        }

        url = f"{BINANCE_BASE_URL}{endpoint}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params)
            else:
                response = requests.post(url, headers=headers, params=params)

            response.raise_for_status()
            data = response.json()

            # Binance error format: {"code": -1xxx, "msg": "..."}
            if isinstance(data, dict) and "code" in data and data["code"] != 200:
                if data["code"] == -1015:  # Rate limit
                    log.warning("Binance rate limit hit. Retrying after delay...")
                    time.sleep(1)
                    return self._request(method, endpoint, params)
                raise ApiException(f"Binance API Error: {data.get('msg')} (Code: {data.get('code')})")

            return data

        except RequestException as e:
            raise ApiException(f"Binance HTTP Request failed: {e}")
        except json.JSONDecodeError:
            raise ApiException(f"Failed to decode JSON response from {url}")

    def fetch_executions(self, category: str, start_time: int, end_time: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """Fetches raw execution records (userTrades) without normalization."""
        endpoint = "/fapi/v1/userTrades"
        all_results = []
        from_id = None

        while True:
            params = {
                "startTime": start_time,
                "endTime": end_time,
                "limit": limit,
            }
            if from_id:
                params["fromId"] = from_id
                params.pop("startTime", None)
                params.pop("endTime", None)

            results = self._request("GET", endpoint, params)

            if not results:
                break

            all_results.extend(results)

            if len(results) < limit:
                break

            from_id = results[-1]["id"] + 1

        return all_results

    def fetch_transaction_log(self, account_type: str, category: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """
        Fetches trade fills and normalizes to the standard format.
        account_type and category params are accepted but ignored (Binance uses a single futures endpoint).

        Returns records with: type, change, fee, orderId, symbol, side, qty, tradePrice, transactionTime
        """
        raw_trades = self.fetch_executions(category, start_time, end_time)

        normalized = []
        for trade in raw_trades:
            realized_pnl = float(trade.get("realizedPnl", 0))
            commission = float(trade.get("commission", 0))

            # Only include trades with realized PnL (closing trades)
            if realized_pnl == 0:
                continue

            # Normalize side: Binance uses "BUY"/"SELL"
            side = trade.get("side", "").capitalize()

            normalized.append({
                "type": "TRADE",
                "change": realized_pnl,
                "fee": -abs(commission),  # Binance commission is positive; negate for consistency
                "orderId": str(trade.get("orderId", "")),
                "symbol": trade.get("symbol", ""),
                "side": side,
                "qty": str(trade.get("qty", 0)),
                "tradePrice": str(trade.get("price", 0)),
                "transactionTime": str(trade.get("time", 0)),
            })

        return normalized

    def fetch_subaccounts(self) -> List[Dict[str, Any]]:
        """Binance sub-account API requires specific permissions. Returns empty for now."""
        return []

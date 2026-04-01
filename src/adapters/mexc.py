# src/adapters/mexc.py
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

# MEXC Futures API
MEXC_BASE_URL = "https://contract.mexc.com"
REQUEST_SLEEP_INTERVAL = 0.15  # Conservative: 20 req/2s


class MEXCAdapter(BaseExchangeAdapter):
    """
    MEXC Futures API adapter.
    Fetches closed position history and normalizes to the standard
    transaction log format for SyncService.
    """

    @property
    def exchange_name(self) -> str:
        return "mexc"

    @property
    def max_query_window_ms(self) -> int:
        return 90 * 24 * 60 * 60 * 1000  # 90 days

    def __init__(self, api_key: str, api_secret: str):
        super().__init__(api_key, api_secret)
        self.last_request_time = 0

    def _sign(self, timestamp: str, params_str: str = "") -> str:
        """
        Generates MEXC signature: HMAC-SHA256(api_key + timestamp + params_str)
        """
        to_sign = self._api_key + str(timestamp) + params_str
        return hmac.new(
            self._api_secret.encode('utf-8'),
            to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Sends a signed request to the MEXC Futures API."""
        elapsed = time.time() - self.last_request_time
        if elapsed < REQUEST_SLEEP_INTERVAL:
            time.sleep(REQUEST_SLEEP_INTERVAL - elapsed)

        self.last_request_time = time.time()
        timestamp = str(int(time.time() * 1000))

        params_str = ""
        if params:
            params_str = json.dumps(params, separators=(',', ':')) if method.upper() == "POST" else urlencode(sorted(params.items()))

        signature = self._sign(timestamp, params_str)

        headers = {
            'ApiKey': self._api_key,
            'Request-Time': timestamp,
            'Signature': signature,
            'Content-Type': 'application/json',
        }

        url = f"{MEXC_BASE_URL}{endpoint}"

        try:
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params)
            else:
                response = requests.post(url, headers=headers, json=params)

            response.raise_for_status()
            data = response.json()

            if data.get("code") != 0 and data.get("success") is not True:
                raise ApiException(f"MEXC API Error: {data.get('msg', data.get('message', 'Unknown'))} (Code: {data.get('code')})")

            return data

        except RequestException as e:
            raise ApiException(f"MEXC HTTP Request failed: {e}")
        except json.JSONDecodeError:
            raise ApiException(f"Failed to decode JSON response from {url}")

    def fetch_executions(self, category: str, start_time: int, end_time: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Fetches raw closed position history from MEXC."""
        endpoint = "/api/v1/private/position/list/history_positions"
        all_results = []
        page_num = 1

        while True:
            params = {
                "page_num": page_num,
                "page_size": limit,
            }

            data = self._request("GET", endpoint, params)
            results = data.get("data", [])

            if not results:
                break

            # Filter by time window
            for record in results:
                update_time = int(record.get("updateTime", 0))
                if start_time <= update_time <= end_time:
                    all_results.append(record)

            # If oldest record in page is before start_time, stop
            oldest_time = min(int(r.get("updateTime", 0)) for r in results)
            if oldest_time < start_time:
                break

            if len(results) < limit:
                break

            page_num += 1

        return all_results

    def fetch_transaction_log(self, account_type: str, category: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """
        Fetches closed position history and normalizes to the standard format.

        Returns records with: type, change, fee, orderId, symbol, side, qty, tradePrice, transactionTime
        """
        raw_positions = self.fetch_executions(category, start_time, end_time)

        normalized = []
        for pos in raw_positions:
            realized_pnl = float(pos.get("realised", 0))

            if realized_pnl == 0:
                continue

            # positionType: 1=long, 2=short
            # For closing: long close = Sell, short close = Buy
            pos_type = pos.get("positionType", 1)
            side = "Sell" if pos_type == 1 else "Buy"

            open_fee = float(pos.get("openPositionFee", 0))
            close_fee = float(pos.get("closePositionFee", 0))
            total_fee = -(abs(open_fee) + abs(close_fee))

            # Symbol normalization: MEXC uses "BTC_USDT" format
            symbol = pos.get("symbol", "")

            normalized.append({
                "type": "TRADE",
                "change": realized_pnl,
                "fee": total_fee,
                "orderId": str(pos.get("positionId", pos.get("id", ""))),
                "symbol": symbol,
                "side": side,
                "qty": str(abs(float(pos.get("closeVol", 0)))),
                "tradePrice": str(pos.get("closeAvgPrice", 0)),
                "transactionTime": str(pos.get("updateTime", 0)),
            })

        return normalized

    def fetch_subaccounts(self) -> List[Dict[str, Any]]:
        """MEXC sub-account support is limited. Returns empty."""
        return []

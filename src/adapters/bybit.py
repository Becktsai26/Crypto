# src/adapters/bybit.py
import time
import hmac
import hashlib
import json
from typing import Any, Dict, List, Optional

import requests
from requests.exceptions import RequestException

from .base import BaseExchangeAdapter
from ..utils.exceptions import ApiException
from ..utils.logger import log

# Bybit API v5 configuration
BYBIT_BASE_URL = "https://api.bybit.com"
# Rate limit: 120 requests/minute per UID. We will use a conservative delay.
# 60s / 120req = 0.5s/req
REQUEST_SLEEP_INTERVAL = 0.55  # A bit over 500ms for safety


class BybitAdapter(BaseExchangeAdapter):
    """
    Bybit API v5 adapter.
    Implements the specific details for interacting with the Bybit API,
    including authentication, pagination, and error handling.
    """

    def __init__(self, api_key: str, api_secret: str):
        super().__init__(api_key, api_secret)
        self.last_request_time = 0

    def _sign(self, params: str, timestamp: int) -> str:
        """
        Generates the HMAC-SHA256 signature for a Bybit API v5 request.
        """
        to_sign = str(timestamp) + self._api_key + "5000" + params
        return hmac.new(self._api_secret.encode('utf-8'), to_sign.encode('utf-8'), hashlib.sha256).hexdigest()

    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Sends a signed request to the Bybit API, handling rate limiting and errors.
        """
        # Rate limiting
        time_since_last_request = time.time() - self.last_request_time
        if time_since_last_request < REQUEST_SLEEP_INTERVAL:
            time.sleep(REQUEST_SLEEP_INTERVAL - time_since_last_request)
        
        self.last_request_time = time.time()
        
        timestamp = int(self.last_request_time * 1000)
        
        query_string = ""
        if params:
            # Bybit requires sorted keys for the query string
            query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

        signature = self._sign(query_string, timestamp)

        headers = {
            'X-BAPI-API-KEY': self._api_key,
            'X-BAPI-SIGN': signature,
            'X-BAPI-TIMESTAMP': str(timestamp),
            'X-BAPI-RECV-WINDOW': '5000', # Recommended by Bybit
            'Content-Type': 'application/json'
        }
        
        url = f"{BYBIT_BASE_URL}{endpoint}?{query_string}"
        
        try:
            response = requests.request(method.upper(), url, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            
            data = response.json()

            # Bybit-specific error handling in the response body
            if data.get("retCode") != 0:
                # Handle rate limit error (10002)
                if data.get("retCode") == 10002:
                    log.warning("Rate limit hit. Retrying after a short delay...")
                    time.sleep(1) # Extra delay
                    return self._request(method, endpoint, params)
                raise ApiException(f"Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')})")
            
            return data

        except RequestException as e:
            raise ApiException(f"HTTP Request failed: {e}")
        except json.JSONDecodeError:
            raise ApiException(f"Failed to decode JSON response from {url}. Response text: {response.text}")

    def _paginated_fetch(self, endpoint: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Helper function to handle pagination for Bybit API endpoints.
        """
        all_results = []
        params['limit'] = params.get('limit', 1000) # Bybit max limit for many endpoints
        
        while True:
            response_data = self._request("GET", endpoint, params)
            results = response_data.get("result", {}).get("list", [])
            
            if not results:
                break
                
            all_results.extend(results)
            
            next_page_cursor = response_data.get("result", {}).get("nextPageCursor")
            if not next_page_cursor:
                break # No more pages
            
            params['cursor'] = next_page_cursor
            
        return all_results

    def fetch_executions(self, category: str, start_time: int, end_time: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetches execution records (trades) with pagination.
        Note: Bybit's execution list doesn't use startTime/endTime, it's cursor-based for the last 7 days.
        We will fetch all and filter locally if needed, though the request implies fetching everything recent.
        """
        endpoint = "/v5/execution/list"
        params = {"category": category, "limit": limit}
        # The prompt mentions startTime/endTime, but v5 execution list is based on the last 7 days via cursor.
        # We will fetch all available in the 7-day window. The sync service will handle filtering.
        return self._paginated_fetch(endpoint, params)

    def fetch_transaction_log(self, account_type: str, category: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """
        Fetches the account transaction log with pagination.
        """
        endpoint = "/v5/account/transaction-log"
        params = {
            "accountType": account_type,
            "category": category,
            "startTime": start_time,
            "endTime": end_time
        }
        return self._paginated_fetch(endpoint, params)

    def fetch_subaccounts(self) -> List[Dict[str, Any]]:
        """
        Fetches the list of subaccounts. Requires Master API key with relevant permissions.
        """
        endpoint = "/v5/user/query-sub-members"
        try:
            response_data = self._request("GET", endpoint, {"limit": 100}) # Max limit is 100
            return response_data.get("result", {}).get("subMembers", [])
        except ApiException as e:
            # It's common to not have subaccount permissions.
            # We'll log this as a warning instead of a critical failure.
            log.warning(f"Could not fetch subaccounts. API key may lack permissions. Error: {e}")
            return []

    def get_positions(self, category: str, settleCoin: str = "USDT") -> List[Dict[str, Any]]:
        """
        Fetches current positions for the account.
        """
        endpoint = "/v5/position/list"
        params = {
            "category": category,
            "settleCoin": settleCoin
        }
        return self._paginated_fetch(endpoint, params)

    def get_closed_pnl(self, category: str, start_time: int = None, end_time: int = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Fetches closed Profit and Loss (PnL) records.
        """
        endpoint = "/v5/position/closed-pnl"
        params = {
            "category": category,
            "limit": limit
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time
            
        return self._paginated_fetch(endpoint, params)

    def get_wallet_balance(self, account_type: str = "UNIFIED", coin: str = None) -> Dict[str, Any]:
        """
        Fetches the wallet balance.
        """
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": account_type}
        if coin:
            params["coin"] = coin
            
        return self._request("GET", endpoint, params)

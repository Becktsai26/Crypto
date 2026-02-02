import time
import hmac
import hashlib
import requests
from typing import Any, Dict, List, Optional
from app.config.settings import settings
from app.config.logging import logger
from app.core.exceptions import DataSourceError
from app.core.models import Trade, BalanceSnapshot
from .mapper import BybitMapper

class BybitClient:
    """
    Bybit V5 API 客戶端。
    負責處理簽章、請求、分頁，並將資料交給 Mapper 轉換。
    """
    
    def __init__(self):
        self.api_key = settings.BYBIT_API_KEY
        self.api_secret = settings.BYBIT_API_SECRET
        self.base_url = "https://api-testnet.bybit.com" if settings.BYBIT_TESTNET else "https://api.bybit.com"
        self.recv_window = "5000"

    def _generate_signature(self, timestamp: str, query_params: str) -> str:
        param_str = timestamp + self.api_key + self.recv_window + query_params
        hash = hmac.new(
            bytes(self.api_secret, "utf-8"),
            param_str.encode("utf-8"),
            hashlib.sha256
        )
        return hash.hexdigest()

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None) -> Dict:
        timestamp = str(int(time.time() * 1000))
        
        # 處理參數
        query_params = ""
        if params:
            query_params = "&".join([f"{k}={v}" for k, v in sorted(params.items())])

        signature = self._generate_signature(timestamp, query_params)
        
        headers = {
            "X-BAPI-API-KEY": self.api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": self.recv_window,
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        if query_params:
            url += f"?{query_params}"

        try:
            response = requests.request(method, url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get("retCode") != 0:
                raise DataSourceError(f"Bybit API Error: {data.get('retMsg')} (Code: {data.get('retCode')})")
            
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Bybit Connection Error: {e}")
            raise DataSourceError(f"Failed to connect to Bybit: {e}")

    def get_closed_pnl(self, category: str = "linear", limit: int = 50) -> List[Trade]:
        """獲取已平倉損益，並轉換為 Trade 物件清單"""
        endpoint = "/v5/position/closed-pnl"
        params = {"category": category, "limit": limit}
        
        try:
            raw_data = self._request("GET", endpoint, params)
            trade_list = raw_data.get("result", {}).get("list", [])
            return [BybitMapper.to_trade(t, category) for t in trade_list]
        except Exception as e:
            logger.error(f"Failed to fetch closed PnL: {e}")
            raise DataSourceError(f"Error fetching trades: {e}")

    def get_balance(self, account_type: str = "UNIFIED") -> BalanceSnapshot:
        """獲取帳戶餘額快照"""
        endpoint = "/v5/account/wallet-balance"
        params = {"accountType": account_type}
        
        try:
            raw_data = self._request("GET", endpoint, params)
            return BybitMapper.to_balance_snapshot(raw_data.get("result", {}))
        except Exception as e:
            logger.error(f"Failed to fetch balance: {e}")
            raise DataSourceError(f"Error fetching balance: {e}")

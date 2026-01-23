# src/adapters/base.py
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

class BaseExchangeAdapter(ABC):
    """
    Abstract base class for exchange API adapters.
    It defines a common interface for all exchange clients, ensuring that
    the core logic can interact with different exchanges in a standardized way.
    """

    def __init__(self, api_key: str, api_secret: str):
        """
        Initializes the adapter with API credentials.

        Args:
            api_key: The API key for the exchange.
            api_secret: The API secret for the exchange.
        """
        self._api_key = api_key
        self._api_secret = api_secret
        self._rate_limit_lock = None  # To be implemented in subclasses

    @abstractmethod
    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Signs the request parameters with the API secret.
        This method should be implemented by each subclass to handle
        the specific signing mechanism of the exchange.
        """
        pass

    @abstractmethod
    def _request(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Sends a request to the exchange API, handling rate limits and errors.
        """
        pass

    @abstractmethod
    def fetch_executions(self, category: str, start_time: int, end_time: int, limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Fetches execution records (trades).

        Args:
            category: The category of the product (e.g., 'linear', 'spot').
            start_time: The start timestamp in milliseconds.
            end_time: The end timestamp in milliseconds.
            limit: The number of records to fetch per page.

        Returns:
            A list of execution records.
        """
        pass

    @abstractmethod
    def fetch_transaction_log(self, account_type: str, category: str, start_time: int, end_time: int) -> List[Dict[str, Any]]:
        """
        Fetches the account transaction log (e.g., fees, funding).

        Args:
            account_type: The account type (e.g., 'UNIFIED', 'CONTRACT').
            category: The product category.
            start_time: The start timestamp in milliseconds.
            end_time: The end timestamp in milliseconds.

        Returns:
            A list of transaction log entries.
        """
        pass

    @abstractmethod
    def fetch_subaccounts(self) -> List[Dict[str, Any]]:
        """
        Fetches the list of subaccounts associated with the main account.

        Returns:
            A list of subaccount details. Returns an empty list if not applicable.
        """
        pass

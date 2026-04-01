# src/adapters/__init__.py
from .bybit import BybitAdapter
from .binance import BinanceAdapter
from .okx import OKXAdapter
from .mexc import MEXCAdapter
from .bitget import BitgetAdapter

ADAPTER_MAP = {
    "bybit": BybitAdapter,
    "binance": BinanceAdapter,
    "okx": OKXAdapter,
    "mexc": MEXCAdapter,
    "bitget": BitgetAdapter,
}

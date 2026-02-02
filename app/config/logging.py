import logging
import sys

# 嘗試 import settings，如果失敗（例如環境變數沒設），則使用預設值
try:
    from app.config.settings import settings
    LOG_LEVEL = settings.LOG_LEVEL.upper() if settings else "INFO"
except Exception:
    LOG_LEVEL = "INFO"

def setup_logging(name: str = "crypto_app") -> logging.Logger:
    """
    統一的日誌配置。
    目前輸出到 Console (Stdout)，方便 Docker 收集。
    """
    logger = logging.getLogger(name)
    
    # 防止重複添加 Handler
    if logger.handlers:
        return logger

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    logger.setLevel(level)

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    return logger

# 預設 Logger
logger = setup_logging()

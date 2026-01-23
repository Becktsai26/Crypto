# src/utils/logger.py
import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logger():
    """
    Sets up a centralized logger for the application.
    """
    logger = logging.getLogger("SyncServiceLogger")
    logger.setLevel(logging.INFO)

    # Prevent duplicate handlers if logger is already configured
    if logger.hasHandlers():
        logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console Handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # File Handler
    # Creates a 'sync.log' file in the project root directory
    file_handler = RotatingFileHandler('sync.log', maxBytes=1024*1024*5, backupCount=2) # 5MB per file, 2 backups
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger

# Create a logger instance to be imported by other modules
log = setup_logger()

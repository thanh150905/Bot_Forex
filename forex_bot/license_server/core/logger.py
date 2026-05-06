"""
Logging system toàn cầu - File + Console
Tất cả log sẽ được lưu vào ./logs/
"""

import logging
import logging.handlers
from pathlib import Path
from datetime import datetime
import sys
import os


LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

# Timestamp cho log file
log_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")


def setup_logger(name: str, level=logging.INFO) -> logging.Logger:
    """
    Setup logger với file + console output
    
    Args:
        name: Tên logger (thường là __name__)
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Loại bỏ duplicate handlers
    if logger.hasHandlers():
        logger.handlers.clear()
    
    # Format chi tiết
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # ─── File Handler (Rotate daily) ───
    file_handler = logging.handlers.RotatingFileHandler(
        LOGS_DIR / f"app_{log_timestamp}.log",
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=10,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # ─── Console Handler ───
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # ─── Error File Handler (Chỉ ERROR + CRITICAL) ───
    error_handler = logging.FileHandler(
        LOGS_DIR / f"errors_{log_timestamp}.log",
        encoding='utf-8'
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    logger.addHandler(error_handler)
    
    return logger


# Global loggers
app_logger = setup_logger("app")
bot_logger = setup_logger("bot")
db_logger = setup_logger("database")
security_logger = setup_logger("security")
email_logger = setup_logger("email")
telegram_logger = setup_logger("telegram")
ai_logger = setup_logger("ai")


def get_logger(name: str) -> logging.Logger:
    """Lấy logger theo tên"""
    return logging.getLogger(name)


def log_trade(symbol: str, direction: str, entry: float, lot: float, ticket: str):
    """Log trade entry"""
    bot_logger.info(f"📊 TRADE ENTRY: {symbol} {direction} @ {entry} | Lot: {lot} | Ticket: {ticket}")


def log_trade_close(symbol: str, ticket: str, exit_price: float, profit: float, pips: float):
    """Log trade close"""
    profit_emoji = "✅" if profit > 0 else "❌"
    bot_logger.info(f"{profit_emoji} TRADE CLOSE: {symbol} | Price: {exit_price} | Profit: {profit}$ ({pips} pips) | Ticket: {ticket}")


def log_error(module: str, error: Exception, context: str = ""):
    """Log error với context"""
    security_logger.error(f"[{module}] {context}\n{type(error).__name__}: {str(error)}", exc_info=True)

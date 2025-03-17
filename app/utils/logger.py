import sys
import os
from datetime import datetime
from loguru import logger
from app.config import LOGS_DIR

# تنظیم مسیرهای ذخیره لاگ‌ها
LOG_FILE = LOGS_DIR / f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"
ERROR_LOG_FILE = LOGS_DIR / f"error_{datetime.now().strftime('%Y-%m-%d')}.log"

# حذف لاگر پیش‌فرض
logger.remove()

# اضافه کردن لاگر کنسول
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# اضافه کردن لاگر فایل برای همه لاگ‌ها
logger.add(
    LOG_FILE,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
    level="INFO",
    rotation="1 day",
    retention="7 days"
)

# اضافه کردن لاگر فایل برای خطاها
logger.add(
    ERROR_LOG_FILE,
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} - {message}",
    level="ERROR",
    rotation="1 day",
    retention="30 days"
)


def get_logger(name):
    """
    تابعی برای ایجاد یک لاگر اختصاصی با نام مشخص
    """
    return logger.bind(name=name)

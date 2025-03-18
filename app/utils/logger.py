import sys
import os
from datetime import datetime
import json
import traceback
from loguru import logger
import socket
from pathlib import Path
import atexit
import logging

from app.config import LOGS_DIR, BOT_CONFIG

# سطح لاگ پیش‌فرض از متغیر محیطی
DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# تنظیم مسیرهای ذخیره لاگ‌ها
LOG_FILE = LOGS_DIR / f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"
ERROR_LOG_FILE = LOGS_DIR / f"error_{datetime.now().strftime('%Y-%m-%d')}.log"
DEBUG_LOG_FILE = LOGS_DIR / f"debug_{datetime.now().strftime('%Y-%m-%d')}.log"
WARN_LOG_FILE = LOGS_DIR / f"warning_{datetime.now().strftime('%Y-%m-%d')}.log"

# اطمینان از وجود دایرکتوری لاگ
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# فرمت ساده‌تر برای کنسول
CONSOLE_FORMAT = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

# فرمت مفصل‌تر برای فایل‌های لاگ
FILE_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {message}"

# فرمت JSON برای فایل JSON
JSON_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}"

# حذف لاگر پیش‌فرض
logger.remove()

# فیلتر برای لاگ‌های اینستاگرامی که باعث شلوغی می‌شوند


def instagram_filter(record):
    # لیست عباراتی که می‌خواهیم فیلتر کنیم
    filter_terms = [
        "unhandled_path",
        "media_info",
        "timeline_feed",
        "API call",
        "HTTP 429",  # Too Many Requests - معمولاً برای هر ارور 429 یک لاگ جداگانه ثبت می‌کنیم
        "Read timed out"  # تایم‌اوت‌های معمولی
    ]

    # بررسی آیا رکورد شامل این عبارات است
    if record["level"].name == "DEBUG":
        for term in filter_terms:
            if term in record["message"]:
                return False

    return True

# تنظیم استایل‌های مختلف لاگ


# اضافه کردن لاگر کنسول
console_handler_id = logger.add(
    sys.stderr,
    format=CONSOLE_FORMAT,
    level=DEFAULT_LOG_LEVEL,
    backtrace=True,
    diagnose=False,
    filter=instagram_filter,
    colorize=True
)

# اضافه کردن لاگر فایل برای همه لاگ‌ها
file_handler_id = logger.add(
    LOG_FILE,
    format=FILE_FORMAT,
    level=DEFAULT_LOG_LEVEL,
    rotation="1 day",
    retention="14 days",
    compression="zip",
    backtrace=True,
    diagnose=True,
    filter=instagram_filter,
    enqueue=True  # برای بهبود عملکرد در multi-threading
)

# اضافه کردن لاگر فایل برای خطاها
error_handler_id = logger.add(
    ERROR_LOG_FILE,
    format=FILE_FORMAT,
    level="ERROR",
    rotation="1 day",
    retention="30 days",
    compression="zip",
    backtrace=True,
    diagnose=True,
    enqueue=True  # برای بهبود عملکرد در multi-threading
)

# اضافه کردن لاگر فایل برای دیباگ
if DEFAULT_LOG_LEVEL == "DEBUG":
    debug_handler_id = logger.add(
        DEBUG_LOG_FILE,
        format=FILE_FORMAT,
        level="DEBUG",
        rotation="1 day",
        retention="7 days",
        compression="zip",
        filter=instagram_filter,
        enqueue=True
    )

# اضافه کردن لاگر فایل برای هشدارها
warning_handler_id = logger.add(
    WARN_LOG_FILE,
    format=FILE_FORMAT,
    level="WARNING",
    rotation="1 day",
    retention="14 days",
    compression="zip",
    enqueue=True
)

# یک پترن Singleton برای اطمینان از یکتا بودن لاگرها در کل برنامه
_loggers = {}


def get_logger(name):
    """
    تابعی برای ایجاد یک لاگر اختصاصی با نام مشخص
    """
    if name not in _loggers:
        _loggers[name] = logger.bind(name=name)
    return _loggers[name]


def log_exception(e, level="ERROR"):
    """
    تابع مفید برای لاگ کردن خطاها با جزئیات بیشتر
    """
    logger_obj = get_logger("exception")
    error_msg = f"Exception: {type(e).__name__}: {str(e)}\n"
    error_msg += f"Traceback: {traceback.format_exc()}"

    if level == "ERROR":
        logger_obj.error(error_msg)
    elif level == "WARNING":
        logger_obj.warning(error_msg)
    elif level == "CRITICAL":
        logger_obj.critical(error_msg)
    else:
        logger_obj.error(error_msg)

# تابع برای ثبت وضعیت سیستم در زمان شروع و پایان


def log_system_info():
    """ثبت اطلاعات سیستم در زمان شروع یا پایان برنامه"""
    sys_logger = get_logger("system")

    try:
        hostname = socket.gethostname()
        ip_address = socket.gethostbyname(hostname)

        system_info = {
            "hostname": hostname,
            "ip_address": ip_address,
            "python_version": sys.version,
            "bot_config": {k: v for k, v in BOT_CONFIG.items() if k != "password"}
        }

        sys_logger.info(
            f"System Info: {json.dumps(system_info, ensure_ascii=False)}")
    except Exception as e:
        sys_logger.error(f"Error logging system info: {str(e)}")


# ثبت وضعیت سیستم در زمان شروع
log_system_info()

# ثبت وضعیت سیستم در زمان پایان
atexit.register(log_system_info)

# فانکشن برای تبدیل لاگرهای پایتون استاندارد به لاگورو


class InterceptHandler(logging.Handler):
    def emit(self, record):
        # افزودن مقدار try-except برای مدیریت خطاها
        try:
            level = logger.level(record.levelname).name
            frame, depth = logging.currentframe(), 2
            while frame.f_code.co_filename == logging.__file__:
                frame = frame.f_back
                depth += 1

            logger.opt(depth=depth, exception=record.exc_info).log(
                level, record.getMessage()
            )
        except Exception as e:
            print(f"Error in log interception: {str(e)}")

# نصب برای کتابخانه‌های خارجی که از logging استاندارد استفاده می‌کنند


def setup_external_loggers():
    # تنظیم مجدد کتابخانه logging استاندارد
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    # لیست نام‌های لاگرهای خارجی که می‌خواهیم هدایت کنیم
    external_loggers = [
        "uvicorn",
        "uvicorn.error",
        "fastapi",
        "sqlalchemy",
        "instagrapi",
        "schedule",
    ]

    # تنظیم همه لاگرهای خارجی
    for logger_name in external_loggers:
        external_logger = logging.getLogger(logger_name)
        external_logger.handlers = [InterceptHandler()]
        external_logger.propagate = False


# تنظیم لاگرهای خارجی
setup_external_loggers()

# لاگر اصلی برای استفاده به عنوان پیش‌فرض
app_logger = get_logger("app")

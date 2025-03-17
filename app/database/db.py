from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.config import DB_CONFIG
import time
import os
from app.utils.logger import get_logger

logger = get_logger("database")

# ایجاد آدرس اتصال به دیتابیس
DATABASE_URL = f"postgresql://{DB_CONFIG['user']}:{DB_CONFIG['password']}@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

# تلاش مجدد برای اتصال به دیتابیس در صورت خطا
max_retries = 5
retry_count = 0

while retry_count < max_retries:
    try:
        # ایجاد موتور SQLAlchemy
        engine = create_engine(DATABASE_URL)

        # تست اتصال
        connection = engine.connect()
        connection.close()
        logger.info("اتصال به دیتابیس با موفقیت برقرار شد")
        break
    except Exception as e:
        retry_count += 1
        logger.error(
            f"خطا در اتصال به دیتابیس (تلاش {retry_count} از {max_retries}): {str(e)}")

        if retry_count < max_retries:
            # صبر کردن قبل از تلاش مجدد
            wait_time = 5 * retry_count
            logger.info(f"تلاش مجدد در {wait_time} ثانیه بعد...")
            time.sleep(wait_time)
        else:
            logger.error(
                "حداکثر تعداد تلاش‌ها برای اتصال به دیتابیس به پایان رسید")
            # اگر نیاز است می‌توانیم خطا را دوباره صادر کنیم
            raise

# ایجاد کلاس پایه برای مدل‌ها
Base = declarative_base()

# ایجاد کلاس Session
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """
    تابعی برای ایجاد یک نشست دیتابیس و بستن آن پس از استفاده
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    تابعی برای ایجاد جداول دیتابیس
    """
    try:
        logger.info("در حال ایجاد جداول دیتابیس...")
        Base.metadata.create_all(bind=engine)
        logger.info("جداول دیتابیس با موفقیت ایجاد شدند")
    except Exception as e:
        logger.error(f"خطا در ایجاد جداول دیتابیس: {str(e)}")
        raise

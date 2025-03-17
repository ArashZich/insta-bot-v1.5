from instagrapi import Client
from instagrapi.exceptions import LoginRequired, TwoFactorRequired, ChallengeRequired
import json
import os
from app.config import INSTAGRAM_CONFIG
from app.utils.logger import get_logger
from app.database.models import BotStatus
from sqlalchemy.orm import Session
from datetime import datetime

logger = get_logger("session_manager")


class SessionManager:
    def __init__(self, db: Session):
        self.client = Client()
        self.session_file = INSTAGRAM_CONFIG["session_file"]
        self.username = INSTAGRAM_CONFIG["username"]
        self.password = INSTAGRAM_CONFIG["password"]
        self.db = db

    def load_session(self):
        """بارگذاری نشست ذخیره شده"""
        if os.path.exists(self.session_file):
            try:
                logger.info("تلاش برای بارگذاری نشست ذخیره شده")
                with open(self.session_file, 'r') as f:
                    session_data = json.load(f)

                self.client.set_settings(session_data)
                # بررسی اعتبار نشست
                try:
                    self.client.get_timeline_feed()
                    logger.info("نشست با موفقیت بارگذاری شد")
                    self._update_bot_status(True)
                    return True
                except LoginRequired:
                    logger.warning("نشست منقضی شده است، نیاز به ورود مجدد")
                    return False
            except Exception as e:
                logger.error(f"خطا در بارگذاری نشست: {str(e)}")
                return False
        else:
            logger.info("فایل نشست پیدا نشد")
            return False

    def login(self):
        """ورود به اکانت اینستاگرام"""
        try:
            logger.info(f"تلاش برای ورود به عنوان {self.username}")

            # تلاش برای ورود با اطلاعات کاربری
            login_attempt = self.client.login(self.username, self.password)

            if login_attempt:
                # ذخیره نشست برای استفاده بعدی
                self._save_session()

                # بروزرسانی وضعیت بات در دیتابیس
                self._update_bot_status(True)

                # تست اعتبار نشست با انجام یک عملیات سبک
                try:
                    self.client.get_timeline_feed()
                    logger.info("نشست با موفقیت ایجاد و تأیید شد")
                except Exception as e:
                    logger.warning(
                        f"نشست ایجاد شد اما در تأیید آن مشکلی وجود دارد: {str(e)}")

                logger.info("ورود با موفقیت انجام شد")
                return True
            else:
                logger.error("ورود ناموفق بود")
                self._update_bot_status(False, "ورود ناموفق بود")
                return False

        except Exception as e:
            logger.error(f"خطا در ورود: {str(e)}")
            self._update_bot_status(False, str(e))
            return False

    def _save_session(self):
        """ذخیره نشست برای استفاده بعدی"""
        settings = self.client.get_settings()
        with open(self.session_file, 'w') as f:
            json.dump(settings, f, indent=4)
        logger.info("نشست با موفقیت ذخیره شد")

    def logout(self):
        """خروج از اکانت اینستاگرام"""
        try:
            self.client.logout()
            if os.path.exists(self.session_file):
                os.remove(self.session_file)
            self._update_bot_status(False)
            logger.info("خروج با موفقیت انجام شد")
            return True
        except Exception as e:
            logger.error(f"خطا در خروج: {str(e)}")
            return False

    def _update_bot_status(self, is_running, error=None):
        """بروزرسانی وضعیت بات در دیتابیس"""
        try:
            status = self.db.query(BotStatus).first()
            if not status:
                status = BotStatus(
                    is_running=False,
                    follows_today=0,
                    unfollows_today=0,
                    comments_today=0,
                    likes_today=0,
                    direct_messages_today=0,
                    story_views_today=0,
                    story_reactions_today=0,
                    error_count=0
                )
                self.db.add(status)

            status.is_running = is_running
            if is_running:
                status.last_login = datetime.now()

            if error:
                status.last_error = error
                status.last_error_time = datetime.now()
                # اطمینان از اینکه error_count صفر نیست
                if status.error_count is None:
                    status.error_count = 1
                else:
                    status.error_count += 1

            self.db.commit()
        except Exception as e:
            logger.error(f"خطا در بروزرسانی وضعیت بات: {str(e)}")
            self.db.rollback()

    def get_client(self):
        """دریافت نمونه client اینستاگرام"""
        return self.client

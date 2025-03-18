from instagrapi import Client
from instagrapi.exceptions import LoginRequired, ChallengeRequired, PleaseWaitFewMinutes
import json
import os
import time
import random
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
        self.login_attempts = 0
        self.last_login_attempt = None
        self.max_login_attempts = 3

        # تنظیم تایم‌اوت طولانی‌تر برای عملیات‌های مختلف
        self.client.request_timeout = 30  # افزایش تایم‌اوت درخواست‌ها به 30 ثانیه

    def load_session(self) -> bool:
        """بارگذاری نشست ذخیره شده"""
        if os.path.exists(self.session_file):
            try:
                logger.info("تلاش برای بارگذاری نشست ذخیره شده")
                with open(self.session_file, 'r') as f:
                    session_data = json.load(f)

                self.client.set_settings(session_data)

                # بررسی اعتبار نشست با یک عملیات سبک
                try:
                    # به جای timeline feed از عملیات سبک‌تر استفاده می‌کنیم
                    self.client.get_settings()
                    logger.info("نشست با موفقیت بارگذاری شد")
                    self._update_bot_status(True)
                    return True
                except LoginRequired:
                    logger.warning("نشست منقضی شده است، نیاز به ورود مجدد")
                    return False
                except PleaseWaitFewMinutes as e:
                    logger.warning(f"محدودیت نرخ: {str(e)}. استراحت کوتاه...")
                    time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
                    return False
                except Exception as e:
                    logger.error(f"خطا در بررسی اعتبار نشست: {str(e)}")
                    return False
            except Exception as e:
                logger.error(f"خطا در بارگذاری نشست: {str(e)}")
                return False
        else:
            logger.info("فایل نشست پیدا نشد")
            return False

    def login(self) -> bool:
        """ورود به اکانت اینستاگرام با مدیریت خطاها و چالش‌ها"""
        # بررسی تعداد تلاش‌های ورود
        current_time = datetime.now()
        if self.last_login_attempt:
            time_diff = (current_time - self.last_login_attempt).seconds
            if time_diff < 3600 and self.login_attempts >= self.max_login_attempts:
                logger.warning(
                    f"بیش از حد تلاش ورود در یک ساعت اخیر ({self.login_attempts}). استراحت...")
                time.sleep(random.randint(1800, 3600))  # 30-60 دقیقه استراحت
                self.login_attempts = 0

        self.last_login_attempt = current_time
        self.login_attempts += 1

        # افزودن تأخیر قبل از ورود برای طبیعی به نظر رسیدن
        delay = random.randint(3, 10)
        logger.info(f"تأخیر {delay} ثانیه قبل از تلاش ورود...")
        time.sleep(delay)

        try:
            logger.info(f"تلاش برای ورود به عنوان {self.username}")

            # تنظیم اطلاعات دستگاه تصادفی برای هر ورود
            self._set_random_device()

            # تلاش برای ورود
            login_attempt = 0
            max_attempts = 3

            while login_attempt < max_attempts:
                try:
                    if login_attempt > 0:
                        logger.info(
                            f"تلاش مجدد ورود ({login_attempt+1}/{max_attempts})")
                        # 5-10 دقیقه استراحت بین تلاش‌ها
                        time.sleep(random.randint(300, 600))

                    login_success = self.client.login(
                        self.username, self.password)

                    if login_success:
                        # بعد از ورود موفق، کمی تأخیر قبل از ذخیره نشست
                        time.sleep(random.randint(2, 5))
                        self._save_session()
                        self._update_bot_status(True)
                        logger.info("ورود با موفقیت انجام شد")
                        return True
                    else:
                        logger.error("ورود ناموفق بود، دلیل مشخص نیست")
                        login_attempt += 1

                except ChallengeRequired:
                    logger.warning(
                        "چالش اینستاگرام دریافت شد. نیاز به انتظار طولانی...")
                    # در صورت مواجهه با چالش، مدت زیادی صبر می‌کنیم
                    wait_time = random.randint(1800, 3600)  # 30-60 دقیقه
                    logger.info(
                        f"انتظار {wait_time} ثانیه قبل از تلاش مجدد...")
                    time.sleep(wait_time)
                    login_attempt += 1

                except PleaseWaitFewMinutes as e:
                    logger.warning(f"محدودیت نرخ: {str(e)}. استراحت...")
                    self._update_bot_status(False, str(e))
                    # 10-20 دقیقه استراحت
                    time.sleep(random.randint(600, 1200))
                    login_attempt += 1

                except Exception as e:
                    logger.error(f"خطای ناشناخته در ورود: {str(e)}")
                    self._update_bot_status(False, str(e))
                    login_attempt += 1

            logger.error(f"ناموفق در ورود پس از {max_attempts} تلاش")
            return False

        except Exception as e:
            logger.error(f"خطا در فرآیند ورود: {str(e)}")
            self._update_bot_status(False, str(e))
            return False

    def _set_random_device(self):
        """تنظیم اطلاعات دستگاه تصادفی برای هر ورود"""
        devices = [
            {
                "app_version": "212.0.0.38.119",
                "android_version": 27,
                "android_release": "8.1.0",
                "dpi": "480dpi",
                "resolution": "1080x1920",
                "manufacturer": "samsung",
                "device": "SM-G950F",
                "model": "dreamlte",
                "cpu": "universal8895"
            },
            {
                "app_version": "203.0.0.29.118",
                "android_version": 26,
                "android_release": "8.0.0",
                "dpi": "640dpi",
                "resolution": "1440x2960",
                "manufacturer": "samsung",
                "device": "SM-G965F",
                "model": "star2lte",
                "cpu": "universal9810"
            },
            {
                "app_version": "195.0.0.31.123",
                "android_version": 29,
                "android_release": "10",
                "dpi": "420dpi",
                "resolution": "1080x2280",
                "manufacturer": "OnePlus",
                "device": "OnePlus6T",
                "model": "OnePlus6T",
                "cpu": "qcom"
            }
        ]

        device = random.choice(devices)
        logger.info(f"تنظیم دستگاه: {device['model']}")

        try:
            self.client.set_device(device)
            # افزودن کمی تأخیر تصادفی بعد از تنظیم دستگاه
            time.sleep(random.uniform(1.5, 3.5))
            return True
        except Exception as e:
            logger.error(f"خطا در تنظیم دستگاه: {str(e)}")
            return False

    def _save_session(self):
        """ذخیره نشست برای استفاده بعدی"""
        try:
            settings = self.client.get_settings()

            # اطمینان از وجود دایرکتوری والد
            os.makedirs(os.path.dirname(self.session_file), exist_ok=True)

            with open(self.session_file, 'w') as f:
                json.dump(settings, f, indent=4)
            logger.info("نشست با موفقیت ذخیره شد")
            return True
        except Exception as e:
            logger.error(f"خطا در ذخیره نشست: {str(e)}")
            return False

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
                self.db.flush()

            # بروزرسانی زمان آخرین فعالیت
            status.is_running = is_running
            if is_running:
                status.last_login = datetime.now()

            # بررسی و مقداردهی error_count در صورت None بودن
            if status.error_count is None:
                status.error_count = 0

            if error:
                status.last_error = error
                status.last_error_time = datetime.now()
                status.error_count += 1

            self.db.commit()
        except Exception as e:
            logger.error(f"خطا در بروزرسانی وضعیت بات: {str(e)}")
            self.db.rollback()

    def get_client(self):
        """دریافت نمونه client اینستاگرام"""
        return self.client

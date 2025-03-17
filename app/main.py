import os
import time
import asyncio
import threading
import random
from datetime import datetime, timedelta
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.config import API_CONFIG, BOT_CONFIG
from app.database.db import init_db, get_db
from app.utils.logger import get_logger
from app.api.router import router as api_router
from app.bot.session_manager import SessionManager
from app.bot.hashtags import HashtagManager
from app.bot.activity import ActivityManager
from app.bot.follow import FollowManager
from app.bot.unfollow import UnfollowManager
from app.bot.comment import CommentManager
from app.bot.direct import DirectMessageManager
from app.bot.story import StoryManager

logger = get_logger("main")

# ایجاد نمونه FastAPI
app = FastAPI(
    title=API_CONFIG["title"],
    description=API_CONFIG["description"],
    version=API_CONFIG["version"]
)

# اضافه کردن روترهای API
app.include_router(api_router)

# رویداد راه‌اندازی اولیه


@app.on_event("startup")
async def startup_event():
    """
    رویداد راه‌اندازی اولیه
    """
    logger.info("در حال راه‌اندازی برنامه...")

    # ایجاد جداول دیتابیس
    init_db()
    logger.info("دیتابیس با موفقیت راه‌اندازی شد")

    # راه‌اندازی بات در یک thread جداگانه
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.daemon = True
    bot_thread.start()
    logger.info("بات با موفقیت راه‌اندازی شد")


def perform_random_action(db, managers, activity_manager):
    """
    انجام یک اقدام تصادفی توسط بات
    """
    if not activity_manager.is_working_hours():
        logger.info("خارج از ساعات کاری است، اقدامی انجام نمی‌شود")
        return False

    # لیست اقدامات ممکن با وزن‌های مختلف
    actions = [
        # فالو کردن کاربران با هشتگ
        (managers["follow"].follow_users_by_hashtag, 20),
        (managers["follow"].follow_back_users, 15),        # فالو متقابل
        # آنفالو کردن غیرفالوکنندگان
        (managers["unfollow"].unfollow_non_followers, 10),
        (managers["unfollow"].unfollow_if_unfollowed, 10),  # آنفالو متقابل
        # کامنت بر روی پست‌های هشتگ
        (managers["comment"].comment_on_hashtag_posts, 15),
        # کامنت بر روی پست‌های فالوکنندگان
        (managers["comment"].comment_on_followers_posts, 10),
        # پیام خوش‌آمدگویی
        (managers["direct"].send_welcome_message_to_new_followers, 5),
        # مشاهده و واکنش به استوری‌ها
        (managers["story"].view_and_react_to_followers_stories, 20)
    ]

    # انتخاب یک اقدام بر اساس وزن‌ها
    weights = [weight for _, weight in actions]
    selected_action_func, _ = random.choices(actions, weights=weights, k=1)[0]

    try:
        logger.info(f"انجام اقدام: {selected_action_func.__name__}")

        # پارامترهای مورد نیاز برای هر تابع
        result = None
        if selected_action_func == managers["follow"].follow_users_by_hashtag:
            hashtag = managers["hashtag"].get_random_hashtag()
            count = random.randint(1, 3)
            result = asyncio.run(selected_action_func(hashtag, count))

        elif selected_action_func == managers["follow"].follow_back_users:
            count = random.randint(2, 5)
            result = asyncio.run(selected_action_func(count))

        elif selected_action_func == managers["unfollow"].unfollow_non_followers:
            count = random.randint(2, 5)
            days = random.randint(5, 15)
            result = asyncio.run(selected_action_func(count, days))

        elif selected_action_func == managers["unfollow"].unfollow_if_unfollowed:
            count = random.randint(2, 5)
            result = asyncio.run(selected_action_func(count))

        elif selected_action_func == managers["comment"].comment_on_hashtag_posts:
            hashtag = managers["hashtag"].get_random_hashtag()
            count = random.randint(1, 2)
            result = asyncio.run(selected_action_func(hashtag, count))

        elif selected_action_func == managers["comment"].comment_on_followers_posts:
            count = random.randint(1, 2)
            result = asyncio.run(selected_action_func(count))

        elif selected_action_func == managers["direct"].send_welcome_message_to_new_followers:
            count = random.randint(1, 3)
            result = asyncio.run(selected_action_func(count))

        elif selected_action_func == managers["story"].view_and_react_to_followers_stories:
            count = random.randint(3, 7)
            result = asyncio.run(selected_action_func(count))

        # بررسی نتیجه، فقط اگر نتیجه موفقیت‌آمیز بود، آن را گزارش می‌کنیم
        if result is not None and result > 0:
            logger.info(
                f"اقدام {selected_action_func.__name__} با موفقیت انجام شد. تعداد: {result}")
            return True
        else:
            logger.warning(
                f"اقدام {selected_action_func.__name__} نتیجه‌ای نداشت یا با خطا مواجه شد")
            return False

    except Exception as e:
        logger.error(
            f"خطا در انجام اقدام {selected_action_func.__name__}: {str(e)}")
        return False


def start_bot():
    """
    راه‌اندازی بات و شروع فعالیت‌های تصادفی
    """
    try:
        # کمی صبر می‌کنیم تا دیتابیس آماده شود
        time.sleep(5)

        # ایجاد session دیتابیس
        db = next(get_db())

        # ایجاد نمونه مدیرت نشست
        session_manager = SessionManager(db)

        # تلاش برای ورود به حساب کاربری
        logger.info("تلاش برای ورود به حساب کاربری اینستاگرام...")
        login_success = False

        # ابتدا تلاش برای بارگذاری نشست
        if session_manager.load_session():
            # تست اتصال بعد از بارگذاری نشست
            try:
                client = session_manager.get_client()
                client.get_timeline_feed()
                logger.info("نشست بارگذاری شده معتبر است")
                login_success = True
            except Exception as e:
                logger.warning(f"نشست بارگذاری شده معتبر نیست: {str(e)}")
                # تلاش برای ورود با رمز عبور
                login_success = session_manager.login()
        else:
            # تلاش برای ورود با رمز عبور
            login_success = session_manager.login()

        if login_success:
            logger.info("ورود به حساب کاربری با موفقیت انجام شد")

            # ایجاد مدیریت‌کننده‌های مختلف
            client = session_manager.get_client()
            hashtag_manager = HashtagManager()
            activity_manager = ActivityManager(
                db, session_manager, hashtag_manager)
            follow_manager = FollowManager(db, client, activity_manager)
            unfollow_manager = UnfollowManager(db, client, activity_manager)
            comment_manager = CommentManager(db, client, activity_manager)
            direct_manager = DirectMessageManager(db, client, activity_manager)
            story_manager = StoryManager(db, client, activity_manager)

            # ذخیره همه مدیریت‌کننده‌ها در یک دیکشنری
            managers = {
                "hashtag": hashtag_manager,
                "activity": activity_manager,
                "follow": follow_manager,
                "unfollow": unfollow_manager,
                "comment": comment_manager,
                "direct": direct_manager,
                "story": story_manager
            }

            # تنظیم وظایف روزانه (مثل ریست شمارنده‌ها)
            activity_manager.setup_daily_tasks()

            # اجرای اولیه - به جای پاسخ به دایرکت‌ها، فقط لاگ می‌کنیم
            logger.info("بات آماده است، شروع اقدامات تصادفی...")

            # بررسی و اجرای وظایف زمانبندی شده
            schedule_thread = threading.Thread(target=run_scheduler)
            schedule_thread.daemon = True
            schedule_thread.start()

            logger.info("بات در حال شروع اقدامات تصادفی...")

            # حلقه اصلی بات
            consecutive_errors = 0
            max_consecutive_errors = 5

            while True:
                # بررسی اینکه آیا ساعت کاری است
                if activity_manager.is_working_hours():
                    # انجام یک اقدام تصادفی
                    success = perform_random_action(
                        db, managers, activity_manager)

                    # بررسی خطاهای متوالی
                    if not success:
                        consecutive_errors += 1
                        logger.warning(
                            f"خطای متوالی {consecutive_errors} از {max_consecutive_errors}")

                        if consecutive_errors >= max_consecutive_errors:
                            logger.error(
                                f"تعداد خطاهای متوالی به {max_consecutive_errors} رسید. تلاش مجدد برای ورود...")
                            # تلاش مجدد برای ورود
                            if session_manager.login():
                                logger.info("ورود مجدد موفقیت‌آمیز بود")
                                consecutive_errors = 0
                                # بروزرسانی کلاینت در مدیریت‌کننده‌ها
                                client = session_manager.get_client()
                                follow_manager.client = client
                                unfollow_manager.client = client
                                comment_manager.client = client
                                direct_manager.client = client
                                story_manager.client = client
                            else:
                                logger.error(
                                    "ورود مجدد ناموفق بود. توقف برای 30 دقیقه...")
                                time.sleep(1800)  # 30 دقیقه استراحت
                    else:
                        consecutive_errors = 0  # ریست شمارنده خطاها در صورت موفقیت

                    # استراحت تصادفی بین اقدامات
                    min_delay = BOT_CONFIG["min_delay_between_actions"]
                    max_delay = BOT_CONFIG["max_delay_between_actions"]

                    # استراحت طولانی‌تر بین اقدامات (2-10 دقیقه)
                    action_sleep = random.randint(min_delay * 4, max_delay * 4)
                    logger.info(
                        f"استراحت به مدت {action_sleep} ثانیه بین اقدامات")
                    time.sleep(action_sleep)
                else:
                    # استراحت تا شروع ساعات کاری بعدی
                    logger.info("خارج از ساعات کاری، بات در حالت استراحت")
                    # بررسی هر 30 دقیقه
                    time.sleep(1800)

        else:
            logger.error("ورود به حساب کاربری ناموفق بود")

    except Exception as e:
        logger.error(f"خطا در راه‌اندازی بات: {str(e)}")


def run_scheduler():
    """
    اجرای زمانبندی روزانه
    """
    import schedule

    logger.info("زمانبندی وظایف روزانه شروع شد")

    while True:
        schedule.run_pending()
        time.sleep(60)  # بررسی وظایف زمانبندی شده هر دقیقه

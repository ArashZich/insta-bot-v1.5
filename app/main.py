import os
import time
import asyncio
import threading
import random
from datetime import datetime, timedelta
from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.config import API_CONFIG, BOT_CONFIG, USER_AGENTS
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
from app.database.models import BotStatus, InteractionType


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

    # تست اتصال به دیتابیس
    try:
        from app.database.test_db import test_database_connection
        from app.database.db import get_db

        db = next(get_db())
        test_result = test_database_connection(db)

        if test_result:
            logger.info("تست دیتابیس با موفقیت انجام شد")
        else:
            logger.error("تست دیتابیس ناموفق بود - بررسی کنید!")
    except Exception as e:
        logger.error(f"خطا در تست دیتابیس: {str(e)}")

    # راه‌اندازی بات در یک thread جداگانه
    bot_thread = threading.Thread(target=start_bot)
    bot_thread.daemon = True
    bot_thread.start()
    logger.info("بات با موفقیت راه‌اندازی شد")


def get_next_action_with_natural_distribution():
    """
    انتخاب اقدام بعدی با توزیع طبیعی‌تر که اولویت‌بندی هم دارد
    """
    # تعریف اقدامات با وزن‌های متغیر
    time_of_day = datetime.now().hour

    # وزن‌های پایه
    base_weights = {
        "follow_users_by_hashtag": 15,
        "follow_back_users": 15,
        "unfollow_non_followers": 10,
        "unfollow_if_unfollowed": 10,
        "comment_on_hashtag_posts": 10,
        "comment_on_followers_posts": 5,
        "send_welcome_message_to_new_followers": 5,
        "view_and_react_to_followers_stories": 15,
        "view_trending_stories": 10,
        "regular_unfollow_routine": 5
    }

    # تنظیم وزن‌ها براساس زمان روز
    if 9 <= time_of_day < 12:  # صبح
        # در صبح بیشتر مشاهده استوری و کامنت
        weights = {
            **base_weights,
            "view_and_react_to_followers_stories": 25,
            "view_trending_stories": 20,
            "comment_on_hashtag_posts": 15
        }
    elif 12 <= time_of_day < 15:  # ظهر
        # در ظهر بیشتر فالو و فالو متقابل
        weights = {
            **base_weights,
            "follow_users_by_hashtag": 25,
            "follow_back_users": 20
        }
    elif 15 <= time_of_day < 19:  # عصر
        # در عصر ترکیبی از کامنت و فالو
        weights = {
            **base_weights,
            "comment_on_hashtag_posts": 20,
            "follow_users_by_hashtag": 20
        }
    else:  # شب
        # در شب بیشتر آنفالو و پیام مستقیم
        weights = {
            **base_weights,
            "unfollow_non_followers": 20,
            "send_welcome_message_to_new_followers": 15,
            "regular_unfollow_routine": 10
        }

    # ساخت لیست اقدامات با وزن‌های تنظیم شده
    actions = []
    for action, weight in weights.items():
        actions.extend([action] * weight)

    # انتخاب تصادفی
    return random.choice(actions)


def should_perform_action(is_important=False):
    """
    تصمیم‌گیری برای انجام یا عدم انجام یک اقدام 
    براساس الگوی رفتاری طبیعی انسان
    """
    # الگوی طبیعی انسان: گاهی فعالیت نکردن برای مدتی
    # این توابع الگوی فعالیت طبیعی را شبیه‌سازی می‌کنند

    # اگر اقدام مهم باشد، با احتمال بیشتری انجام می‌دهیم
    if is_important:
        return random.random() < 0.9  # 90% احتمال

    # روز هفته
    day_of_week = datetime.now().weekday()  # 0-6 (دوشنبه تا یکشنبه)

    # ساعت روز
    hour = datetime.now().hour

    # در آخر هفته کمتر فعالیت می‌کنیم
    if day_of_week >= 5:  # جمعه و شنبه
        if random.random() < 0.3:  # 30% احتمال عدم انجام
            return False

    # در ساعات اوج کاری (10-13 و 16-19) فعالیت بیشتر
    if (10 <= hour <= 13) or (16 <= hour <= 19):
        return random.random() < 0.85  # 85% احتمال انجام

    # در ساعات استراحت (13-15) و شب (21-23) کمتر فعالیت می‌کنیم
    if (13 <= hour <= 15) or (21 <= hour <= 23):
        return random.random() < 0.5  # 50% احتمال انجام

    # در سایر ساعات، احتمال متوسط
    return random.random() < 0.7  # 70% احتمال انجام


async def perform_random_action(db, managers, activity_manager):
    """
    انجام یک اقدام تصادفی توسط بات با رفتار طبیعی‌تر
    """
    if not activity_manager.is_working_hours():
        logger.info("خارج از ساعات کاری است، اقدامی انجام نمی‌شود")
        return False

    # انتخاب اقدام تصادفی با توزیع طبیعی‌تر
    selected_action = get_next_action_with_natural_distribution()

    # تصمیم‌گیری برای انجام یا عدم انجام اقدام
    is_important = "follow_back" in selected_action or "welcome_message" in selected_action
    if not should_perform_action(is_important):
        logger.info(
            f"تصمیم گرفته شد اقدام {selected_action} انجام نشود (الگوی رفتار طبیعی)")
        # گاهی اوقات قبل از انصراف از اقدام، کمی صبر می‌کنیم
        time.sleep(random.uniform(1.0, 5.0))
        return True  # اگرچه اقدامی انجام نشد، اما سیستم سالم است

    try:
        logger.info(f"انجام اقدام: {selected_action}")

        # تست اعتبار نشست قبل از انجام اقدام
        try:
            client = managers["follow"].client  # هر مدیریتی که client دارد
            client.get_timeline_feed(amount=1)
            logger.info("نشست معتبر است")
        except Exception as e:
            logger.error(f"نشست نامعتبر است، تلاش برای ورود مجدد: {str(e)}")

            # تلاش برای ورود مجدد
            session_manager = SessionManager(db)
            if session_manager.login():
                logger.info("ورود مجدد موفقیت‌آمیز بود")

                # بروزرسانی کلاینت در تمام مدیریت‌کننده‌ها
                new_client = session_manager.get_client()
                for manager_name in ["follow", "unfollow", "comment", "direct", "story"]:
                    if manager_name in managers and hasattr(managers[manager_name], 'client'):
                        managers[manager_name].client = new_client
                        logger.info(f"کلاینت در {manager_name} بروزرسانی شد")
            else:
                logger.error("ورود مجدد ناموفق بود")
                return False

        # اجرای اقدام انتخاب شده
        result = None

        # فالو کردن کاربران با هشتگ
        if selected_action == "follow_users_by_hashtag":
            hashtag = managers["hashtag"].get_random_hashtag()
            count = random.randint(1, 2)  # کاهش تعداد برای تشخیص نشدن
            result = await managers["follow"].follow_users_by_hashtag(hashtag, count)

            # ثبت آمار
            if result and result > 0:
                logger.info(f"آمار فالو بروزرسانی شد: {result} فالو جدید")

        # فالو متقابل
        elif selected_action == "follow_back_users":
            count = random.randint(1, 2)
            result = await managers["follow"].follow_back_users(count)

            # ثبت آمار
            if result and result > 0:
                logger.info(f"آمار فالو بروزرسانی شد: {result} فالو متقابل")

        # آنفالو کردن غیرفالوکنندگان
        elif selected_action == "unfollow_non_followers":
            count = random.randint(1, 2)
            days = random.randint(7, 15)  # افزایش زمان انتظار قبل از آنفالو
            result = await managers["unfollow"].unfollow_non_followers(count, days)

            # ثبت آمار
            if result and result > 0:
                logger.info(f"آمار آنفالو بروزرسانی شد: {result} آنفالو جدید")

        # آنفالو متقابل
        elif selected_action == "unfollow_if_unfollowed":
            count = random.randint(1, 2)
            result = await managers["unfollow"].unfollow_if_unfollowed(count)

            # ثبت آمار
            if result and result > 0:
                logger.info(
                    f"آمار آنفالو بروزرسانی شد: {result} آنفالو متقابل")

        # روتین منظم آنفالو
        elif selected_action == "regular_unfollow_routine":
            count = random.randint(1, 3)
            result = await managers["unfollow"].regular_unfollow_routine(count)

            # ثبت آمار
            if result and result > 0:
                logger.info(
                    f"آمار آنفالو بروزرسانی شد: {result} آنفالو در روتین منظم")

        # کامنت بر روی پست‌های هشتگ
        elif selected_action == "comment_on_hashtag_posts":
            hashtag = managers["hashtag"].get_random_hashtag()
            count = 1  # فقط 1 کامنت در هر بار
            result = await managers["comment"].comment_on_hashtag_posts(hashtag, count)

            # ثبت آمار
            if result and result > 0:
                logger.info(f"آمار کامنت بروزرسانی شد: {result} کامنت جدید")

        # کامنت بر روی پست‌های فالوورها
        elif selected_action == "comment_on_followers_posts":
            count = 1  # فقط 1 کامنت در هر بار
            result = await managers["comment"].comment_on_followers_posts(count)

            # ثبت آمار
            if result and result > 0:
                logger.info(f"آمار کامنت بروزرسانی شد: {result} کامنت جدید")

        # پیام خوش‌آمدگویی
        elif selected_action == "send_welcome_message_to_new_followers":
            count = 1  # فقط 1 پیام در هر بار
            result = await managers["direct"].send_welcome_message_to_new_followers(count)

            # ثبت آمار
            if result and result > 0:
                logger.info(f"آمار پیام بروزرسانی شد: {result} پیام جدید")

        # مشاهده و واکنش به استوری‌های فالوورها
        elif selected_action == "view_and_react_to_followers_stories":
            count = random.randint(1, 3)
            result = await managers["story"].view_and_react_to_followers_stories(count)

            # ثبت آمار
            if result and result > 0:
                logger.info(
                    f"آمار استوری بروزرسانی شد: {result} مشاهده استوری")

        # مشاهده استوری‌های ترند
        elif selected_action == "view_trending_stories":
            count = random.randint(1, 3)
            result = await managers["story"].view_trending_stories(count)

            # ثبت آمار
            if result and result > 0:
                logger.info(
                    f"آمار استوری بروزرسانی شد: {result} مشاهده استوری ترند")

        # بررسی نتیجه، فقط اگر نتیجه موفقیت‌آمیز بود، آن را گزارش می‌کنیم
        if result is not None and result > 0:
            logger.info(
                f"اقدام {selected_action} با موفقیت انجام شد. تعداد: {result}")

            # بروزرسانی آخرین فعالیت در هر صورت
            status = db.query(BotStatus).first()
            if status:
                status.last_activity = datetime.now()
                db.commit()
                logger.info("زمان آخرین فعالیت بروزرسانی شد")

            return True
        else:
            logger.warning(
                f"اقدام {selected_action} نتیجه‌ای نداشت یا با خطا مواجه شد")
            return False

    except Exception as e:
        logger.error(f"خطا در انجام اقدام {selected_action}: {str(e)}")
        return False


async def start_bot():
    """
    راه‌اندازی بات و شروع فعالیت‌های تصادفی با استراتژی رفتار انسانی
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
                client.get_timeline_feed(amount=1)
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

            # بررسی و اجرای وظایف زمانبندی شده
            schedule_thread = threading.Thread(target=run_scheduler)
            schedule_thread.daemon = True
            schedule_thread.start()

            logger.info("بات در حال شروع اقدامات تصادفی...")

            # تاخیر اولیه برای شبیه‌سازی رفتار طبیعی
            startup_delay = random.randint(60, 300)  # 1-5 دقیقه
            logger.info(f"تاخیر اولیه به مدت {startup_delay} ثانیه...")
            time.sleep(startup_delay)

            # حلقه اصلی بات با رفتار طبیعی‌تر
            consecutive_errors = 0
            max_consecutive_errors = 5

            # متغیرهای حالت برای شبیه‌سازی رفتار انسانی
            active_period = True
            last_activity_change = datetime.now()
            activity_period_length = random.randint(1800, 3600)  # 30-60 دقیقه
            inactive_period_length = random.randint(1800, 7200)  # 30-120 دقیقه

            while True:
                try:
                    # بررسی تغییر حالت فعالیت (فعال/غیرفعال)
                    current_time = datetime.now()
                    time_since_change = (
                        current_time - last_activity_change).total_seconds()

                    if active_period and time_since_change > activity_period_length:
                        # تغییر به حالت غیرفعال
                        active_period = False
                        last_activity_change = current_time
                        inactive_period_length = random.randint(
                            1800, 7200)  # 30-120 دقیقه
                        logger.info(
                            f"تغییر به حالت غیرفعال به مدت {inactive_period_length} ثانیه")
                        # 5-10 دقیقه استراحت اولیه
                        time.sleep(random.randint(300, 600))

                    elif not active_period and time_since_change > inactive_period_length:
                        # تغییر به حالت فعال
                        active_period = True
                        last_activity_change = current_time
                        activity_period_length = random.randint(
                            1800, 3600)  # 30-60 دقیقه
                        logger.info(
                            f"تغییر به حالت فعال به مدت {activity_period_length} ثانیه")

                    # اگر در حالت غیرفعال هستیم، فقط گاهی اوقات چک می‌کنیم
                    if not active_period:
                        check_interval = random.randint(
                            600, 1200)  # 10-20 دقیقه
                        logger.info(
                            f"در حالت غیرفعال، استراحت به مدت {check_interval} ثانیه")
                        time.sleep(check_interval)
                        continue

                    # بررسی اینکه آیا ساعت کاری است
                    if activity_manager.is_working_hours():
                        # انجام یک اقدام تصادفی
                        success = await perform_random_action(db, managers, activity_manager)

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
                                        "ورود مجدد ناموفق بود. توقف برای 60 دقیقه...")
                                    time.sleep(3600)  # 60 دقیقه استراحت
                        else:
                            consecutive_errors = 0  # ریست شمارنده خطاها در صورت موفقیت

                        # استراحت تصادفی بین اقدامات - توزیع طبیعی‌تر
                        action_delay = random.randint(
                            BOT_CONFIG["min_delay_between_actions"],
                            BOT_CONFIG["max_delay_between_actions"]
                        )

                        # اضافه کردن عامل تصادفی بیشتر
                        if random.random() < 0.2:  # 20% احتمال
                            # استراحت طولانی‌تر
                            action_delay *= random.uniform(1.5, 2.5)
                            logger.info(
                                f"استراحت طولانی‌تر به مدت {action_delay:.0f} ثانیه")
                        elif random.random() < 0.3:  # 30% احتمال
                            # استراحت کوتاه‌تر
                            action_delay *= random.uniform(0.5, 0.8)
                            logger.info(
                                f"استراحت کوتاه‌تر به مدت {action_delay:.0f} ثانیه")
                        else:
                            logger.info(
                                f"استراحت به مدت {action_delay} ثانیه بین اقدامات")

                        # تقسیم استراحت به چند بخش برای شبیه‌سازی بهتر رفتار انسان
                        chunks = random.randint(3, 6)
                        chunk_size = action_delay / chunks

                        for i in range(chunks):
                            # در طول استراحت، گاهی فعالیت‌های سبک انجام می‌دهیم (مثل چک کردن تایم‌لاین)
                            if i > 0 and random.random() < 0.3:  # 30% احتمال
                                try:
                                    client.get_timeline_feed(amount=1)
                                    logger.debug(
                                        "بررسی تایم‌لاین در حین استراحت")
                                except Exception:
                                    pass  # نادیده گرفتن خطاها در فعالیت‌های غیر اصلی

                            time.sleep(chunk_size)
                    else:
                        # استراحت تا شروع ساعات کاری بعدی
                        logger.info("خارج از ساعات کاری، بات در حالت استراحت")

                        # محاسبه زمان تقریبی تا شروع ساعات کاری بعدی
                        current_hour = datetime.now().hour
                        current_day = datetime.now().weekday()

                        if current_day >= 5:  # آخر هفته
                            next_start_hour = BOT_CONFIG["working_hours"].get(
                                "weekend_start", BOT_CONFIG["working_hours"]["start"])
                        else:
                            next_start_hour = BOT_CONFIG["working_hours"]["start"]

                        # اگر همین امروز ساعات کاری شروع می‌شود
                        if current_hour < next_start_hour:
                            sleep_seconds = (
                                next_start_hour - current_hour) * 3600
                            # کم‌تر از کل زمان می‌خوابیم و مجدداً چک می‌کنیم
                            # حداکثر 30 دقیقه یکبار چک کنیم
                            sleep_time = min(1800, sleep_seconds)
                        else:
                            # تا فردا صبح باید منتظر بمانیم
                            sleep_time = 1800  # 30 دقیقه بعد دوباره چک می‌کنیم

                        logger.info(
                            f"استراحت به مدت {sleep_time} ثانیه تا چک مجدد ساعات کاری")
                        time.sleep(sleep_time)

                except Exception as e:
                    logger.error(f"خطا در حلقه اصلی بات: {str(e)}")
                    # 5 دقیقه استراحت در صورت بروز خطای غیرمنتظره
                    time.sleep(300)

        else:
            logger.error("ورود به حساب کاربری ناموفق بود")
            # استراحت طولانی در صورت ناموفق بودن ورود اولیه
            time.sleep(3600)  # 60 دقیقه استراحت

    except Exception as e:
        logger.error(f"خطا در راه‌اندازی بات: {str(e)}")


def run_scheduler():
    """
    اجرای زمانبندی وظایف روزانه
    """
    import schedule

    logger.info("زمانبندی وظایف روزانه شروع شد")

    while True:
        try:
            schedule.run_pending()
        except Exception as e:
            logger.error(f"خطا در اجرای زمانبندی: {str(e)}")

        time.sleep(60)  # بررسی وظایف زمانبندی شده هر دقیقه

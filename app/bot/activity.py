import time
import random
import schedule
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from app.config import BOT_CONFIG
from app.utils.logger import get_logger
from app.database.models import BotStatus, DailyStats, InteractionType
from app.bot.session_manager import SessionManager
from app.bot.hashtags import HashtagManager

logger = get_logger("activity")


class ActivityManager:
    def __init__(self, db: Session, session_manager: SessionManager, hashtag_manager: HashtagManager):
        self.db = db
        self.session_manager = session_manager
        self.client = session_manager.get_client()
        self.hashtag_manager = hashtag_manager
        self.max_interactions = BOT_CONFIG["max_interactions_per_day"]
        self.working_hours = BOT_CONFIG["working_hours"]
        self.min_delay = BOT_CONFIG["min_delay_between_actions"]
        self.max_delay = BOT_CONFIG["max_delay_between_actions"]

    def is_working_hours(self):
        """بررسی اینکه آیا زمان فعلی در ساعات کاری تعریف شده است"""
        current_hour = datetime.now().hour
        return self.working_hours["start"] <= current_hour < self.working_hours["end"]

    def random_delay(self):
        """ایجاد تأخیر تصادفی بین اقدامات"""
        delay = random.randint(self.min_delay, self.max_delay)
        logger.info(f"استراحت برای {delay} ثانیه")
        time.sleep(delay)

    def reset_daily_counters(self):
        """ریست کردن شمارنده‌های روزانه و ایجاد رکورد آمار جدید"""
        try:
            # دریافت تاریخ فعلی
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)

            # بررسی وجود آمار برای دیروز
            existing_stats = self.db.query(DailyStats).filter(
                DailyStats.date == yesterday).first()
            if existing_stats:
                logger.info(f"آمار برای تاریخ {yesterday} قبلاً ثبت شده است")
                # به روزرسانی آمار موجود
                stats = self.db.query(BotStatus).first()
                if stats:
                    # ریست کردن شمارنده‌ها
                    stats.follows_today = 0
                    stats.unfollows_today = 0
                    stats.comments_today = 0
                    stats.likes_today = 0
                    stats.direct_messages_today = 0
                    stats.story_views_today = 0
                    stats.story_reactions_today = 0
                    self.db.commit()
                    logger.info("شمارنده‌های روزانه با موفقیت ریست شدند")
                return

            # ذخیره آمار روز قبل
            stats = self.db.query(BotStatus).first()

            if stats:
                # بررسی وجود داده‌های آماری واقعی
                has_data = (stats.follows_today > 0 or stats.unfollows_today > 0 or
                            stats.comments_today > 0 or stats.likes_today > 0 or
                            stats.direct_messages_today > 0 or stats.story_views_today > 0 or
                            stats.story_reactions_today > 0)

                if has_data:
                    # ذخیره داده‌های آماری موجود
                    daily_stats = DailyStats(
                        date=yesterday,
                        follows=stats.follows_today,
                        unfollows=stats.unfollows_today,
                        comments=stats.comments_today,
                        likes=stats.likes_today,
                        direct_messages=stats.direct_messages_today,
                        story_views=stats.story_views_today,
                        story_reactions=stats.story_reactions_today,
                        new_followers=0,  # این مقادیر باید در کد دیگری بروزرسانی شوند
                        lost_followers=0
                    )
                    self.db.add(daily_stats)
                    logger.info(f"آمار روز {yesterday} با موفقیت ثبت شد")
                else:
                    logger.info(
                        "هیچ داده آماری برای روز گذشته وجود ندارد، ایجاد نمی‌شود")

                # ریست کردن شمارنده‌ها
                stats.follows_today = 0
                stats.unfollows_today = 0
                stats.comments_today = 0
                stats.likes_today = 0
                stats.direct_messages_today = 0
                stats.story_views_today = 0
                stats.story_reactions_today = 0

                self.db.commit()
                logger.info("شمارنده‌های روزانه با موفقیت ریست شدند")

        except Exception as e:
            logger.error(f"خطا در ریست کردن شمارنده‌های روزانه: {str(e)}")
            self.db.rollback()

    def update_bot_status_activity(self, interaction_type=None):
        """بروزرسانی زمان آخرین فعالیت و شمارنده تعاملات"""
        try:
            # ایجاد یک سشن جدید برای اطمینان از دسترسی به دیتابیس
            status = self.db.query(BotStatus).first()

            if not status:
                logger.error("رکورد وضعیت بات یافت نشد! در حال ایجاد...")
                status = BotStatus(
                    is_running=True,
                    last_login=datetime.now(),
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
                logger.info("رکورد وضعیت بات ایجاد شد")

            # بروزرسانی زمان آخرین فعالیت
            status.last_activity = datetime.now()

            # بروزرسانی شمارنده مربوط به نوع تعامل
            if interaction_type:
                if interaction_type == InteractionType.FOLLOW:
                    status.follows_today += 1
                    logger.info(
                        f"شمارنده فالو افزایش یافت: {status.follows_today}")
                elif interaction_type == InteractionType.UNFOLLOW:
                    status.unfollows_today += 1
                    logger.info(
                        f"شمارنده آنفالو افزایش یافت: {status.unfollows_today}")
                elif interaction_type == InteractionType.COMMENT:
                    status.comments_today += 1
                    logger.info(
                        f"شمارنده کامنت افزایش یافت: {status.comments_today}")
                elif interaction_type == InteractionType.LIKE:
                    status.likes_today += 1
                    logger.info(
                        f"شمارنده لایک افزایش یافت: {status.likes_today}")
                elif interaction_type == InteractionType.DIRECT_MESSAGE:
                    status.direct_messages_today += 1
                    logger.info(
                        f"شمارنده پیام مستقیم افزایش یافت: {status.direct_messages_today}")
                elif interaction_type == InteractionType.STORY_VIEW:
                    status.story_views_today += 1
                    logger.info(
                        f"شمارنده مشاهده استوری افزایش یافت: {status.story_views_today}")
                elif interaction_type == InteractionType.STORY_REACTION:
                    status.story_reactions_today += 1
                    logger.info(
                        f"شمارنده واکنش استوری افزایش یافت: {status.story_reactions_today}")

            # کامیت تغییرات
            self.db.commit()
            logger.info(
                f"وضعیت بات با موفقیت بروزرسانی شد (نوع تعامل: {interaction_type})")

        except Exception as e:
            logger.error(f"خطا در بروزرسانی وضعیت فعالیت بات: {str(e)}")
            self.db.rollback()
            # تلاش مجدد با ایجاد سشن جدید
            try:
                from app.database.db import get_db
                new_db = next(get_db())
                status = new_db.query(BotStatus).first()
                if status and interaction_type:
                    if interaction_type == InteractionType.FOLLOW:
                        status.follows_today += 1
                    elif interaction_type == InteractionType.UNFOLLOW:
                        status.unfollows_today += 1
                    elif interaction_type == InteractionType.COMMENT:
                        status.comments_today += 1
                    elif interaction_type == InteractionType.LIKE:
                        status.likes_today += 1
                    elif interaction_type == InteractionType.DIRECT_MESSAGE:
                        status.direct_messages_today += 1
                    elif interaction_type == InteractionType.STORY_VIEW:
                        status.story_views_today += 1
                    elif interaction_type == InteractionType.STORY_REACTION:
                        status.story_reactions_today += 1
                    status.last_activity = datetime.now()
                    new_db.commit()
                    logger.info(
                        "تلاش مجدد برای بروزرسانی وضعیت بات موفقیت‌آمیز بود")
            except Exception as inner_e:
                logger.error(
                    f"تلاش مجدد برای بروزرسانی وضعیت بات ناموفق بود: {str(inner_e)}")

    def can_perform_interaction(self, interaction_type):
        """بررسی اینکه آیا می‌توان تعامل مورد نظر را انجام داد (با توجه به محدودیت‌های روزانه)"""
        status = self.db.query(BotStatus).first()
        if not status:
            return True

        if interaction_type == InteractionType.FOLLOW:
            return status.follows_today < BOT_CONFIG["max_follows_per_day"]
        elif interaction_type == InteractionType.UNFOLLOW:
            return status.unfollows_today < BOT_CONFIG["max_unfollows_per_day"]
        elif interaction_type == InteractionType.COMMENT:
            return status.comments_today < BOT_CONFIG["max_comments_per_day"]
        elif interaction_type == InteractionType.LIKE:
            return status.likes_today < BOT_CONFIG["max_likes_per_day"]
        elif interaction_type == InteractionType.DIRECT_MESSAGE:
            return status.direct_messages_today < BOT_CONFIG["max_direct_messages_per_day"]
        elif interaction_type == InteractionType.STORY_VIEW or interaction_type == InteractionType.STORY_REACTION:
            return status.story_views_today < BOT_CONFIG["max_story_views_per_day"]

        return True

    def setup_daily_tasks(self):
        """تنظیم وظایف روزانه"""
        # ریست شمارنده‌ها در ساعت 00:01 هر روز
        schedule.every().day.at("00:01").do(self.reset_daily_counters)

        logger.info("وظایف روزانه با موفقیت تنظیم شدند")

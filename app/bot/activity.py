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
        self.resting = False
        self.last_rest = datetime.now()
        self.last_action_type = None
        self.consecutive_actions = 0

    def is_working_hours(self):
        """بررسی اینکه آیا زمان فعلی در ساعات کاری تعریف شده است با توجه به روز هفته"""
        current_hour = datetime.now().hour
        current_day = datetime.now().weekday()  # 0 = دوشنبه، 6 = یکشنبه

        # تعریف ساعات متفاوت برای روزهای مختلف
        if current_day in [4, 5]:  # پنجشنبه و جمعه
            # ساعات کاری متفاوت در آخر هفته
            start_hour = self.working_hours.get(
                "weekend_start", self.working_hours["start"])
            end_hour = self.working_hours.get(
                "weekend_end", self.working_hours["end"])
        else:
            # ساعات کاری عادی
            start_hour = self.working_hours["start"]
            end_hour = self.working_hours["end"]

        return start_hour <= current_hour < end_hour

    def need_extended_rest(self):
        """بررسی نیاز به استراحت طولانی براساس الگوی فعالیت"""
        # اگر تعداد فعالیت‌های متوالی از یک آستانه بیشتر شود، نیاز به استراحت طولانی داریم
        max_consecutive = BOT_CONFIG.get("max_consecutive_actions", 10)
        if self.consecutive_actions >= max_consecutive:
            return True

        # اگر از آخرین استراحت طولانی بیش از زمان مشخصی گذشته باشد
        hours_between = BOT_CONFIG.get("hours_between_extended_rests", 2)
        hours_since_last_rest = (
            datetime.now() - self.last_rest).seconds / 3600
        if hours_since_last_rest >= hours_between:
            return True

        # افزودن عامل تصادفی - 10% شانس استراحت طولانی در هر زمان
        if random.random() < 0.1:
            return True

        return False

    def random_delay(self):
        """ایجاد تأخیر تصادفی بین اقدامات با توزیع طبیعی‌تر"""
        if self.need_extended_rest():
            # استراحت طولانی
            delay = random.randint(900, 1800)  # 15-30 دقیقه
            self.last_rest = datetime.now()
            self.consecutive_actions = 0
            self.resting = True
            logger.info(f"استراحت طولانی برای {delay} ثانیه")
        elif self.consecutive_actions > 5:
            # استراحت متوسط بعد از چند فعالیت متوالی
            delay = random.randint(300, 900)  # 5-15 دقیقه
            logger.info(
                f"استراحت متوسط برای {delay} ثانیه بعد از {self.consecutive_actions} فعالیت متوالی")
        else:
            # استراحت معمولی
            base_delay = random.randint(self.min_delay, self.max_delay)

            # اضافه کردن تغییرات گوسی
            # میانگین 1.0 با انحراف معیار 0.2
            gaussian_factor = random.gauss(1.0, 0.2)
            # محدود کردن به 0.5x تا 1.5x
            delay = int(base_delay * max(0.5, min(gaussian_factor, 1.5)))

            # افزایش احتمال تأخیرهای کوچک و بزرگ
            if random.random() < 0.7:  # 70% احتمال تأخیر معمولی
                pass  # همان تأخیر محاسبه شده را حفظ می‌کنیم
            elif random.random() < 0.5:  # 15% احتمال تأخیر کوتاه
                delay = int(delay * 0.5)
            else:  # 15% احتمال تأخیر طولانی
                delay = int(delay * 2)

            self.consecutive_actions += 1
            self.resting = False

        logger.info(f"استراحت برای {delay} ثانیه")

        # تقسیم تأخیر به قطعات کوچکتر برای شبیه‌سازی رفتار انسانی
        segments = random.randint(3, 8)
        segment_time = delay / segments

        for i in range(segments):
            actual_segment = segment_time * \
                (0.8 + random.random() * 0.4)  # 80% تا 120% زمان هر قطعه
            time.sleep(actual_segment)

            # گاهی اوقات یک عملیات سبک انجام می‌دهیم تا انسانی‌تر به نظر برسد
            if random.random() < 0.3 and not self.resting:
                try:
                    if i % 2 == 0:
                        # شبیه‌سازی بررسی تایم‌لاین
                        self.client.get_timeline_feed(amount=1)
                    else:
                        # شبیه‌سازی بررسی اکسپلور
                        self.client.get_explore_feed()
                except Exception:
                    # اگر خطایی رخ داد، آن را نادیده می‌گیریم
                    pass

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
            # بررسی اگر نوع تعامل تغییر کرده است
            if interaction_type != self.last_action_type:
                self.last_action_type = interaction_type
                # کاهش شمارنده فعالیت‌های متوالی در صورت تغییر نوع فعالیت
                if self.consecutive_actions > 2:
                    self.consecutive_actions = 2

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

        # بررسی محدودیت کلی تعاملات روزانه
        total_interactions = (
            status.follows_today +
            status.unfollows_today +
            status.comments_today +
            status.likes_today +
            status.direct_messages_today +
            status.story_views_today +
            status.story_reactions_today
        )

        if total_interactions >= self.max_interactions:
            logger.info(
                f"محدودیت کلی تعاملات روزانه ({self.max_interactions}) به حداکثر رسیده است")
            return False

        # افزودن عامل تصادفی برای محدودیت تعاملات (گاهی اوقات حتی قبل از رسیدن به حداکثر متوقف می‌شویم)
        threshold_percentage = 0.85  # 85% محدودیت
        if total_interactions >= int(self.max_interactions * threshold_percentage) and random.random() < 0.3:
            logger.info(
                f"محدودیت تصادفی تعاملات روزانه در {total_interactions} از {self.max_interactions}")
            return False

        # بررسی محدودیت خاص نوع تعامل
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
        # ریست شمارنده‌ها در زمان‌های مختلف بین نیمه‌شب تا 1 صبح
        minutes = random.randint(0, 59)
        schedule.every().day.at(f"00:{minutes:02d}").do(
            self.reset_daily_counters)

        # افزودن وقفه کوتاه در ساعات ناهار
        lunch_hour = random.randint(12, 14)
        lunch_minutes = random.randint(0, 59)
        schedule.every().day.at(f"{lunch_hour:02d}:{lunch_minutes:02d}").do(
            self.take_lunch_break)

        # افزودن وقفه شبانه
        evening_hour = random.randint(22, 23)
        evening_minutes = random.randint(0, 59)
        schedule.every().day.at(f"{evening_hour:02d}:{evening_minutes:02d}").do(
            self.take_evening_break)

        logger.info("وظایف روزانه با موفقیت تنظیم شدند")

    def take_lunch_break(self):
        """استراحت ناهار - وقفه طولانی در فعالیت"""
        logger.info("شروع استراحت ناهار")
        self.resting = True
        self.last_rest = datetime.now()
        self.consecutive_actions = 0
        # در اینجا می‌توان اقدامات دیگری نیز انجام داد
        return True

    def take_evening_break(self):
        """استراحت شبانه - کاهش فعالیت در ساعات شب"""
        logger.info("شروع استراحت شبانه")
        self.resting = True
        self.last_rest = datetime.now()
        self.consecutive_actions = 0
        # در اینجا می‌توان اقدامات دیگری نیز انجام داد
        return True

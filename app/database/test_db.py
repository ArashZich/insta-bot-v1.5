from sqlalchemy.orm import Session
from datetime import datetime
from app.database.models import BotStatus, InteractionType, Interaction, User, DailyStats
from app.utils.logger import get_logger

logger = get_logger("database_test")


def test_database_connection(db: Session):
    """
    تست اتصال به دیتابیس و صحت عملکرد آن
    """
    try:
        logger.info("شروع تست اتصال به دیتابیس...")

        # تست خواندن وضعیت بات
        bot_status = db.query(BotStatus).first()
        if bot_status:
            logger.info(
                f"وضعیت بات: فعال = {bot_status.is_running}, آخرین ورود = {bot_status.last_login}")
        else:
            logger.warning("رکورد وضعیت بات یافت نشد!")

            # ایجاد رکورد جدید
            new_status = BotStatus(
                is_running=True,
                last_login=datetime.now(),
                last_activity=datetime.now(),
                follows_today=0,
                unfollows_today=0,
                comments_today=0,
                likes_today=0,
                direct_messages_today=0,
                story_views_today=0,
                story_reactions_today=0,
                error_count=0
            )
            db.add(new_status)
            db.commit()
            logger.info("رکورد وضعیت بات ایجاد شد")

        # تست ایجاد تعامل آزمایشی
        test_interaction = Interaction(
            type=InteractionType.FOLLOW,
            content="تست اتصال به دیتابیس",
            status=True,
            created_at=datetime.now()
        )
        db.add(test_interaction)
        db.commit()
        logger.info(f"تعامل آزمایشی با آیدی {test_interaction.id} ایجاد شد")

        # تست بروزرسانی وضعیت بات
        bot_status = db.query(BotStatus).first()
        if bot_status:
            bot_status.last_activity = datetime.now()
            bot_status.follows_today += 1
            db.commit()
            logger.info("وضعیت بات بروزرسانی شد")

        # تست ایجاد آمار روزانه
        today = datetime.now().date()
        daily_stats = db.query(DailyStats).filter(
            DailyStats.date == today).first()
        if not daily_stats:
            new_stats = DailyStats(
                date=today,
                follows=1,
                unfollows=0,
                comments=0,
                likes=0,
                direct_messages=0,
                story_views=0,
                story_reactions=0,
                new_followers=0,
                lost_followers=0
            )
            db.add(new_stats)
            db.commit()
            logger.info("آمار روزانه جدید ایجاد شد")

        # بررسی امکان ریکوئری تراکنش ها
        try:
            # ایجاد یک خطای عمدی
            invalid_interaction = Interaction(
                type="invalid_type",  # این مقدار نامعتبر است
                content="این نباید ذخیره شود",
                status=True,
                created_at=datetime.now()
            )
            db.add(invalid_interaction)
            db.commit()
        except Exception as e:
            logger.info(f"تست ریکاوری تراکنش موفقیت‌آمیز بود: {str(e)}")
            db.rollback()

        logger.info("تست اتصال به دیتابیس با موفقیت انجام شد")
        return True
    except Exception as e:
        logger.error(f"خطا در تست اتصال به دیتابیس: {str(e)}")
        db.rollback()
        return False

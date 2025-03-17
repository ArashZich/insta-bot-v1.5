from instagrapi import Client
from instagrapi.exceptions import ClientError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("unfollow")


class UnfollowManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager

    async def unfollow_user(self, username=None, user_id=None):
        """آنفالو کردن یک کاربر با نام کاربری یا آیدی"""
        if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
            logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        try:
            # ابتدا اطلاعات کاربر را دریافت می‌کنیم
            if username and not user_id:
                user_info = self.client.user_info_by_username(username)
                user_id = user_info.pk
            elif not username and not user_id:
                logger.error("نام کاربری یا آیدی کاربر باید مشخص شود")
                return False

            # بررسی می‌کنیم که این کاربر را فالو کرده باشیم
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_id)).first()
            if db_user and not db_user.is_following:
                logger.info(
                    f"کاربر {username or user_id} قبلاً آنفالو شده است")
                return False

            # آنفالو کردن کاربر
            result = self.client.user_unfollow(user_id)

            if result:
                logger.info(f"کاربر {username or user_id} با موفقیت آنفالو شد")

                # بروزرسانی رکورد کاربر در دیتابیس
                if db_user:
                    db_user.is_following = False
                    db_user.following_since = None
                else:
                    # احتمالاً این کاربر در دیتابیس ما وجود ندارد
                    try:
                        user_info = self.client.user_info(user_id)
                        db_user = User(
                            instagram_id=str(user_id),
                            username=user_info.username,
                            full_name=user_info.full_name,
                            is_following=False
                        )
                        self.db.add(db_user)
                    except Exception as e:
                        logger.error(
                            f"خطا در دریافت اطلاعات کاربر {user_id}: {str(e)}")

                # ثبت تعامل در دیتابیس
                if db_user and db_user.id:
                    interaction = Interaction(
                        user_id=db_user.id,
                        type=InteractionType.UNFOLLOW,
                        status=True,
                        created_at=datetime.now()
                    )
                    self.db.add(interaction)

                self.db.commit()

                # بروزرسانی شمارنده‌های فعالیت
                self.activity_manager.update_bot_status_activity(
                    InteractionType.UNFOLLOW)

                return True
            else:
                logger.warning(
                    f"آنفالو کردن کاربر {username or user_id} ناموفق بود")
                return False

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در آنفالو کردن کاربر {username or user_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(
                f"خطا در آنفالو کردن کاربر {username or user_id}: {str(e)}")
            self.db.rollback()
            return False

    async def unfollow_non_followers(self, max_users=10, min_days=7):
        """آنفالو کردن کاربرانی که ما را فالو نکرده‌اند و مدتی از فالو کردن آنها گذشته است"""
        if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
            logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
            return 0

        try:
            # محاسبه تاریخ مرز برای فالو کردن
            cutoff_date = datetime.now() - timedelta(days=min_days)

            # کاربرانی که ما آنها را فالو کرده‌ایم ولی آنها ما را فالو نکرده‌اند و حداقل min_days روز از فالو کردن آنها گذشته است
            users_to_unfollow = self.db.query(User).filter(
                User.is_following == True,
                User.is_follower == False,
                User.following_since <= cutoff_date
            ).limit(max_users).all()

            if not users_to_unfollow:
                logger.info("هیچ کاربری برای آنفالو یافت نشد")
                return 0

            unfollowed_count = 0
            for user in users_to_unfollow:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
                    logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
                    break

                if await self.unfollow_user(user_id=user.instagram_id):
                    unfollowed_count += 1

            logger.info(f"{unfollowed_count} کاربر آنفالو شدند")
            return unfollowed_count

        except Exception as e:
            logger.error(f"خطا در آنفالو کردن: {str(e)}")
            return 0

    async def unfollow_if_unfollowed(self, max_users=10):
        """آنفالو کردن متقابل کاربرانی که ما را آنفالو کرده‌اند"""
        if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
            logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
            return 0

        try:
            # کاربرانی که قبلاً ما را فالو کرده بودند ولی الان نمی‌کنند، ولی ما هنوز آنها را فالو می‌کنیم
            users_to_unfollow = self.db.query(User).filter(
                User.is_following == True,
                User.is_follower == False,
                User.follower_since != None  # یعنی قبلاً ما را فالو می‌کرده
            ).limit(max_users).all()

            if not users_to_unfollow:
                logger.info("هیچ کاربری برای آنفالو متقابل یافت نشد")
                return 0

            unfollowed_count = 0
            for user in users_to_unfollow:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
                    logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
                    break

                if await self.unfollow_user(user_id=user.instagram_id):
                    unfollowed_count += 1

            logger.info(f"{unfollowed_count} کاربر به صورت متقابل آنفالو شدند")
            return unfollowed_count

        except Exception as e:
            logger.error(f"خطا در آنفالو متقابل: {str(e)}")
            return 0

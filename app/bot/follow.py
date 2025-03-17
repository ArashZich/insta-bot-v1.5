from instagrapi import Client
from instagrapi.exceptions import ClientError
from sqlalchemy.orm import Session
from datetime import datetime
import random

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("follow")


class FollowManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager

    async def follow_user(self, username=None, user_id=None):
        """دنبال کردن یک کاربر با نام کاربری یا آیدی"""
        if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
            logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
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

            # بررسی می‌کنیم که قبلاً این کاربر را فالو نکرده باشیم
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_id)).first()
            if db_user and db_user.is_following:
                logger.info(f"کاربر {username or user_id} قبلاً فالو شده است")
                return False

            # فالو کردن کاربر
            result = self.client.user_follow(user_id)

            if result:
                logger.info(f"کاربر {username or user_id} با موفقیت فالو شد")

                # بروزرسانی یا ایجاد رکورد کاربر در دیتابیس
                if not db_user:
                    user_info = self.client.user_info(user_id)
                    db_user = User(
                        instagram_id=str(user_id),
                        username=user_info.username,
                        full_name=user_info.full_name,
                        is_following=True,
                        following_since=datetime.now()
                    )
                    self.db.add(db_user)
                else:
                    db_user.is_following = True
                    db_user.following_since = datetime.now()

                # ثبت تعامل در دیتابیس
                interaction = Interaction(
                    user_id=db_user.id if db_user.id else None,
                    type=InteractionType.FOLLOW,
                    status=True,
                    created_at=datetime.now()
                )
                self.db.add(interaction)

                self.db.commit()

                # بروزرسانی شمارنده‌های فعالیت
                self.activity_manager.update_bot_status_activity(
                    InteractionType.FOLLOW)

                return True
            else:
                logger.warning(
                    f"فالو کردن کاربر {username or user_id} ناموفق بود")
                return False

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در فالو کردن کاربر {username or user_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(
                f"خطا در فالو کردن کاربر {username or user_id}: {str(e)}")
            self.db.rollback()
            return False

    async def follow_users_by_hashtag(self, hashtag, max_users=5):
        """فالو کردن کاربران بر اساس هشتگ"""
        if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
            logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
            return 0

        try:
            logger.info(f"جستجوی پست‌ها با هشتگ {hashtag}")

            # تست اعتبار نشست قبل از انجام عملیات
            try:
                self.client.get_timeline_feed()
            except Exception as e:
                logger.error(
                    f"نشست نامعتبر است، تلاش برای ورود مجدد: {str(e)}")

                # تلاش برای ورود مجدد
                from app.bot.session_manager import SessionManager
                session_manager = SessionManager(self.db)
                if session_manager.login():
                    logger.info("ورود مجدد موفقیت‌آمیز بود")
                    self.client = session_manager.get_client()
                else:
                    logger.error("ورود مجدد ناموفق بود")
                    return 0

            # انجام جستجو براساس هشتگ
            try:
                medias = self.client.hashtag_medias_recent(
                    hashtag, max_users * 3)
            except Exception as e:
                logger.error(f"خطا در دریافت پست‌های هشتگ {hashtag}: {str(e)}")
                return 0

            if not medias:
                logger.info(f"هیچ پستی با هشتگ {hashtag} یافت نشد")
                return 0

            followed_count = 0
            for media in medias:
                if followed_count >= max_users:
                    break

                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
                    logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
                    break

                user_id = media.user.pk

                # بررسی قبل از فالو کردن
                try:
                    user_info = self.client.user_info(user_id)
                    username = user_info.username
                    logger.info(
                        f"تلاش برای فالو کردن کاربر {username} با آیدی {user_id}")
                except Exception as e:
                    logger.warning(
                        f"خطا در دریافت اطلاعات کاربر {user_id}: {str(e)}")
                    continue

                success = await self.follow_user(user_id=user_id)
                if success:
                    followed_count += 1
                    logger.info(f"کاربر {username} با موفقیت فالو شد")
                    # بروزرسانی آمار بات
                    self.activity_manager.update_bot_status_activity(
                        InteractionType.FOLLOW)
                else:
                    logger.warning(f"فالو کردن کاربر {username} ناموفق بود")

            logger.info(f"{followed_count} کاربر با هشتگ {hashtag} فالو شدند")
            return followed_count

        except Exception as e:
            logger.error(
                f"خطا در فالو کردن کاربران با هشتگ {hashtag}: {str(e)}")
            return 0

    async def follow_back_users(self, max_users=10):
        """فالو کردن متقابل کاربرانی که ما را فالو کرده‌اند ولی ما آنها را فالو نکرده‌ایم"""
        if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
            logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
            return 0

        try:
            # کاربرانی که ما را فالو کرده‌اند ولی ما آنها را فالو نکرده‌ایم
            users_to_follow = self.db.query(User).filter(
                User.is_follower == True,
                User.is_following == False
            ).limit(max_users).all()

            if not users_to_follow:
                logger.info("هیچ کاربری برای فالو متقابل یافت نشد")
                return 0

            followed_count = 0
            for user in users_to_follow:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
                    logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
                    break

                if await self.follow_user(user_id=user.instagram_id):
                    followed_count += 1

            logger.info(f"{followed_count} کاربر به صورت متقابل فالو شدند")
            return followed_count

        except Exception as e:
            logger.error(f"خطا در فالو متقابل: {str(e)}")
            return 0

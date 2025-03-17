from instagrapi import Client
from instagrapi.exceptions import ClientError
from sqlalchemy.orm import Session
from datetime import datetime
import random

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("comment")


class CommentManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager
        self.comment_templates = [
            "عالی بود 👌",
            "چقدر زیبا 😍",
            "فوق‌العاده است 👏",
            "خیلی خوبه ✨",
            "خیلی قشنگه 🙌",
            "عالیه 🔥",
            "محشره 💯",
            "دمت گرم 👍",
            "خیلی جالبه 🌟",
            "کارت درسته 💪",
            "خیلی خوشم اومد 🎯",
            "عالی کار کردی 🌹",
            "واقعا قشنگه 👌✨",
            "دوستش دارم 💖"
        ]

    def get_random_comment(self):
        """انتخاب یک کامنت تصادفی از قالب‌ها"""
        return random.choice(self.comment_templates)

    async def add_comment(self, media_id=None, text=None):
        """افزودن کامنت به یک پست"""
        if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
            logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        if not media_id:
            logger.error("آیدی رسانه باید مشخص شود")
            return False

        if not text:
            text = self.get_random_comment()

        try:
            result = self.client.media_comment(media_id, text)

            if result:
                logger.info(
                    f"کامنت با موفقیت به پست {media_id} افزوده شد: {text}")

                # دریافت اطلاعات صاحب پست
                try:
                    media_info = self.client.media_info(media_id)
                    user_id = media_info.user.pk
                    username = media_info.user.username

                    # بررسی یا ایجاد کاربر در دیتابیس
                    db_user = self.db.query(User).filter(
                        User.instagram_id == str(user_id)).first()
                    if not db_user:
                        db_user = User(
                            instagram_id=str(user_id),
                            username=username,
                            full_name=media_info.user.full_name
                        )
                        self.db.add(db_user)
                        self.db.flush()

                    # ثبت تعامل در دیتابیس
                    interaction = Interaction(
                        user_id=db_user.id,
                        type=InteractionType.COMMENT,
                        content=text,
                        media_id=media_id,
                        status=True,
                        created_at=datetime.now()
                    )
                    self.db.add(interaction)

                except Exception as e:
                    logger.error(
                        f"خطا در دریافت اطلاعات پست {media_id}: {str(e)}")

                    # اگر نتوانستیم اطلاعات کاربر را دریافت کنیم، فقط تعامل را ثبت می‌کنیم
                    interaction = Interaction(
                        type=InteractionType.COMMENT,
                        content=text,
                        media_id=media_id,
                        status=True,
                        created_at=datetime.now()
                    )
                    self.db.add(interaction)

                self.db.commit()

                # بروزرسانی شمارنده‌های فعالیت
                self.activity_manager.update_bot_status_activity(
                    InteractionType.COMMENT)

                return True
            else:
                logger.warning(f"افزودن کامنت به پست {media_id} ناموفق بود")
                return False

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در افزودن کامنت به پست {media_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"خطا در افزودن کامنت به پست {media_id}: {str(e)}")
            self.db.rollback()
            return False

    async def comment_on_hashtag_posts(self, hashtag, max_posts=5):
        """کامنت گذاشتن بر روی پست‌های دارای هشتگ خاص"""
        if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
            logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
            return 0

        try:
            logger.info(f"جستجوی پست‌ها با هشتگ {hashtag}")
            medias = self.client.hashtag_medias_recent(hashtag, max_posts * 3)

            if not medias:
                logger.info(f"هیچ پستی با هشتگ {hashtag} یافت نشد")
                return 0

            comment_count = 0
            for media in medias:
                if comment_count >= max_posts:
                    break

                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
                    logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
                    break

                # انتخاب تصادفی کامنت
                comment_text = self.get_random_comment()

                if await self.add_comment(media_id=media.id, text=comment_text):
                    comment_count += 1

            logger.info(
                f"{comment_count} کامنت برای پست‌های با هشتگ {hashtag} افزوده شد")
            return comment_count

        except Exception as e:
            logger.error(
                f"خطا در کامنت گذاشتن بر روی پست‌های با هشتگ {hashtag}: {str(e)}")
            return 0

    async def comment_on_followers_posts(self, max_posts=5):
        """کامنت گذاشتن بر روی پست‌های دنبال‌کنندگان"""
        if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
            logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
            return 0

        try:
            # دریافت کاربرانی که ما را فالو می‌کنند
            followers = self.db.query(User).filter(
                User.is_follower == True).limit(10).all()

            if not followers:
                logger.info("هیچ دنبال‌کننده‌ای یافت نشد")
                return 0

            comment_count = 0
            for follower in followers:
                if comment_count >= max_posts:
                    break

                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
                    logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
                    break

                try:
                    # دریافت آخرین پست‌های کاربر
                    user_medias = self.client.user_medias(
                        follower.instagram_id, 5)

                    if user_medias:
                        media = random.choice(user_medias)

                        # انتخاب تصادفی کامنت
                        comment_text = self.get_random_comment()

                        if await self.add_comment(media_id=media.id, text=comment_text):
                            comment_count += 1

                except Exception as e:
                    logger.error(
                        f"خطا در دریافت پست‌های کاربر {follower.username}: {str(e)}")
                    continue

            logger.info(
                f"{comment_count} کامنت برای پست‌های دنبال‌کنندگان افزوده شد")
            return comment_count

        except Exception as e:
            logger.error(
                f"خطا در کامنت گذاشتن بر روی پست‌های دنبال‌کنندگان: {str(e)}")
            return 0

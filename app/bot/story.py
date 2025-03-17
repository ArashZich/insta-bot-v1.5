from instagrapi import Client
from instagrapi.exceptions import ClientError
from sqlalchemy.orm import Session
from datetime import datetime
import random

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("story")


class StoryManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager
        self.story_reactions = ["❤️", "👍", "👏", "🔥", "😍", "😂", "💯", "🙌"]

    def get_random_reaction(self):
        """انتخاب یک واکنش تصادفی برای استوری"""
        return random.choice(self.story_reactions)

    async def view_user_stories(self, user_id=None, username=None):
        """مشاهده استوری‌های یک کاربر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.STORY_VIEW):
            logger.info("محدودیت مشاهده استوری روزانه به حداکثر رسیده است")
            return 0

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return 0

        # اگر user_id ارائه نشده و username داریم، user_id را پیدا می‌کنیم
        if not user_id and username:
            try:
                user_info = self.client.user_info_by_username(username)
                user_id = user_info.pk
            except Exception as e:
                logger.error(f"خطا در یافتن کاربر {username}: {str(e)}")
                return 0

        if not user_id:
            logger.error("آیدی کاربر یا نام کاربری باید مشخص شود")
            return 0

        try:
            # دریافت استوری‌های کاربر
            user_stories = self.client.user_stories(user_id)

            if not user_stories:
                logger.info(f"کاربر {username or user_id} استوری فعالی ندارد")
                return 0

            # بررسی یا ایجاد کاربر در دیتابیس
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_id)).first()
            if not db_user:
                try:
                    user_info = self.client.user_info(user_id)
                    db_user = User(
                        instagram_id=str(user_id),
                        username=user_info.username,
                        full_name=user_info.full_name
                    )
                    self.db.add(db_user)
                    self.db.flush()
                except Exception as e:
                    logger.error(
                        f"خطا در دریافت اطلاعات کاربر {user_id}: {str(e)}")

            view_count = 0
            for story in user_stories:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.STORY_VIEW):
                    logger.info(
                        "محدودیت مشاهده استوری روزانه به حداکثر رسیده است")
                    break

                # دیدن استوری
                self.client.story_seen([story.pk])
                view_count += 1

                # ثبت تعامل در دیتابیس
                interaction = Interaction(
                    user_id=db_user.id if db_user else None,
                    type=InteractionType.STORY_VIEW,
                    media_id=str(story.pk),
                    status=True,
                    created_at=datetime.now()
                )
                self.db.add(interaction)

                # بروزرسانی شمارنده‌های فعالیت
                self.activity_manager.update_bot_status_activity(
                    InteractionType.STORY_VIEW)

            self.db.commit()
            logger.info(
                f"{view_count} استوری از کاربر {username or user_id} مشاهده شد")
            return view_count

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در مشاهده استوری‌های کاربر {username or user_id}: {str(e)}")
            return 0
        except Exception as e:
            logger.error(
                f"خطا در مشاهده استوری‌های کاربر {username or user_id}: {str(e)}")
            self.db.rollback()
            return 0

    async def react_to_story(self, story_id, reaction=None):
        """واکنش نشان دادن به یک استوری"""
        if not self.activity_manager.can_perform_interaction(InteractionType.STORY_REACTION):
            logger.info("محدودیت واکنش استوری روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        if not reaction:
            reaction = self.get_random_reaction()

        try:
            # دریافت اطلاعات استوری
            story_info = self.client.story_info(story_id)
            user_id = story_info.user.pk

            # ارسال واکنش به استوری
            result = self.client.story_send_reaction(story_id, reaction)

            if result:
                logger.info(
                    f"واکنش {reaction} با موفقیت به استوری {story_id} ارسال شد")

                # بررسی یا ایجاد کاربر در دیتابیس
                db_user = self.db.query(User).filter(
                    User.instagram_id == str(user_id)).first()
                if not db_user:
                    try:
                        user_info = self.client.user_info(user_id)
                        db_user = User(
                            instagram_id=str(user_id),
                            username=user_info.username,
                            full_name=user_info.full_name
                        )
                        self.db.add(db_user)
                        self.db.flush()
                    except Exception as e:
                        logger.error(
                            f"خطا در دریافت اطلاعات کاربر {user_id}: {str(e)}")

                # ثبت تعامل در دیتابیس
                interaction = Interaction(
                    user_id=db_user.id if db_user else None,
                    type=InteractionType.STORY_REACTION,
                    content=reaction,
                    media_id=str(story_id),
                    status=True,
                    created_at=datetime.now()
                )
                self.db.add(interaction)

                self.db.commit()

                # بروزرسانی شمارنده‌های فعالیت
                self.activity_manager.update_bot_status_activity(
                    InteractionType.STORY_REACTION)

                return True
            else:
                logger.warning(f"ارسال واکنش به استوری {story_id} ناموفق بود")
                return False

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در ارسال واکنش به استوری {story_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"خطا در ارسال واکنش به استوری {story_id}: {str(e)}")
            self.db.rollback()
            return False

    async def view_and_react_to_followers_stories(self, max_users=5):
        """مشاهده و واکنش به استوری‌های دنبال‌کنندگان"""
        if not self.activity_manager.can_perform_interaction(InteractionType.STORY_VIEW):
            logger.info("محدودیت مشاهده استوری روزانه به حداکثر رسیده است")
            return 0

        try:
            # دریافت کاربرانی که ما را فالو می‌کنند
            followers = self.db.query(User).filter(
                User.is_follower == True).limit(max_users).all()

            if not followers:
                logger.info("هیچ دنبال‌کننده‌ای یافت نشد")
                return 0

            reaction_count = 0
            for follower in followers:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                # مشاهده استوری‌های کاربر
                user_stories = await self.view_user_stories(user_id=follower.instagram_id)

                if user_stories and random.random() < 0.5:  # با احتمال 50% واکنش نشان می‌دهیم
                    try:
                        # دریافت استوری‌های کاربر
                        stories = self.client.user_stories(
                            follower.instagram_id)

                        if stories and len(stories) > 0:
                            # انتخاب یک استوری تصادفی
                            story = random.choice(stories)

                            # ارسال واکنش
                            if await self.react_to_story(story.pk):
                                reaction_count += 1

                    except Exception as e:
                        logger.error(
                            f"خطا در ارسال واکنش به استوری کاربر {follower.username}: {str(e)}")
                        continue

            logger.info(
                f"به {reaction_count} استوری از دنبال‌کنندگان واکنش نشان داده شد")
            return reaction_count

        except Exception as e:
            logger.error(
                f"خطا در مشاهده و واکنش به استوری‌های دنبال‌کنندگان: {str(e)}")
            return 0

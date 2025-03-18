from instagrapi import Client
from instagrapi.exceptions import ClientError, PleaseWaitFewMinutes, FeedbackRequired
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import time

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("story")


class StoryManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager

        # واکنش‌های استوری با تنوع بیشتر
        self.story_reactions = [
            "❤️", "👍", "👏", "🔥", "😍", "😂", "💯", "🙌",
            "👌", "✨", "🌹", "💪", "👊", "🎉", "😊", "🌺"
        ]

        # احتمال واکنش نشان دادن به استوری بعد از دیدن آن
        self.reaction_probability = 0.4  # 40% احتمال

        # محدودیت تعداد استوری‌هایی که از یک کاربر می‌بینیم
        self.max_stories_per_user = 5

        # سطح احتیاط در واکنش به استوری (0 تا 1)
        self.caution_level = 0.6  # هرچه بیشتر، واکنش‌های کمتر و محتاطانه‌تر

    def get_random_reaction(self):
        """انتخاب یک واکنش تصادفی برای استوری"""
        # واکنش‌های محبوب‌تر شانس بیشتری دارند
        popular_reactions = ["❤️", "👍", "🔥", "😍"]

        if random.random() < 0.7:  # 70% احتمال
            return random.choice(popular_reactions)
        else:
            return random.choice(self.story_reactions)

    def should_react_to_story(self, user_info=None):
        """تصمیم‌گیری هوشمند برای واکنش نشان دادن یا ندادن به استوری"""
        # اگر سطح احتیاط بالا باشد، با احتمال کمتری واکنش می‌دهیم
        if random.random() < self.caution_level:
            return False

        # احتمال پایه واکنش دادن
        should_react = random.random() < self.reaction_probability

        # بررسی‌های بیشتر اگر اطلاعات کاربر موجود باشد
        if user_info:
            # اگر کاربر ما را فالو می‌کند، احتمال واکنش بیشتر است
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_info.pk)).first()
            if db_user and db_user.is_follower:
                should_react = should_react or (
                    random.random() < 0.6)  # 60% احتمال اضافه

            # اگر قبلاً با کاربر تعامل داشته‌ایم، احتمال واکنش بیشتر است
            if db_user:
                previous_interactions = self.db.query(Interaction).filter(
                    Interaction.user_id == db_user.id).count()
                if previous_interactions > 0:
                    should_react = should_react or (
                        random.random() < 0.5)  # 50% احتمال اضافه

        return should_react

    def get_natural_story_view_delay(self, story_count):
        """محاسبه تاخیر طبیعی بین دیدن استوری‌ها"""
        # استوری‌های اول را سریع‌تر می‌بینیم
        if story_count <= 2:
            return random.uniform(1.0, 3.0)
        # استوری‌های میانی را با سرعت متوسط می‌بینیم
        elif story_count <= 5:
            return random.uniform(2.0, 5.0)
        # استوری‌های بیشتر را آهسته‌تر می‌بینیم (خستگی کاربر)
        else:
            return random.uniform(3.0, 7.0)

    async def view_user_stories(self, user_id=None, username=None):
        """مشاهده استوری‌های یک کاربر با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.STORY_VIEW):
            logger.info("محدودیت مشاهده استوری روزانه به حداکثر رسیده است")
            return 0

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return 0

        # اضافه کردن تاخیر قبل از دیدن استوری (مثل زمان باز کردن پروفایل)
        time.sleep(random.uniform(1.0, 3.0))

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

            # محدود کردن تعداد استوری‌ها برای افزایش طبیعی بودن
            if len(user_stories) > self.max_stories_per_user:
                # انتخاب تصادفی max_stories_per_user استوری از ابتدای لیست
                # (عموماً استوری‌های جدیدتر در ابتدا هستند)
                user_stories = user_stories[:self.max_stories_per_user]

            # دریافت اطلاعات کاربر
            try:
                user_info = self.client.user_info(user_id)
            except Exception:
                user_info = None

            # بررسی یا ایجاد کاربر در دیتابیس
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_id)).first()
            if not db_user:
                try:
                    if user_info:
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
            reaction_count = 0

            # مشاهده کردن استوری‌ها یکی یکی با تاخیر طبیعی
            for story_index, story in enumerate(user_stories):
                # تأخیر طبیعی بین دیدن استوری‌ها
                view_delay = self.get_natural_story_view_delay(story_index + 1)
                time.sleep(view_delay)

                if not self.activity_manager.can_perform_interaction(InteractionType.STORY_VIEW):
                    logger.info(
                        "محدودیت مشاهده استوری روزانه به حداکثر رسیده است")
                    break

                # دیدن استوری با گروه‌بندی طبیعی
                try:
                    # دیدن استوری‌ها در گروه‌های کوچک (بیشتر شبیه رفتار کاربر واقعی)
                    if story_index % 3 == 0 or story_index == len(user_stories) - 1:
                        stories_to_see = user_stories[max(
                            0, story_index-2):story_index+1]
                        story_ids = [s.pk for s in stories_to_see]
                        self.client.story_seen(story_ids)

                    view_count += 1

                    # ثبت تعامل دیدن استوری در دیتابیس
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

                    # تصمیم‌گیری برای واکنش نشان دادن به استوری
                    if self.should_react_to_story(user_info):
                        # تاخیر قبل از واکنش (مثل زمان فکر کردن و انتخاب ایموجی)
                        reaction_delay = random.uniform(1.0, 3.0)
                        time.sleep(reaction_delay)

                        reaction = self.get_random_reaction()

                        try:
                            result = self.client.story_send_reaction(
                                story.pk, reaction)

                            if result:
                                logger.info(
                                    f"واکنش {reaction} به استوری {story.pk} ارسال شد")
                                reaction_count += 1

                                # ثبت تعامل واکنش استوری در دیتابیس
                                reaction_interaction = Interaction(
                                    user_id=db_user.id if db_user else None,
                                    type=InteractionType.STORY_REACTION,
                                    content=reaction,
                                    media_id=str(story.pk),
                                    status=True,
                                    created_at=datetime.now()
                                )
                                self.db.add(reaction_interaction)

                                # بروزرسانی شمارنده‌های فعالیت
                                self.activity_manager.update_bot_status_activity(
                                    InteractionType.STORY_REACTION)
                        except Exception as e:
                            logger.warning(
                                f"خطا در ارسال واکنش به استوری {story.pk}: {str(e)}")

                except Exception as e:
                    logger.warning(f"خطا در دیدن استوری {story.pk}: {str(e)}")
                    continue

            self.db.commit()
            logger.info(
                f"{view_count} استوری از کاربر {username or user_id} مشاهده شد و به {reaction_count} استوری واکنش نشان داده شد")

            return view_count

        except FeedbackRequired as e:
            logger.error(
                f"خطای محدودیت در مشاهده استوری‌های کاربر {username or user_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return 0

        except PleaseWaitFewMinutes as e:
            logger.error(
                f"محدودیت نرخ در مشاهده استوری‌های کاربر {username or user_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return 0

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
        """واکنش نشان دادن به یک استوری با تاخیر طبیعی"""
        if not self.activity_manager.can_perform_interaction(InteractionType.STORY_REACTION):
            logger.info("محدودیت واکنش استوری روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        if not reaction:
            reaction = self.get_random_reaction()

        # تاخیر قبل از واکنش (مثل زمان فکر کردن و انتخاب ایموجی)
        time.sleep(random.uniform(1.0, 3.0))

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

        except FeedbackRequired as e:
            logger.error(
                f"خطای محدودیت در ارسال واکنش به استوری {story_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return False

        except PleaseWaitFewMinutes as e:
            logger.error(
                f"محدودیت نرخ در ارسال واکنش به استوری {story_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return False

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در ارسال واکنش به استوری {story_id}: {str(e)}")
            return False

        except Exception as e:
            logger.error(f"خطا در ارسال واکنش به استوری {story_id}: {str(e)}")
            self.db.rollback()
            return False

    async def view_and_react_to_followers_stories(self, max_users=2):
        """مشاهده و واکنش به استوری‌های دنبال‌کنندگان با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.STORY_VIEW):
            logger.info("محدودیت مشاهده استوری روزانه به حداکثر رسیده است")
            return 0

        try:
            # دریافت کاربرانی که ما را فالو می‌کنند
            followers = self.db.query(User).filter(
                User.is_follower == True).limit(max_users * 3).all()

            if not followers:
                logger.info("هیچ دنبال‌کننده‌ای یافت نشد")
                return 0

            # الویت‌بندی فالوورها برای دیدن استوری‌ها:
            # 1. فالوورهایی که ما هم آنها را فالو کرده‌ایم
            # 2. فالوورهای فعال (با تعامل قبلی)
            # 3. سایر فالوورها

            # فالوورهایی که ما هم آنها را فالو کرده‌ایم
            mutual_followers = [f for f in followers if f.is_following]

            # سایر فالوورها
            other_followers = [f for f in followers if not f.is_following]

            # ترکیب لیست‌ها با الویت‌بندی
            prioritized_followers = mutual_followers + other_followers

            # انتخاب تصادفی تعدادی از فالوورها
            selected_followers = prioritized_followers[:max_users]
            if len(selected_followers) > max_users:
                selected_followers = random.sample(
                    selected_followers, max_users)

            view_count = 0
            for follower in selected_followers:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                # مشاهده استوری‌های کاربر
                viewed_stories = await self.view_user_stories(user_id=follower.instagram_id)
                view_count += viewed_stories

                # اضافه کردن تاخیر بین دیدن استوری‌های کاربران مختلف
                if viewed_stories > 0:
                    time.sleep(random.uniform(10.0, 30.0))

            logger.info(
                f"در مجموع {view_count} استوری از دنبال‌کنندگان مشاهده شد")
            return view_count

        except Exception as e:
            logger.error(
                f"خطا در مشاهده و واکنش به استوری‌های دنبال‌کنندگان: {str(e)}")
            return 0

    async def view_trending_stories(self, max_stories=5):
        """مشاهده استوری‌های ترند (از اکسپلور یا استوری‌های پیشنهادی)"""
        if not self.activity_manager.can_perform_interaction(InteractionType.STORY_VIEW):
            logger.info("محدودیت مشاهده استوری روزانه به حداکثر رسیده است")
            return 0

        try:
            # تلاش برای دریافت استوری‌های پیشنهادی یا ترند
            try:
                # روش 1: استفاده از explore feed برای پیدا کردن کاربران محبوب
                explore_feed = self.client.explore_feed()

                # استخراج کاربران از پست‌های اکسپلور
                trending_users = []
                for media in explore_feed:
                    trending_users.append(media.user.pk)

                # حذف تکرار و محدود کردن تعداد
                trending_users = list(set(trending_users))

                if not trending_users:
                    logger.info("هیچ کاربر ترندی در اکسپلور یافت نشد")
                    return 0

                # محدود کردن تعداد
                if len(trending_users) > max_stories:
                    trending_users = random.sample(trending_users, max_stories)

                # دیدن استوری‌های کاربران ترند
                view_count = 0
                for user_id in trending_users:
                    # تأخیر تصادفی بین اقدامات
                    self.activity_manager.random_delay()

                    # مشاهده استوری‌های کاربر
                    viewed_stories = await self.view_user_stories(user_id=user_id)
                    view_count += viewed_stories

                    # اضافه کردن تاخیر بین دیدن استوری‌های کاربران مختلف
                    if viewed_stories > 0:
                        time.sleep(random.uniform(10.0, 30.0))

                logger.info(
                    f"در مجموع {view_count} استوری از کاربران ترند مشاهده شد")
                return view_count

            except Exception as e:
                logger.warning(f"خطا در دریافت استوری‌های ترند: {str(e)}")
                return 0

        except Exception as e:
            logger.error(f"خطا در مشاهده استوری‌های ترند: {str(e)}")
            return 0

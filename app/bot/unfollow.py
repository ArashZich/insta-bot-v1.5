from instagrapi import Client
from instagrapi.exceptions import ClientError, PleaseWaitFewMinutes, FeedbackRequired
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import time

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("unfollow")


class UnfollowManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager
        # تعریف فاصله زمانی بین فالو و آنفالو
        self.min_follow_days = 3  # حداقل زمان قبل از آنفالو (روز)
        # درصد احتمال آنفالو کردن کاربرانی که ما را فالو می‌کنند
        self.unfollow_followers_chance = 0.2  # 20% شانس آنفالو کردن فالوورها

    async def simulate_profile_check(self, user_id):
        """شبیه‌سازی بررسی پروفایل قبل از آنفالو کردن"""
        try:
            # بررسی اطلاعات پروفایل
            user_info = self.client.user_info(user_id)

            # تاخیر مثل زمان خواندن پروفایل
            time.sleep(random.uniform(2.0, 4.0))

            # گاهی اوقات بررسی تعدادی از پست‌های کاربر
            if random.random() < 0.3:  # 30% احتمال
                user_medias = self.client.user_medias(user_id, 3)
                if user_medias:
                    media = random.choice(user_medias)
                    self.client.media_info(media.id)
                    time.sleep(random.uniform(1.5, 3.0))

            return user_info
        except Exception as e:
            logger.warning(f"خطا در شبیه‌سازی بررسی پروفایل: {str(e)}")
            return None

    async def unfollow_user(self, username=None, user_id=None):
        """آنفالو کردن یک کاربر با نام کاربری یا آیدی"""
        if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
            logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        # اضافه کردن تاخیر قبل از آنفالو کردن
        time.sleep(random.uniform(1.0, 3.0))

        try:
            # ابتدا اطلاعات کاربر را دریافت می‌کنیم
            if username and not user_id:
                try:
                    user_info = self.client.user_info_by_username(username)
                    user_id = user_info.pk
                except Exception as e:
                    logger.error(
                        f"خطا در دریافت اطلاعات کاربر {username}: {str(e)}")
                    return False
            elif not username and not user_id:
                logger.error("نام کاربری یا آیدی کاربر باید مشخص شود")
                return False
            else:
                # دریافت اطلاعات کاربر با استفاده از آیدی
                try:
                    user_info = await self.simulate_profile_check(user_id)
                    if user_info:
                        username = user_info.username
                except Exception as e:
                    logger.error(
                        f"خطا در دریافت اطلاعات کاربر با آیدی {user_id}: {str(e)}")
                    return False

            # بررسی می‌کنیم که این کاربر را فالو کرده باشیم
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_id)).first()
            if db_user and not db_user.is_following:
                logger.info(
                    f"کاربر {username or user_id} قبلاً آنفالو شده است")
                return False

            # اگر کاربر ما را فالو می‌کند، با احتمال کمتری آنفالو می‌کنیم
            if db_user and db_user.is_follower and random.random() > self.unfollow_followers_chance:
                logger.info(
                    f"کاربر {username or user_id} ما را فالو می‌کند، آنفالو نمی‌کنیم")
                return False

            # اضافه کردن تاخیر طبیعی قبل از آنفالو
            time.sleep(random.uniform(1.0, 3.0))

            # تلاش برای آنفالو کردن کاربر با مدیریت خطاها
            try:
                result = self.client.user_unfollow(user_id)

                if result:
                    logger.info(
                        f"کاربر {username or user_id} با موفقیت آنفالو شد")

                    # بروزرسانی رکورد کاربر در دیتابیس
                    if db_user:
                        db_user.is_following = False
                        db_user.following_since = None
                    else:
                        # احتمالاً این کاربر در دیتابیس ما وجود ندارد
                        try:
                            if not user_info:
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

            except FeedbackRequired as e:
                logger.error(
                    f"خطای محدودیت در آنفالو کردن کاربر {username or user_id}: {str(e)}")
                # استراحت طولانی برای جلوگیری از محدودیت بیشتر
                time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
                return False

            except PleaseWaitFewMinutes as e:
                logger.error(
                    f"خطای محدودیت نرخ در آنفالو کردن کاربر {username or user_id}: {str(e)}")
                # استراحت طولانی برای جلوگیری از محدودیت بیشتر
                time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
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

    async def unfollow_non_followers(self, max_users=2, min_days=3):
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
                # دریافت تعداد بیشتری برای انتخاب تصادفی
            ).limit(max_users * 2).all()

            if not users_to_unfollow:
                logger.info("هیچ کاربری برای آنفالو یافت نشد")
                return 0

            # انتخاب تصادفی کاربران برای آنفالو کردن
            if len(users_to_unfollow) > max_users:
                users_to_unfollow = random.sample(users_to_unfollow, max_users)

            unfollowed_count = 0
            for user in users_to_unfollow:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
                    logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
                    break

                # شبیه‌سازی یک الگوی طبیعی: گاهی اوقات پیش از آنفالو کردن، پروفایل کاربر را چک می‌کنیم
                if random.random() < 0.5:  # 50% احتمال
                    try:
                        await self.simulate_profile_check(user.instagram_id)
                    except Exception:
                        pass  # اگر نتوانستیم پروفایل را چک کنیم، آنفالو را ادامه می‌دهیم

                if await self.unfollow_user(user_id=user.instagram_id):
                    unfollowed_count += 1

                    # اضافه کردن تاخیر متغیر بین آنفالوها
                    unfollow_delay = random.uniform(30, 90)
                    time.sleep(unfollow_delay)

            logger.info(f"{unfollowed_count} کاربر آنفالو شدند")
            return unfollowed_count

        except Exception as e:
            logger.error(f"خطا در آنفالو کردن: {str(e)}")
            return 0

    async def unfollow_if_unfollowed(self, max_users=2):
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
                # دریافت تعداد بیشتری برای انتخاب تصادفی
            ).limit(max_users * 2).all()

            if not users_to_unfollow:
                logger.info("هیچ کاربری برای آنفالو متقابل یافت نشد")
                return 0

            # انتخاب تصادفی کاربران برای آنفالو کردن
            if len(users_to_unfollow) > max_users:
                users_to_unfollow = random.sample(users_to_unfollow, max_users)

            unfollowed_count = 0
            for user in users_to_unfollow:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
                    logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
                    break

                # شبیه‌سازی بررسی وضعیت فالو بودن کاربر
                try:
                    friendship_status = self.client.user_friendship(
                        user.instagram_id)
                    if friendship_status.following:
                        # کمی تاخیر قبل از آنفالو کردن
                        time.sleep(random.uniform(1.0, 2.0))
                    else:
                        # کاربر قبلاً آنفالو شده است - بروزرسانی دیتابیس
                        user.is_following = False
                        self.db.commit()
                        continue
                except Exception as e:
                    logger.warning(
                        f"خطا در بررسی وضعیت فالو کاربر {user.username}: {str(e)}")
                    # ادامه می‌دهیم و سعی می‌کنیم آنفالو کنیم

                if await self.unfollow_user(user_id=user.instagram_id):
                    unfollowed_count += 1

                    # اضافه کردن تاخیر متغیر بین آنفالوها
                    unfollow_delay = random.uniform(30, 90)
                    time.sleep(unfollow_delay)

            logger.info(f"{unfollowed_count} کاربر به صورت متقابل آنفالو شدند")
            return unfollowed_count

        except Exception as e:
            logger.error(f"خطا در آنفالو متقابل: {str(e)}")
            return 0

    async def regular_unfollow_routine(self, max_users=5):
        """روتین منظم آنفالو کردن برای حفظ نسبت فالوئینگ/فالوور"""
        if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
            logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
            return 0

        try:
            # اجرای استراتژی مخلوط: ترکیبی از آنفالو کردن قدیمی‌ترین فالوئینگ‌ها و غیرفالوورها

            # ابتدا کاربرانی که ما را فالو نمی‌کنند
            non_followers = self.db.query(User).filter(
                User.is_following == True,
                User.is_follower == False
            ).order_by(User.following_since).limit(int(max_users * 0.7)).all()

            # سپس قدیمی‌ترین فالوئینگ‌ها، حتی اگر ما را فالو می‌کنند (با درصد کمتر)
            oldest_following = self.db.query(User).filter(
                User.is_following == True
            ).order_by(User.following_since).limit(int(max_users * 0.3)).all()

            # ترکیب و شافل کردن لیست
            users_to_unfollow = non_followers + [user for user in oldest_following
                                                 if user not in non_followers and random.random() < 0.3]

            if not users_to_unfollow:
                logger.info("هیچ کاربری برای آنفالو روتین یافت نشد")
                return 0

            # محدود کردن به حداکثر تعداد مورد نظر
            if len(users_to_unfollow) > max_users:
                users_to_unfollow = users_to_unfollow[:max_users]

            # مخلوط کردن لیست برای الگوی آنفالو تصادفی‌تر
            random.shuffle(users_to_unfollow)

            unfollowed_count = 0
            for user in users_to_unfollow:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.UNFOLLOW):
                    logger.info("محدودیت آنفالو روزانه به حداکثر رسیده است")
                    break

                if await self.unfollow_user(user_id=user.instagram_id):
                    unfollowed_count += 1

                    # اضافه کردن تاخیر متغیر بین آنفالوها
                    unfollow_delay = random.uniform(30, 90)
                    time.sleep(unfollow_delay)

            logger.info(f"{unfollowed_count} کاربر در روتین منظم آنفالو شدند")
            return unfollowed_count

        except Exception as e:
            logger.error(f"خطا در روتین منظم آنفالو: {str(e)}")
            return 0

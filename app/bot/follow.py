from instagrapi import Client
from instagrapi.exceptions import ClientError, PleaseWaitFewMinutes, FeedbackRequired
from sqlalchemy.orm import Session
from datetime import datetime
import random
import time

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("follow")


class FollowManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager
        self.engagement_required = True  # درگیر شدن با محتوا قبل از فالو کردن
        self.max_follows_per_hashtag = 2  # حداکثر فالو برای هر هشتگ

    async def simulate_natural_browsing(self, media, user_info=None):
        """شبیه‌سازی مرور طبیعی محتوا قبل از فالو کردن"""
        try:
            # بررسی رندوم پست
            if random.random() < 0.7:  # 70% احتمال
                # شبیه‌سازی دیدن پست
                self.client.media_info(media.id)

                # تاخیر کوتاه مثل دیدن پست
                time.sleep(random.uniform(1.5, 4.0))

                # گاهی اوقات لایک کردن پست
                if random.random() < 0.5:  # 50% احتمال
                    self.client.media_like(media.id)
                    logger.info(f"پست {media.id} لایک شد (قبل از فالو کردن)")

                    # ثبت تعامل لایک در دیتابیس
                    if user_info:
                        # بررسی یا ایجاد کاربر در دیتابیس
                        db_user = self.db.query(User).filter(
                            User.instagram_id == str(user_info.pk)).first()
                        if db_user:
                            # ثبت تعامل در دیتابیس
                            interaction = Interaction(
                                user_id=db_user.id,
                                type=InteractionType.LIKE,
                                media_id=media.id,
                                status=True,
                                created_at=datetime.now()
                            )
                            self.db.add(interaction)
                            self.db.commit()

                    # اضافه کردن تاخیر بعد از لایک
                    time.sleep(random.uniform(1.0, 3.0))

            # گاهی اوقات بررسی پروفایل قبل از فالو کردن
            if random.random() < 0.8:  # 80% احتمال
                if not user_info:
                    user_info = self.client.user_info(media.user.pk)

                # شبیه‌سازی بررسی تعداد پست‌ها و فالوورها
                time.sleep(random.uniform(1.0, 3.0))

                # گاهی اوقات بررسی یکی دو پست دیگر از همان کاربر
                if random.random() < 0.4:  # 40% احتمال
                    user_medias = self.client.user_medias(user_info.pk, 3)
                    if user_medias and len(user_medias) > 1:
                        # بررسی یک پست تصادفی دیگر
                        other_media = random.choice(user_medias)
                        if other_media.id != media.id:
                            self.client.media_info(other_media.id)
                            time.sleep(random.uniform(1.0, 3.5))

            return True
        except Exception as e:
            logger.warning(f"خطا در شبیه‌سازی مرور طبیعی: {str(e)}")
            return False

    async def follow_user(self, username=None, user_id=None, media=None):
        """دنبال کردن یک کاربر با نام کاربری یا آیدی"""
        if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
            logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        # اضافه کردن تاخیر قبل از فالو کردن
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
                    user_info = self.client.user_info(user_id)
                    username = user_info.username
                except Exception as e:
                    logger.error(
                        f"خطا در دریافت اطلاعات کاربر با آیدی {user_id}: {str(e)}")
                    return False

            # بررسی می‌کنیم که قبلاً این کاربر را فالو نکرده باشیم
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_id)).first()
            if db_user and db_user.is_following:
                logger.info(f"کاربر {username or user_id} قبلاً فالو شده است")
                return False

            # شبیه‌سازی تعامل طبیعی قبل از فالو کردن
            if self.engagement_required and media:
                await self.simulate_natural_browsing(media, user_info)

            # بررسی نسبت فالوورها به فالوئینگ‌ها
            if hasattr(user_info, 'follower_count') and hasattr(user_info, 'following_count') and user_info.follower_count > 0:
                ratio = user_info.following_count / user_info.follower_count
                if ratio > 2.5 and random.random() < 0.7:
                    logger.info(
                        f"کاربر {username} نسبت فالوئینگ به فالوور بالایی دارد ({ratio:.1f}). فالو نمی‌کنیم.")
                    return False

            # تلاش برای فالو کردن کاربر با مدیریت خطاها
            try:
                result = self.client.user_follow(user_id)

                if result:
                    logger.info(f"کاربر {username} با موفقیت فالو شد")

                    # بروزرسانی یا ایجاد رکورد کاربر در دیتابیس
                    if not db_user:
                        db_user = User(
                            instagram_id=str(user_id),
                            username=user_info.username,
                            full_name=user_info.full_name,
                            is_following=True,
                            following_since=datetime.now()
                        )
                        self.db.add(db_user)
                        self.db.flush()
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

            except FeedbackRequired as e:
                logger.error(
                    f"خطای محدودیت در فالو کردن کاربر {username or user_id}: {str(e)}")
                # استراحت طولانی برای جلوگیری از محدودیت بیشتر
                time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
                return False

            except PleaseWaitFewMinutes as e:
                logger.error(
                    f"خطای محدودیت نرخ در فالو کردن کاربر {username or user_id}: {str(e)}")
                # استراحت طولانی برای جلوگیری از محدودیت بیشتر
                time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
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

    async def follow_users_by_hashtag(self, hashtag, max_users=2):
        """فالو کردن کاربران بر اساس هشتگ با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
            logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
            return 0

        try:
            logger.info(f"جستجوی پست‌ها با هشتگ {hashtag}")

            # تست اعتبار نشست قبل از انجام عملیات
            try:
                self.client.get_timeline_feed(amount=1)
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

            # انجام جستجو براساس هشتگ - درخواست تعداد بیشتری پست برای افزایش تنوع
            try:
                medias = self.client.hashtag_medias_recent(
                    hashtag, amount=20)
            except Exception as e:
                logger.error(f"خطا در دریافت پست‌های هشتگ {hashtag}: {str(e)}")
                return 0

            if not medias:
                logger.info(f"هیچ پستی با هشتگ {hashtag} یافت نشد")
                return 0

            # مخلوط کردن پست‌ها برای افزایش تنوع
            random.shuffle(medias)

            # شبیه‌سازی مرور هشتگ
            browse_count = random.randint(2, 5)
            for i in range(min(browse_count, len(medias))):
                try:
                    # بررسی چند پست قبل از شروع فالو کردن
                    media = medias[i]
                    self.client.media_info(media.id)

                    # گاهی اوقات لایک کردن پست
                    if random.random() < 0.3:  # 30% احتمال
                        self.client.media_like(media.id)
                        logger.info(
                            f"پست {media.id} از هشتگ {hashtag} لایک شد (مرور اولیه)")

                    # تاخیر طبیعی بین بررسی پست‌ها
                    time.sleep(random.uniform(2.0, 5.0))
                except Exception:
                    continue

            followed_count = 0
            attempted_count = 0

            # محدودیت تعداد تلاش‌های فالو
            max_attempts = min(10, len(medias))

            for media in medias:
                if followed_count >= max_users or attempted_count >= max_attempts:
                    break

                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
                    logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
                    break

                attempted_count += 1
                user_id = media.user.pk

                # بررسی قبل از فالو کردن
                try:
                    user_info = self.client.user_info(user_id)
                    username = user_info.username

                    # بررسی معیارهای فیلتر کردن کاربران

                    # فیلتر براساس تعداد فالوورها - فقط کاربران با تعداد متوسط فالوور را فالو می‌کنیم
                    if hasattr(user_info, 'follower_count'):
                        if user_info.follower_count < 100 or user_info.follower_count > 10000:
                            logger.info(
                                f"کاربر {username} با {user_info.follower_count} فالوور در محدوده مطلوب نیست")
                            continue

                    # فیلتر براساس تعداد پست‌ها - کاربران با پست کم را فالو نمی‌کنیم
                    if hasattr(user_info, 'media_count') and user_info.media_count < 10:
                        logger.info(
                            f"کاربر {username} با {user_info.media_count} پست فعال نیست")
                        continue

                    # فیلتر براساس نام کاربری (اجتناب از کاربران تبلیغاتی)
                    if any(keyword in username.lower() for keyword in ['shop', 'store', 'official', 'admin', 'org']):
                        logger.info(
                            f"کاربر {username} احتمالاً یک صفحه تجاری است")
                        continue

                    logger.info(
                        f"تلاش برای فالو کردن کاربر {username} با آیدی {user_id}")
                except Exception as e:
                    logger.warning(
                        f"خطا در دریافت اطلاعات کاربر {user_id}: {str(e)}")
                    continue

                # فالو کردن کاربر با ارسال پست برای شبیه‌سازی بهتر
                success = await self.follow_user(user_id=user_id, media=media)
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

    async def follow_back_users(self, max_users=2):
        """فالو کردن متقابل کاربرانی که ما را فالو کرده‌اند ولی ما آنها را فالو نکرده‌ایم"""
        if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
            logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
            return 0

        try:
            # کاربرانی که ما را فالو کرده‌اند ولی ما آنها را فالو نکرده‌ایم
            users_to_follow = self.db.query(User).filter(
                User.is_follower == True,
                User.is_following == False
                # دریافت تعداد بیشتری برای انتخاب تصادفی
            ).limit(max_users * 2).all()

            if not users_to_follow:
                logger.info("هیچ کاربری برای فالو متقابل یافت نشد")
                return 0

            # انتخاب تصادفی کاربران برای فالو کردن
            if len(users_to_follow) > max_users:
                users_to_follow = random.sample(users_to_follow, max_users)

            followed_count = 0
            for user in users_to_follow:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.FOLLOW):
                    logger.info("محدودیت فالو روزانه به حداکثر رسیده است")
                    break

                # دریافت آخرین پست‌های کاربر برای شبیه‌سازی بهتر
                try:
                    user_medias = self.client.user_medias(user.instagram_id, 5)
                    media = user_medias[0] if user_medias else None
                except Exception:
                    media = None

                # فالو کردن کاربر
                if await self.follow_user(user_id=user.instagram_id, media=media):
                    followed_count += 1

                    # اضافه کردن تاخیر متغیر بین فالوها
                    follow_delay = random.uniform(30, 90)
                    time.sleep(follow_delay)

            logger.info(f"{followed_count} کاربر به صورت متقابل فالو شدند")
            return followed_count

        except Exception as e:
            logger.error(f"خطا در فالو متقابل: {str(e)}")
            return 0

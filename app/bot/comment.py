from instagrapi import Client
from instagrapi.exceptions import ClientError, PleaseWaitFewMinutes, FeedbackRequired
from sqlalchemy.orm import Session
from datetime import datetime
import random
import time
import re

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
            # کامنت‌های ساده و کوتاه
            "عالی بود 👌",
            "چقدر زیبا 😍",
            "فوق‌العاده است 👏",
            "خیلی خوبه ✨",
            "خیلی قشنگه 🙌",

            # کامنت‌های با طول متوسط
            "عالیه 🔥 کارت درسته",
            "محشره 💯 خیلی خوشم اومد",
            "دمت گرم 👍 عالی بود",
            "خیلی جالبه 🌟 لذت بردم",
            "کارت درسته 💪 ادامه بده",

            # کامنت‌های طبیعی‌تر با محتوای بیشتر
            "خیلی خوشم اومد 🎯 واقعا با کیفیت بود",
            "عالی کار کردی 🌹 مثل همیشه",
            "واقعا قشنگه 👌✨ ممنون که به اشتراک گذاشتی",
            "دوستش دارم 💖 کارهای بعدیت رو هم حتما میبینم",
            "چقدر خلاقانه 🌈 آفرین به شما"
        ]

        # کامنت‌های مختص موضوعات خاص
        self.topic_comments = {
            "غذا": [
                "به نظر خوشمزه میاد 😋",
                "دستپختت عالیه 👨‍🍳",
                "خیلی اشتهابرانگیزه 🍽️",
                "دستور پختش رو میشه بگی؟ 👌",
                "چقدر خوشمزه به نظر میرسه 😍"
            ],
            "طبیعت": [
                "طبیعت زیبای ایران 🌿",
                "منظره فوق‌العاده‌ای هست 🏞️",
                "چه جای زیبایی 🌄 کجاست؟",
                "عکاسیت عالیه 📸",
                "دلم خواست برم اینجا 🍃"
            ],
            "سفر": [
                "سفر خوش بگذره ✈️",
                "چه جای قشنگی برای سفر 🧳",
                "منم عاشق سفرم 🗺️",
                "خوش به حالت، جای قشنگیه 🏝️",
                "سفرنامت رو کامل بنویس 📝"
            ]
        }

        # سطح احتیاط در کامنت گذاشتن (0 تا 1)
        self.caution_level = 0.7  # هرچه بیشتر، کامنت‌های کمتر و محتاطانه‌تر

    def get_natural_delay_before_comment(self):
        """محاسبه تاخیر طبیعی قبل از کامنت گذاشتن (مثل زمان تایپ کردن و خواندن پست)"""
        # محاسبه زمان مطالعه پست (بسته به طول کپشن و تعداد تصاویر)
        base_reading_time = random.uniform(3.0, 10.0)

        # محاسبه زمان تایپ (حدود 1-2 ثانیه برای هر کلمه)
        avg_comment_length = 3  # میانگین تعداد کلمات در کامنت‌های ما
        typing_time = random.uniform(
            avg_comment_length, avg_comment_length * 2)

        return base_reading_time + typing_time

    def get_topic_based_comment(self, hashtags=None, caption=None):
        """انتخاب کامنت مناسب براساس موضوع پست"""
        if not hashtags and not caption:
            return self.get_random_comment()

        detected_topics = []

        # بررسی هشتگ‌ها
        if hashtags:
            for topic in self.topic_comments.keys():
                if any(topic in tag.lower() for tag in hashtags):
                    detected_topics.append(topic)

        # بررسی کپشن
        if caption:
            for topic in self.topic_comments.keys():
                if topic in caption.lower():
                    if topic not in detected_topics:
                        detected_topics.append(topic)

        # اگر موضوعی تشخیص داده شد
        if detected_topics:
            # انتخاب یک موضوع تصادفی از موضوعات تشخیص داده شده
            selected_topic = random.choice(detected_topics)
            # انتخاب یک کامنت تصادفی برای این موضوع
            return random.choice(self.topic_comments[selected_topic])

        # اگر موضوع خاصی تشخیص داده نشد، از کامنت‌های عمومی استفاده می‌کنیم
        return self.get_random_comment()

    def get_random_comment(self):
        """انتخاب یک کامنت تصادفی از قالب‌ها"""
        return random.choice(self.comment_templates)

    def should_comment_on_post(self, media_info=None):
        """تصمیم‌گیری هوشمند برای کامنت گذاشتن یا نگذاشتن"""
        # اگر سطح احتیاط بالا باشد، با احتمال کمتری کامنت می‌گذاریم
        if random.random() < self.caution_level:
            return False

        if not media_info:
            return True

        # بررسی تعداد کامنت‌های پست
        if hasattr(media_info, 'comment_count') and media_info.comment_count > 50:
            # روی پست‌های با کامنت زیاد، با احتمال کمتری کامنت می‌گذاریم
            return random.random() > 0.7

        # بررسی تعداد لایک‌های پست
        if hasattr(media_info, 'like_count') and media_info.like_count > 1000:
            # روی پست‌های خیلی محبوب، با احتمال کمتری کامنت می‌گذاریم
            return random.random() > 0.8

        # بررسی قدیمی بودن پست
        if hasattr(media_info, 'taken_at'):
            post_age_days = (datetime.now() - media_info.taken_at).days
            if post_age_days > 30:
                # روی پست‌های قدیمی کمتر کامنت می‌گذاریم
                return random.random() > 0.9

        return True

    async def add_comment(self, media_id=None, text=None, hashtags=None, caption=None):
        """افزودن کامنت به یک پست با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
            logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        if not media_id:
            logger.error("آیدی رسانه باید مشخص شود")
            return False

        # دریافت اطلاعات پست برای تصمیم‌گیری بهتر
        try:
            media_info = self.client.media_info(media_id)

            # تصمیم‌گیری هوشمند برای کامنت گذاشتن
            if not self.should_comment_on_post(media_info):
                logger.info(f"تصمیم گرفته شد روی پست {media_id} کامنت نگذاریم")
                return False

            # استخراج هشتگ‌ها و کپشن برای کامنت مرتبط‌تر
            if not hashtags and hasattr(media_info, 'caption_text'):
                caption = media_info.caption_text
                hashtags = re.findall(r'#(\w+)', caption)

        except Exception as e:
            logger.warning(f"خطا در دریافت اطلاعات پست {media_id}: {str(e)}")
            # ادامه می‌دهیم، ولی بدون اطلاعات اضافی

        if not text:
            text = self.get_topic_based_comment(hashtags, caption)

        # شبیه‌سازی تاخیر طبیعی قبل از کامنت گذاشتن
        delay = self.get_natural_delay_before_comment()
        time.sleep(delay)

        try:
            result = self.client.media_comment(media_id, text)

            if result:
                logger.info(
                    f"کامنت با موفقیت به پست {media_id} افزوده شد: {text}")

                # دریافت اطلاعات صاحب پست
                try:
                    if not media_info:
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

        except FeedbackRequired as e:
            logger.error(
                f"خطای محدودیت در افزودن کامنت به پست {media_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return False

        except PleaseWaitFewMinutes as e:
            logger.error(
                f"محدودیت نرخ در افزودن کامنت به پست {media_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return False

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در افزودن کامنت به پست {media_id}: {str(e)}")
            return False

        except Exception as e:
            logger.error(f"خطا در افزودن کامنت به پست {media_id}: {str(e)}")
            self.db.rollback()
            return False

    async def comment_on_hashtag_posts(self, hashtag, max_posts=1):
        """کامنت گذاشتن بر روی پست‌های دارای هشتگ خاص با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
            logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
            return 0

        try:
            logger.info(f"جستجوی پست‌ها با هشتگ {hashtag}")

            # گرفتن تعداد بیشتری پست و انتخاب تصادفی از میان آنها
            medias = self.client.hashtag_medias_recent(hashtag, amount=50)

            if not medias:
                logger.info(f"هیچ پستی با هشتگ {hashtag} یافت نشد")
                return 0

            # فیلتر کردن پست‌ها براساس معیارهای مناسب
            filtered_medias = []
            for media in medias:
                try:
                    # دریافت اطلاعات کامل پست
                    media_info = self.client.media_info(media.id)

                    # فیلتر براساس معیارها
                    # 1. پست‌های با کامنت خیلی زیاد را رد می‌کنیم
                    if hasattr(media_info, 'comment_count') and media_info.comment_count > 500:
                        continue

                    # 2. پست‌های خیلی قدیمی را رد می‌کنیم
                    if hasattr(media_info, 'taken_at'):
                        post_age_days = (datetime.now() -
                                         media_info.taken_at).days
                        if post_age_days > 14:  # پست‌های قدیمی‌تر از 2 هفته
                            continue

                    # 3. پست‌های کاربران با فالوور خیلی زیاد یا خیلی کم را رد می‌کنیم
                    user_info = self.client.user_info(media_info.user.pk)
                    if hasattr(user_info, 'follower_count'):
                        if user_info.follower_count < 100 or user_info.follower_count > 100000:
                            continue

                    filtered_medias.append(media_info)

                    # کمی تاخیر بین بررسی پست‌ها
                    time.sleep(random.uniform(0.5, 1.5))

                except Exception:
                    # اگر نتوانستیم اطلاعات پست را دریافت کنیم، آن را نادیده می‌گیریم
                    continue

                # به اندازه کافی پست پیدا کردیم
                if len(filtered_medias) >= max_posts * 3:
                    break

            # اگر پست مناسبی پیدا نشد
            if not filtered_medias:
                logger.info(f"هیچ پست مناسبی با هشتگ {hashtag} یافت نشد")
                return 0

            # مخلوط کردن پست‌ها برای انتخاب تصادفی
            random.shuffle(filtered_medias)

            comment_count = 0
            for media in filtered_medias:
                if comment_count >= max_posts:
                    break

                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
                    logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
                    break

                # شبیه‌سازی مرور پست
                # گاهی اوقات لایک کردن قبل از کامنت
                if random.random() < 0.7:  # 70% احتمال
                    try:
                        self.client.media_like(media.id)
                        logger.info(f"پست {media.id} لایک شد (قبل از کامنت)")
                        time.sleep(random.uniform(1.0, 3.0))
                    except Exception as e:
                        logger.warning(
                            f"خطا در لایک کردن پست {media.id}: {str(e)}")

                # استخراج هشتگ‌ها و کپشن برای کامنت متناسب
                caption = media.caption_text if hasattr(
                    media, 'caption_text') else ""
                hashtags = re.findall(r'#(\w+)', caption)

                # انتخاب کامنت مناسب براساس محتوای پست
                comment_text = self.get_topic_based_comment(hashtags, caption)

                if await self.add_comment(media_id=media.id, text=comment_text, hashtags=hashtags, caption=caption):
                    comment_count += 1

                    # افزودن تاخیر اضافی بین کامنت‌ها
                    time.sleep(random.uniform(60, 180))  # 1-3 دقیقه

            logger.info(
                f"{comment_count} کامنت برای پست‌های با هشتگ {hashtag} افزوده شد")
            return comment_count

        except Exception as e:
            logger.error(
                f"خطا در کامنت گذاشتن بر روی پست‌های با هشتگ {hashtag}: {str(e)}")
            return 0

    async def comment_on_followers_posts(self, max_posts=1):
        """کامنت گذاشتن بر روی پست‌های دنبال‌کنندگان با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.COMMENT):
            logger.info("محدودیت کامنت روزانه به حداکثر رسیده است")
            return 0

        try:
            # دریافت کاربرانی که ما را فالو می‌کنند
            followers = self.db.query(User).filter(
                User.is_follower == True).limit(max_posts * 5).all()

            if not followers:
                logger.info("هیچ دنبال‌کننده‌ای یافت نشد")
                return 0

            # انتخاب تصادفی تعدادی از فالوورها
            selected_followers = random.sample(
                followers, min(max_posts * 2, len(followers)))

            comment_count = 0
            for follower in selected_followers:
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
                        follower.instagram_id, 10)

                    if user_medias:
                        # انتخاب تصادفی یک پست از آخرین پست‌ها
                        media = random.choice(user_medias)

                        # دریافت اطلاعات کامل پست
                        media_info = self.client.media_info(media.id)

                        # بررسی مناسب بودن پست
                        if hasattr(media_info, 'taken_at'):
                            post_age_days = (
                                datetime.now() - media_info.taken_at).days
                            if post_age_days > 7:  # پست‌های قدیمی‌تر از 1 هفته را رد می‌کنیم
                                continue

                        # شبیه‌سازی مرور پست
                        time.sleep(random.uniform(1.5, 4.0))

                        # گاهی اوقات لایک کردن قبل از کامنت
                        if random.random() < 0.8:  # 80% احتمال برای فالوورها
                            try:
                                self.client.media_like(media.id)
                                logger.info(
                                    f"پست {media.id} از فالوور {follower.username} لایک شد (قبل از کامنت)")
                                time.sleep(random.uniform(1.0, 3.0))
                            except Exception as e:
                                logger.warning(
                                    f"خطا در لایک کردن پست {media.id}: {str(e)}")

                        # استخراج هشتگ‌ها و کپشن برای کامنت متناسب
                        caption = media.caption_text if hasattr(
                            media, 'caption_text') else ""
                        hashtags = re.findall(r'#(\w+)', caption)

                        # انتخاب کامنت مناسب براساس محتوای پست
                        comment_text = self.get_topic_based_comment(
                            hashtags, caption)

                        if await self.add_comment(media_id=media.id, text=comment_text, hashtags=hashtags, caption=caption):
                            comment_count += 1

                            # افزودن تاخیر اضافی بین کامنت‌ها به فالوورها
                            time.sleep(random.uniform(90, 240))  # 1.5-4 دقیقه

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

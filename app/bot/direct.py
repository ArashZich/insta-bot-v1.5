from instagrapi import Client
from instagrapi.exceptions import ClientError, PleaseWaitFewMinutes, FeedbackRequired
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random
import time
import re

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("direct")


class DirectMessageManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager
        # پیام‌های ساده و کوتاه
        self.message_templates = [
            "سلام! پست‌هات خیلی جالبه 👋",
            "سلام، از محتوای پیج‌ات خوشم اومد 👌",
            "درود! از آشنایی با شما خوشحالم ✨",
            "سلام! می‌تونیم تبادل نظر داشته باشیم 🤝",
            "سلام، پروفایلت برام جالب بود 👍",
            "درود! محتوای خوبی داری 💯",
            "سلام! چقدر پست‌های خوبی داری 🌟"
        ]

        # پیام‌های خوش‌آمدگویی به فالوورهای جدید
        self.welcome_messages = [
            "سلام {name}! ممنون که ما رو فالو کردی. خوشحال میشیم با محتوای ما همراه باشی 🌹",
            "درود {name}! از اینکه پیج ما رو دنبال می‌کنی سپاسگزاریم. امیدوارم از محتوای ما لذت ببری ✨",
            "سلام {name} عزیز! خیلی خوشحالم که به جمع دنبال‌کننده‌های ما پیوستی. منتظر نظرات ارزشمندت هستیم 🙏",
            "به جمع ما خوش اومدی {name}! ممنون از حمایتت 👋",
            "سلام {name}! ممنون که پیج ما رو فالو کردی. اگه سوالی داشتی خوشحال میشم کمکت کنم 🤝"
        ]

        # پاسخ‌های اتوماتیک به پیام‌های دریافتی
        self.auto_replies = [
            "ممنون از پیام شما! بزودی پاسخ میدم 🙏",
            "پیامت دریافت شد، ممنون از تماست. در اولین فرصت بررسی و پاسخ میدم ✨",
            "سلام! ممنون از پیامت. به محض اینکه فرصت کنم جواب میدم 👋",
            "با تشکر از پیامت، بزودی باهات در تماس خواهم بود 👌"
        ]

        # بیشترین تعداد پیام در یک روز به یک کاربر
        self.max_messages_per_user_daily = 2

        # سطح احتیاط در ارسال پیام (0 تا 1)
        self.caution_level = 0.8  # هرچه بیشتر، پیام‌های کمتر و محتاطانه‌تر

    def get_natural_delay_before_message(self):
        """محاسبه تاخیر طبیعی قبل از ارسال پیام (مثل زمان تایپ کردن)"""
        # محاسبه زمان تایپ (حدود 0.5-1 ثانیه برای هر کلمه)
        avg_message_length = 8  # میانگین تعداد کلمات در پیام‌های ما
        typing_time = random.uniform(
            avg_message_length * 0.5, avg_message_length)

        # تاخیر اضافی برای واقعی‌تر شدن
        extra_delay = random.uniform(2.0, 5.0)

        return typing_time + extra_delay

    def get_personalized_message(self, user_info=None, message_type="welcome"):
        """انتخاب و شخصی‌سازی یک پیام براساس اطلاعات کاربر"""
        if message_type == "welcome":
            templates = self.welcome_messages
        else:
            templates = self.message_templates

        message = random.choice(templates)

        # شخصی‌سازی پیام با نام کاربر اگر موجود باشد
        if user_info and hasattr(user_info, 'full_name') and user_info.full_name:
            name = user_info.full_name.split()[0]  # فقط نام اول
            message = message.format(name=name)
        else:
            # اگر نام در دسترس نیست، {name} را حذف می‌کنیم
            message = message.replace("{name}", "").replace("  ", " ").strip()

        return message

    def should_send_message_to_user(self, user_id=None, username=None):
        """تصمیم‌گیری هوشمند برای ارسال پیام به کاربر"""
        # اگر سطح احتیاط بالا باشد، با احتمال کمتری پیام می‌فرستیم
        if random.random() < self.caution_level:
            return False

        # بررسی پیام‌های قبلی به این کاربر
        if user_id:
            # پیدا کردن کاربر در دیتابیس
            db_user = self.db.query(User).filter(
                User.instagram_id == str(user_id)).first()

            if db_user:
                # بررسی تعداد پیام‌های ارسال شده به این کاربر در 24 ساعت گذشته
                yesterday = datetime.now() - timedelta(days=1)

                recent_messages = self.db.query(Interaction).filter(
                    Interaction.user_id == db_user.id,
                    Interaction.type == InteractionType.DIRECT_MESSAGE,
                    Interaction.created_at >= yesterday
                ).count()

                if recent_messages >= self.max_messages_per_user_daily:
                    logger.info(
                        f"در 24 ساعت گذشته {recent_messages} پیام به کاربر {username or user_id} ارسال شده است")
                    return False

        return True

    async def send_direct_message(self, user_id=None, username=None, text=None):
        """ارسال پیام مستقیم به یک کاربر با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
            logger.info("محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
            return False

        # تصمیم‌گیری هوشمند برای ارسال پیام
        if not self.should_send_message_to_user(user_id, username):
            logger.info(
                f"تصمیم گرفته شد به کاربر {username or user_id} پیام ارسال نشود")
            return False

        # اگر user_id ارائه نشده و username داریم، user_id را پیدا می‌کنیم
        if not user_id and username:
            try:
                user_info = self.client.user_info_by_username(username)
                user_id = user_info.pk
            except Exception as e:
                logger.error(f"خطا در یافتن کاربر {username}: {str(e)}")
                return False

        if not user_id:
            logger.error("آیدی کاربر یا نام کاربری باید مشخص شود")
            return False

        # دریافت اطلاعات کاربر برای شخصی‌سازی پیام
        user_info = None
        try:
            user_info = self.client.user_info(user_id)
            if not username:
                username = user_info.username
        except Exception as e:
            logger.warning(f"خطا در دریافت اطلاعات کاربر {user_id}: {str(e)}")
            # ادامه می‌دهیم، حتی اگر نتوانستیم اطلاعات کاربر را دریافت کنیم

        if not text:
            text = self.get_personalized_message(user_info, "regular")

        # شبیه‌سازی تاخیر طبیعی قبل از ارسال پیام
        delay = self.get_natural_delay_before_message()
        time.sleep(delay)

        try:
            # ایجاد یا بازیابی thread با کاربر
            thread = self.client.direct_thread_by_participants([user_id])

            # ارسال پیام
            result = self.client.direct_send(text, thread_ids=[thread.id])

            if result:
                logger.info(
                    f"پیام با موفقیت به کاربر {username or user_id} ارسال شد: {text}")

                # بررسی یا ایجاد کاربر در دیتابیس
                db_user = self.db.query(User).filter(
                    User.instagram_id == str(user_id)).first()
                if not db_user:
                    try:
                        if not user_info:
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
                    type=InteractionType.DIRECT_MESSAGE,
                    content=text,
                    status=True,
                    created_at=datetime.now()
                )
                self.db.add(interaction)

                self.db.commit()

                # بروزرسانی شمارنده‌های فعالیت
                self.activity_manager.update_bot_status_activity(
                    InteractionType.DIRECT_MESSAGE)

                return True
            else:
                logger.warning(
                    f"ارسال پیام به کاربر {username or user_id} ناموفق بود")
                return False

        except FeedbackRequired as e:
            logger.error(
                f"خطای محدودیت در ارسال پیام به کاربر {username or user_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return False

        except PleaseWaitFewMinutes as e:
            logger.error(
                f"محدودیت نرخ در ارسال پیام به کاربر {username or user_id}: {str(e)}")
            # استراحت طولانی برای جلوگیری از محدودیت بیشتر
            time.sleep(random.randint(300, 600))  # 5-10 دقیقه استراحت
            return False

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در ارسال پیام به کاربر {username or user_id}: {str(e)}")
            return False

        except Exception as e:
            logger.error(
                f"خطا در ارسال پیام به کاربر {username or user_id}: {str(e)}")
            self.db.rollback()
            return False

    async def send_welcome_message_to_new_followers(self, max_messages=1):
        """ارسال پیام خوش‌آمدگویی به دنبال‌کنندگان جدید"""
        if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
            logger.info("محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
            return 0

        try:
            # دریافت کاربرانی که به تازگی ما را فالو کرده‌اند و هنوز به آنها پیام نداده‌ایم
            two_days_ago = datetime.now() - timedelta(days=2)

            new_followers = self.db.query(User).filter(
                User.is_follower == True,
                User.follower_since >= two_days_ago,
                ~User.interactions.any(
                    Interaction.type == InteractionType.DIRECT_MESSAGE)
                # دریافت تعداد بیشتری برای انتخاب تصادفی
            ).limit(max_messages * 3).all()

            if not new_followers:
                logger.info("هیچ دنبال‌کننده جدیدی برای ارسال پیام یافت نشد")
                return 0

            # انتخاب تصادفی کاربران برای ارسال پیام
            if len(new_followers) > max_messages:
                selected_followers = random.sample(new_followers, max_messages)
            else:
                selected_followers = new_followers

            message_count = 0
            for follower in selected_followers:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
                    logger.info(
                        "محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
                    break

                # تصمیم‌گیری هوشمند برای ارسال پیام
                if not self.should_send_message_to_user(follower.instagram_id, follower.username):
                    continue

                # دریافت اطلاعات کاربر برای شخصی‌سازی پیام
                user_info = None
                try:
                    user_info = self.client.user_info(follower.instagram_id)
                except Exception as e:
                    logger.warning(
                        f"خطا در دریافت اطلاعات کاربر {follower.username}: {str(e)}")

                welcome_message = self.get_personalized_message(
                    user_info, "welcome")

                # ارسال پیام خوش‌آمدگویی
                if await self.send_direct_message(user_id=follower.instagram_id, text=welcome_message):
                    message_count += 1

                    # افزودن تاخیر اضافی بین پیام‌ها
                    time.sleep(random.uniform(120, 300))  # 2-5 دقیقه

            logger.info(
                f"{message_count} پیام خوش‌آمدگویی به دنبال‌کنندگان جدید ارسال شد")
            return message_count

        except Exception as e:
            logger.error(
                f"خطا در ارسال پیام خوش‌آمدگویی به دنبال‌کنندگان جدید: {str(e)}")
            return 0

    async def reply_to_direct_messages(self, max_replies=1):
        """پاسخ به پیام‌های دریافتی با رفتار طبیعی‌تر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
            logger.info("محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
            return 0

        try:
            # دریافت نشست‌های پیام جدید
            try:
                pending_threads = []
                inbox_threads = []

                try:
                    # دریافت پیام‌های معلق (در انتظار تایید)
                    pending_threads = self.client.direct_pending_inbox()
                except Exception as e:
                    logger.warning(f"خطا در دریافت پیام‌های معلق: {str(e)}")

                try:
                    # دریافت پیام‌های اصلی
                    inbox_threads = self.client.direct_threads()
                except Exception as e:
                    logger.warning(f"خطا در دریافت پیام‌های ورودی: {str(e)}")

                # ترکیب همه نشست‌ها
                all_threads = pending_threads + inbox_threads

                if not all_threads:
                    logger.info("هیچ نشست پیام جدیدی یافت نشد")
                    return 0

                logger.info(f"{len(all_threads)} نشست پیام یافت شد")

                # فیلتر کردن نشست‌هایی که پیام خوانده نشده دارند
                unread_threads = []

                for thread in all_threads:
                    has_unread = False

                    # بررسی وضعیت خوانده شدن
                    if hasattr(thread, 'unread_count') and thread.unread_count > 0:
                        has_unread = True
                    elif hasattr(thread, 'has_newer') and thread.has_newer:
                        has_unread = True
                    elif hasattr(thread, 'unread') and thread.unread:
                        has_unread = True
                    else:
                        # بررسی آخرین پیام
                        try:
                            messages = self.client.direct_messages(thread.id)
                            if messages and len(messages) > 0:
                                last_message = messages[0]
                                # اگر آخرین پیام از طرف ما نباشد، فرض می‌کنیم خوانده نشده است
                                if hasattr(last_message, 'user_id') and str(last_message.user_id) != str(self.client.user_id):
                                    has_unread = True
                        except Exception:
                            continue

                    if has_unread:
                        unread_threads.append(thread)

                # بررسی تعداد نشست‌های خوانده نشده
                if not unread_threads:
                    logger.info("هیچ پیام خوانده نشده‌ای یافت نشد")
                    return 0

                logger.info(
                    f"{len(unread_threads)} نشست با پیام خوانده نشده یافت شد")

                # محدود کردن تعداد پاسخ‌ها
                if len(unread_threads) > max_replies:
                    unread_threads = random.sample(unread_threads, max_replies)

                reply_count = 0
                for thread in unread_threads:
                    # تأخیر تصادفی بین اقدامات
                    self.activity_manager.random_delay()

                    if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
                        logger.info(
                            "محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
                        break

                    # دریافت پیام‌های نشست
                    try:
                        messages = self.client.direct_messages(thread.id)
                    except Exception as e:
                        logger.warning(
                            f"خطا در دریافت پیام‌های نشست: {str(e)}")
                        continue

                    # بررسی آخرین پیام
                    if messages and len(messages) > 0:
                        last_message = messages[0]

                        # اگر آخرین پیام از طرف ما نباشد، پاسخ می‌دهیم
                        if hasattr(last_message, 'user_id') and str(last_message.user_id) != str(self.client.user_id):
                            # دریافت اطلاعات فرستنده
                            sender_id = last_message.user_id

                            # شبیه‌سازی خواندن پیام و تایپ کردن پاسخ
                            time.sleep(random.uniform(3.0, 7.0))

                            # انتخاب یک پاسخ اتوماتیک
                            reply_text = random.choice(self.auto_replies)

                            # ارسال پاسخ
                            try:
                                # ابتدا با direct_answer تلاش می‌کنیم
                                if hasattr(self.client, 'direct_answer'):
                                    result = self.client.direct_answer(
                                        thread.id, reply_text)
                                else:
                                    # اگر direct_answer موجود نیست، از direct_send استفاده می‌کنیم
                                    result = self.client.direct_send(
                                        reply_text, thread_ids=[thread.id])

                                if result:
                                    logger.info(
                                        f"پاسخ به پیام در نشست {thread.id} ارسال شد")

                                    # ثبت تعامل در دیتابیس
                                    try:
                                        # بررسی یا ایجاد کاربر در دیتابیس
                                        db_user = self.db.query(User).filter(
                                            User.instagram_id == str(sender_id)).first()

                                        if not db_user:
                                            try:
                                                user_info = self.client.user_info(
                                                    sender_id)
                                                db_user = User(
                                                    instagram_id=str(
                                                        sender_id),
                                                    username=user_info.username,
                                                    full_name=user_info.full_name
                                                )
                                                self.db.add(db_user)
                                                self.db.flush()
                                            except Exception as e:
                                                logger.error(
                                                    f"خطا در دریافت اطلاعات کاربر {sender_id}: {str(e)}")

                                        # ثبت تعامل
                                        interaction = Interaction(
                                            user_id=db_user.id if db_user else None,
                                            type=InteractionType.DIRECT_MESSAGE,
                                            content=reply_text,
                                            status=True,
                                            created_at=datetime.now()
                                        )
                                        self.db.add(interaction)
                                        self.db.commit()
                                    except Exception as e:
                                        logger.error(
                                            f"خطا در ثبت تعامل پیام در دیتابیس: {str(e)}")

                                    # بروزرسانی شمارنده‌های فعالیت
                                    self.activity_manager.update_bot_status_activity(
                                        InteractionType.DIRECT_MESSAGE)

                                    reply_count += 1

                                    # افزودن تاخیر اضافی بین پاسخ‌ها
                                    time.sleep(random.uniform(
                                        60, 180))  # 1-3 دقیقه
                            except Exception as e:
                                logger.error(
                                    f"خطا در ارسال پاسخ به نشست {thread.id}: {str(e)}")

                logger.info(f"به {reply_count} پیام دریافتی پاسخ داده شد")
                return reply_count

            except Exception as e:
                logger.error(f"خطا در دریافت نشست‌های پیام: {str(e)}")
                return 0

        except Exception as e:
            logger.error(f"خطا در پاسخ به پیام‌های دریافتی: {str(e)}")
            return 0

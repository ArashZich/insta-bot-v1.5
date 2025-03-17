from instagrapi import Client
from instagrapi.exceptions import ClientError
from sqlalchemy.orm import Session
from datetime import datetime
import random

from app.utils.logger import get_logger
from app.database.models import User, Interaction, InteractionType
from app.bot.activity import ActivityManager

logger = get_logger("direct")


class DirectMessageManager:
    def __init__(self, db: Session, client: Client, activity_manager: ActivityManager):
        self.db = db
        self.client = client
        self.activity_manager = activity_manager
        self.message_templates = [
            "سلام! پست‌هات خیلی جالبه 👋",
            "سلام، از محتوای پیج‌ات خوشم اومد 👌",
            "درود! از آشنایی با شما خوشحالم ✨",
            "سلام! می‌تونیم تبادل نظر داشته باشیم 🤝",
            "سلام، پروفایلت برام جالب بود 👍",
            "درود! محتوای خوبی داری 💯",
            "سلام! چقدر پست‌های خوبی داری 🌟"
        ]

    def get_random_message(self):
        """انتخاب یک پیام تصادفی از قالب‌ها"""
        return random.choice(self.message_templates)

    async def send_direct_message(self, user_id=None, username=None, text=None):
        """ارسال پیام مستقیم به یک کاربر"""
        if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
            logger.info("محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
            return False

        if not self.activity_manager.is_working_hours():
            logger.info("خارج از ساعات کاری است")
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

        if not text:
            text = self.get_random_message()

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

        except ClientError as e:
            logger.error(
                f"خطای کلاینت در ارسال پیام به کاربر {username or user_id}: {str(e)}")
            return False
        except Exception as e:
            logger.error(
                f"خطا در ارسال پیام به کاربر {username or user_id}: {str(e)}")
            self.db.rollback()
            return False

    async def send_welcome_message_to_new_followers(self, max_messages=5):
        """ارسال پیام خوش‌آمدگویی به دنبال‌کنندگان جدید"""
        if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
            logger.info("محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
            return 0

        try:
            # دریافت کاربرانی که به تازگی ما را فالو کرده‌اند و هنوز به آنها پیام نداده‌ایم
            new_followers = self.db.query(User).filter(
                User.is_follower == True,
                ~User.interactions.any(
                    Interaction.type == InteractionType.DIRECT_MESSAGE)
            ).limit(max_messages).all()

            if not new_followers:
                logger.info("هیچ دنبال‌کننده جدیدی برای ارسال پیام یافت نشد")
                return 0

            message_count = 0
            for follower in new_followers:
                # تأخیر تصادفی بین اقدامات
                self.activity_manager.random_delay()

                if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
                    logger.info(
                        "محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
                    break

                welcome_message = f"سلام {follower.full_name or ''}! از اینکه ما را دنبال کردید سپاسگزاریم. خوشحال میشیم با ما در ارتباط باشید! 🌹"

                if await self.send_direct_message(user_id=follower.instagram_id, text=welcome_message):
                    message_count += 1

            logger.info(
                f"{message_count} پیام خوش‌آمدگویی به دنبال‌کنندگان جدید ارسال شد")
            return message_count

        except Exception as e:
            logger.error(
                f"خطا در ارسال پیام خوش‌آمدگویی به دنبال‌کنندگان جدید: {str(e)}")
            return 0

    async def reply_to_direct_messages(self):
        """پاسخ به پیام‌های دریافتی"""
        try:
            # نسخه‌های جدید instagrapi از direct_pending استفاده می‌کنند
            threads = []

            try:
                pending_threads = self.client.direct_pending_inbox()
                threads.extend(pending_threads)
            except Exception as e:
                logger.warning(f"خطا در دریافت پیام‌های معلق: {str(e)}")

            try:
                inbox_threads = self.client.direct_threads()
                threads.extend(inbox_threads)
            except Exception as e:
                logger.warning(f"خطا در دریافت پیام‌های ورودی: {str(e)}")

            logger.info(f"{len(threads)} مکالمه پیام مستقیم یافت شد")

            replied_count = 0
            for thread in threads:
                # بررسی اگر پیام خوانده نشده وجود داشته باشد
                # در برخی نسخه‌ها unread_count متفاوت است یا وجود ندارد
                has_unread = False

                if hasattr(thread, 'unread_count'):
                    has_unread = thread.unread_count > 0
                elif hasattr(thread, 'has_newer'):
                    has_unread = thread.has_newer
                elif hasattr(thread, 'unread'):
                    has_unread = thread.unread
                else:
                    # اگر نتوانستیم وضعیت خوانده شدن را تشخیص دهیم
                    # از روش دیگری استفاده می‌کنیم
                    try:
                        messages = self.client.direct_messages(thread.id)
                        if messages and len(messages) > 0:
                            # فقط آخرین پیام را بررسی می‌کنیم
                            last_message = messages[0]
                            # اگر آخرین پیام از طرف ما نباشد، فرض می‌کنیم خوانده نشده است
                            if hasattr(last_message, 'user_id') and last_message.user_id != self.client.user_id:
                                has_unread = True
                    except Exception as e:
                        logger.warning(
                            f"خطا در دریافت پیام‌های thread: {str(e)}")

                if has_unread:
                    # تأخیر تصادفی بین اقدامات
                    self.activity_manager.random_delay()

                    if not self.activity_manager.can_perform_interaction(InteractionType.DIRECT_MESSAGE):
                        logger.info(
                            "محدودیت پیام مستقیم روزانه به حداکثر رسیده است")
                        break

                    # دریافت پیام‌های thread
                    try:
                        messages = self.client.direct_messages(thread.id)
                    except Exception as e:
                        logger.warning(
                            f"خطا در دریافت پیام‌های thread: {str(e)}")
                        continue

                    # اگر پیام وجود داشته باشد و از طرف کاربر دیگر باشد
                    if messages and len(messages) > 0 and hasattr(messages[0], 'user_id') and messages[0].user_id != self.client.user_id:
                        reply_text = "ممنون از پیام شما! به زودی پاسخ می‌دهیم. 🙏"

                        # ارسال پاسخ - ابتدا با direct_answer امتحان می‌کنیم
                        result = False
                        try:
                            if hasattr(self.client, 'direct_answer'):
                                result = self.client.direct_answer(
                                    thread.id, reply_text)
                            else:
                                result = self.client.direct_send(
                                    reply_text, thread_ids=[thread.id])
                        except Exception as e:
                            logger.warning(
                                f"خطا در ارسال پاسخ با روش اول: {str(e)}")
                            # تلاش با روش دوم
                            try:
                                result = self.client.direct_send(
                                    reply_text, thread_ids=[thread.id])
                            except Exception as e:
                                logger.warning(
                                    f"خطا در ارسال پاسخ با روش دوم: {str(e)}")

                        if result:
                            replied_count += 1
                            logger.info(
                                f"پاسخ به پیام دریافتی در thread {thread.id} ارسال شد")

                            # بروزرسانی شمارنده‌های فعالیت
                            self.activity_manager.update_bot_status_activity(
                                InteractionType.DIRECT_MESSAGE)

            logger.info(f"به {replied_count} پیام دریافتی پاسخ داده شد")
            return replied_count

        except Exception as e:
            logger.error(f"خطا در پاسخ به پیام‌های دریافتی: {str(e)}")
            # برای مدیریت خطای AttributeError (نسخه‌های متفاوت instagrapi)
            try:
                # روش جایگزین ساده‌تر
                logger.info("تلاش با روش جایگزین برای پاسخ به پیام‌ها")
                threads = []

                try:
                    threads = self.client.direct_threads()
                except Exception as e:
                    logger.warning(
                        f"خطا در دریافت پیام‌ها با روش جایگزین: {str(e)}")
                    return 0

                replied_count = 0
                for thread in threads:
                    try:
                        thread_id = thread.id if hasattr(
                            thread, 'id') else None
                        if not thread_id:
                            continue

                        messages = self.client.direct_messages(thread_id)
                        if messages and len(messages) > 0:
                            last_message = messages[0]
                            # بررسی اینکه آیا آخرین پیام از طرف ما نیست
                            if hasattr(last_message, 'user_id') and last_message.user_id != self.client.user_id:
                                reply_text = "ممنون از پیام شما! به زودی پاسخ می‌دهیم. 🙏"
                                result = self.client.direct_send(
                                    reply_text, thread_ids=[thread_id])

                                if result:
                                    replied_count += 1
                                    logger.info(
                                        f"پاسخ به پیام دریافتی در thread {thread_id} ارسال شد")
                                    self.activity_manager.update_bot_status_activity(
                                        InteractionType.DIRECT_MESSAGE)
                    except Exception as e:
                        logger.warning(
                            f"خطا در پردازش thread جایگزین: {str(e)}")
                        continue

                return replied_count
            except Exception as e:
                logger.error(f"خطا در روش جایگزین: {str(e)}")
                return 0

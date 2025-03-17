import os
import random
from app.config import BOT_CONFIG
from app.utils.logger import get_logger

logger = get_logger("hashtags")


class HashtagManager:
    def __init__(self):
        self.hashtags_file = BOT_CONFIG["hashtags_file"]
        self.hashtags = self._load_hashtags()

    def _load_hashtags(self):
        """بارگذاری هشتگ‌ها از فایل"""
        if not os.path.exists(self.hashtags_file):
            with open(self.hashtags_file, 'w', encoding='utf-8') as f:
                # نوشتن چند هشتگ پیش‌فرض فارسی
                default_hashtags = [
                    "ایران", "تهران", "عکاسی", "طبیعت", "سفر", "گردشگری",
                    "موسیقی", "هنر", "کتاب", "فیلم", "ورزش", "فوتبال",
                    "آشپزی", "غذا", "مد", "زیبایی", "تکنولوژی", "برنامه‌نویسی"
                ]
                f.write('\n'.join(default_hashtags))
            logger.info("فایل هشتگ‌ها ایجاد شد و هشتگ‌های پیش‌فرض اضافه شدند")

        try:
            with open(self.hashtags_file, 'r', encoding='utf-8') as f:
                hashtags = [line.strip()
                            for line in f.readlines() if line.strip()]
            logger.info(f"{len(hashtags)} هشتگ با موفقیت بارگذاری شد")
            return hashtags
        except Exception as e:
            logger.error(f"خطا در بارگذاری هشتگ‌ها: {str(e)}")
            return []

    def get_random_hashtag(self):
        """دریافت یک هشتگ تصادفی"""
        if not self.hashtags:
            return None
        return random.choice(self.hashtags)

    def get_random_hashtags(self, count=5):
        """دریافت چند هشتگ تصادفی"""
        if not self.hashtags:
            return []
        count = min(count, len(self.hashtags))
        return random.sample(self.hashtags, count)

    def add_hashtag(self, hashtag):
        """اضافه کردن هشتگ جدید"""
        if hashtag not in self.hashtags:
            with open(self.hashtags_file, 'a', encoding='utf-8') as f:
                f.write(f"\n{hashtag}")
            self.hashtags.append(hashtag)
            logger.info(f"هشتگ جدید اضافه شد: {hashtag}")
            return True
        return False

    def reload_hashtags(self):
        """بارگذاری مجدد هشتگ‌ها از فایل"""
        self.hashtags = self._load_hashtags()
        return self.hashtags

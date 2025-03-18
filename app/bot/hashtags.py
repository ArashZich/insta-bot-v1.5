import os
import random
import json
from datetime import datetime, timedelta
from app.config import BOT_CONFIG
from app.utils.logger import get_logger

logger = get_logger("hashtags")


class HashtagManager:
    def __init__(self):
        self.hashtags_file = BOT_CONFIG["hashtags_file"]
        self.hashtags_stats_file = str(
            self.hashtags_file).replace('.txt', '_stats.json')
        self.hashtags = []
        self.categories = {}
        self.hashtag_stats = {}
        self.last_used = {}
        self._load_hashtags()
        self._load_stats()

    def _load_hashtags(self):
        """بارگذاری هشتگ‌ها از فایل با پشتیبانی از دسته‌بندی"""
        if not os.path.exists(self.hashtags_file):
            self._create_default_hashtags_file()

        try:
            with open(self.hashtags_file, 'r', encoding='utf-8') as f:
                lines = [line.strip()
                         for line in f.readlines() if line.strip()]

            # خواندن و پردازش خط به خط فایل
            current_category = "عمومی"  # دسته‌بندی پیش‌فرض
            self.categories[current_category] = []

            for line in lines:
                # اگر خط با [[ شروع و با ]] تمام شود، این یک دسته‌بندی است
                if line.startswith('[[') and line.endswith(']]'):
                    # استخراج نام دسته‌بندی
                    current_category = line[2:-2].strip()
                    if current_category not in self.categories:
                        self.categories[current_category] = []
                # در غیر این صورت، این یک هشتگ است
                elif line:
                    if not line.startswith('#'):
                        line = '#' + line  # اضافه کردن # اگر نداشته باشد

                    hashtag = line.strip()
                    self.hashtags.append(hashtag)
                    self.categories[current_category].append(hashtag)

            logger.info(
                f"{len(self.hashtags)} هشتگ در {len(self.categories)} دسته‌بندی با موفقیت بارگذاری شد")
            return self.hashtags
        except Exception as e:
            logger.error(f"خطا در بارگذاری هشتگ‌ها: {str(e)}")
            self._create_default_hashtags_file()
            return self.hashtags

    def _create_default_hashtags_file(self):
        """ایجاد فایل هشتگ‌های پیش‌فرض با دسته‌بندی"""
        try:
            with open(self.hashtags_file, 'w', encoding='utf-8') as f:
                # ایجاد دسته‌بندی‌های مختلف با هشتگ‌های مرتبط
                f.write("[[عمومی]]\n")
                f.write("#ایران\n#تهران\n#زندگی\n#عکس\n#ایرانی\n#دوستان\n#خاطرات\n")

                f.write("\n[[غذا و آشپزی]]\n")
                f.write(
                    "#غذا\n#آشپزی\n#دستپخت\n#رستوران\n#کافه\n#شیرینی\n#دسر\n#صبحانه\n#ناهار\n#شام\n")

                f.write("\n[[سفر و گردشگری]]\n")
                f.write(
                    "#سفر\n#گردشگری\n#طبیعت\n#طبیعتگردی\n#ایرانگردی\n#جهانگردی\n#تور\n#مسافرت\n")

                f.write("\n[[هنر و فرهنگ]]\n")
                f.write(
                    "#هنر\n#نقاشی\n#موسیقی\n#سینما\n#فیلم\n#کتاب\n#خوشنویسی\n#عکاسی\n#تئاتر\n")

                f.write("\n[[ورزش و سلامتی]]\n")
                f.write(
                    "#ورزش\n#فوتبال\n#بسکتبال\n#یوگا\n#بدنسازی\n#فیتنس\n#سلامتی\n#تغذیه\n")

                f.write("\n[[مد و زیبایی]]\n")
                f.write(
                    "#مد\n#فشن\n#لباس\n#استایل\n#زیبایی\n#آرایش\n#مو\n#اکسسوری\n")

                f.write("\n[[تکنولوژی]]\n")
                f.write(
                    "#تکنولوژی\n#فناوری\n#موبایل\n#لپتاپ\n#گیمینگ\n#گیم\n#اپلیکیشن\n#دیجیتال\n")

                f.write("\n[[کسب و کار]]\n")
                f.write(
                    "#کسب_و_کار\n#استارتاپ\n#کارآفرینی\n#موفقیت\n#بیزینس\n#مدیریت\n#بازاریابی\n")

            logger.info("فایل هشتگ‌های پیش‌فرض با دسته‌بندی ایجاد شد")

            # بازخوانی هشتگ‌ها
            self._load_hashtags()
        except Exception as e:
            logger.error(f"خطا در ایجاد فایل هشتگ‌های پیش‌فرض: {str(e)}")
            # ایجاد لیست‌های پیش‌فرض در حافظه
            self.hashtags = ["#ایران", "#تهران", "#عکاسی", "#طبیعت", "#سفر", "#گردشگری",
                             "#موسیقی", "#هنر", "#کتاب", "#فیلم", "#ورزش", "#فوتبال",
                             "#آشپزی", "#غذا", "#مد", "#زیبایی", "#تکنولوژی", "#برنامه‌نویسی"]
            self.categories = {"عمومی": self.hashtags}

    def _load_stats(self):
        """بارگذاری آمار استفاده از هشتگ‌ها"""
        try:
            if os.path.exists(self.hashtags_stats_file):
                with open(self.hashtags_stats_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.hashtag_stats = data.get('stats', {})

                    # تبدیل تاریخ‌های ذخیره شده به فرمت datetime
                    self.last_used = {}
                    for hashtag, date_str in data.get('last_used', {}).items():
                        try:
                            self.last_used[hashtag] = datetime.fromisoformat(
                                date_str)
                        except:
                            # اگر تبدیل ناموفق باشد، تاریخ فعلی را استفاده می‌کنیم
                            self.last_used[hashtag] = datetime.now()

                logger.info(
                    f"آمار {len(self.hashtag_stats)} هشتگ با موفقیت بارگذاری شد")
            else:
                logger.info(
                    "فایل آمار هشتگ‌ها یافت نشد، آمار جدیدی ایجاد می‌شود")
                self.hashtag_stats = {
                    hashtag: {"success": 0, "fail": 0} for hashtag in self.hashtags}
                self.last_used = {hashtag: datetime.now() - timedelta(days=7)
                                  for hashtag in self.hashtags}
                self._save_stats()
        except Exception as e:
            logger.error(f"خطا در بارگذاری آمار هشتگ‌ها: {str(e)}")
            # ایجاد آمار پیش‌فرض
            self.hashtag_stats = {hashtag: {"success": 0, "fail": 0}
                                  for hashtag in self.hashtags}
            self.last_used = {hashtag: datetime.now() - timedelta(days=7)
                              for hashtag in self.hashtags}

    def _save_stats(self):
        """ذخیره آمار استفاده از هشتگ‌ها"""
        try:
            # تبدیل تاریخ‌ها به رشته برای ذخیره در JSON
            last_used_str = {}
            for hashtag, date in self.last_used.items():
                last_used_str[hashtag] = date.isoformat()

            data = {
                'stats': self.hashtag_stats,
                'last_used': last_used_str
            }

            with open(self.hashtags_stats_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)

            logger.debug("آمار هشتگ‌ها با موفقیت ذخیره شد")
        except Exception as e:
            logger.error(f"خطا در ذخیره آمار هشتگ‌ها: {str(e)}")

    def get_random_hashtag(self, category=None):
        """دریافت یک هشتگ تصادفی با اولویت‌بندی هوشمند"""
        if not self.hashtags:
            logger.warning("هیچ هشتگی یافت نشد")
            return None

        # اگر دسته‌بندی مشخص شده باشد
        if category and category in self.categories:
            available_hashtags = self.categories[category]
            if not available_hashtags:
                logger.warning(f"هیچ هشتگی در دسته‌بندی {category} یافت نشد")
                return self.get_random_hashtag()  # استفاده از روش عمومی
        else:
            available_hashtags = self.hashtags

        # اولویت‌بندی هشتگ‌ها
        weighted_hashtags = []
        now = datetime.now()

        for hashtag in available_hashtags:
            # محاسبه وزن براساس موفقیت قبلی و زمان آخرین استفاده
            success_rate = 0.5  # نرخ پیش‌فرض
            if hashtag in self.hashtag_stats:
                total = self.hashtag_stats[hashtag]["success"] + \
                    self.hashtag_stats[hashtag]["fail"]
                if total > 0:
                    success_rate = self.hashtag_stats[hashtag]["success"] / total

            # محاسبه روزهای گذشته از آخرین استفاده
            days_since_last_use = 7  # پیش‌فرض 7 روز
            if hashtag in self.last_used:
                days_since_last_use = (now - self.last_used[hashtag]).days
                if days_since_last_use < 0:
                    days_since_last_use = 0

            # وزن نهایی: ترکیبی از نرخ موفقیت و زمان آخرین استفاده
            # هشتگ‌هایی که موفق‌تر بوده‌اند و مدت بیشتری استفاده نشده‌اند، وزن بیشتری دارند
            weight = (0.7 * success_rate) + \
                (0.3 * min(days_since_last_use / 7, 1))

            # افزودن به لیست با وزن محاسبه شده
            weighted_hashtags.append((hashtag, weight))

        # مرتب‌سازی براساس وزن (نزولی)
        weighted_hashtags.sort(key=lambda x: x[1], reverse=True)

        # انتخاب از میان بهترین هشتگ‌ها
        # حداقل 3، حداکثر 10 یا یک سوم کل
        top_count = max(3, min(10, len(weighted_hashtags) // 3))
        top_hashtags = [h[0] for h in weighted_hashtags[:top_count]]

        # انتخاب تصادفی از میان بهترین‌ها
        selected_hashtag = random.choice(top_hashtags)

        # بروزرسانی زمان آخرین استفاده
        self.last_used[selected_hashtag] = now
        self._save_stats()

        logger.info(f"هشتگ انتخاب شده: {selected_hashtag}")
        return selected_hashtag

    def get_random_hashtags(self, count=3, category=None):
        """دریافت چند هشتگ تصادفی با اولویت‌بندی هوشمند"""
        if not self.hashtags:
            logger.warning("هیچ هشتگی یافت نشد")
            return []

        # اگر دسته‌بندی مشخص شده باشد
        if category and category in self.categories:
            available_hashtags = self.categories[category]
            if not available_hashtags:
                logger.warning(f"هیچ هشتگی در دسته‌بندی {category} یافت نشد")
                return self.get_random_hashtags(count)  # استفاده از روش عمومی
        else:
            available_hashtags = self.hashtags

        count = min(count, len(available_hashtags))

        # انتخاب چند هشتگ متمایز
        selected_hashtags = []
        for _ in range(count):
            # استفاده از روش اولویت‌بندی تکی برای هر انتخاب
            remaining_hashtags = [
                h for h in available_hashtags if h not in selected_hashtags]
            if not remaining_hashtags:
                break

            # یک هشتگ با روش اولویت‌بندی انتخاب می‌کنیم
            hashtag = self.get_random_hashtag(category)

            # اگر تصادفاً هشتگ تکراری انتخاب شد، یک هشتگ دیگر انتخاب می‌کنیم
            if hashtag in selected_hashtags:
                remaining_hashtags = [
                    h for h in available_hashtags if h not in selected_hashtags]
                if remaining_hashtags:
                    hashtag = random.choice(remaining_hashtags)
                else:
                    break

            selected_hashtags.append(hashtag)

        logger.info(
            f"{len(selected_hashtags)} هشتگ انتخاب شدند: {', '.join(selected_hashtags)}")
        return selected_hashtags

    def add_hashtag(self, hashtag, category="عمومی"):
        """اضافه کردن هشتگ جدید به دسته‌بندی مشخص"""
        if not hashtag.startswith('#'):
            hashtag = '#' + hashtag  # اضافه کردن # اگر نداشته باشد

        hashtag = hashtag.strip()

        # اطمینان از اینکه دسته‌بندی وجود دارد
        if category not in self.categories:
            self.categories[category] = []

        # بررسی تکراری نبودن هشتگ
        if hashtag not in self.hashtags:
            try:
                # افزودن به فایل
                with open(self.hashtags_file, 'r+', encoding='utf-8') as f:
                    content = f.read()

                    # جستجوی بخش دسته‌بندی
                    category_marker = f'[[{category}]]'
                    if category_marker in content:
                        # افزودن هشتگ بعد از بخش دسته‌بندی
                        parts = content.split(category_marker)
                        # یافتن محل مناسب در بخش دسته‌بندی
                        category_content = parts[1]
                        next_category_pos = category_content.find('[[')
                        if next_category_pos != -1:
                            # افزودن قبل از دسته‌بندی بعدی
                            parts[1] = category_content[:next_category_pos] + \
                                hashtag + '\n' + \
                                category_content[next_category_pos:]
                        else:
                            # افزودن به انتهای بخش دسته‌بندی
                            parts[1] = category_content + hashtag + '\n'

                        content = category_marker.join(parts)
                    else:
                        # افزودن دسته‌بندی جدید به انتهای فایل
                        content += f'\n\n[[{category}]]\n{hashtag}\n'

                    # بازنویسی فایل
                    f.seek(0)
                    f.write(content)
                    f.truncate()

                # افزودن به لیست‌های در حافظه
                self.hashtags.append(hashtag)
                self.categories[category].append(hashtag)

                # ایجاد آمار برای هشتگ جدید
                self.hashtag_stats[hashtag] = {"success": 0, "fail": 0}
                self.last_used[hashtag] = datetime.now() - timedelta(days=7)
                self._save_stats()

                logger.info(
                    f"هشتگ جدید {hashtag} در دسته‌بندی {category} اضافه شد")
                return True
            except Exception as e:
                logger.error(f"خطا در افزودن هشتگ {hashtag}: {str(e)}")
                return False
        else:
            logger.info(f"هشتگ {hashtag} قبلاً وجود دارد")
            return False

    def update_hashtag_stats(self, hashtag, success=True):
        """بروزرسانی آمار موفقیت یا شکست استفاده از هشتگ"""
        if hashtag not in self.hashtag_stats:
            self.hashtag_stats[hashtag] = {"success": 0, "fail": 0}

        if success:
            self.hashtag_stats[hashtag]["success"] += 1
        else:
            self.hashtag_stats[hashtag]["fail"] += 1

        self._save_stats()
        logger.debug(
            f"آمار هشتگ {hashtag} بروزرسانی شد: {'موفق' if success else 'ناموفق'}")

    def get_categories(self):
        """دریافت لیست دسته‌بندی‌های موجود"""
        return list(self.categories.keys())

    def get_hashtags_by_category(self, category):
        """دریافت هشتگ‌های یک دسته‌بندی خاص"""
        if category in self.categories:
            return self.categories[category]
        return []

    def reload_hashtags(self):
        """بارگذاری مجدد هشتگ‌ها از فایل"""
        self._load_hashtags()
        self._load_stats()
        return self.hashtags

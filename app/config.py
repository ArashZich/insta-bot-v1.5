import os
from dotenv import load_dotenv
import pathlib

# Load .env file
load_dotenv()

# Base paths
BASE_DIR = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"

# Ensure directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "postgres"),
    "port": os.getenv("DB_PORT", "5432"),
    "user": os.getenv("DB_USER", "instabot"),
    "password": os.getenv("DB_PASSWORD", "instabot_password"),
    "database": os.getenv("DB_NAME", "instabot_db"),
}

# Instagram configuration
INSTAGRAM_CONFIG = {
    "username": os.getenv("INSTA_USERNAME"),
    "password": os.getenv("INSTA_PASSWORD"),
    "session_file": DATA_DIR / "session.json",
}

# Bot behavior configuration - محدودیت‌های بسیار کمتر برای تشخیص نشدن توسط اینستاگرام
BOT_CONFIG = {
    "hashtags_file": DATA_DIR / "hashtags.txt",

    # محدودیت‌های کلی
    "max_interactions_per_day": 50,     # کاهش از 100 به 50

    # محدودیت‌های تعامل
    "max_follows_per_day": 10,          # کاهش از 30 به 10
    "max_unfollows_per_day": 8,         # کاهش از 30 به 8
    "max_comments_per_day": 5,          # کاهش از 15 به 5
    "max_likes_per_day": 25,            # کاهش از 50 به 25
    "max_direct_messages_per_day": 3,   # کاهش از 5 به 3
    "max_story_views_per_day": 25,      # کاهش از 50 به 25

    # تنظیمات تاخیر
    # افزایش از 60 به 120 ثانیه (حداقل 2 دقیقه)
    "min_delay_between_actions": 120,
    # افزایش از 300 به 600 ثانیه (حداکثر 10 دقیقه)
    "max_delay_between_actions": 600,

    # تنظیمات رفتار انسانی
    # حداکثر تعداد اقدامات متوالی قبل از استراحت طولانی
    "max_consecutive_actions": 5,
    "hours_between_extended_rests": 2,  # هر چند ساعت یک استراحت طولانی داشته باشیم

    # ساعات کاری
    "working_hours": {
        "start": 9,                     # ساعت شروع فعالیت (9 صبح)
        "end": 22,                      # ساعت پایان فعالیت (10 شب)
        "weekend_start": 11,            # ساعت شروع در آخر هفته
        "weekend_end": 23               # ساعت پایان در آخر هفته
    }
}

# User agent variations for more natural behavior
USER_AGENTS = [
    # Android devices
    "Instagram 212.0.0.38.119 Android (27/8.1.0; 480dpi; 1080x1920; samsung; SM-G950F; dreamlte; universal8895; en_US; 329675731)",
    "Instagram 195.0.0.31.123 Android (29/10; 420dpi; 1080x2280; OnePlus; OnePlus6T; OnePlus6T; qcom; en_US; 302733750)",
    "Instagram 203.0.0.29.118 Android (26/8.0.0; 640dpi; 1440x2960; samsung; SM-G965F; star2lte; universal9810; en_US; 314665256)",

    # iOS devices
    "Instagram 187.0.0.32.120 (iPhone12,1; iOS 14_4_2; en_US; en-US; scale=2.00; 828x1792; 289335886)"
]

# API Configuration
API_CONFIG = {
    "title": "Instagram Bot API",
    "description": "API برای مدیریت و نظارت بر بات اینستاگرام",
    "version": "1.0.0",
}

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

# Logging original configuration variables to debug
print(f"DB_CONFIG from environment: {DB_CONFIG}")

# Instagram configuration
INSTAGRAM_CONFIG = {
    "username": os.getenv("INSTA_USERNAME"),
    "password": os.getenv("INSTA_PASSWORD"),
    "session_file": DATA_DIR / "session.json",
}

# Bot behavior configuration
BOT_CONFIG = {
    "hashtags_file": DATA_DIR / "hashtags.txt",
    "max_interactions_per_day": 100,     # کاهش از 150 به 100
    "max_follows_per_day": 30,          # کاهش از 50 به 30
    "max_unfollows_per_day": 30,        # کاهش از 50 به 30
    "max_comments_per_day": 15,         # کاهش از 20 به 15
    "max_likes_per_day": 50,            # کاهش از 80 به 50
    "max_direct_messages_per_day": 5,   # کاهش از 10 به 5
    "max_story_views_per_day": 50,      # کاهش از 100 به 50
    "min_delay_between_actions": 60,    # افزایش از 30 به 60 ثانیه
    "max_delay_between_actions": 300,   # افزایش از 180 به 300 ثانیه
    "working_hours": {
        "start": 8,  # ساعت شروع فعالیت (8 صبح)
        "end": 23,   # ساعت پایان فعالیت (11 شب)
    }
}

# API Configuration
API_CONFIG = {
    "title": "Instagram Bot API",
    "description": "API برای مدیریت و نظارت بر بات اینستاگرام",
    "version": "1.0.0",
}

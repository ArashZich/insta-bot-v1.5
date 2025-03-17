from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, ForeignKey, Enum, Text
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.database.db import Base


class InteractionType(enum.Enum):
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    LIKE = "like"
    COMMENT = "comment"
    DIRECT_MESSAGE = "direct_message"
    STORY_VIEW = "story_view"
    STORY_REACTION = "story_reaction"


class User(Base):
    """مدل برای ذخیره اطلاعات کاربران اینستاگرام"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    instagram_id = Column(String(50), unique=True, index=True)
    username = Column(String(50), unique=True, index=True)
    full_name = Column(String(100), nullable=True)
    is_following = Column(Boolean, default=False)
    is_follower = Column(Boolean, default=False)
    follower_since = Column(DateTime, nullable=True)
    following_since = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # ارتباط یک به چند با جدول تعاملات
    interactions = relationship("Interaction", back_populates="user")


class Interaction(Base):
    """مدل برای ذخیره تعاملات با کاربران"""
    __tablename__ = "interactions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    type = Column(Enum(InteractionType))
    content = Column(Text, nullable=True)  # محتوای کامنت یا پیام
    media_id = Column(String(100), nullable=True)  # آیدی پست یا استوری
    status = Column(Boolean, default=True)  # موفقیت‌آمیز بودن تعامل
    created_at = Column(DateTime, default=datetime.now)

    # ارتباط با جدول کاربران
    user = relationship("User", back_populates="interactions")


class BotStatus(Base):
    """مدل برای ذخیره وضعیت بات"""
    __tablename__ = "bot_status"

    id = Column(Integer, primary_key=True)
    is_running = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    last_activity = Column(DateTime, nullable=True)
    follows_today = Column(Integer, default=0)
    unfollows_today = Column(Integer, default=0)
    comments_today = Column(Integer, default=0)
    likes_today = Column(Integer, default=0)
    direct_messages_today = Column(Integer, default=0)
    story_views_today = Column(Integer, default=0)
    story_reactions_today = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    last_error_time = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class DailyStats(Base):
    """مدل برای ذخیره آمار روزانه"""
    __tablename__ = "daily_stats"

    id = Column(Integer, primary_key=True)
    date = Column(DateTime, unique=True, index=True)
    follows = Column(Integer, default=0)
    unfollows = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    direct_messages = Column(Integer, default=0)
    story_views = Column(Integer, default=0)
    story_reactions = Column(Integer, default=0)
    new_followers = Column(Integer, default=0)
    lost_followers = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)

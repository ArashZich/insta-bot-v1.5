from pydantic import BaseModel, Field
from datetime import datetime, date
from typing import List, Optional
from enum import Enum


class InteractionTypeEnum(str, Enum):
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    LIKE = "like"
    COMMENT = "comment"
    DIRECT_MESSAGE = "direct_message"
    STORY_VIEW = "story_view"
    STORY_REACTION = "story_reaction"


class TimeRangeEnum(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    SIX_MONTHS = "six_months"
    YEARLY = "yearly"


class DateRangeRequest(BaseModel):
    start_date: date = Field(..., description="تاریخ شروع")
    end_date: date = Field(..., description="تاریخ پایان")
    time_range: Optional[TimeRangeEnum] = Field(
        None, description="بازه زمانی از پیش تعریف شده")


class BotStatusResponse(BaseModel):
    is_running: bool
    last_login: Optional[datetime]
    last_activity: Optional[datetime]
    follows_today: int
    unfollows_today: int
    comments_today: int
    likes_today: int
    direct_messages_today: int
    story_views_today: int
    story_reactions_today: int
    error_count: int
    last_error: Optional[str]
    last_error_time: Optional[datetime]


class StatsItem(BaseModel):
    date: date
    follows: int
    unfollows: int
    comments: int
    likes: int
    direct_messages: int
    story_views: int
    story_reactions: int
    new_followers: int
    lost_followers: int


class StatsResponse(BaseModel):
    data: List[StatsItem]
    total_follows: int
    total_unfollows: int
    total_comments: int
    total_likes: int
    total_direct_messages: int
    total_story_views: int
    total_story_reactions: int
    total_new_followers: int
    total_lost_followers: int


class InteractionItem(BaseModel):
    id: int
    user_id: Optional[int]
    username: Optional[str]
    type: InteractionTypeEnum
    content: Optional[str]
    media_id: Optional[str]
    created_at: datetime


class InteractionsResponse(BaseModel):
    data: List[InteractionItem]
    total: int


class ActionResponse(BaseModel):
    success: bool
    message: str

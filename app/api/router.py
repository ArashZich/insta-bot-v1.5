from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, date
from typing import List, Optional
from enum import Enum

from app.database.db import get_db
from app.database.models import BotStatus, DailyStats, Interaction, User, InteractionType
from app.api.schemas import (
    BotStatusResponse, StatsResponse, InteractionsResponse,
    DateRangeRequest, ActionResponse, InteractionItem
)

# تعریف یک enum برای بازه‌های زمانی


class TimeRange(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"
    six_months = "six_months"
    yearly = "yearly"


router = APIRouter(prefix="/api", tags=["Bot API"])


@router.get("/status", response_model=BotStatusResponse)
async def get_bot_status(db: Session = Depends(get_db)):
    """دریافت وضعیت فعلی بات"""
    status = db.query(BotStatus).first()
    if not status:
        # ایجاد یک رکورد وضعیت خالی اگر وجود نداشته باشد
        status = BotStatus(
            is_running=False,
            follows_today=0,
            unfollows_today=0,
            comments_today=0,
            likes_today=0,
            direct_messages_today=0,
            story_views_today=0,
            story_reactions_today=0,
            error_count=0
        )
        db.add(status)
        db.commit()
        db.refresh(status)

    # تبدیل به دیکشنری برای سازگاری با مدل پاسخ
    return {
        "is_running": status.is_running,
        "last_login": status.last_login,
        "last_activity": status.last_activity,
        "follows_today": status.follows_today,
        "unfollows_today": status.unfollows_today,
        "comments_today": status.comments_today,
        "likes_today": status.likes_today,
        "direct_messages_today": status.direct_messages_today,
        "story_views_today": status.story_views_today,
        "story_reactions_today": status.story_reactions_today,
        "error_count": status.error_count,
        "last_error": status.last_error,
        "last_error_time": status.last_error_time
    }


def calculate_date_range(time_range: TimeRange):
    """محاسبه بازه زمانی براساس گزینه انتخاب شده"""
    end_date = datetime.now().date()

    if time_range == TimeRange.daily:
        start_date = end_date
    elif time_range == TimeRange.weekly:
        start_date = end_date - timedelta(days=7)
    elif time_range == TimeRange.monthly:
        start_date = end_date - timedelta(days=30)
    elif time_range == TimeRange.six_months:
        start_date = end_date - timedelta(days=180)
    elif time_range == TimeRange.yearly:
        start_date = end_date - timedelta(days=365)
    else:
        # پیش‌فرض: هفتگی
        start_date = end_date - timedelta(days=7)

    return start_date, end_date


@router.get("/stats", response_model=StatsResponse)
async def get_stats(
    time_range: TimeRange = Query(TimeRange.weekly, description="بازه زمانی"),
    db: Session = Depends(get_db)
):
    """دریافت آمار بات در بازه زمانی مشخص"""
    # محاسبه بازه زمانی
    start_date, end_date = calculate_date_range(time_range)

    # دریافت داده‌های آماری
    stats = db.query(DailyStats).filter(
        DailyStats.date >= start_date,
        DailyStats.date <= end_date
    ).order_by(DailyStats.date).all()

    # اگر آماری وجود نداشت، یک لیست خالی برمی‌گردانیم
    if not stats:
        return {
            "data": [],
            "total_follows": 0,
            "total_unfollows": 0,
            "total_comments": 0,
            "total_likes": 0,
            "total_direct_messages": 0,
            "total_story_views": 0,
            "total_story_reactions": 0,
            "total_new_followers": 0,
            "total_lost_followers": 0
        }

    # محاسبه مجموع‌ها
    total_follows = sum(stat.follows for stat in stats)
    total_unfollows = sum(stat.unfollows for stat in stats)
    total_comments = sum(stat.comments for stat in stats)
    total_likes = sum(stat.likes for stat in stats)
    total_direct_messages = sum(stat.direct_messages for stat in stats)
    total_story_views = sum(stat.story_views for stat in stats)
    total_story_reactions = sum(stat.story_reactions for stat in stats)
    total_new_followers = sum(stat.new_followers for stat in stats)
    total_lost_followers = sum(stat.lost_followers for stat in stats)

    return {
        "data": stats,
        "total_follows": total_follows,
        "total_unfollows": total_unfollows,
        "total_comments": total_comments,
        "total_likes": total_likes,
        "total_direct_messages": total_direct_messages,
        "total_story_views": total_story_views,
        "total_story_reactions": total_story_reactions,
        "total_new_followers": total_new_followers,
        "total_lost_followers": total_lost_followers
    }


@router.get("/interactions", response_model=InteractionsResponse)
async def get_interactions(
    time_range: TimeRange = Query(TimeRange.weekly, description="بازه زمانی"),
    interaction_type: Optional[str] = Query(None, description="نوع تعامل"),
    page: int = Query(1, ge=1, description="شماره صفحه"),
    limit: int = Query(20, ge=1, le=100, description="تعداد آیتم در هر صفحه"),
    db: Session = Depends(get_db)
):
    """دریافت لیست تعاملات بات در بازه زمانی مشخص"""
    # محاسبه بازه زمانی
    start_date, end_date = calculate_date_range(time_range)

    # تبدیل تاریخ‌ها به datetime
    start_datetime = datetime.combine(start_date, datetime.min.time())
    end_datetime = datetime.combine(end_date, datetime.max.time())

    # آماده‌سازی کوئری
    query = db.query(Interaction).filter(
        Interaction.created_at >= start_datetime,
        Interaction.created_at <= end_datetime
    )

    # فیلتر بر اساس نوع تعامل
    if interaction_type:
        try:
            interaction_enum = InteractionType[interaction_type.upper()]
            query = query.filter(Interaction.type == interaction_enum)
        except KeyError:
            raise HTTPException(
                status_code=400, detail=f"نوع تعامل نامعتبر: {interaction_type}")

    # شمارش کل آیتم‌ها
    total = query.count()

    # اگر تعاملی وجود نداشت، یک لیست خالی برمی‌گردانیم
    if total == 0:
        return {
            "data": [],
            "total": 0
        }

    # اعمال صفحه‌بندی
    offset = (page - 1) * limit
    interactions = query.order_by(
        Interaction.created_at.desc()).offset(offset).limit(limit).all()

    # آماده‌سازی پاسخ
    result_data = []
    for interaction in interactions:
        username = None
        if interaction.user:
            username = interaction.user.username

        item = {
            "id": interaction.id,
            "user_id": interaction.user_id,
            "username": username,
            "type": interaction.type.value,
            "content": interaction.content,
            "media_id": interaction.media_id,
            "created_at": interaction.created_at
        }
        result_data.append(item)

    return {
        "data": result_data,
        "total": total
    }


@router.get("/followers", response_model=dict)
async def get_followers(
    page: int = Query(1, ge=1, description="شماره صفحه"),
    limit: int = Query(20, ge=1, le=100, description="تعداد آیتم در هر صفحه"),
    db: Session = Depends(get_db)
):
    """دریافت لیست دنبال‌کنندگان"""
    # آماده‌سازی کوئری
    query = db.query(User).filter(User.is_follower == True)

    # شمارش کل آیتم‌ها
    total = query.count()

    # اعمال صفحه‌بندی
    offset = (page - 1) * limit
    followers = query.order_by(User.follower_since.desc()).offset(
        offset).limit(limit).all()

    # آماده‌سازی پاسخ
    result_data = []
    for follower in followers:
        # دریافت آخرین تعامل با این کاربر
        last_interaction = db.query(Interaction).filter(
            Interaction.user_id == follower.id
        ).order_by(Interaction.created_at.desc()).first()

        interaction_type = None
        interaction_date = None
        if last_interaction:
            interaction_type = last_interaction.type.value
            interaction_date = last_interaction.created_at

        item = {
            "id": follower.id,
            "username": follower.username,
            "full_name": follower.full_name,
            "follower_since": follower.follower_since,
            "is_following": follower.is_following,
            "last_interaction_type": interaction_type,
            "last_interaction_date": interaction_date
        }
        result_data.append(item)

    return {
        "data": result_data,
        "total": total
    }


@router.get("/following", response_model=dict)
async def get_following(
    page: int = Query(1, ge=1, description="شماره صفحه"),
    limit: int = Query(20, ge=1, le=100, description="تعداد آیتم در هر صفحه"),
    db: Session = Depends(get_db)
):
    """دریافت لیست افرادی که بات آنها را دنبال می‌کند"""
    # آماده‌سازی کوئری
    query = db.query(User).filter(User.is_following == True)

    # شمارش کل آیتم‌ها
    total = query.count()

    # اعمال صفحه‌بندی
    offset = (page - 1) * limit
    following = query.order_by(User.following_since.desc()).offset(
        offset).limit(limit).all()

    # آماده‌سازی پاسخ
    result_data = []
    for follow in following:
        # دریافت آخرین تعامل با این کاربر
        last_interaction = db.query(Interaction).filter(
            Interaction.user_id == follow.id
        ).order_by(Interaction.created_at.desc()).first()

        interaction_type = None
        interaction_date = None
        if last_interaction:
            interaction_type = last_interaction.type.value
            interaction_date = last_interaction.created_at

        item = {
            "id": follow.id,
            "username": follow.username,
            "full_name": follow.full_name,
            "following_since": follow.following_since,
            "is_follower": follow.is_follower,
            "last_interaction_type": interaction_type,
            "last_interaction_date": interaction_date
        }
        result_data.append(item)

    return {
        "data": result_data,
        "total": total
    }

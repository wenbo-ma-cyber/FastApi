from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import Settings
from app.service import TopicService


def create_scheduler(service: TopicService, settings: Settings) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    scheduler.add_job(
        service.collect_topics,
        trigger=CronTrigger(
            hour=settings.collect_hour,
            minute=settings.collect_minute,
            timezone=settings.scheduler_timezone,
        ),
        id="daily-ai-hot-topic-collect",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    return scheduler


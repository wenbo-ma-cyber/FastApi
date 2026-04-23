from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from app.collector import RSSCollector
from app.config import Settings
from app.models import CollectionRunRecord, CollectionStats, FeedSource, TopicRecord
from app.repository import TopicRepository

logger = logging.getLogger(__name__)


class TopicService:
    def __init__(
        self,
        settings: Settings,
        repository: TopicRepository,
        collector: RSSCollector,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.collector = collector

    async def collect_topics(self) -> CollectionStats:
        started_at = datetime.now(timezone.utc)
        run_id = self.repository.create_run(
            started_at=started_at,
            requested_sources=len(self.settings.feed_sources),
        )

        try:
            result = await self.collector.collect(self.settings.feed_sources)
            saved_items, updated_items = self.repository.upsert_topics(result.topics)
            stats = CollectionStats(
                started_at=result.started_at,
                finished_at=result.finished_at,
                requested_sources=result.requested_sources,
                successful_sources=result.requested_sources - len(result.failed_sources),
                failed_sources=result.failed_sources,
                fetched_items=len(result.topics),
                saved_items=saved_items,
                updated_items=updated_items,
            )
            status = "success"
            if result.failed_sources and result.topics:
                status = "partial"
            elif result.failed_sources and not result.topics:
                status = "failure"
            self.repository.finish_run(run_id, stats, status)
            return stats
        except Exception:
            logger.exception("collect topics failed")
            failed_at = datetime.now(timezone.utc)
            stats = CollectionStats(
                started_at=started_at,
                finished_at=failed_at,
                requested_sources=len(self.settings.feed_sources),
                successful_sources=0,
                failed_sources=["collector execution failed"],
                fetched_items=0,
                saved_items=0,
                updated_items=0,
            )
            self.repository.finish_run(run_id, stats, "failure")
            raise

    def list_topics(
        self,
        target_date: date | None = None,
        limit: int = 20,
        source: str | None = None,
        tag: str | None = None,
    ) -> list[TopicRecord]:
        return self.repository.list_topics(
            target_date=target_date,
            limit=limit,
            source=source,
            tag=tag,
        )

    def get_latest_run(self) -> CollectionRunRecord | None:
        return self.repository.get_latest_run()

    def list_sources(self) -> list[FeedSource]:
        return self.settings.feed_sources


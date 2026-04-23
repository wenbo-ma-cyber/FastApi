from __future__ import annotations

import asyncio
import json

from app.collector import RSSCollector
from app.config import Settings
from app.repository import TopicRepository
from app.service import TopicService


async def _run_collect() -> None:
    settings = Settings()
    repository = TopicRepository(
        database_path=settings.database_path,
        display_timezone=settings.scheduler_timezone,
    )
    repository.init_db()
    service = TopicService(
        settings=settings,
        repository=repository,
        collector=RSSCollector(settings),
    )
    result = await service.collect_topics()
    print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


def main() -> None:
    asyncio.run(_run_collect())


if __name__ == "__main__":
    main()


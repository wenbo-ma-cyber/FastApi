from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router, public_router
from app.collector import RSSCollector
from app.config import Settings, get_settings
from app.hotspot import AIHotspotService
from app.repository import TopicRepository
from app.scheduler import create_scheduler
from app.service import TopicService


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    repository = TopicRepository(
        database_path=app_settings.database_path,
        display_timezone=app_settings.scheduler_timezone,
    )
    collector = RSSCollector(app_settings)
    ai_hotspot_service = AIHotspotService(app_settings)
    service = TopicService(
        settings=app_settings,
        repository=repository,
        collector=collector,
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        repository.init_db()
        application.state.settings = app_settings
        application.state.topic_service = service
        application.state.ai_hotspot_service = ai_hotspot_service
        application.state.scheduler = None

        if app_settings.scheduler_enabled:
            scheduler = create_scheduler(service, app_settings)
            scheduler.start()
            application.state.scheduler = scheduler

        if app_settings.collect_on_startup:
            await service.collect_topics()

        try:
            yield
        finally:
            scheduler = getattr(application.state, "scheduler", None)
            if scheduler is not None:
                scheduler.shutdown(wait=False)

    application = FastAPI(
        title=app_settings.app_name,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=app_settings.api_prefix)
    application.include_router(public_router)

    @application.get("/")
    def index() -> dict[str, str]:
        return {
            "name": app_settings.app_name,
            "docs": "/docs",
            "health": f"{app_settings.api_prefix}/health",
        }

    return application


app = create_app()

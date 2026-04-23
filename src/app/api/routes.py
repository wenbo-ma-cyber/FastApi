from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Query, Request, status

from app.models import CollectionRunRecord, CollectionStats, FeedSource, TopicRecord
from app.service import TopicService

router = APIRouter()


def _get_service(request: Request) -> TopicService:
    return request.app.state.topic_service


@router.get("/health")
def health_check(request: Request) -> dict[str, str | bool]:
    return {
        "status": "ok",
        "scheduler_enabled": request.app.state.settings.scheduler_enabled,
    }


@router.get("/topics", response_model=list[TopicRecord])
def list_topics(
    request: Request,
    target_date: date | None = Query(default=None, alias="date"),
    limit: int = Query(default=20, ge=1, le=100),
    source: str | None = Query(default=None),
    tag: str | None = Query(default=None),
) -> list[TopicRecord]:
    service = _get_service(request)
    return service.list_topics(
        target_date=target_date,
        limit=limit,
        source=source,
        tag=tag,
    )


@router.post("/collect", response_model=CollectionStats, status_code=status.HTTP_202_ACCEPTED)
async def collect_topics(request: Request) -> CollectionStats:
    service = _get_service(request)
    return await service.collect_topics()


@router.get("/runs/latest", response_model=CollectionRunRecord | None)
def latest_run(request: Request) -> CollectionRunRecord | None:
    return _get_service(request).get_latest_run()


@router.get("/sources", response_model=list[FeedSource])
def list_sources(request: Request) -> list[FeedSource]:
    return _get_service(request).list_sources()


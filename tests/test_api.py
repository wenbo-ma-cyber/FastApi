from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from app.models import CollectionStats, TopicCreate
from app.config import Settings


def test_list_topics_returns_saved_records(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "topics.db",
        scheduler_enabled=False,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        service = app.state.topic_service
        service.repository.upsert_topics(
            [
                TopicCreate(
                    source_name="Mock Source",
                    source_url="https://example.com/rss.xml",
                    title="DeepSeek releases a new multimodal model",
                    summary="A new release targets enterprise usage.",
                    link="https://example.com/article",
                    published_at=datetime(2026, 4, 23, 8, 0, tzinfo=timezone.utc),
                    collected_at=datetime(2026, 4, 23, 8, 5, tzinfo=timezone.utc),
                    score=9.6,
                    tags=["china", "multimodal"],
                    dedupe_key="topic-1",
                )
            ]
        )

        response = client.get("/api/v1/topics")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["title"] == "DeepSeek releases a new multimodal model"
    assert payload[0]["tags"] == ["china", "multimodal"]


def test_collect_endpoint_uses_service_result(tmp_path) -> None:
    settings = Settings(
        database_path=tmp_path / "collect.db",
        scheduler_enabled=False,
    )
    app = create_app(settings)

    with TestClient(app) as client:
        async def fake_collect() -> CollectionStats:
            return CollectionStats(
                started_at=datetime(2026, 4, 23, 0, 0, tzinfo=timezone.utc),
                finished_at=datetime(2026, 4, 23, 0, 1, tzinfo=timezone.utc),
                requested_sources=4,
                successful_sources=4,
                failed_sources=[],
                fetched_items=12,
                saved_items=10,
                updated_items=2,
            )

        app.state.topic_service.collect_topics = fake_collect
        response = client.post("/api/v1/collect")

    assert response.status_code == 202
    payload = response.json()
    assert payload["saved_items"] == 10
    assert payload["updated_items"] == 2

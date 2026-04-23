from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class FeedSource(BaseModel):
    name: str
    url: str
    category: str = "news"
    weight: float = 1.0


class TopicCreate(BaseModel):
    source_name: str
    source_url: str
    title: str
    summary: str = ""
    link: str
    published_at: datetime
    collected_at: datetime
    score: float = 0.0
    tags: list[str] = Field(default_factory=list)
    dedupe_key: str


class TopicRecord(BaseModel):
    id: int
    source_name: str
    source_url: str
    title: str
    summary: str = ""
    link: str
    published_at: datetime
    collected_at: datetime
    score: float = 0.0
    tags: list[str] = Field(default_factory=list)


class CollectorResult(BaseModel):
    started_at: datetime
    finished_at: datetime
    requested_sources: int
    topics: list[TopicCreate] = Field(default_factory=list)
    source_item_counts: dict[str, int] = Field(default_factory=dict)
    failed_sources: list[str] = Field(default_factory=list)


class CollectionStats(BaseModel):
    started_at: datetime
    finished_at: datetime
    requested_sources: int
    successful_sources: int
    failed_sources: list[str] = Field(default_factory=list)
    fetched_items: int
    saved_items: int
    updated_items: int


class CollectionRunRecord(CollectionStats):
    id: int
    status: str


class AIHotspotItem(BaseModel):
    title: str
    link: str
    published_at: datetime


class AIHotspotSummaryResponse(BaseModel):
    date: str
    timezone: str
    source_name: str
    source_url: str
    model: str
    summary_titles: list[str] = Field(default_factory=list)
    items: list[AIHotspotItem] = Field(default_factory=list)

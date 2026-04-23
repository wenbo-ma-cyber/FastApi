from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.models import FeedSource

DEFAULT_FEEDS = [
    {
        "name": "Google News AI",
        "url": "https://news.google.com/rss/search?q=artificial+intelligence+OR+OpenAI+OR+Anthropic+OR+DeepMind&hl=en-US&gl=US&ceid=US:en",
        "category": "news",
        "weight": 1.3,
    },
    {
        "name": "Google News LLM",
        "url": "https://news.google.com/rss/search?q=large+language+model+OR+AI+agent+OR+GPT+OR+Claude+OR+Gemini&hl=en-US&gl=US&ceid=US:en",
        "category": "news",
        "weight": 1.2,
    },
    {
        "name": "TechCrunch AI",
        "url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "category": "media",
        "weight": 1.15,
    },
    {
        "name": "Hacker News AI",
        "url": "https://hnrss.org/newest?q=OpenAI+OR+Anthropic+OR+AI+OR+LLM",
        "category": "community",
        "weight": 1.0,
    },
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="AI_HOT_",
        extra="ignore",
    )

    app_name: str = "AI Daily Hot Topics"
    api_prefix: str = "/api/v1"
    database_path: Path = Path("data/ai_hot_topics.db")
    request_timeout_seconds: float = 12.0
    max_items_per_source: int = 20
    scheduler_enabled: bool = True
    collect_on_startup: bool = False
    collect_hour: int = 8
    collect_minute: int = 0
    scheduler_timezone: str = "Asia/Shanghai"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.4"
    openai_request_timeout_seconds: float = 30.0
    hotspot_source_name: str = "Google News AI"
    hotspot_source_url: str = DEFAULT_FEEDS[0]["url"]
    hotspot_max_items: int = 8
    feed_sources: list[FeedSource] = Field(
        default_factory=lambda: [FeedSource(**item) for item in DEFAULT_FEEDS]
    )

    @field_validator("feed_sources", mode="before")
    @classmethod
    def parse_feed_sources(cls, value: Any) -> Any:
        if value in (None, ""):
            return [FeedSource(**item) for item in DEFAULT_FEEDS]
        if isinstance(value, str):
            return json.loads(value)
        return value

    @field_validator("database_path", mode="before")
    @classmethod
    def normalize_database_path(cls, value: Any) -> Path:
        return Path(value).expanduser()

    @field_validator("openai_api_key", mode="before")
    @classmethod
    def resolve_openai_api_key(cls, value: Any) -> str | None:
        if value not in (None, ""):
            return str(value)
        return os.getenv("OPENAI_API_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()

from __future__ import annotations

import asyncio
import hashlib
import html
import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from app.config import Settings
from app.models import CollectorResult, FeedSource, TopicCreate

logger = logging.getLogger(__name__)

TAG_KEYWORDS = {
    "openai": ("openai", "gpt", "chatgpt"),
    "anthropic": ("anthropic", "claude"),
    "google": ("google", "gemini", "deepmind"),
    "meta": ("meta", "llama"),
    "agents": ("agent", "agents", "智能体"),
    "multimodal": ("multimodal", "vision", "video", "voice"),
    "reasoning": ("reasoning", "推理"),
    "chips": ("nvidia", "gpu", "chip", "inference"),
    "china": ("deepseek", "baidu", "阿里", "腾讯", "字节"),
    "research": ("paper", "research", "benchmark", "arxiv"),
}


class RSSCollector:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def collect(self, sources: list[FeedSource]) -> CollectorResult:
        started_at = datetime.now(timezone.utc)
        async with self._maybe_managed_client() as client:
            tasks = [self._collect_source(client, source) for source in sources]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        topics: list[TopicCreate] = []
        source_item_counts: dict[str, int] = {}
        failed_sources: list[str] = []

        for source, result in zip(sources, results, strict=True):
            if isinstance(result, Exception):
                logger.warning("collect source failed: %s: %s", source.name, result)
                failed_sources.append(f"{source.name}: {result}")
                source_item_counts[source.name] = 0
                continue
            topics.extend(result)
            source_item_counts[source.name] = len(result)

        finished_at = datetime.now(timezone.utc)
        return CollectorResult(
            started_at=started_at,
            finished_at=finished_at,
            requested_sources=len(sources),
            topics=topics,
            source_item_counts=source_item_counts,
            failed_sources=failed_sources,
        )

    async def _collect_source(
        self, client: httpx.AsyncClient, source: FeedSource
    ) -> list[TopicCreate]:
        response = await client.get(
            source.url,
            headers={"User-Agent": "ai-hot-topics-bot/0.1"},
        )
        response.raise_for_status()
        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise ValueError("feed parse failed")

        collected_at = datetime.now(timezone.utc)
        topics: list[TopicCreate] = []
        for entry in parsed.entries[: self.settings.max_items_per_source]:
            topic = self._entry_to_topic(source, entry, collected_at)
            if topic is not None:
                topics.append(topic)
        return topics

    def _entry_to_topic(
        self,
        source: FeedSource,
        entry: Any,
        collected_at: datetime,
    ) -> TopicCreate | None:
        title = self._clean_text(getattr(entry, "title", ""))
        link = self._canonicalize_url(getattr(entry, "link", ""))
        if not title or not link:
            return None

        raw_summary = getattr(entry, "summary", "") or getattr(entry, "description", "")
        summary = self._truncate_text(self._clean_text(raw_summary), max_length=320)
        published_at = self._parse_datetime(entry)
        tags = self._extract_tags(title, summary)
        score = self._score_topic(title, summary, published_at, source.weight)
        dedupe_key = self._build_dedupe_key(title, link)

        return TopicCreate(
            source_name=source.name,
            source_url=source.url,
            title=title,
            summary=summary,
            link=link,
            published_at=published_at,
            collected_at=collected_at,
            score=score,
            tags=tags,
            dedupe_key=dedupe_key,
        )

    def _score_topic(
        self,
        title: str,
        summary: str,
        published_at: datetime,
        source_weight: float,
    ) -> float:
        text = f"{title} {summary}".lower()
        keyword_score = 0.0
        for keywords in TAG_KEYWORDS.values():
            for keyword in keywords:
                if keyword.lower() in text:
                    keyword_score += 1.0

        age_hours = max(
            (datetime.now(timezone.utc) - published_at).total_seconds() / 3600,
            0,
        )
        freshness_score = max(0.0, 24 - min(age_hours, 24)) / 6
        title_bonus = 1.2 if any(token in title.lower() for token in ("ai", "gpt", "llm")) else 0.0
        return round((keyword_score + freshness_score + title_bonus) * source_weight, 2)

    def _extract_tags(self, title: str, summary: str) -> list[str]:
        text = f"{title} {summary}".lower()
        tags = [
            tag
            for tag, keywords in TAG_KEYWORDS.items()
            if any(keyword.lower() in text for keyword in keywords)
        ]
        return sorted(set(tags))

    @staticmethod
    def _clean_text(value: str) -> str:
        if not value:
            return ""
        text = re.sub(r"<[^>]+>", " ", value)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @staticmethod
    def _truncate_text(value: str, max_length: int) -> str:
        if len(value) <= max_length:
            return value
        return value[: max_length - 3].rstrip() + "..."

    @staticmethod
    def _build_dedupe_key(title: str, link: str) -> str:
        payload = f"{title.lower().strip()}::{link}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        if not url:
            return ""
        parsed = urlsplit(url)
        filtered_query = [
            (key, value)
            for key, value in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.startswith("utm_") and key not in {"oc", "gaa_at", "guccounter"}
        ]
        cleaned = parsed._replace(query=urlencode(filtered_query, doseq=True), fragment="")
        return urlunsplit(cleaned).rstrip("/")

    @staticmethod
    def _parse_datetime(entry: Any) -> datetime:
        for attr_name in ("published_parsed", "updated_parsed"):
            parsed = getattr(entry, attr_name, None)
            if parsed:
                return datetime(*parsed[:6], tzinfo=timezone.utc)

        for attr_name in ("published", "updated", "created"):
            raw_value = getattr(entry, attr_name, None)
            if not raw_value:
                continue
            try:
                parsed_dt = parsedate_to_datetime(raw_value)
                if parsed_dt.tzinfo is None:
                    return parsed_dt.replace(tzinfo=timezone.utc)
                return parsed_dt.astimezone(timezone.utc)
            except (TypeError, ValueError):
                continue

        return datetime.now(timezone.utc)

    def _maybe_managed_client(self) -> "_ClientManager":
        return _ClientManager(self._client, self.settings.request_timeout_seconds)


class _ClientManager:
    def __init__(self, client: httpx.AsyncClient | None, timeout_seconds: float) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._owned_client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        self._owned_client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=self._timeout_seconds,
        )
        return self._owned_client

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._owned_client is not None:
            await self._owned_client.aclose()

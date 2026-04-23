from __future__ import annotations

import html
import json
import re
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import feedparser
import requests

from app.config import Settings
from app.models import AIHotspotItem, AIHotspotSummaryResponse


class HotspotServiceError(Exception):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class AIHotspotService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def scrape_ai_hotspot(self) -> AIHotspotSummaryResponse:
        local_zone = ZoneInfo(self.settings.scheduler_timezone)
        target_date = self._current_local_date(local_zone)
        items = self._fetch_today_items(target_date, local_zone)
        summary_titles = self._summarize_titles(target_date, items)
        return AIHotspotSummaryResponse(
            date=target_date.isoformat(),
            timezone=self.settings.scheduler_timezone,
            source_name=self.settings.hotspot_source_name,
            source_url=self.settings.hotspot_source_url,
            model=self.settings.openai_model,
            summary_titles=summary_titles,
            items=items,
        )

    def _fetch_today_items(
        self,
        target_date: date,
        local_zone: ZoneInfo,
    ) -> list[AIHotspotItem]:
        try:
            response = requests.get(
                self.settings.hotspot_source_url,
                headers={"User-Agent": "ai-hot-topics-bot/0.1"},
                timeout=self.settings.request_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise HotspotServiceError(
                f"Failed to fetch hotspot RSS from {self.settings.hotspot_source_url}: {exc}",
                status_code=502,
            ) from exc

        parsed = feedparser.parse(response.content)
        if getattr(parsed, "bozo", False) and not parsed.entries:
            raise HotspotServiceError("Failed to parse hotspot RSS feed", status_code=502)

        seen_links: set[str] = set()
        items: list[AIHotspotItem] = []
        for entry in parsed.entries:
            title = self._clean_text(getattr(entry, "title", ""))
            link = self._canonicalize_url(getattr(entry, "link", ""))
            if not title or not link or link in seen_links:
                continue

            published_at = self._parse_datetime(entry)
            if published_at.astimezone(local_zone).date() != target_date:
                continue

            items.append(
                AIHotspotItem(
                    title=title,
                    link=link,
                    published_at=published_at,
                )
            )
            seen_links.add(link)

            if len(items) >= self.settings.hotspot_max_items:
                break

        if not items:
            raise HotspotServiceError(
                f"No AI hotspot items found for {target_date.isoformat()}",
                status_code=404,
            )

        return items

    def _summarize_titles(
        self,
        target_date: date,
        items: list[AIHotspotItem],
    ) -> list[str]:
        if not self.settings.openai_api_key:
            raise HotspotServiceError(
                "OPENAI_API_KEY is not configured",
                status_code=503,
            )

        hotspot_lines = []
        for index, item in enumerate(items, start=1):
            hotspot_lines.append(
                f"{index}. 标题：{item.title}\n"
                f"链接：{item.link}\n"
                f"发布时间：{item.published_at.isoformat()}"
            )

        payload = {
            "model": self.settings.openai_model,
            "instructions": (
                "你是一名 AI 行业编辑。"
                "请根据给定的今日 AI 热点材料，总结成 3 条中文标题。"
                "标题必须简洁、准确、信息密度高，不得编造材料中没有的信息。"
            ),
            "input": (
                f"日期：{target_date.isoformat()}\n"
                "下面是今天抓取到的 AI 热点，请整合成 3 条中文标题：\n\n"
                + "\n\n".join(hotspot_lines)
            ),
            "reasoning": {"effort": "low"},
            "max_output_tokens": 300,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "ai_hotspot_headlines",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "titles": {
                                "type": "array",
                                "items": {"type": "string"},
                                "minItems": 3,
                                "maxItems": 3,
                            }
                        },
                        "required": ["titles"],
                        "additionalProperties": False,
                    },
                }
            },
        }

        try:
            response = requests.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {self.settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self.settings.openai_request_timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise HotspotServiceError(
                f"Failed to summarize AI hotspots with OpenAI: {exc}",
                status_code=502,
            ) from exc

        data = response.json()
        output_text = data.get("output_text") or self._extract_output_text(data)
        if not output_text:
            raise HotspotServiceError("OpenAI response did not contain output_text", status_code=502)

        try:
            parsed = json.loads(output_text)
        except json.JSONDecodeError as exc:
            raise HotspotServiceError("OpenAI response was not valid JSON", status_code=502) from exc

        titles = parsed.get("titles")
        if not isinstance(titles, list):
            raise HotspotServiceError("OpenAI response JSON did not contain titles", status_code=502)

        cleaned_titles = [self._clean_text(str(title)) for title in titles if self._clean_text(str(title))]
        if len(cleaned_titles) != 3:
            raise HotspotServiceError("OpenAI response did not return exactly 3 titles", status_code=502)

        return cleaned_titles

    @staticmethod
    def _extract_output_text(payload: dict[str, Any]) -> str:
        texts: list[str] = []
        for item in payload.get("output", []):
            for content in item.get("content", []):
                if content.get("type") == "output_text" and content.get("text"):
                    texts.append(str(content["text"]))
        return "".join(texts)

    @staticmethod
    def _clean_text(value: str) -> str:
        if not value:
            return ""
        text = re.sub(r"<[^>]+>", " ", value)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

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

    @staticmethod
    def _current_local_date(local_zone: ZoneInfo) -> date:
        return datetime.now(local_zone).date()

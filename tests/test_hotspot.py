from __future__ import annotations

import json as json_lib
from datetime import date

from app.config import Settings
from app.hotspot import AIHotspotService

RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>AI Feed</title>
    <item>
      <title>OpenAI launches new reasoning model</title>
      <link>https://example.com/openai-reasoning?utm_source=rss&id=1#top</link>
      <description><![CDATA[The new GPT model focuses on reasoning and agent workflows.]]></description>
      <pubDate>Thu, 23 Apr 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Anthropic improves Claude for enterprise</title>
      <link>https://example.com/claude-enterprise</link>
      <description><![CDATA[Claude adds tools for enterprise AI deployments.]]></description>
      <pubDate>Thu, 23 Apr 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class DummyResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"",
        json_data: dict | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = content
        self._json_data = json_data or {}
        self.text = content.decode("utf-8", errors="ignore") if content else json_lib.dumps(self._json_data)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")

    def json(self) -> dict:
        return self._json_data


def test_scrape_ai_hotspot_uses_rss_and_openai(monkeypatch) -> None:
    settings = Settings(
        scheduler_enabled=False,
        scheduler_timezone="UTC",
        openai_api_key="test-key",
        hotspot_source_url="https://example.com/rss.xml",
        hotspot_max_items=5,
    )
    service = AIHotspotService(settings)

    def fake_get(url: str, headers: dict, timeout: float) -> DummyResponse:
        assert url == "https://example.com/rss.xml"
        assert headers["User-Agent"] == "ai-hot-topics-bot/0.1"
        assert timeout == settings.request_timeout_seconds
        return DummyResponse(content=RSS_SAMPLE)

    def fake_post(url: str, headers: dict, json: dict, timeout: float) -> DummyResponse:
        assert url == "https://api.openai.com/v1/responses"
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "gpt-5.4"
        assert json["text"]["format"]["type"] == "json_schema"
        return DummyResponse(
            json_data={
                "output_text": json_lib.dumps(
                    {
                        "titles": [
                            "OpenAI 与 Anthropic 发布新模型能力更新",
                            "AI 推理与企业落地成为今日焦点",
                            "大模型工具化能力继续升温",
                        ]
                    },
                    ensure_ascii=False,
                )
            }
        )

    monkeypatch.setattr("app.hotspot.requests.get", fake_get)
    monkeypatch.setattr("app.hotspot.requests.post", fake_post)
    monkeypatch.setattr(service, "_current_local_date", lambda _: date(2026, 4, 23))

    result = service.scrape_ai_hotspot()

    assert result.date == "2026-04-23"
    assert len(result.items) == 2
    assert result.items[0].link == "https://example.com/openai-reasoning?id=1"
    assert result.summary_titles[0] == "OpenAI 与 Anthropic 发布新模型能力更新"

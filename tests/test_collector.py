from __future__ import annotations

import httpx
import pytest

from app.collector import RSSCollector
from app.config import Settings
from app.models import FeedSource

RSS_SAMPLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>AI Feed</title>
    <item>
      <title>OpenAI launches new reasoning model</title>
      <link>https://example.com/openai-reasoning?utm_source=rss&id=1#top</link>
      <description><![CDATA[The new GPT model focuses on reasoning and agent workflows.]]></description>
      <pubDate>Tue, 22 Apr 2026 08:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Anthropic improves Claude for enterprise</title>
      <link>https://example.com/claude-enterprise</link>
      <description><![CDATA[Claude adds tools for enterprise AI deployments.]]></description>
      <pubDate>Tue, 22 Apr 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


@pytest.mark.anyio
async def test_collect_from_mock_rss_feed() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=200, content=RSS_SAMPLE)

    settings = Settings(
        scheduler_enabled=False,
        feed_sources=[
            FeedSource(
                name="Mock Feed",
                url="https://example.com/rss.xml",
                category="test",
                weight=1.0,
            )
        ],
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        collector = RSSCollector(settings, client=client)
        result = await collector.collect(settings.feed_sources)

    assert result.failed_sources == []
    assert result.source_item_counts["Mock Feed"] == 2
    assert len(result.topics) == 2
    assert result.topics[0].link == "https://example.com/openai-reasoning?id=1"
    assert "reasoning" in result.topics[0].tags
    assert result.topics[0].score > 0

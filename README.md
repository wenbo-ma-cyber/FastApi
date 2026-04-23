# 每日 AI 热点采集 FastAPI 项目

一个从公开 RSS/新闻源抓取 AI 热点、自动去重落库，并通过 FastAPI 提供查询和手动触发接口的示例项目。

## 功能

- 每日定时采集 AI 热点新闻
- 支持 API 手动触发采集
- 基于标题关键词做简单热度评分
- 采集结果持久化到 SQLite
- 提供热点列表、最新任务状态、源列表等接口

## 目录结构

```text
.
├── data/
├── src/app/
│   ├── api/
│   ├── cli.py
│   ├── collector.py
│   ├── config.py
│   ├── main.py
│   ├── models.py
│   ├── repository.py
│   ├── scheduler.py
│   └── service.py
└── tests/
```

## 启动方式

1. 创建虚拟环境并安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

2. 启动服务

```bash
uvicorn app.main:app --reload --app-dir src
```

3. 手动执行一次采集

```bash
PYTHONPATH=src python3 -m app.cli
```

## 默认接口

- `GET /`：项目说明
- `GET /api/v1/health`：健康检查
- `GET /api/v1/topics`：查询热点
- `POST /api/v1/collect`：立即执行一次采集
- `GET /api/v1/runs/latest`：查看最近一次采集任务
- `GET /api/v1/sources`：查看当前采集源
- `GET /scrape-ai-hotspot`：抓取今日 AI 热点并用 GPT-5.4 总结成 3 条中文标题

## 常用环境变量

```bash
AI_HOT_DATABASE_PATH=data/ai_hot_topics.db
AI_HOT_SCHEDULER_ENABLED=true
AI_HOT_COLLECT_ON_STARTUP=false
AI_HOT_COLLECT_HOUR=8
AI_HOT_COLLECT_MINUTE=0
AI_HOT_SCHEDULER_TIMEZONE=Asia/Shanghai
AI_HOT_OPENAI_MODEL=gpt-5.4
AI_HOT_HOTSPOT_SOURCE_URL=https://news.google.com/rss/search?q=artificial+intelligence+OR+OpenAI+OR+Anthropic+OR+DeepMind&hl=en-US&gl=US&ceid=US:en
OPENAI_API_KEY=your_api_key
```

如果要自定义采集源，可以设置 `AI_HOT_FEED_SOURCES`，值为 JSON 数组，例如：

```json
[
  {
    "name": "My Feed",
    "url": "https://example.com/rss.xml",
    "category": "news",
    "weight": 1.0
  }
]
```

## 说明

- 当前“热点”排序使用发布时间和关键词命中的简单加权规则，适合做日报/看板的第一版。
- RSS 源偶发失败不会中断整次任务，失败信息会记录到最近一次采集任务状态中。
- `/scrape-ai-hotspot` 会实时请求公开 RSS，并调用 OpenAI `v1/responses` 接口使用 `gpt-5.4` 生成严格 3 条中文标题。

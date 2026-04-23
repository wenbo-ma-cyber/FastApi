from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.models import CollectionRunRecord, CollectionStats, TopicCreate, TopicRecord


class TopicRepository:
    def __init__(self, database_path: Path, display_timezone: str) -> None:
        self.database_path = Path(database_path)
        self.display_timezone = display_timezone

    def init_db(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    link TEXT NOT NULL,
                    published_at TEXT NOT NULL,
                    collected_at TEXT NOT NULL,
                    score REAL NOT NULL,
                    tags_json TEXT NOT NULL,
                    dedupe_key TEXT NOT NULL UNIQUE
                );

                CREATE INDEX IF NOT EXISTS idx_topics_published_at
                    ON topics (published_at DESC);

                CREATE INDEX IF NOT EXISTS idx_topics_score
                    ON topics (score DESC);

                CREATE TABLE IF NOT EXISTS collection_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    requested_sources INTEGER NOT NULL,
                    successful_sources INTEGER NOT NULL,
                    failed_sources_json TEXT NOT NULL,
                    fetched_items INTEGER NOT NULL,
                    saved_items INTEGER NOT NULL,
                    updated_items INTEGER NOT NULL
                );
                """
            )

    def create_run(self, started_at: datetime, requested_sources: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO collection_runs (
                    started_at,
                    finished_at,
                    status,
                    requested_sources,
                    successful_sources,
                    failed_sources_json,
                    fetched_items,
                    saved_items,
                    updated_items
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    started_at.isoformat(),
                    None,
                    "running",
                    requested_sources,
                    0,
                    "[]",
                    0,
                    0,
                    0,
                ),
            )
            return int(cursor.lastrowid)

    def finish_run(self, run_id: int, stats: CollectionStats, status: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE collection_runs
                SET finished_at = ?,
                    status = ?,
                    requested_sources = ?,
                    successful_sources = ?,
                    failed_sources_json = ?,
                    fetched_items = ?,
                    saved_items = ?,
                    updated_items = ?
                WHERE id = ?
                """,
                (
                    stats.finished_at.isoformat(),
                    status,
                    stats.requested_sources,
                    stats.successful_sources,
                    json.dumps(stats.failed_sources, ensure_ascii=False),
                    stats.fetched_items,
                    stats.saved_items,
                    stats.updated_items,
                    run_id,
                ),
            )

    def upsert_topics(self, topics: list[TopicCreate]) -> tuple[int, int]:
        saved_items = 0
        updated_items = 0
        with self._connect() as connection:
            for topic in topics:
                exists = connection.execute(
                    "SELECT id FROM topics WHERE dedupe_key = ?",
                    (topic.dedupe_key,),
                ).fetchone()

                payload = (
                    topic.source_name,
                    topic.source_url,
                    topic.title,
                    topic.summary,
                    topic.link,
                    topic.published_at.isoformat(),
                    topic.collected_at.isoformat(),
                    topic.score,
                    json.dumps(topic.tags, ensure_ascii=False),
                    topic.dedupe_key,
                )

                if exists:
                    connection.execute(
                        """
                        UPDATE topics
                        SET source_name = ?,
                            source_url = ?,
                            title = ?,
                            summary = ?,
                            link = ?,
                            published_at = ?,
                            collected_at = ?,
                            score = ?,
                            tags_json = ?
                        WHERE dedupe_key = ?
                        """,
                        payload,
                    )
                    updated_items += 1
                else:
                    connection.execute(
                        """
                        INSERT INTO topics (
                            source_name,
                            source_url,
                            title,
                            summary,
                            link,
                            published_at,
                            collected_at,
                            score,
                            tags_json,
                            dedupe_key
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        payload,
                    )
                    saved_items += 1
        return saved_items, updated_items

    def list_topics(
        self,
        target_date: date | None,
        limit: int,
        source: str | None = None,
        tag: str | None = None,
    ) -> list[TopicRecord]:
        query = """
            SELECT id, source_name, source_url, title, summary, link,
                   published_at, collected_at, score, tags_json
            FROM topics
        """
        where_clauses: list[str] = []
        params: list[str | int] = []

        if target_date is not None:
            start_utc, end_utc = self._local_date_range_to_utc(target_date)
            where_clauses.append("published_at >= ? AND published_at < ?")
            params.extend([start_utc.isoformat(), end_utc.isoformat()])

        if source:
            where_clauses.append("source_name = ?")
            params.append(source)

        if tag:
            where_clauses.append("tags_json LIKE ?")
            params.append(f'%"{tag.lower()}"%')

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        query += " ORDER BY score DESC, published_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        return [self._row_to_topic(row) for row in rows]

    def get_latest_run(self) -> CollectionRunRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, started_at, finished_at, status, requested_sources,
                       successful_sources, failed_sources_json,
                       fetched_items, saved_items, updated_items
                FROM collection_runs
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None
        return self._row_to_run(row)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _row_to_topic(self, row: sqlite3.Row) -> TopicRecord:
        return TopicRecord(
            id=row["id"],
            source_name=row["source_name"],
            source_url=row["source_url"],
            title=row["title"],
            summary=row["summary"],
            link=row["link"],
            published_at=datetime.fromisoformat(row["published_at"]),
            collected_at=datetime.fromisoformat(row["collected_at"]),
            score=row["score"],
            tags=json.loads(row["tags_json"] or "[]"),
        )

    def _row_to_run(self, row: sqlite3.Row) -> CollectionRunRecord:
        finished_at_raw = row["finished_at"] or row["started_at"]
        return CollectionRunRecord(
            id=row["id"],
            status=row["status"],
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(finished_at_raw),
            requested_sources=row["requested_sources"],
            successful_sources=row["successful_sources"],
            failed_sources=json.loads(row["failed_sources_json"] or "[]"),
            fetched_items=row["fetched_items"],
            saved_items=row["saved_items"],
            updated_items=row["updated_items"],
        )

    def _local_date_range_to_utc(self, target_date: date) -> tuple[datetime, datetime]:
        local_zone = ZoneInfo(self.display_timezone)
        start_local = datetime.combine(target_date, time.min, tzinfo=local_zone)
        end_local = datetime.combine(target_date + timedelta(days=1), time.min, tzinfo=local_zone)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        return start_utc, end_utc

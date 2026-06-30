from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .config import Settings
from .models import ReportRecord, SourceDocument, TaskRecord, utc_now
from .text import chunk_text, query_terms


class Storage:
    def __init__(self, config: Settings):
        self.config = config
        config.ensure_directories()
        self.path = config.database_path
        self._initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, topic TEXT NOT NULL, status TEXT NOT NULL,
                    error TEXT, report_id TEXT, created_at TEXT NOT NULL, completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, source_type TEXT NOT NULL,
                    title TEXT NOT NULL, url TEXT, content TEXT NOT NULL,
                    metadata TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    report_id TEXT, source_id TEXT, source_title TEXT NOT NULL,
                    content TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, task_id TEXT NOT NULL, title TEXT NOT NULL,
                    content TEXT NOT NULL, path TEXT NOT NULL, citations TEXT NOT NULL,
                    qa_warnings TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, report_id TEXT NOT NULL,
                    role TEXT NOT NULL, content TEXT NOT NULL, citations TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_chunks_report ON chunks(report_id);
                CREATE INDEX IF NOT EXISTS idx_sources_task ON sources(task_id);
                """
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(reports)")}
            if "qa_warnings" not in columns:
                db.execute("ALTER TABLE reports ADD COLUMN qa_warnings TEXT NOT NULL DEFAULT '[]'")

    def create_task(self, task_id: str, topic: str) -> TaskRecord:
        record = TaskRecord(id=task_id, topic=topic, status="pending", created_at=utc_now())
        with self.connect() as db:
            db.execute(
                "INSERT INTO tasks(id, topic, status, created_at) VALUES (?, ?, ?, ?)",
                (record.id, record.topic, record.status, record.created_at),
            )
        return record

    def update_task(self, task_id: str, **fields: Any) -> None:
        allowed = {"status", "error", "report_id", "completed_at"}
        values = {key: value for key, value in fields.items() if key in allowed}
        if not values:
            return
        statement = ", ".join(f"{key} = ?" for key in values)
        with self.connect() as db:
            db.execute(
                f"UPDATE tasks SET {statement} WHERE id = ?",
                (*values.values(), task_id),
            )

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return TaskRecord(**dict(row)) if row else None

    def add_source(self, task_id: str, source: SourceDocument) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT OR REPLACE INTO sources
                (id, task_id, source_type, title, url, content, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source.id, task_id, source.source_type, source.title, source.url,
                    source.content, json.dumps(source.metadata, ensure_ascii=False), utc_now(),
                ),
            )
            db.execute("DELETE FROM chunks WHERE task_id = ? AND source_id = ?", (task_id, source.id))
            db.executemany(
                """INSERT INTO chunks(task_id, source_id, source_title, content)
                VALUES (?, ?, ?, ?)""",
                [
                    (task_id, source.id, source.title, chunk)
                    for chunk in chunk_text(
                        source.content, self.config.chunk_size, self.config.chunk_overlap
                    )
                ],
            )

    def save_report(self, report: ReportRecord) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO reports(id, task_id, title, content, path, citations, qa_warnings, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    report.id, report.task_id, report.title, report.content, report.path,
                    json.dumps(report.citations, ensure_ascii=False),
                    json.dumps(report.qa_warnings, ensure_ascii=False), report.created_at,
                ),
            )
            db.executemany(
                """INSERT INTO chunks(task_id, report_id, source_title, content)
                VALUES (?, ?, ?, ?)""",
                [
                    (report.task_id, report.id, report.title, chunk)
                    for chunk in chunk_text(
                        report.content, self.config.chunk_size, self.config.chunk_overlap
                    )
                ],
            )

    def get_report(self, report_id: str) -> ReportRecord | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["citations"] = json.loads(data["citations"])
        data["qa_warnings"] = json.loads(data.get("qa_warnings") or "[]")
        return ReportRecord(**data)

    def list_reports(self, limit: int = 50) -> list[ReportRecord]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        reports = []
        for row in rows:
            data = dict(row)
            data["citations"] = json.loads(data["citations"])
            data["qa_warnings"] = json.loads(data.get("qa_warnings") or "[]")
            reports.append(ReportRecord(**data))
        return reports

    def retrieve(self, report_id: str, query: str, limit: int = 8) -> list[dict[str, Any]]:
        report = self.get_report(report_id)
        if not report:
            return []
        with self.connect() as db:
            rows = db.execute(
                """SELECT source_id, source_title, content FROM chunks
                WHERE report_id = ? OR task_id = ?""",
                (report_id, report.task_id),
            ).fetchall()
        terms = query_terms(query)
        scored = []
        for row in rows:
            content_lower = row["content"].lower()
            score = sum(1 + min(content_lower.count(term.lower()), 3) for term in terms if term)
            if score:
                scored.append((score, dict(row)))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[:limit] if scored else [(0, dict(row)) for row in rows[:limit]]
        return [item for _, item in selected]

    def add_message(
        self, report_id: str, role: str, content: str, citations: list[dict[str, Any]] | None = None
    ) -> None:
        with self.connect() as db:
            db.execute(
                """INSERT INTO conversations(report_id, role, content, citations, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (report_id, role, content, json.dumps(citations or [], ensure_ascii=False), utc_now()),
            )

    def recent_messages(self, report_id: str, limit: int = 6) -> list[dict[str, str]]:
        with self.connect() as db:
            rows = db.execute(
                """SELECT role, content FROM conversations WHERE report_id = ?
                ORDER BY id DESC LIMIT ?""",
                (report_id, limit),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

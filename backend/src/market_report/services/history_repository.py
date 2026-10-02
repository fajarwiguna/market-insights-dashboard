"""Repository riwayat observasi SBN dengan backend JSON atau PostgreSQL."""

from __future__ import annotations

import json
import os
from pathlib import Path


class JsonSbnHistoryRepository:
    def __init__(self, path: Path):
        self.path = Path(path)

    def list(self, limit: int = 30) -> list[dict]:
        if limit <= 0:
            return []
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(value, list):
            return []
        return [row for row in value if isinstance(row, dict) and row.get("date") and row.get("close") is not None][-limit:]

    def upsert(self, date: str, close: float, limit: int = 30) -> list[dict]:
        previous = self.list(limit=100000)
        if limit <= 0:
            updated = []
        else:
            updated = sorted(
                [row for row in previous if str(row.get("date"))[:10] != date]
                + [{"date": date, "close": close}],
                key=lambda row: str(row["date"]),
            )[-limit:]
        if updated != previous:
            from market_report.calculate import persist_json_data

            persist_json_data(updated, self.path)
        return updated


class PostgresSbnHistoryRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("Adapter PostgreSQL memerlukan psycopg. Pasang dependensi requirements.txt.") from error
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def list(self, limit: int = 30) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT dates, close FROM sbn_history ORDER BY dates DESC LIMIT %s",
                (max(0, limit),),
            ).fetchall()
        return [{"date": row["dates"].isoformat(), "close": float(row["close"])} for row in reversed(rows)]

    def upsert(self, date: str, close: float, limit: int = 30) -> list[dict]:
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO sbn_history (dates, close) VALUES (%s, %s)
                   ON CONFLICT (dates) DO UPDATE SET close = EXCLUDED.close""",
                (date, close),
            )
            connection.execute(
                """DELETE FROM sbn_history WHERE dates NOT IN
                   (SELECT dates FROM sbn_history ORDER BY dates DESC LIMIT %s)""",
                (max(0, limit),),
            )
            rows = connection.execute(
                "SELECT dates, close FROM sbn_history ORDER BY dates DESC LIMIT %s",
                (max(0, limit),),
            ).fetchall()
        return [{"date": row["dates"].isoformat(), "close": float(row["close"])} for row in reversed(rows)]


def configured_history_repository(default_path: Path):
    from market_report.config import load_environment

    load_environment()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    return PostgresSbnHistoryRepository(database_url) if database_url else JsonSbnHistoryRepository(default_path)

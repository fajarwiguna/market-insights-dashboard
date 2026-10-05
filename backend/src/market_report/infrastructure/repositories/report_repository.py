"""Repository versi laporan dengan penyimpanan lokal atau PostgreSQL."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


class JsonReportRepository:
    """Simpan versi laporan dan penunjuk laporan aktif dengan penulisan atomik."""

    def __init__(self, active_path: Path, versions_path: Path | None = None):
        self.active_path = Path(active_path)
        self.versions_path = Path(versions_path or self.active_path.parent / f"{self.active_path.stem}_versions")

    def get_active(self) -> dict | None:
        return self._read(self.active_path)

    def get_version(self, report_id: str) -> dict | None:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", report_id or ""):
            return None
        return self._read(self.versions_path / f"{report_id}.json")

    def list_versions(self, limit: int = 30) -> list[dict]:
        if not self.versions_path.exists():
            return []
        paths = sorted(self.versions_path.glob("*.json"), reverse=True)
        versions = [self._read(path) for path in paths[:max(0, limit)]]
        return [item for item in versions if item is not None]

    def publish(self, report: dict) -> dict:
        from market_report.calculate import persist_json_data

        published = dict(report)
        now = datetime.now(timezone.utc)
        published.setdefault("report_id", now.strftime("%Y%m%dT%H%M%S%fZ"))
        published.setdefault("published_at", now.isoformat(timespec="seconds"))

        # Simpan versi dahulu; file aktif menjadi penunjuk commit.
        self.versions_path.mkdir(parents=True, exist_ok=True)
        version_path = self.versions_path / f"{published['report_id']}.json"
        existing = self._read(version_path)
        if existing is not None:
            persist_json_data(existing, self.active_path)
            return existing
        persist_json_data(published, version_path)
        persist_json_data(published, self.active_path)
        return published

    @staticmethod
    def _read(path: Path) -> dict | None:
        try:
            with path.open(encoding="utf-8") as source:
                value = json.load(source)
            return value if isinstance(value, dict) else None
        except (OSError, json.JSONDecodeError):
            return None


class PostgresReportRepository:
    """Repository PostgreSQL; memerlukan schema dari backend/migrations/001_report_versions.sql."""

    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL belum diatur.")
        self.database_url = database_url

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("Adapter PostgreSQL memerlukan psycopg. Pasang dependensi requirements.txt.") from error
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def get_active(self) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT v.payload FROM active_report a
                   JOIN report_versions v USING (report_id) WHERE a.slot = 'active'"""
            ).fetchone()
        return row["payload"] if row else None

    def get_version(self, report_id: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload FROM report_versions WHERE report_id = %s", (report_id,)
            ).fetchone()
        return row["payload"] if row else None

    def list_versions(self, limit: int = 30) -> list[dict]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM report_versions ORDER BY dates DESC LIMIT %s",
                (max(0, limit),),
            ).fetchall()
        return [row["payload"] for row in rows]

    def publish(self, report: dict) -> dict:
        published = dict(report)
        now = datetime.now(timezone.utc)
        published.setdefault("report_id", now.strftime("%Y%m%dT%H%M%S%fZ"))
        published.setdefault("published_at", now.isoformat(timespec="seconds"))
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO report_versions (report_id, dates, schema_version, payload)
                   VALUES (%s, %s, %s, %s::jsonb)
                   ON CONFLICT (report_id) DO NOTHING""",
                (published["report_id"], published["published_at"], published.get("schema_version", 1),
                 json.dumps(published, ensure_ascii=False, default=str)),
            )
            stored = connection.execute(
                "SELECT payload FROM report_versions WHERE report_id = %s",
                (published["report_id"],),
            ).fetchone()
            canonical = stored["payload"]
            connection.execute(
                """INSERT INTO active_report (slot, report_id) VALUES ('active', %s)
                   ON CONFLICT (slot) DO UPDATE SET report_id = EXCLUDED.report_id""",
                (published["report_id"],),
            )
        return canonical


def configured_report_repository(default_path: Path):
    """Gunakan PostgreSQL bila DATABASE_URL tersedia; selain itu gunakan JSON lokal."""
    from market_report.config import load_environment

    load_environment()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    return PostgresReportRepository(database_url) if database_url else JsonReportRepository(default_path)

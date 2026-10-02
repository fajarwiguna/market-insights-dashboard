"""Impor arsip dan laporan aktif JSON ke PostgreSQL yang sudah dimigrasikan."""

import os
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market_report.config import load_environment, market_data_directory
from market_report.infrastructure.repositories.history_repository import (
    JsonSbnHistoryRepository,
    PostgresSbnHistoryRepository,
)
from market_report.infrastructure.repositories.report_repository import (
    JsonReportRepository,
    PostgresReportRepository,
)


def _split_sql_statements(sql: str) -> list[str]:
    """Pisahkan statement tanpa memecah semicolon di string atau blok DO dollar-quote."""
    statements = []
    start = index = 0
    quote = None
    dollar_quote = None
    line_comment = False
    block_comment = False
    while index < len(sql):
        if line_comment:
            if sql[index] == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if sql.startswith("*/", index):
                block_comment = False
                index += 2
            else:
                index += 1
            continue
        if dollar_quote:
            if sql.startswith(dollar_quote, index):
                index += len(dollar_quote)
                dollar_quote = None
            else:
                index += 1
            continue
        if quote:
            if sql[index] == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue

        if sql.startswith("--", index):
            line_comment = True
            index += 2
        elif sql.startswith("/*", index):
            block_comment = True
            index += 2
        elif sql[index] in ("'", '"'):
            quote = sql[index]
            index += 1
        elif sql[index] == "$":
            marker = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql[index:])
            if marker:
                dollar_quote = marker.group(0)
                index += len(dollar_quote)
            else:
                index += 1
        elif sql[index] == ";":
            statement = sql[start:index].strip()
            if statement:
                statements.append(statement)
            index += 1
            start = index
        else:
            index += 1
    remainder = sql[start:].strip()
    if remainder:
        statements.append(remainder)
    return statements


def apply_schema_migrations(database_url: str) -> None:
    """Jalankan migrasi schema yang idempotent sebelum memindahkan data."""
    import psycopg

    migrations_dir = Path(__file__).resolve().parents[2] / "migrations"
    with psycopg.connect(database_url) as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS schema_migrations (
                   version TEXT PRIMARY KEY,
                   dates TIMESTAMPTZ NOT NULL DEFAULT now()
               )"""
        )
        for migration_path in sorted(migrations_dir.glob("*.sql")):
            version = migration_path.name
            already_applied = connection.execute(
                "SELECT 1 FROM schema_migrations WHERE version = %s", (version,)
            ).fetchone()
            if already_applied:
                continue
            sql = migration_path.read_text(encoding="utf-8")
            for statement in _split_sql_statements(sql):
                connection.execute(statement)
            connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))


def _report_content(report: dict) -> dict:
    return {key: value for key, value in report.items() if key not in {"report_id", "published_at"}}


def _assign_legacy_identity(report: dict, current_database_report: dict | None) -> dict:
    report = dict(report)
    if report.get("report_id"):
        return report
    if current_database_report and _report_content(current_database_report) == _report_content(report):
        report["report_id"] = current_database_report["report_id"]
        report["published_at"] = current_database_report.get("published_at")
        return report
    date_key = re.sub(r"[^A-Za-z0-9_-]", "", str(report.get("report_date_iso") or ""))
    if not date_key:
        canonical = json.dumps(report, sort_keys=True, ensure_ascii=False, default=str)
        date_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]
    report["report_id"] = f"legacy-{date_key}"
    return report


def main() -> int:
    load_environment()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL tidak ditemukan. Isi file .env di root project.")

    apply_schema_migrations(database_url)

    data_dir = market_data_directory()
    source = JsonReportRepository(data_dir / "report_data.json")
    archived = source.list_versions(limit=10000)
    active = source.get_active()

    reports = {item.get("report_id"): item for item in archived if item.get("report_id")}
    if active and active.get("report_id"):
        reports.pop(active["report_id"], None)
    if not reports and not active:
        raise SystemExit("Tidak ditemukan report_data.json atau arsip report_versions.")

    destination = PostgresReportRepository(database_url)
    if active:
        active = _assign_legacy_identity(active, destination.get_active())
    # Versi arsip lama lebih dahulu, lalu aktif lokal menjadi penunjuk aktif di database.
    for report in sorted(reports.values(), key=lambda item: item.get("published_at", "")):
        destination.publish(report)
    if active:
        destination.publish(active)
    history_source = JsonSbnHistoryRepository(data_dir / "history_sbn.json")
    history = history_source.list(limit=30)
    history_destination = PostgresSbnHistoryRepository(database_url)
    for point in history:
        history_destination.upsert(point["date"], float(point["close"]), limit=30)
    print(
        f"Berhasil mengimpor {len(reports) + bool(active)} versi laporan dan "
        f"{len(history)} titik riwayat SBN; laporan aktif mengikuti report_data.json."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as error:
        # Hindari mencetak DSN atau kredensial dalam exception koneksi.
        raise SystemExit(f"Migrasi gagal ({type(error).__name__}). Periksa koneksi, izin database, dan schema.") from None

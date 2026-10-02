"""Impor arsip dan laporan aktif JSON ke PostgreSQL yang sudah dimigrasikan."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.report_repository import JsonReportRepository, PostgresReportRepository


def main() -> int:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("Atur DATABASE_URL ke database PostgreSQL tujuan.")

    data_dir = Path(__file__).resolve().parents[1] / "data"
    source = JsonReportRepository(data_dir / "report_data.json")
    archived = source.list_versions(limit=10000)
    active = source.get_active()

    reports = {item.get("report_id"): item for item in archived if item.get("report_id")}
    if active and active.get("report_id"):
        reports.pop(active["report_id"], None)
    if not reports and not active:
        raise SystemExit("Tidak ditemukan report_data.json atau arsip report_versions.")

    destination = PostgresReportRepository(database_url)
    # Versi arsip lama lebih dahulu, lalu aktif lokal menjadi penunjuk aktif di database.
    for report in sorted(reports.values(), key=lambda item: item.get("published_at", "")):
        destination.publish(report)
    if active:
        destination.publish(active)
    print(f"Berhasil mengimpor {len(reports) + bool(active)} versi laporan; laporan aktif mengikuti report_data.json.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

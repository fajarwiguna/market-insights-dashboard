"""Terapkan migrasi schema saja, tanpa mengimpor atau mengubah laporan aktif."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_environment
from migrate_reports_to_postgres import apply_schema_migrations


def main() -> int:
    load_environment()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL tidak ditemukan. Isi file .env di root project.")
    try:
        apply_schema_migrations(database_url)
    except Exception as error:
        raise SystemExit(
            f"Migrasi schema gagal ({type(error).__name__}). Periksa koneksi, izin database, dan schema."
        ) from None
    print("Migrasi schema selesai.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

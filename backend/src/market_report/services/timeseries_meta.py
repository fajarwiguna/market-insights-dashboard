"""Sinkronisasi katalog pipeline ke `meta_table` + `meta_timeseries`.

Katalog (`timeseries_catalog.PIPELINE_SERIES`) adalah satu-satunya acuan:
nama tabel kanonis, nama kolom series, dan identitas `series_id`. Modul ini
menerjemahkannya menjadi baris metadata plus tabel fisik wide (satu kolom per
series) lewat repository aktif.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def parse_meta(series_list: list[dict] | None = None) -> list[dict]:
    """Kembalikan katalog pipeline lengkap (atau daftar yang disuplai).

    Nama dipertahankan sebagai alias tipis atas `PIPELINE_SERIES` agar
    pemanggil lama tidak perlu berubah.
    """
    if series_list is not None:
        return list(series_list)
    from market_report.services.timeseries_catalog import PIPELINE_SERIES

    return [dict(entry) for entry in PIPELINE_SERIES]


def sync_to_database(series_list: list[dict] | None = None,
                     repository=None, *, prune: bool | None = None) -> int:
    """Tulis katalog ke `meta_table`/`meta_timeseries` dan pastikan tabel ada.

    Saat memakai katalog lengkap (`series_list` None) katalog menjadi acuan
    tunggal, sehingga baris metadata yang ID-nya tidak lagi dipakai dibuang
    (`prune=True`). Pemanggil yang menyuplai daftar parsial tidak memangkas
    apa pun secara default.
    """
    if series_list is None:
        series_list = parse_meta()
        if prune is None:
            prune = True
    if prune is None:
        prune = False
    if not series_list:
        return 0
    if repository is None:
        from market_report.config import market_data_directory
        from market_report.infrastructure.repositories.timeseries_repository import (
            configured_timeseries_repository,
        )

        repository = configured_timeseries_repository(market_data_directory())

    # Prune dulu agar baris yatim tidak memblokir upsert lewat constraint
    # UNIQUE(series_id) sebelum katalog baru masuk.
    if prune and hasattr(repository, "prune_series"):
        repository.prune_series({s["series_id"] for s in series_list})
    if hasattr(repository, "sync_catalog"):
        return repository.sync_catalog(series_list)

    count = 0
    for series in series_list:
        repository.upsert_series(series)
        count += 1
    return count

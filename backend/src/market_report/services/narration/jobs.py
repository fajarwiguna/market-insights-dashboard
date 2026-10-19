"""Job refresh narasi: dipanggil worker atau dijalankan manual.

Belum dijahit ke `refresh_service`/scheduler karena pembekuan narasi ke laporan
terbit (blueprint §15.1) adalah perubahan terpisah pada `publish_snapshot()`.
Sementara ini worker/operator dapat memanggil fungsi di bawah, atau menjalankan
modul ini langsung:

    PYTHONPATH=backend/src python -m market_report.services.narration.jobs --page dashboard
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta
from typing import Iterable, Sequence

from market_report.domain.narration_contract import NarrativePage, NarrativeRequest, NarrativeResult
from market_report.services.narration.engine import NarrativeEngine

logger = logging.getLogger(__name__)

DEFAULT_PAGES = (NarrativePage.DASHBOARD, NarrativePage.EQUITY_SNAPSHOT)


def refresh_narratives(pages: Sequence[NarrativePage] = DEFAULT_PAGES, *, engine: NarrativeEngine | None = None,
                       force: bool = False, allow_search: bool = True) -> list[NarrativeResult]:
    """Buat narasi untuk halaman yang diminta, dibatasi `cost.max_calls_per_refresh`.

    Satu halaman gagal tidak menghentikan halaman lain: hasilnya tetap
    deterministik dan kegagalan dicatat pada audit masing-masing run.
    """
    active = engine or NarrativeEngine()
    limit = active.rules.integer("cost.max_calls_per_refresh", 2)
    results: list[NarrativeResult] = []
    for page in list(pages)[:max(1, limit)]:
        try:
            results.append(active.generate(NarrativeRequest(page=page, allow_search=allow_search,
                                                           reason="refresh"), force=force))
        except Exception as error:  # narasi tidak boleh menggagalkan worker
            logger.exception("Gagal membuat narasi %s: %s", page.value, error)
    return results


def stale_pages(engine: NarrativeEngine | None = None,
                pages: Iterable[NarrativePage] = DEFAULT_PAGES) -> list[NarrativePage]:
    """Halaman yang narasinya belum ada atau sudah kedaluwarsa untuk laporan aktif."""
    active = engine or NarrativeEngine()
    stale: list[NarrativePage] = []
    for page in pages:
        context = active.context_for(page)
        if not context.report_date:
            continue
        entry = active.cache.get(page=page, report_id=context.report_id)
        if entry is None or entry.expired:
            stale.append(page)
    return stale


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Buat narasi pasar untuk laporan aktif.")
    parser.add_argument("--page", action="append", choices=[page.value for page in DEFAULT_PAGES],
                        help="halaman yang dibuat (boleh diulang); default dua halaman")
    parser.add_argument("--no-search", action="store_true", help="lewati pengumpulan bukti eksternal")
    parser.add_argument("--force", action="store_true", help="abaikan cache yang masih berlaku")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pages = [NarrativePage.parse(value) for value in (args.page or [])] or list(DEFAULT_PAGES)
    results = refresh_narratives(pages, force=args.force, allow_search=not args.no_search)
    print(json.dumps([{"page": result.page.value, "status": result.status.value,
                       "reason": result.reason, "report_date": result.report_date,
                       "run_id": result.run_id} for result in results], ensure_ascii=False))
    return 0


if __name__ == "__main__":  # pragma: no cover - jalur operasional
    raise SystemExit(main())

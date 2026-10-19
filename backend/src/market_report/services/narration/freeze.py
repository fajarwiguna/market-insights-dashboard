"""Pembekuan narasi ke laporan terbit (blueprint §15.1).

Narasi yang dipakai laporan versi itu dibekukan bersama payload laporan,
sehingga PDF dan halaman laporan lama selalu menampilkan teks yang sama
walaupun narasi kemudian dibuat ulang. Pembekuan hanya berjalan ketika fitur
narasi LLM diaktifkan (`LLM_NARRATIVE_ENABLED`); bila tidak, laporan terbit
tetap memakai ringkasan deterministik yang sudah ada.

Kegagalan apa pun di sini tidak boleh menggagalkan publikasi laporan.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from market_report.domain.narration_contract import (
    NarrativePage,
    NarrativeRequest,
    NarrativeResult,
    NarrativeStatus,
    utc_now_iso,
)
from market_report.services.narration.engine import NarrativeEngine

logger = logging.getLogger(__name__)

FREEZE_KEY = "narrative"
FREEZE_PAGES: tuple[NarrativePage, ...] = (NarrativePage.DASHBOARD, NarrativePage.EQUITY_SNAPSHOT)

# Status yang boleh dipakai sebagai narasi beku: hasil LLM yang lulus validasi
# atau narasi deterministik yang aman.
_FREEZABLE_STATUSES = {NarrativeStatus.PUBLISHED.value, NarrativeStatus.FALLBACK.value}


def freeze_enabled() -> bool:
    """Pembekuan mengikuti status fitur; `NARRATIVE_FREEZE=always` untuk memaksa."""
    forced = os.environ.get("NARRATIVE_FREEZE", "").strip().lower()
    if forced in {"always", "true", "1", "on"}:
        return True
    if forced in {"never", "false", "0", "off"}:
        return False
    from market_report.services.narration.providers.registry import narrative_enabled

    return narrative_enabled()


def _freezable_entry(entry: object) -> dict | None:
    """Kembalikan entri bila statusnya boleh dipakai sebagai narasi beku."""
    if isinstance(entry, dict) and entry.get("status") in _FREEZABLE_STATUSES:
        return entry
    return None


def frozen_entry(report: dict, page: NarrativePage | str) -> dict | None:
    """Entri narasi beku untuk satu halaman, atau None bila tidak ada."""
    key = page.value if isinstance(page, NarrativePage) else str(page)
    block = (report or {}).get(FREEZE_KEY)
    if not isinstance(block, dict):
        return None
    return _freezable_entry(block.get(key))


def frozen_narrative(report: dict, page: NarrativePage | str) -> str:
    """Teks narasi beku untuk halaman; kosong bila belum dibekukan."""
    entry = frozen_entry(report, page)
    return str(entry.get("narrative") or "") if entry else ""


def frozen_sections(report: dict, page: NarrativePage | str) -> list[dict]:
    entry = frozen_entry(report, page)
    sections = (entry or {}).get("sections") or []
    return [dict(section) for section in sections if isinstance(section, dict)]


def _entry_payload(result: NarrativeResult) -> dict:
    payload = result.to_payload()
    payload["frozen"] = True
    payload["frozen_at"] = utc_now_iso()
    return payload


def attach_narratives(report: dict, *, engine: NarrativeEngine | None = None,
                      pages: Iterable[NarrativePage] = FREEZE_PAGES) -> dict:
    """Bekukan narasi ke dalam payload laporan yang akan diterbitkan.

    Mengembalikan laporan yang sama (diubah di tempat) agar pemanggil pada
    jalur publikasi tetap sederhana.
    """
    if not freeze_enabled():
        return report
    try:
        active = engine or NarrativeEngine()
        block = dict(report.get(FREEZE_KEY) or {})
        for page in pages:
            snapshot = report.get("equity_snapshot") if page is NarrativePage.EQUITY_SNAPSHOT else None
            result = active.generate(
                NarrativeRequest(page=page, report_id=report.get("report_id") or None,
                                 reason="publish"),
                report=report, snapshot=snapshot if isinstance(snapshot, dict) else None,
                force=True,
            )
            block[page.value] = _entry_payload(result)
            if page is NarrativePage.EQUITY_SNAPSHOT and isinstance(snapshot, dict):
                # Halaman equity membaca salinan snapshot pada laporan, jadi
                # narasinya disimpan di sana juga.
                snapshot["narrative_frozen"] = dict(block[page.value])
        if block:
            report[FREEZE_KEY] = block
    except Exception as error:  # publikasi harus tetap berjalan
        logger.exception("Gagal membekukan narasi ke laporan terbit: %s", error)
    return report


def apply_frozen_narrative(
    payload: dict,
    report: dict | None = None,
    *,
    page: NarrativePage = NarrativePage.EQUITY_SNAPSHOT,
) -> dict:
    """Salinan payload dengan `narratives` diganti sections beku bila ada.

    Sumber prioritas mengikuti blueprint: salinan entri pada payload itu sendiri
    (`narrative_frozen`) lalu blok narasi laporan terbit. Narasi deterministik
    dipertahankan bila tidak ada sections beku, sehingga halaman tetap terisi.
    """
    if not isinstance(payload, dict):
        return payload
    entry = _freezable_entry(payload.get("narrative_frozen"))
    if entry is None:
        entry = frozen_entry(report or {}, page)
    if entry is None:
        return payload

    result = dict(payload)
    sections = [dict(section) for section in (entry.get("sections") or [])
                if isinstance(section, dict)]
    applied = bool(sections)
    if applied:
        result["narratives"] = sections
    result["narrative_status"] = str(entry.get("status") or "")
    result["narrative_frozen"] = applied
    return result

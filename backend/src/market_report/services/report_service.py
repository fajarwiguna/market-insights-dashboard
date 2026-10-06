"""Alur bersama untuk membentuk, memvalidasi, dan menerbitkan laporan pasar."""

import json
import logging
import math
from contextlib import nullcontext
from datetime import datetime, timezone
from pathlib import Path

from market_report.infrastructure.repositories.report_repository import (
    JsonReportRepository,
    configured_report_repository,
)
from market_report.config import market_data_directory


_DATA_DIR = market_data_directory()
_REPORT_PATH = _DATA_DIR / "report_data.json"
_SNAPSHOT_PATH = _DATA_DIR / "snapshot.json"
_DEMO_REPORT_PATH = _DATA_DIR / "demo_report_data.json"
_logger = logging.getLogger(__name__)


def _repository(path: Path | None = None):
    if path is not None:
        return JsonReportRepository(path)
    return configured_report_repository(path or _REPORT_PATH)


def load_report(path: Path | None = None) -> dict | None:
    """Baca laporan aktif terakhir yang sudah diterbitkan."""
    return _repository(path).get_active()


def load_report_version(report_id: str, path: Path | None = None) -> dict | None:
    """Baca versi laporan berdasarkan ID tetap."""
    return _repository(path).get_version(report_id)


def list_report_versions(limit: int = 30, path: Path | None = None) -> list[dict]:
    """Daftar versi laporan terbaru yang tersimpan."""
    return _repository(path).list_versions(limit)


def _valid_price(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value) and value > 0


def _saved_antam_observation(report: dict) -> dict | None:
    """Ambil observasi Antam terakhir yang tersimpan pada versi laporan."""
    from market_report.services.history_service import source_date_iso

    snapshot = report.get("_source_snapshot")
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    source_reading = snapshot.get("antam_gold")
    source_reading = source_reading if isinstance(source_reading, dict) else {}
    candidates = [source_reading]

    commodities = report.get("commodities")
    if isinstance(commodities, dict):
        candidates.extend(
            reading for name, reading in commodities.items()
            if "antam" in str(name).lower() and isinstance(reading, dict)
        )

    gold = report.get("gold")
    if isinstance(gold, dict):
        candidates.extend(
            reading for name, reading in gold.items()
            if "antam" in str(name).lower() and isinstance(reading, dict)
        )

    for reading in candidates:
        price = reading.get("price") if reading.get("price") is not None else reading.get("today")
        day = source_date_iso(reading.get("date"))
        series_id = reading.get("series_id")
        if series_id != "ocebsi_antam_buy_1g":
            continue
        if _valid_price(price) and day:
            return {
                "price": price,
                "date": day,
                "source": reading.get("source") or "https://ocebsi.com/macro/gold-antam/",
                "source_name": reading.get("source_name") or "Antam price feed",
                "series_id": series_id,
                "basis": reading.get("basis") or "Harga beli Antam 1 gram.",
            }

    # Some report versions contain the cumulative series but not the Antam row itself.
    for history in (
        report.get("_antam_gold_history"),
        snapshot.get("_antam_gold_history"),
    ):
        points = []
        for point in history if isinstance(history, list) else []:
            if not isinstance(point, dict):
                continue
            day = source_date_iso(point.get("date") or point.get("dates"))
            price = point.get("close")
            if day and _valid_price(price) and point.get("series_id") == "ocebsi_antam_buy_1g":
                points.append((day, price, point.get("series_id") or "legacy_antam"))
        if points:
            day, price, series_id = max(points, key=lambda point: point[0])
            return {
                "price": price,
                "date": day,
                "series_id": series_id,
                "source": "https://ocebsi.com/macro/gold-antam/",
                "source_name": "OCEBSI ANTAM (histori tersimpan)",
                "basis": "Harga beli Antam 1 gram.",
            }
    return None


def _latest_saved_antam_observation() -> dict | None:
    """Cari harga Antam valid terakhir tanpa mengandalkan urutan ID versi."""
    reports = list_report_versions(limit=420)
    active = load_report()
    active_id = active.get("report_id") if isinstance(active, dict) else None
    if isinstance(active, dict) and not any(
        item.get("report_id") == active_id for item in reports
    ):
        reports.append(active)

    def published_timestamp(item: dict) -> float:
        raw = item.get("published_at") or item.get("generated_at")
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.timestamp()
        except (TypeError, ValueError, OverflowError):
            return float("inf") if active_id and item.get("report_id") == active_id else float("-inf")

    ordered = sorted(
        enumerate(reports),
        key=lambda pair: (
            active_id is not None and pair[1].get("report_id") == active_id,
            published_timestamp(pair[1]),
            pair[0],
        ),
        reverse=True,
    )
    for _, report in ordered:
        observation = _saved_antam_observation(report)
        if observation:
            return observation
    return None


def load_snapshot(path: Path | None = None) -> dict:
    """Baca snapshot sumber yang sama dengan laporan aktif."""
    if path is None:
        report = load_report()
        if report and isinstance(report.get("_source_snapshot"), dict):
            return report["_source_snapshot"]
        snapshot_path = _SNAPSHOT_PATH
    else:
        snapshot_path = path
    if not snapshot_path.exists():
        return {}
    try:
        with snapshot_path.open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError):
        return {}


def validate_report(report: dict) -> None:
    """Tolak laporan live yang tidak berisi sedikitnya dua observasi pasar valid."""
    if not isinstance(report, dict) or report.get("is_demo"):
        raise ValueError("Hasil pipeline live harus berupa laporan pasar non-demo.")

    jumlah = 0
    for section in ("fx", "indices", "yields", "commodities"):
        values = report.get(section)
        if not isinstance(values, dict):
            continue
        for row in values.values():
            if not isinstance(row, dict):
                continue
            value = row.get("today")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                jumlah += 1
    if jumlah < 2:
        raise RuntimeError(
            "Data pasar terbaru tidak cukup (kurang dari 2 instrumen berhasil dibaca). "
            "Laporan sebelumnya tetap dipakai; coba perbarui lagi nanti."
        )


def publish_snapshot(snapshot: dict, *, report_path: Path | None = None,
                     snapshot_path: Path | None = None, report_id: str | None = None) -> dict:
    """Bangun dan validasi laporan dari payload snapshot yang diberikan, lalu terbitkan."""
    from market_report.calculate import build_report_data, persist_json_data

    report = build_report_data(snapshot)
    report["schema_version"] = 2
    report["_source_snapshot"] = snapshot
    if isinstance(snapshot.get("_sbn_history"), list):
        report["_sbn_history"] = snapshot["_sbn_history"]
    if isinstance(snapshot.get("_antam_gold_history"), list):
        report["_antam_gold_history"] = snapshot["_antam_gold_history"]
    if report_id:
        report["report_id"] = report_id
    validate_report(report)

    # Repository menyimpan versi immutable, lalu mengganti laporan aktif atomik.
    report = _repository(report_path).publish(report)

    # Snapshot terpisah hanya menjadi salinan diagnostik; UI membaca salinan
    # yang tertanam pada laporan aktif agar kedua tampilan memakai versi sama.
    try:
        persist_json_data(snapshot, snapshot_path or _SNAPSHOT_PATH)
    except OSError:
        _logger.exception("Gagal menyimpan salinan snapshot diagnostik")
    return report


def run_live_pipeline(*, publication_guard=None, report_id: str | None = None) -> dict:
    """Ambil sumber satu kali, bentuk laporan dari payload itu, lalu terbitkan."""
    from market_report.fetch_data import run_all

    snapshot = run_all(persist=False)
    # Capture the SBN chart series in the immutable report version. A PDF for
    # an older report must not silently use today's global history table.
    from market_report.calculate import build_report_data
    from market_report.domain.market_analysis import market_facts
    from market_report.services.history_service import load_sbn_history, record_sbn_history

    antam = snapshot.get("antam_gold")
    if not isinstance(antam, dict) or not _valid_price(antam.get("price")):
        last_antam = _latest_saved_antam_observation()
        if last_antam:
            fetch_error = antam.get("error") if isinstance(antam, dict) else None
            last_antam["availability"] = "stale"
            if fetch_error:
                last_antam["fetch_error"] = str(fetch_error)
            last_antam["availability_note"] = (
                f"Harga Antam belum berhasil diperbarui. Menampilkan observasi "
                f"{last_antam.get('basis') or last_antam.get('source_name')} per {last_antam['date']}."
            )
            snapshot["antam_gold"] = last_antam

    # Seed published history from OCEBSI and continue carrying it across versions.
    antam = snapshot.get("antam_gold")
    if isinstance(antam, dict) and isinstance(antam.get("price"), (int, float)) \
            and not isinstance(antam.get("price"), bool) and math.isfinite(antam["price"]):
        from market_report.services.history_service import MAX_HISTORY_POINTS, source_date_iso

        antam_day = source_date_iso(antam.get("date"))
        series_id = antam.get("series_id") or "ocebsi_antam_buy_1g"
        observations: dict[tuple[str, str], float] = {}
        for point in antam.get("history", []):
            if not isinstance(point, dict):
                continue
            point_day = source_date_iso(point.get("date"))
            point_price = point.get("close")
            if point_day and _valid_price(point_price):
                observations[(series_id, point_day)] = float(point_price)

        prior_reports = list_report_versions(limit=MAX_HISTORY_POINTS)
        active_report = load_report()
        active_report_id = active_report.get("report_id") if isinstance(active_report, dict) else None
        if isinstance(active_report, dict) and not any(
            prior.get("report_id") == active_report.get("report_id") for prior in prior_reports
        ):
            # JSON and PostgreSQL repositories may order versions by ID. Always
            # include the active version, which carries the latest cumulative history.
            prior_reports.append(active_report)

        def publication_order(item: tuple[int, dict]) -> tuple[float, int]:
            index, prior_report = item
            if active_report_id and prior_report.get("report_id") == active_report_id:
                return float("inf"), index
            raw_timestamp = prior_report.get("published_at") or prior_report.get("generated_at")
            try:
                timestamp = datetime.fromisoformat(str(raw_timestamp).replace("Z", "+00:00"))
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=timezone.utc)
                return timestamp.timestamp(), index
            except (TypeError, ValueError, OverflowError):
                return float("-inf"), index

        # Version repositories can return rows in ID order, which is not
        # necessarily publication order (especially for worker-generated IDs).
        ordered_reports = sorted(enumerate(reversed(prior_reports)), key=publication_order)
        for _, prior_report in ordered_reports:
            # Newer report versions carry a cumulative history. Merge it first;
            # the current reading below remains authoritative for its date.
            prior_history = prior_report.get("_antam_gold_history")
            for point in prior_history if isinstance(prior_history, list) else []:
                if not isinstance(point, dict):
                    continue
                prior_day = source_date_iso(point.get("date") or point.get("dates"))
                prior_value = point.get("close")
                prior_series = point.get("series_id") or "legacy_antam"
                if prior_day and isinstance(prior_value, (int, float)) \
                        and not isinstance(prior_value, bool) and math.isfinite(prior_value):
                    observations[(prior_series, prior_day)] = float(prior_value)

            prior_snapshot = prior_report.get("_source_snapshot")
            prior_snapshot = prior_snapshot if isinstance(prior_snapshot, dict) else {}
            prior_source_reading = prior_snapshot.get("antam_gold")
            if isinstance(prior_source_reading, dict):
                prior_day = source_date_iso(prior_source_reading.get("date"))
                prior_value = prior_source_reading.get("price")
                prior_series = prior_source_reading.get("series_id") or "legacy_antam"
                if prior_day and _valid_price(prior_value):
                    observations[(prior_series, prior_day)] = float(prior_value)

            prior_reading = (prior_report.get("commodities") or {}).get("Emas Antam 1 gr (Rp)", {})
            prior_day = source_date_iso(prior_reading.get("date"))
            prior_value = prior_reading.get("today")
            prior_series = prior_reading.get("series_id") or "legacy_antam"
            if prior_day and isinstance(prior_value, (int, float)) and not isinstance(prior_value, bool) \
                    and math.isfinite(prior_value):
                observations[(prior_series, prior_day)] = float(prior_value)

        previous_days = [day for source, day in observations if source == series_id and antam_day and day < antam_day]
        if previous_days:
            antam["prev"] = observations[(series_id, max(previous_days))]
            antam["change_pct"] = round(
                (float(antam["price"]) - antam["prev"]) / antam["prev"] * 100, 4
            ) if antam["prev"] else None
        if antam_day:
            observations[(series_id, antam_day)] = float(antam["price"])
            snapshot["_antam_gold_history"] = [
                {"date": day, "close": value, "series_id": source}
                for source in sorted({key[0] for key in observations})
                for day, value in sorted(
                    (key[1], value) for key, value in observations.items() if key[0] == source
                )[-MAX_HISTORY_POINTS:]
            ]

    candidate = build_report_data(snapshot)
    sbn10 = market_facts(candidate).get("sbn10", {})
    history = load_sbn_history()
    if sbn10.get("today") is not None and sbn10.get("date"):
        from market_report.services.history_service import source_date_iso

        date = source_date_iso(sbn10["date"])
        if date:
            history = [point for point in history if point.get("date") != date]
            history.append({"date": date, "close": float(sbn10["today"])})
            history.sort(key=lambda point: point.get("date", ""), reverse=True)
            history = history[:420]
    snapshot["_sbn_history"] = history
    guard = publication_guard() if publication_guard else nullcontext()
    with guard:
        report = publish_snapshot(snapshot, report_id=report_id)

    # Riwayat SBN dikumpulkan saat pipeline menerbitkan laporan, bukan saat
    # halaman dashboard dibuka. Kegagalan pencatatan riwayat tidak membatalkan laporan.
    try:
        if sbn10.get("today") is not None:
            record_sbn_history(sbn10["today"], sbn10.get("date"))
    except Exception:
        _logger.exception("Gagal memperbarui riwayat SBN setelah laporan diterbitkan")
    return report


def rebuild_from_saved_snapshot() -> dict:
    """Bangun ulang laporan dengan snapshot yang sudah tersimpan tanpa fetch."""
    snapshot = load_snapshot()
    if not snapshot:
        raise RuntimeError("Snapshot sumber belum tersedia untuk dibangun ulang.")
    return publish_snapshot(snapshot)


def save_demo_report(report: dict, path: Path | None = None) -> Path:
    """Simpan data demo terpisah agar tidak mengganti laporan live yang aktif."""
    from market_report.calculate import persist_report_data

    report = dict(report)
    report.update({"schema_version": 1, "is_demo": True})
    demo_path = path or _DEMO_REPORT_PATH
    persist_report_data(report, demo_path)
    return demo_path

"""Scheduler ringan yang memasukkan refresh terjadwal ke antrean PostgreSQL."""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, time as clock_time, timedelta, timezone as fixed_timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market_report.config import load_environment
from market_report.services.job_repository import PostgresJobRepository


_logger = logging.getLogger("market_report.scheduler")


def parse_refresh_times(value: str) -> list[clock_time]:
    times = []
    for item in value.split(","):
        try:
            times.append(datetime.strptime(item.strip(), "%H:%M").time())
        except ValueError as error:
            raise ValueError(f"Format REFRESH_TIMES tidak valid: {item!r}. Gunakan HH:MM.") from error
    if not times:
        raise ValueError("REFRESH_TIMES harus berisi setidaknya satu waktu HH:MM.")
    return sorted(set(times))


def resolve_timezone(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        # Windows sering tidak menyertakan IANA tzdata; Jakarta tidak memakai DST.
        if name == "Asia/Jakarta":
            return fixed_timezone(timedelta(hours=7), name="Asia/Jakarta")
        raise


def dispatch_due_slots(repository, schedule_name: str, now: datetime,
                       refresh_times: list[clock_time], catchup_minutes: int) -> int:
    dispatched = 0
    for scheduled_time in refresh_times:
        slot = datetime.combine(now.date(), scheduled_time, tzinfo=now.tzinfo)
        delay = now - slot
        if delay < timedelta(0) or delay > timedelta(minutes=catchup_minutes):
            continue
        result = repository.enqueue_scheduled_refresh(schedule_name, slot)
        job = result["job"]
        if result["scheduled"]:
            dispatched += 1
            _logger.info("Slot %s memasukkan job %s (%s)", slot.isoformat(), job["job_id"], job["status"])
    return dispatched


def main() -> int:
    parser = argparse.ArgumentParser(description="Scheduler refresh Daily Market Report")
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--once", action="store_true", help="Periksa slot saat ini satu kali lalu keluar")
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds harus lebih besar dari nol")

    load_environment()
    raw_times = os.environ.get("REFRESH_TIMES", "").strip()
    if not raw_times:
        raise SystemExit("REFRESH_TIMES belum diatur; isi satu atau lebih waktu HH:MM di .env.")
    try:
        refresh_times = parse_refresh_times(raw_times)
        timezone = resolve_timezone(os.environ.get("REFRESH_TIMEZONE", "Asia/Jakarta").strip())
    except (ValueError, ZoneInfoNotFoundError) as error:
        raise SystemExit(str(error)) from None
    schedule_name = os.environ.get("REFRESH_SCHEDULE_NAME", "daily-market-report").strip()
    if not schedule_name:
        raise SystemExit("REFRESH_SCHEDULE_NAME tidak boleh kosong.")
    try:
        catchup_minutes = int(os.environ.get("REFRESH_CATCHUP_MINUTES", "10"))
    except ValueError:
        raise SystemExit("REFRESH_CATCHUP_MINUTES harus berupa bilangan bulat.") from None
    if catchup_minutes < 0:
        raise SystemExit("REFRESH_CATCHUP_MINUTES tidak boleh negatif.")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    repository = PostgresJobRepository.from_environment()
    _logger.info("Scheduler aktif pada zona %s, waktu %s", timezone.key, raw_times)
    while True:
        try:
            dispatch_due_slots(repository, schedule_name, datetime.now(timezone), refresh_times, catchup_minutes)
        except Exception:
            _logger.exception("Gagal memeriksa jadwal refresh")
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

"""Worker polling untuk mengeksekusi job refresh yang persisten."""

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.job_repository import PostgresJobRepository
from services.report_service import run_live_pipeline


_logger = logging.getLogger("market_report.worker")


def process_one(repository: PostgresJobRepository) -> bool:
    job = repository.claim_next()
    if job is None:
        return False
    job_id = job["job_id"]
    _logger.info("Memproses refresh job %s (percobaan %s)", job_id, job["attempt"])
    try:
        report = run_live_pipeline()
    except Exception as error:
        _logger.exception("Refresh job %s gagal", job_id)
        repository.fail(job_id, error)
    else:
        # Jika pencatatan selesai gagal setelah laporan terbit, lease akan dipulihkan
        # worker setelah 15 menit; report aktif sendiri sudah ditulis atomik.
        repository.complete(job_id, report.get("report_id"))
        _logger.info("Refresh job %s selesai, report_id=%s", job_id, report.get("report_id"))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Worker Daily Market Report")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--once", action="store_true", help="Proses maksimal satu job lalu keluar")
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds harus lebih besar dari nol")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    repository = PostgresJobRepository.from_environment()
    _logger.info("Worker dimulai; interval polling %.1f detik", args.poll_seconds)
    while True:
        try:
            processed = process_one(repository)
        except Exception:
            _logger.exception("Worker gagal memproses antrean")
            if args.once:
                return 1
            processed = False
        if args.once:
            return 0
        if not processed:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

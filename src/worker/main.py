"""Worker polling untuk mengeksekusi job refresh yang persisten."""

import argparse
import logging
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.job_repository import PostgresJobRepository
from services import export_service, history_service
from services.report_service import run_live_pipeline


_logger = logging.getLogger("market_report.worker")


def process_one(repository: PostgresJobRepository) -> bool:
    job = repository.claim_next()
    if job is None:
        return False
    job_id = job["job_id"]
    owner_token = job["owner_token"]
    _logger.info("Memproses refresh job %s (percobaan %s)", job_id, job["attempt"])
    stop_heartbeat = threading.Event()
    lease_lost = threading.Event()

    def keep_lease_alive() -> None:
        while not stop_heartbeat.wait(30):
            try:
                if not repository.heartbeat(job_id, owner_token):
                    lease_lost.set()
                    _logger.error("Worker kehilangan lease job %s", job_id)
                    return
            except Exception:
                _logger.exception("Gagal memperbarui lease job %s", job_id)
                lease_lost.set()
                return

    heartbeat_thread = threading.Thread(target=keep_lease_alive, daemon=True)
    heartbeat_thread.start()
    try:
        report = run_live_pipeline(
            publication_guard=lambda: repository.publication_guard(job_id, owner_token)
        )
    except Exception as error:
        _logger.exception("Refresh job %s gagal", job_id)
        if not lease_lost.is_set():
            repository.fail(job_id, owner_token, error)
    else:
        try:
            project_root = Path(__file__).resolve().parents[2]
            history = history_service.load_sbn_history()
            pdf_path = export_service.save_report_pdf(report, history, project_root / "reports")
            _logger.info("PDF laporan %s disimpan ke %s", report.get("report_id"), pdf_path)
        except Exception:
            # Laporan sudah terbit. Kegagalan PDF dicatat tanpa mengulang publikasi report.
            _logger.exception("Gagal membuat PDF untuk laporan %s", report.get("report_id"))
        if repository.complete(job_id, owner_token, report.get("report_id")):
            _logger.info("Refresh job %s selesai, report_id=%s", job_id, report.get("report_id"))
        else:
            _logger.error("Hasil job %s terbit, tetapi lease sudah tidak dimiliki worker ini", job_id)
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=2)
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

"""Worker polling untuk mengeksekusi job refresh yang persisten."""

import argparse
import logging
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from market_report.infrastructure.repositories.job_repository import PostgresJobRepository
from market_report.services import export_service, history_service
from market_report.services import report_service
from market_report.config import report_artifact_directory


_logger = logging.getLogger("market_report.worker")


def process_one(repository: PostgresJobRepository) -> bool:
    job = repository.claim_next()
    if job is None:
        return False
    job_id = job["job_id"]
    owner_token = job["owner_token"]
    _logger.info("Memproses job %s jenis %s (percobaan %s)", job_id, job["job_type"], job["attempt"])
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
        if job["job_type"] == "refresh":
            report = report_service.run_live_pipeline(
                publication_guard=lambda: repository.publication_guard(job_id, owner_token)
            )
        elif job["job_type"] == "export_pdf":
            report = report_service.load_report_version(job.get("report_id"))
            if report is None:
                raise RuntimeError("Versi laporan untuk ekspor tidak ditemukan.")
        else:
            raise RuntimeError(f"Jenis job tidak didukung: {job['job_type']}")
    except Exception as error:
        _logger.exception("Job %s gagal", job_id)
        if not lease_lost.is_set():
            repository.fail(job_id, owner_token, error)
    else:
        try:
            version_history = report.get("_sbn_history")
            history = version_history if isinstance(version_history, list) else history_service.load_sbn_history()
            with repository.ownership_guard(job_id, owner_token):
                pdf_path, download_name = export_service.save_report_pdf(
                    report, history, report_artifact_directory(),
                    storage_prefix=f"{job_id}_",
                )
                artifact = repository.record_pdf_artifact(
                    report["report_id"], download_name, pdf_path.name
                )
            _logger.info("PDF laporan %s disimpan sebagai artefak %s", report.get("report_id"), artifact["artifact_id"])
        except Exception:
            if job["job_type"] == "export_pdf":
                _logger.exception("Ekspor PDF untuk laporan %s gagal", report.get("report_id"))
                if not lease_lost.is_set():
                    repository.fail(job_id, owner_token, RuntimeError("pdf_export_failed"))
                return True
            # Laporan sudah terbit. Kegagalan PDF tidak mengulang publikasi report.
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

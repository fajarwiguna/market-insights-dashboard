from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Callable


def worker_refresh_enabled() -> bool:
    from market_report.config import load_environment

    load_environment()
    return bool(os.environ.get("DATABASE_URL", "").strip())


def request_refresh() -> dict:
    """Antrekan refresh pada PostgreSQL; gunakan pipeline langsung untuk mode JSON lokal."""
    if worker_refresh_enabled():
        from market_report.infrastructure.repositories.job_repository import PostgresJobRepository

        return {"mode": "queued", "job": PostgresJobRepository.from_environment().enqueue_refresh()}

    from market_report.services.report_service import run_live_pipeline

    return {"mode": "completed", "report": run_live_pipeline()}


def get_refresh_job(job_id: str) -> dict | None:
    from market_report.infrastructure.repositories.job_repository import PostgresJobRepository

    return PostgresJobRepository.from_environment().get_job(job_id)


def trigger_and_wait_refresh(
    timeout: float = 180.0,
    poll_interval: float = 2.0,
    on_progress: Callable[[float], None] | None = None,
) -> dict:
    """Memicu refresh dan (bila mode antrean) menunggu worker menyelesaikannya."""
    from market_report.config import load_environment

    load_environment()
    result = request_refresh()
    if result.get("mode") == "completed":
        return result

    job = result.get("job")
    if not job or "job_id" not in job:
        raise RuntimeError("Gagal memasukkan job refresh ke antrean.")

    job_id = job["job_id"]
    start_time = time.time()
    elapsed = 0.0
    while elapsed < timeout:
        current_job = get_refresh_job(job_id)
        if current_job:
            status = current_job.get("status")
            if status == "succeeded":
                return {
                    "mode": "completed",
                    "job": current_job,
                    "report_id": current_job.get("report_id"),
                }
            if status == "failed":
                error_code = current_job.get("error_code") or "unknown_error"
                raise RuntimeError(f"Job refresh {job_id} gagal diproses worker: {error_code}")
        time.sleep(poll_interval)
        elapsed = time.time() - start_time
        if on_progress:
            on_progress(elapsed)

    raise TimeoutError(f"Job refresh {job_id} melebihi batas waktu tunggu ({timeout:.0f} detik).")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pemicu refresh data Daily Market Report")
    parser.add_argument("--wait", action="store_true", help="Tunggu hingga proses refresh selesai")
    parser.add_argument("--timeout", type=float, default=180.0, help="Batas waktu tunggu dalam detik")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        if args.wait:
            print("Memulai penarikan data pasar...")
            last_reported = 0

            def report_progress(seconds: float) -> None:
                nonlocal last_reported
                if int(seconds) - last_reported >= 10:
                    last_reported = int(seconds)
                    print(f"Menunggu worker menyinkronkan data ke database... ({last_reported} detik)")

            res = trigger_and_wait_refresh(timeout=args.timeout, on_progress=report_progress)
            report_id = (
                res.get("report_id")
                or (res.get("job") or {}).get("report_id")
                or (res.get("report") or {}).get("report_id")
            )
            print(f"Pembaruan data selesai (report_id: {report_id}).")
        else:
            res = request_refresh()
            if res.get("mode") == "queued":
                print(f"Job refresh telah dimasukkan ke antrean (ID: {res['job']['job_id']}).")
            else:
                report_id = (res.get("report") or {}).get("report_id")
                print(f"Pembaruan data selesai (report_id: {report_id}).")
        return 0
    except Exception as error:
        print(f"Gagal melakukan refresh data: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())

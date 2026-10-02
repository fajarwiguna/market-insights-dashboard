"""Contract API, dispatch scheduler, dan alur worker tanpa menulis ke database lokal."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, time, timezone
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from fastapi import HTTPException  # noqa: E402
from fastapi.security import HTTPAuthorizationCredentials  # noqa: E402
from market_report.api.dependencies import require_operator_access, require_read_access  # noqa: E402
from market_report.api.routers import jobs, reports  # noqa: E402
from market_report.scheduler.main import dispatch_due_slots  # noqa: E402
from market_report.worker import main as worker_main  # noqa: E402


class ApiContractTests(unittest.TestCase):
    @patch.dict(os.environ, {"API_READ_TOKEN": "test-read-token"})
    def test_report_requires_read_token(self):
        with self.assertRaises(HTTPException) as missing:
            require_read_access(None)
        self.assertEqual(missing.exception.status_code, 401)
        with self.assertRaises(HTTPException) as invalid:
            require_read_access(HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong-token"))
        self.assertEqual(invalid.exception.status_code, 401)
        require_read_access(HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-read-token"))

    @patch.dict(os.environ, {"API_READ_TOKEN": "test-read-token"})
    @patch("market_report.api.routers.reports.report_service.load_report")
    def test_report_returns_contract_with_valid_token(self, load_report):
        load_report.return_value = {
            "report_id": "report-test",
            "schema_version": 1,
            "report_date": "2 Oktober 2026",
            "report_date_iso": "2026-10-02",
            "fx": {},
            "indices": {},
            "yields": {},
            "commodities": {},
            "sources": [],
            "_private_snapshot": {"internal": True},
        }
        result = reports.read_latest_report()
        self.assertEqual(result["report_id"], "report-test")
        self.assertNotIn("_private_snapshot", result)

    @patch.dict(os.environ, {"API_OPERATOR_TOKEN": "test-operator-token"})
    def test_operator_token_is_separate_from_read_token(self):
        with self.assertRaises(HTTPException) as invalid:
            require_operator_access(HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-read-token"))
        self.assertEqual(invalid.exception.status_code, 401)
        require_operator_access(HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-operator-token"))

    @patch("market_report.api.routers.jobs.PostgresJobRepository.from_environment")
    def test_refresh_route_enqueues_job(self, from_environment):
        job = {
            "job_id": "b4dd4f91-c740-4a8a-89e5-1796fd3ab2ca",
            "job_type": "refresh",
            "status": "queued",
            "attempts": 0,
            "max_attempts": 3,
            "dates": "2026-10-02T08:00:00+00:00",
            "report_id": None,
            "error_code": None,
            "events": [],
        }
        repository = from_environment.return_value
        repository.enqueue_refresh.return_value = job
        response = jobs.enqueue_refresh()
        self.assertEqual(response["job_id"], job["job_id"])
        repository.enqueue_refresh.assert_called_once_with()


class FakeJobRepository:
    def __init__(self, job):
        self.job = job
        self.completed = []
        self.failed = []
        self.artifacts = []
        self.publication_guard_used = False

    def claim_next(self):
        return self.job

    @contextmanager
    def ownership_guard(self, _job_id, _owner_token):
        yield

    @contextmanager
    def publication_guard(self, _job_id, _owner_token):
        self.publication_guard_used = True
        yield

    def record_pdf_artifact(self, report_id, file_name, storage_key):
        item = {
            "artifact_id": "artifact-test",
            "report_id": report_id,
            "file_name": file_name,
            "storage_key": storage_key,
        }
        self.artifacts.append(item)
        return item

    def complete(self, job_id, owner_token, report_id):
        self.completed.append((job_id, owner_token, report_id))
        return True

    def fail(self, job_id, owner_token, error):
        self.failed.append((job_id, owner_token, str(error)))
        return True


class WorkerAndSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.artifact_directory = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def make_job(self, job_type, report_id=None):
        return {
            "job_id": "job-test",
            "owner_token": "owner-test",
            "job_type": job_type,
            "report_id": report_id,
            "attempt": 1,
        }

    @patch("market_report.worker.main.report_artifact_directory")
    @patch("market_report.worker.main.export_service.save_report_pdf")
    @patch("market_report.worker.main.report_service.run_live_pipeline")
    def test_refresh_worker_publishes_pdf_and_completes_job(
        self, run_pipeline, save_pdf, artifact_directory
    ):
        report = {"report_id": "report-test", "_sbn_history": []}

        def publish_with_guard(publication_guard):
            with publication_guard():
                return report

        run_pipeline.side_effect = publish_with_guard
        pdf_path = self.artifact_directory / "job-test_Daily_Market_Update_20261002.pdf"
        save_pdf.return_value = (pdf_path, "Daily_Market_Update_20261002.pdf")
        artifact_directory.return_value = self.artifact_directory
        repository = FakeJobRepository(self.make_job("refresh"))

        self.assertTrue(worker_main.process_one(repository))
        run_pipeline.assert_called_once()
        self.assertTrue(repository.publication_guard_used)
        self.assertEqual(repository.artifacts[0]["storage_key"], pdf_path.name)
        self.assertEqual(repository.completed[0][2], "report-test")
        self.assertFalse(repository.failed)

    @patch("market_report.worker.main.report_artifact_directory")
    @patch("market_report.worker.main.export_service.save_report_pdf")
    @patch("market_report.worker.main.report_service.load_report_version")
    def test_export_worker_fails_job_when_pdf_generation_fails(
        self, load_version, save_pdf, artifact_directory
    ):
        load_version.return_value = {"report_id": "report-test"}
        save_pdf.side_effect = OSError("disk unavailable")
        artifact_directory.return_value = self.artifact_directory
        repository = FakeJobRepository(self.make_job("export_pdf", "report-test"))

        self.assertTrue(worker_main.process_one(repository))
        self.assertFalse(repository.completed)
        self.assertEqual(repository.failed[0][2], "pdf_export_failed")

    def test_scheduler_dispatches_only_due_and_not_already_scheduled_slots(self):
        class ScheduleRepository:
            def __init__(self):
                self.slots = []

            def enqueue_scheduled_refresh(self, name, slot):
                self.slots.append((name, slot))
                return {"scheduled": len(self.slots) == 1, "job": {"job_id": "job-test", "status": "queued"}}

        now = datetime(2026, 10, 2, 16, 32, tzinfo=timezone.utc)
        repository = ScheduleRepository()
        dispatched = dispatch_due_slots(
            repository,
            "daily-market-report",
            now,
            [time(16, 30), time(17, 0)],
            catchup_minutes=5,
        )
        self.assertEqual(dispatched, 1)
        self.assertEqual(len(repository.slots), 1)
        self.assertEqual(repository.slots[0][1].hour, 16)


if __name__ == "__main__":
    unittest.main()

"""Antrean job refresh PostgreSQL yang aman dipakai oleh API dan worker terpisah."""

from __future__ import annotations

import os
import uuid


class PostgresJobRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL belum diatur.")
        self.database_url = database_url

    @classmethod
    def from_environment(cls):
        from config import load_environment

        load_environment()
        return cls(os.environ.get("DATABASE_URL", "").strip())

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("Job worker memerlukan psycopg dari requirements.txt.") from error
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def enqueue_refresh(self) -> dict:
        job_id = uuid.uuid4()
        with self._connect() as connection:
            row = connection.execute(
                """INSERT INTO refresh_jobs (job_id, job_type, status)
                   VALUES (%s, 'refresh', 'queued')
                   ON CONFLICT (job_type) WHERE status IN ('queued', 'running') DO NOTHING
                   RETURNING job_id::text, job_type, status, attempts, max_attempts, dates, report_id, error_code""",
                (job_id,),
            ).fetchone()
            if row:
                connection.execute(
                    "INSERT INTO refresh_job_events (job_id, status, details) VALUES (%s, 'queued', '{}'::jsonb)",
                    (job_id,),
                )
                active = row
            else:
                active = connection.execute(
                    """SELECT job_id::text, job_type, status, attempts, max_attempts, dates, report_id, error_code
                       FROM refresh_jobs WHERE job_type = 'refresh' AND status IN ('queued', 'running')"""
                ).fetchone()
        if active is None:
            raise RuntimeError("Job refresh gagal dibuat atau ditemukan.")
        return self.get_job(active["job_id"])

    def get_job(self, job_id: str) -> dict | None:
        try:
            normalized_id = uuid.UUID(str(job_id))
        except (ValueError, TypeError, AttributeError):
            return None
        with self._connect() as connection:
            row = connection.execute(
                """SELECT job_id::text, job_type, status, attempts, max_attempts, dates, report_id, error_code
                   FROM refresh_jobs WHERE job_id = %s""",
                (normalized_id,),
            ).fetchone()
            if row is None:
                return None
            events = connection.execute(
                "SELECT status, dates, details FROM refresh_job_events WHERE job_id = %s ORDER BY dates, event_id",
                (normalized_id,),
            ).fetchall()
        result = dict(row)
        result["dates"] = result["dates"].isoformat()
        result["events"] = [
            {**event, "dates": event["dates"].isoformat()}
            for event in events
        ]
        return result

    def claim_next(self) -> dict | None:
        """Ambil satu job; job running yang macet lebih dari 15 menit dipulihkan."""
        with self._connect() as connection:
            stale_jobs = connection.execute(
                """SELECT j.job_id, j.attempts, j.max_attempts
                   FROM refresh_jobs j
                   WHERE j.status = 'running'
                     AND (SELECT max(e.dates) FROM refresh_job_events e
                          WHERE e.job_id = j.job_id AND e.status = 'running') < now() - interval '15 minutes'
                   FOR UPDATE"""
            ).fetchall()
            for stale in stale_jobs:
                status = "failed" if stale["attempts"] >= stale["max_attempts"] else "queued"
                connection.execute(
                    "UPDATE refresh_jobs SET status = %s, error_code = 'worker_lease_expired' WHERE job_id = %s",
                    (status, stale["job_id"]),
                )
                connection.execute(
                    """INSERT INTO refresh_job_events (job_id, status, details)
                       VALUES (%s, %s, '{"reason":"worker_lease_expired"}'::jsonb)""",
                    (stale["job_id"], status),
                )

            row = connection.execute(
                """SELECT job_id, job_type, attempts, max_attempts FROM refresh_jobs
                   WHERE status = 'queued' ORDER BY dates, job_id LIMIT 1 FOR UPDATE SKIP LOCKED"""
            ).fetchone()
            if row is None:
                return None
            attempt = row["attempts"] + 1
            connection.execute(
                "UPDATE refresh_jobs SET status = 'running', attempts = %s, error_code = NULL WHERE job_id = %s",
                (attempt, row["job_id"]),
            )
            connection.execute(
                """INSERT INTO refresh_job_events (job_id, status, details)
                   VALUES (%s, 'running', jsonb_build_object('attempt', %s))""",
                (row["job_id"], attempt),
            )
            return {"job_id": str(row["job_id"]), "job_type": row["job_type"], "attempt": attempt}

    def complete(self, job_id: str, report_id: str | None) -> None:
        self._transition(job_id, "succeeded", report_id=report_id)

    def fail(self, job_id: str, error: Exception) -> None:
        job_uuid = uuid.UUID(str(job_id))
        with self._connect() as connection:
            job = connection.execute(
                "SELECT attempts, max_attempts FROM refresh_jobs WHERE job_id = %s FOR UPDATE",
                (job_uuid,),
            ).fetchone()
            if job is None:
                return
            status = "queued" if job["attempts"] < job["max_attempts"] else "failed"
            code = type(error).__name__[:80]
            connection.execute(
                "UPDATE refresh_jobs SET status = %s, error_code = %s WHERE job_id = %s",
                (status, code, job_uuid),
            )
            connection.execute(
                """INSERT INTO refresh_job_events (job_id, status, details)
                   VALUES (%s, %s, jsonb_build_object('error_code', %s))""",
                (job_uuid, status, code),
            )

    def _transition(self, job_id: str, status: str, *, report_id: str | None = None) -> None:
        job_uuid = uuid.UUID(str(job_id))
        with self._connect() as connection:
            connection.execute(
                "UPDATE refresh_jobs SET status = %s, report_id = %s, error_code = NULL WHERE job_id = %s",
                (status, report_id, job_uuid),
            )
            connection.execute(
                "INSERT INTO refresh_job_events (job_id, status, details) VALUES (%s, %s, '{}'::jsonb)",
                (job_uuid, status),
            )

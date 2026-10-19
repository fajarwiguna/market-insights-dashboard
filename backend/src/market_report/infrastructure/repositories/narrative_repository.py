"""Repository audit trail narasi di PostgreSQL (migrasi 017).

Berkas audit di `runtime/narrative/audit/` tetap menjadi catatan utama; tabel
ini menambahkan pencarian dan penelusuran per run. Kegagalan database tidak
boleh menggagalkan narasi, jadi setiap pemanggilan dari engine dibungkus
try/except di pemanggil.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterable, Sequence

logger = logging.getLogger(__name__)


class PostgresNarrativeRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("DATABASE_URL belum diatur.")
        self.database_url = database_url

    @classmethod
    def from_environment(cls) -> "PostgresNarrativeRepository | None":
        """Kembalikan None bila database belum dikonfigurasi (narasi tetap jalan)."""
        from market_report.config import load_environment

        try:
            load_environment()
        except Exception:  # pragma: no cover - .env opsional
            pass
        url = os.environ.get("DATABASE_URL", "").strip()
        if not url:
            return None
        try:
            return cls(url)
        except ValueError:
            return None

    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:  # pragma: no cover - psycopg ada di requirements
            raise RuntimeError("Audit narasi memerlukan psycopg dari requirements.txt.") from error
        return psycopg.connect(self.database_url, row_factory=dict_row)

    # ── penulisan ───────────────────────────────────────────────

    def save_run(self, record: dict, *, narrative: str = "", output: dict | None = None,
                 published: bool = False, evidence: Sequence[dict] = (),
                 claims: Sequence[dict] = ()) -> bool:
        """Simpan satu run narasi; idempoten terhadap `run_id` yang sama."""
        row = {
            "run_id": str(record.get("run_id") or ""),
            "page": str(record.get("page") or "dashboard"),
            "report_id": str(record.get("report_id") or ""),
            "report_date": str(record.get("report_date") or ""),
            "status": str(record.get("status") or "fallback"),
            "reason": record.get("reason") or None,
            "rules_path": record.get("rules_path") or None,
            "rules_hash": str(record.get("rules_hash") or ""),
            "prompt_version": str(record.get("prompt_version") or ""),
            "provider": str(record.get("provider") or "none"),
            "model": record.get("model") or None,
            "context_hash": str(record.get("context_hash") or ""),
            "cache_key": record.get("cache_key") or None,
            "latency_ms": int(record.get("latency_ms") or 0),
            "tokens_in": int(record.get("tokens_in") or 0),
            "tokens_out": int(record.get("tokens_out") or 0),
            "cost_usd": float(record.get("cost_usd") or 0.0),
            "repair_count": int(record.get("repair_count") or 0),
            "evidence_count": int(record.get("evidence_count") or 0),
            "validation": json.dumps(record.get("validation") or {}),
        }
        if not row["report_date"]:
            # Kolom report_date NOT NULL; run tanpa tanggal (mis. konteks halaman
            # tidak tersedia) tetap tercatat di berkas audit JSONL, bukan di sini.
            logger.info("Audit narasi PostgreSQL dilewati: report_date kosong (run_id=%s).",
                        row["run_id"])
            return False
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO narrative_runs (
                       run_id, page, report_id, report_date, status, reason, rules_path, rules_hash,
                       prompt_version, provider, model, context_hash, cache_key, latency_ms,
                       tokens_in, tokens_out, cost_usd, repair_count, evidence_count, validation, dates)
                   VALUES (
                       %(run_id)s, %(page)s, %(report_id)s, %(report_date)s, %(status)s, %(reason)s,
                       %(rules_path)s, %(rules_hash)s, %(prompt_version)s, %(provider)s, %(model)s,
                       %(context_hash)s, %(cache_key)s, %(latency_ms)s, %(tokens_in)s, %(tokens_out)s,
                       %(cost_usd)s, %(repair_count)s, %(evidence_count)s, %(validation)s::jsonb, now())
                   ON CONFLICT (run_id) DO NOTHING""",
                row,
            )
            if narrative or output:
                connection.execute(
                    """INSERT INTO narrative_outputs (run_id, narrative_json, rendered_text, published)
                       VALUES (%s, %s::jsonb, %s, %s)
                       ON CONFLICT (run_id) DO UPDATE SET
                           narrative_json = EXCLUDED.narrative_json,
                           rendered_text = EXCLUDED.rendered_text,
                           published = EXCLUDED.published""",
                    (row["run_id"], json.dumps(output or {}), narrative, published),
                )
            self._save_evidence(connection, row["run_id"], evidence)
            self._save_claims(connection, row["run_id"], claims)
        return True

    def _save_evidence(self, connection, run_id: str, evidence: Iterable[dict]) -> None:
        rows = list(evidence or [])
        if not rows:
            return
        used_ids = set()
        with connection.cursor() as cursor:
            for item in rows:
                used_ids.add(str(item.get("evidence_id") or ""))
                cursor.execute(
                    """INSERT INTO narrative_evidence (
                           run_id, evidence_id, url, source, source_tier, published_at, relevance,
                           used_in_claims, snippet)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (run_id, evidence_id) DO UPDATE SET
                           url = EXCLUDED.url, relevance = EXCLUDED.relevance,
                           used_in_claims = EXCLUDED.used_in_claims, snippet = EXCLUDED.snippet""",
                    (run_id, str(item.get("evidence_id") or ""), str(item.get("url") or ""),
                     str(item.get("source") or ""), str(item.get("source_tier") or "secondary"),
                     (item.get("published_at") or None), item.get("relevance"), False,
                     (item.get("summary") or "")[:500]),
                )

    def _save_claims(self, connection, run_id: str, claims: Iterable[dict]) -> None:
        rows = list(claims or [])
        if not rows:
            return
        with connection.cursor() as cursor:
            for claim in rows:
                cursor.execute(
                    """INSERT INTO narrative_claims (
                           run_id, claim_id, text, claim_type, evidence_ids, accepted, rejected_reason)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (run_id, claim_id) DO UPDATE SET
                           accepted = EXCLUDED.accepted, rejected_reason = EXCLUDED.rejected_reason""",
                    (run_id, str(claim.get("claim_id") or ""), str(claim.get("text") or "")[:2000],
                     str(claim.get("claim_type") or claim.get("type") or "statement"),
                     [str(value) for value in (claim.get("evidence_ids") or [])],
                     bool(claim.get("accepted", True)), claim.get("rejected_reason") or None),
                )
            used = {str(value) for claim in rows if claim.get("accepted")
                    for value in (claim.get("evidence_ids") or [])}
            for evidence_id in used:
                cursor.execute(
                    """UPDATE narrative_evidence SET used_in_claims = TRUE
                       WHERE run_id = %s AND evidence_id = %s""",
                    (run_id, evidence_id),
                )

    # ── pembacaan ───────────────────────────────────────────────

    def recent_runs(self, page: str = "", limit: int = 20) -> list[dict]:
        query = """SELECT run_id, page, report_id, report_date, status, reason, provider, model,
                          latency_ms, tokens_in, tokens_out, cost_usd, repair_count,
                          evidence_count, rules_hash, prompt_version, dates
                   FROM narrative_runs"""
        params: list[object] = []
        if page:
            query += " WHERE page = %s"
            params.append(page)
        query += " ORDER BY dates DESC LIMIT %s"
        params.append(int(limit))
        with self._connect() as connection:
            return [dict(row) for row in connection.execute(query, params).fetchall()]

    def get_run(self, run_id: str) -> dict | None:
        with self._connect() as connection:
            run = connection.execute(
                """SELECT run_id, page, report_id, report_date, status, reason, rules_hash,
                          prompt_version, provider, model, latency_ms, tokens_in, tokens_out,
                          cost_usd, repair_count, evidence_count, validation, dates
                   FROM narrative_runs WHERE run_id = %s""",
                (run_id,),
            ).fetchone()
            if not run:
                return None
            details = dict(run)
            details["evidence"] = [dict(row) for row in connection.execute(
                """SELECT evidence_id, url, source, source_tier, published_at, relevance, used_in_claims
                   FROM narrative_evidence WHERE run_id = %s ORDER BY evidence_id""",
                (run_id,),
            ).fetchall()]
            details["claims"] = [dict(row) for row in connection.execute(
                """SELECT claim_id, claim_type, accepted, rejected_reason, evidence_ids
                   FROM narrative_claims WHERE run_id = %s ORDER BY claim_id""",
                (run_id,),
            ).fetchall()]
            output = connection.execute(
                """SELECT narrative_json, rendered_text, published FROM narrative_outputs
                   WHERE run_id = %s""",
                (run_id,),
            ).fetchone()
            details["output"] = dict(output) if output else None
            return details

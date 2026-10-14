"""Repository time-series (katalog metadata + observasi) dengan backend JSON atau PostgreSQL.

Model mengikuti `panduan_penamaan.md`:
- setiap dataset adalah tabel fisik wide `{cakupan}_{Subjek}_{sumber}_{frekuensi}`
  dengan kolom `dates` sebagai primary key dan satu kolom per series;
- katalog metadata ada di `meta_table` (satu baris per tabel) dan
  `meta_timeseries` (satu baris per series).

Backend JSON menyimpan metadata ke berkas dan observasi per `series_id`;
backend PostgreSQL memakai tabel fisik sebenarnya.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
# Nama tabel memakai PascalCase pada komponen Subjek; nama kolom lowercase.
_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _quoted(name: str) -> str:
    """Kutip identifier tabel/kolom setelah dipastikan bentuknya aman."""
    if not _IDENTIFIER.fullmatch(str(name or "")):
        raise ValueError(f"Identifier tidak aman: {name!r}")
    return f'"{name}"'


def _meta_series_row(series: dict) -> dict:
    """Terjemahkan satu entri katalog menjadi baris `meta_timeseries`."""
    return {
        "id": series["series_id"],
        "table_name": series["table"],
        "series_name": series["series_name"],
        "series_id": series["series_id"],
        "data_type": series.get("data_type") or "NUMERIC(19,6)",
        "description": series.get("description") or "",
        "unit": series.get("unit"),
        "source": series.get("source"),
        "tag": series.get("tag"),
    }


def _meta_table_rows(series_list: list[dict]) -> list[dict]:
    """Satu baris `meta_table` per tabel unik dalam `series_list`."""
    tables: dict[str, dict] = {}
    for series in series_list:
        table = series["table"]
        if table in tables:
            continue
        tables[table] = {
            "id": table,
            "table_name": table,
            "table_title": series.get("table_title") or table,
            "scope": series.get("scope") or table.split("_", 1)[0],
            "source": series.get("source") or table.split("_")[2],
            "frequency": series.get("frequency") or table.rsplit("_", 1)[1],
            "table_type": series.get("table_type") or "observation",
            "organizational_access": series.get("organizational_access") or "public",
        }
    return list(tables.values())


class JsonTimeseriesRepository:
    """Katalog metadata + observasi per series disimpan ke berkas JSON lokal."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._table_path = self.data_dir / "meta_table.json"
        self._series_path = self.data_dir / "meta_timeseries.json"
        self._observation_path = self.data_dir / "ts_observations.json"

    # --- Internals ---
    def _read(self, path: Path, default):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return default
        return value if isinstance(value, type(default)) else default

    def _persist(self, value, path: Path) -> None:
        from market_report.calculate import persist_json_data

        persist_json_data(value, path)

    # --- Katalog metadata ---
    def sync_catalog(self, series_list: list[dict]) -> int:
        """Tulis `meta_table` + `meta_timeseries` dari katalog pipeline."""
        if not series_list:
            return 0
        self._persist(_meta_table_rows(series_list), self._table_path)
        self._persist([_meta_series_row(s) for s in series_list], self._series_path)
        return len(series_list)

    def upsert_series(self, series: dict) -> None:
        catalog = self._read(self._series_path, [])
        row = _meta_series_row(series)
        for index, item in enumerate(catalog):
            if isinstance(item, dict) and item.get("series_id") == row["series_id"]:
                catalog[index] = row
                break
        else:
            catalog.append(row)
        self._persist(catalog, self._series_path)
        tables = self._read(self._table_path, [])
        existing = {t.get("table_name") for t in tables if isinstance(t, dict)}
        for table_row in _meta_table_rows([series]):
            if table_row["table_name"] not in existing:
                tables.append(table_row)
        self._persist(tables, self._table_path)

    def bulk_upsert_series(self, series_list: list[dict]) -> int:
        if not series_list:
            return 0
        catalog = {s["series_id"]: s for s in self._read(self._series_path, [])
                   if isinstance(s, dict) and s.get("series_id")}
        for series in series_list:
            catalog[series["series_id"]] = _meta_series_row(series)
        self._persist(list(catalog.values()), self._series_path)
        return len(series_list)

    def list_series(self, *, frequency: str = "", source: str = "",
                    tags: str = "", scope: str = "", limit: int = 1000) -> list[dict]:
        catalog = self._read(self._series_path, [])
        tables = {t["table_name"]: t for t in self._read(self._table_path, [])
                  if isinstance(t, dict) and t.get("table_name")}
        result = []
        for item in catalog:
            if not isinstance(item, dict):
                continue
            table = tables.get(item.get("table_name"), {})
            if frequency and table.get("frequency") != frequency:
                continue
            if source and item.get("source") != source:
                continue
            if scope and table.get("scope") != scope:
                continue
            if tags:
                item_tags = str(item.get("tag") or "")
                if not all(t in item_tags for t in tags.split(",")):
                    continue
            result.append({**item, "scope": table.get("scope"),
                           "frequency": table.get("frequency"),
                           "table_title": table.get("table_title")})
        return result[: max(0, limit)]

    def get_series(self, series_id: str) -> dict | None:
        for item in self._read(self._series_path, []):
            if isinstance(item, dict) and item.get("series_id") == series_id:
                return item
        return None

    def prune_series(self, keep_ids) -> int:
        """Buang series yang tidak lagi ada di katalog pipeline."""
        keep = {str(sid) for sid in keep_ids if sid}
        if not keep:
            return 0
        catalog = [item for item in self._read(self._series_path, [])
                   if isinstance(item, dict) and item.get("series_id") in keep]
        removed = len(self._read(self._series_path, [])) - len(catalog)
        self._persist(catalog, self._series_path)
        live_tables = {item.get("table_name") for item in catalog}
        tables = [t for t in self._read(self._table_path, [])
                  if isinstance(t, dict) and t.get("table_name") in live_tables]
        self._persist(tables, self._table_path)
        if removed:
            store = self._read(self._observation_path, {})
            for series_id in [sid for sid in store if sid not in keep]:
                store.pop(sid, None)
            self._persist(store, self._observation_path)
        return removed

    # --- Observasi ---
    def list_observations(self, series_id: str, limit: int = 420) -> list[dict]:
        store = self._read(self._observation_path, {})
        points = store.get(series_id) if isinstance(store, dict) else None
        if not isinstance(points, list):
            return []
        result = sorted((p for p in points if isinstance(p, dict)),
                        key=lambda item: str(item.get("dates") or ""))
        if limit > 0:
            result = result[-limit:]
        return result

    def upsert_observation(self, series_id: str, dates: str, value: float,
                           limit: int = 420) -> list[dict]:
        return self.bulk_upsert_observations(
            series_id, [{"dates": dates, "value": value}], limit=limit)

    def bulk_upsert_observations(self, series_id: str, observations: list[dict],
                                 limit: int = 420) -> list[dict]:
        if not observations:
            return self.list_observations(series_id, limit=limit)
        store = self._read(self._observation_path, {})
        points = store.setdefault(series_id, []) if isinstance(store, dict) else []
        by_date = {str(p.get("dates")): p for p in points
                   if isinstance(p, dict) and p.get("dates")}
        stamp = datetime.now(timezone.utc).isoformat()
        for point in observations:
            dates = str(point.get("dates") or point.get("date") or "").strip()
            value = point.get("value")
            if not dates or value is None:
                continue
            by_date[dates] = {"dates": dates, "value": float(value), "fetched_at": stamp}
        store[series_id] = sorted(by_date.values(), key=lambda item: str(item["dates"]))
        self._persist(store, self._observation_path)
        return self.list_observations(series_id, limit=limit)


class PostgresTimeseriesRepository:
    """Tabel fisik wide per dataset plus katalog `meta_table`/`meta_timeseries`."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.database_url, row_factory=dict_row)

    # --- Katalog metadata ---
    def sync_catalog(self, series_list: list[dict]) -> int:
        """Pastikan tabel+kolom ada, lalu sinkronkan `meta_table`/`meta_timeseries`."""
        if not series_list:
            return 0
        grouped: dict[str, list[dict]] = {}
        for series in series_list:
            grouped.setdefault(series["table"], []).append(series)
        with self._connect() as conn:
            for table, rows in grouped.items():
                conn.execute(
                    f"CREATE TABLE IF NOT EXISTS {_quoted(table)} "
                    f"(dates DATE PRIMARY KEY)"
                )
                for row in rows:
                    conn.execute(
                        f"ALTER TABLE {_quoted(table)} ADD COLUMN IF NOT EXISTS "
                        f"{_quoted(row['series_name'])} {row.get('data_type') or 'NUMERIC(19,6)'}"
                    )
            with conn.cursor() as cur:
                cur.executemany(
                    """INSERT INTO meta_table (id, table_name, table_title, scope,
                           source, frequency, table_type, organizational_access)
                       VALUES (%(id)s, %(table_name)s, %(table_title)s, %(scope)s,
                               %(source)s, %(frequency)s, %(table_type)s,
                               %(organizational_access)s)
                       ON CONFLICT (table_name) DO UPDATE SET
                           table_title = EXCLUDED.table_title,
                           scope       = EXCLUDED.scope,
                           source      = EXCLUDED.source,
                           frequency   = EXCLUDED.frequency,
                           table_type  = EXCLUDED.table_type""",
                    _meta_table_rows(series_list),
                )
                cur.executemany(
                    """INSERT INTO meta_timeseries (id, table_name, series_name,
                           series_id, data_type, description, unit, source, tag)
                       VALUES (%(id)s, %(table_name)s, %(series_name)s, %(series_id)s,
                               %(data_type)s, %(description)s, %(unit)s,
                               %(source)s, %(tag)s)
                       ON CONFLICT (series_id) DO UPDATE SET
                           table_name  = EXCLUDED.table_name,
                           series_name = EXCLUDED.series_name,
                           data_type   = EXCLUDED.data_type,
                           description = EXCLUDED.description,
                           unit        = EXCLUDED.unit,
                           source      = EXCLUDED.source,
                           tag         = EXCLUDED.tag""",
                    [_meta_series_row(s) for s in series_list],
                )
        return len(series_list)

    def upsert_series(self, series: dict) -> None:
        self.sync_catalog([series])

    def bulk_upsert_series(self, series_list: list[dict]) -> int:
        return self.sync_catalog(series_list)

    def list_series(self, *, frequency: str = "", source: str = "",
                    tags: str = "", scope: str = "", limit: int = 1000) -> list[dict]:
        where = ""
        params: list = []
        if frequency:
            where += " AND t.frequency = %s"
            params.append(frequency)
        if scope:
            where += " AND t.scope = %s"
            params.append(scope)
        if source:
            where += " AND s.source = %s"
            params.append(source)
        if tags:
            where += " AND s.tag = ANY(%s)"
            params.append([t for t in tags.split(",") if t])
        with self._connect() as conn:
            rows = conn.execute(
                f"""SELECT s.series_id, s.table_name, s.series_name, s.data_type,
                           s.description, s.unit, s.source, s.tag,
                           t.table_title, t.scope, t.frequency
                    FROM meta_timeseries s
                    JOIN meta_table t ON t.table_name = s.table_name
                    WHERE TRUE{where}
                    ORDER BY s.series_id LIMIT %s""",
                params + [max(0, limit)],
            ).fetchall()
        return [dict(row) for row in rows]

    def get_series(self, series_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT s.series_id, s.table_name, s.series_name, s.data_type,
                          s.description, s.unit, s.source, s.tag,
                          t.table_title, t.scope, t.frequency
                   FROM meta_timeseries s
                   JOIN meta_table t ON t.table_name = s.table_name
                   WHERE s.series_id = %s""",
                (series_id,),
            ).fetchone()
        return dict(row) if row else None

    def prune_series(self, keep_ids) -> int:
        """Hapus baris `meta_timeseries` yang tidak ada di `keep_ids`."""
        keep = [str(sid) for sid in keep_ids if sid]
        if not keep:
            return 0
        with self._connect() as conn:
            removed = conn.execute(
                "DELETE FROM meta_timeseries WHERE series_id <> ALL(%s)", (keep,)
            ).rowcount
            # Buang metadata tabel yang tidak lagi punya series (mis. setelah rename).
            conn.execute(
                "DELETE FROM meta_table t WHERE NOT EXISTS ("
                "SELECT 1 FROM meta_timeseries m WHERE m.table_name = t.table_name)"
            )
        return removed or 0

    # --- Observasi (tabel wide per dataset) ---
    def _resolve(self, conn, series_id: str):
        row = conn.execute(
            "SELECT table_name, series_name FROM meta_timeseries WHERE series_id = %s",
            (series_id,),
        ).fetchone()
        return (row["table_name"], row["series_name"]) if row else (None, None)

    def list_observations(self, series_id: str, limit: int = 420) -> list[dict]:
        with self._connect() as conn:
            table, column = self._resolve(conn, series_id)
            if not table:
                return []
            query = (
                f"SELECT dates, {_quoted(column)} AS value FROM {_quoted(table)} "
                f"WHERE {_quoted(column)} IS NOT NULL ORDER BY dates ASC"
            )
            if limit > 0:
                query += " LIMIT %s"
                rows = conn.execute(query, (limit,)).fetchall()
            else:
                rows = conn.execute(query).fetchall()
        return [{
            "dates": row["dates"].isoformat() if hasattr(row["dates"], "isoformat") else str(row["dates"]),
            "value": float(row["value"]),
        } for row in rows]

    def upsert_observation(self, series_id: str, dates: str, value: float,
                           limit: int = 420) -> list[dict]:
        return self.bulk_upsert_observations(
            series_id, [{"dates": dates, "value": value}], limit=limit)

    def bulk_upsert_observations(self, series_id: str,
                                 observations: list[dict],
                                 limit: int = 420) -> list[dict]:
        if not observations:
            return self.list_observations(series_id, limit=limit)
        rows = []
        for point in observations:
            day = str(point.get("dates") or point.get("date") or "").strip()
            value = point.get("value")
            if not _ISO_DATE.fullmatch(day) or value is None:
                continue
            rows.append((day, float(value)))
        if not rows:
            return self.list_observations(series_id, limit=limit)
        with self._connect() as conn:
            table, column = self._resolve(conn, series_id)
            if not table:
                return []
            quoted_col = _quoted(column)
            with conn.cursor() as cur:
                cur.executemany(
                    f"INSERT INTO {_quoted(table)} (dates, {quoted_col}) "
                    f"VALUES (%s, %s) "
                    f"ON CONFLICT (dates) DO UPDATE SET {quoted_col} = EXCLUDED.{quoted_col}",
                    rows,
                )
        return self.list_observations(series_id, limit=limit)


def configured_timeseries_repository(default_data_dir: Path):
    """Gunakan PostgreSQL bila DATABASE_URL tersedia; selain itu gunakan JSON lokal."""
    from market_report.config import load_environment

    load_environment()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    return PostgresTimeseriesRepository(database_url) if database_url else JsonTimeseriesRepository(default_data_dir)

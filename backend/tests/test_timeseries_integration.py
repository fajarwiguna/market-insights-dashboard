"""Test integrasi: penamaan panduan, repository metadata + observasi."""

from __future__ import annotations

import os
import re

import pytest

# Regex resmi dari panduan_penamaan.md §7.1.
TABLE_RE = re.compile(
    r"^(glob|natl|prov|reg|muni|meta)\d*_[A-Z][A-Za-z0-9]*_[a-z][a-z0-9]*_[dwmqy]$"
)
SERIES_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)+$")

# Pengecualian legacy yang secara eksplisit diizinkan panduan §6.
LEGACY_TABLES = {"meta_date_idx_d"}


def _sid(table, series_name):
    from market_report.services.timeseries_catalog import series_id_for
    return series_id_for(table, series_name)


def _json_repo(tmp_path):
    from market_report.infrastructure.repositories.timeseries_repository import (
        JsonTimeseriesRepository,
    )
    return JsonTimeseriesRepository(tmp_path / "ts_data")


def _sample_series(table="glob_Commodity_yahoo_d", series_name="gold_comex_futures",
                   source="Yahoo Finance"):
    return {
        "table": table,
        "table_title": "Test Table",
        "table_type": "observation",
        "series_name": series_name,
        "series_id": _sid(table, series_name),
        "scope": table.split("_", 1)[0],
        "source": source,
        "frequency": table.rsplit("_", 1)[1],
        "data_type": "NUMERIC(19,6)",
        "description": "Test series",
        "unit": "IDR",
        "tag": "test",
    }


class TestNamingGuide:
    def test_every_table_conforms(self):
        from market_report.services.timeseries_catalog import TABLES
        offenders = [t for t in TABLES if t not in LEGACY_TABLES and not TABLE_RE.fullmatch(t)]
        assert offenders == []

    def test_every_series_name_conforms(self):
        from market_report.services.timeseries_catalog import PIPELINE_SERIES
        offenders = [s["series_name"] for s in PIPELINE_SERIES
                     if not SERIES_RE.fullmatch(s["series_name"])]
        assert offenders == []

    def test_scope_source_frequency_registered(self):
        from market_report.services.timeseries_catalog import (
            FREQUENCIES, PIPELINE_SERIES, SCOPE_VALUES, SOURCE_CODES, SOURCE_NAMES,
        )
        for series in PIPELINE_SERIES:
            code = series["source_code"]
            assert series["scope"] in SCOPE_VALUES, series["series_id"]
            assert code in SOURCE_CODES, series["series_id"]
            assert series["frequency"] in FREQUENCIES, series["series_id"]
            assert series["table"].split("_", 1)[0] == series["scope"]
            assert series["table"].rsplit("_", 1)[1] == series["frequency"]
            # Nama tabel memakai kode ringkas, kolom `source` memakai nama penerbit.
            assert series["table"].split("_")[2] == code
            assert series["source"] == SOURCE_NAMES[code]
            assert series["source"] != code, series["series_id"]

    def test_table_meta_covers_every_table(self):
        from market_report.services.timeseries_catalog import TABLE_META, TABLES
        assert set(TABLE_META) == set(TABLES)

    def test_series_id_is_derived_from_table_and_series(self):
        from market_report.services.timeseries_catalog import PIPELINE_SERIES
        for series in PIPELINE_SERIES:
            expected = (series["table"].replace("_", "")
                        + "_" + series["series_name"].replace("_", ""))
            assert series["series_id"] == expected, series["series_id"]

    def test_series_ids_unique(self):
        from market_report.services.timeseries_catalog import PIPELINE_SERIES
        ids = [s["series_id"] for s in PIPELINE_SERIES]
        assert len(ids) == len(set(ids))

    def test_table_columns_cover_all_series(self):
        from market_report.services.timeseries_catalog import PIPELINE_SERIES, table_columns
        grouped = table_columns()
        total = sum(len(cols) for cols in grouped.values())
        assert total == len(PIPELINE_SERIES)


class TestJsonMetadataCatalog:
    def test_sync_catalog_writes_metadata(self, tmp_path):
        from market_report.services.timeseries_catalog import table_specs
        repo = _json_repo(tmp_path)
        assert repo.sync_catalog([_sample_series()]) == 1
        assert repo.get_series(_sid("glob_Commodity_yahoo_d", "gold_comex_futures")) is not None
        assert table_specs()  # katalog mendefinisikan tabel

    def test_filter_by_scope(self, tmp_path):
        repo = _json_repo(tmp_path)
        repo.sync_catalog([
            _sample_series("glob_Commodity_yahoo_d", "gold_comex_futures"),
            _sample_series("natl_Rates_bi_d", "id_bi_rate", source="Bank Indonesia"),
        ])
        assert len(repo.list_series(scope="natl")) == 1
        assert repo.list_series(scope="natl")[0]["series_name"] == "id_bi_rate"

    def test_filter_by_source_and_frequency(self, tmp_path):
        repo = _json_repo(tmp_path)
        repo.sync_catalog([
            _sample_series("glob_Commodity_yahoo_d", "gold_comex_futures"),
            _sample_series("natl_Macro_bi_m", "id_credit_yoy", source="Bank Indonesia"),
        ])
        assert len(repo.list_series(source="Bank Indonesia")) == 1
        assert len(repo.list_series(frequency="m")) == 1
        assert len(repo.list_series(frequency="d")) == 1

    def test_prune_drops_unlisted_series(self, tmp_path):
        repo = _json_repo(tmp_path)
        keep = _sample_series("glob_Commodity_yahoo_d", "gold_comex_futures")
        drop = _sample_series("natl_Rates_bi_d", "id_bi_rate", source="Bank Indonesia")
        repo.sync_catalog([keep, drop])
        assert repo.prune_series({keep["series_id"]}) == 1
        assert repo.get_series(keep["series_id"]) is not None
        assert repo.get_series(drop["series_id"]) is None

    def test_prune_empty_keep_is_noop(self, tmp_path):
        repo = _json_repo(tmp_path)
        repo.sync_catalog([_sample_series()])
        assert repo.prune_series(set()) == 0
        assert repo.list_series() != []


class TestJsonObservations:
    def test_empty(self, tmp_path):
        assert _json_repo(tmp_path).list_observations("x") == []

    def test_upsert_single(self, tmp_path):
        repo = _json_repo(tmp_path)
        pts = repo.upsert_observation("s1", "2025-01-15", 1234.5)
        assert len(pts) == 1 and pts[0]["value"] == 1234.5

    def test_overwrite_same_date(self, tmp_path):
        repo = _json_repo(tmp_path)
        repo.upsert_observation("s1", "2025-01-15", 1000)
        repo.upsert_observation("s1", "2025-01-15", 2000)
        assert _json_repo(tmp_path).list_observations("s1")[0]["value"] == 2000

    def test_sorted_ascending_and_limit(self, tmp_path):
        repo = _json_repo(tmp_path)
        repo.upsert_observation("s1", "2025-01-03", 300)
        repo.upsert_observation("s1", "2025-01-01", 100)
        repo.upsert_observation("s1", "2025-01-02", 200)
        dates = [p["dates"] for p in repo.list_observations("s1")]
        assert dates == ["2025-01-01", "2025-01-02", "2025-01-03"]
        assert len(repo.list_observations("s1", limit=2)) == 2

    def test_bulk_upsert(self, tmp_path):
        repo = _json_repo(tmp_path)
        repo.bulk_upsert_observations("s1", [
            {"dates": "2025-01-01", "value": 100},
            {"dates": "2025-01-02", "value": 200},
        ])
        repo.bulk_upsert_observations("s1", [{"dates": "2025-01-01", "value": 150}])
        pts = repo.list_observations("s1")
        assert pts[0]["value"] == 150.0 and len(pts) == 2


class TestSnapshotExtraction:
    def test_observations_are_all_catalog_series(self):
        from market_report.services import timeseries_catalog as catalog
        snapshot = {
            "yfinance": {
                "USDIDR": {"last": 16000, "date": "2026-10-08"},
                "IHSG": {"last": 6100, "date": "2026-10-08"},
                "GOLD": {"last": 2400, "date": "2026-10-08"},
            },
        }
        points = catalog.observations_from_snapshot(snapshot)
        ids = {p["series_id"] for p in points}
        assert ids <= catalog.catalog_series_ids()
        assert catalog.series_id_for("glob_Monetary_yahoo_d", "usd_idr") in ids
        assert catalog.series_id_for("natl_FinancialMarket_yahoo_d", "idx_composite") in ids

    def test_sync_observations_writes_to_repo(self, tmp_path):
        from market_report.services import timeseries_catalog as catalog
        snapshot = {"yfinance": {"USDIDR": {"last": 16000, "date": "2026-10-08"}}}
        repo = _json_repo(tmp_path)
        repo.sync_catalog([_sample_series("glob_Monetary_yahoo_d", "usd_idr")])
        assert catalog.sync_observations(snapshot, repository=repo) >= 1
        series = repo.list_observations(_sid("glob_Monetary_yahoo_d", "usd_idr"))
        assert series[0]["value"] == 16000.0

    def test_skip_list_excluded(self):
        from market_report.services import timeseries_catalog as catalog
        snapshot = {
            "bi": {"bi_rate": 5.75, "bi_rate_date": "2026-10-08",
                   "foreign_reserves": None},
            "yfinance": {},
        }
        ids = {p["series_id"] for p in catalog.observations_from_snapshot(snapshot)}
        assert catalog.series_id_for("natl_Rates_bi_d", "id_bi_rate") in ids
        assert catalog.OBSERVATION_SKIP.isdisjoint(ids)


class TestPostgresTimeseries:
    TABLE = "glob_TestFixture_pgtest_d"
    SERIES = "us_test_value"

    @pytest.fixture(autouse=True)
    def _isolated(self):
        url = os.environ.get("DATABASE_URL", "").strip()
        if not url:
            pytest.skip("DATABASE_URL tidak diatur")
        yield
        import psycopg
        with psycopg.connect(url) as conn:
            conn.execute("DELETE FROM meta_timeseries WHERE table_name = %s", (self.TABLE,))
            conn.execute("DELETE FROM meta_table WHERE table_name = %s", (self.TABLE,))
            conn.execute(f'DROP TABLE IF EXISTS "{self.TABLE}"')

    def _repo(self):
        from market_report.infrastructure.repositories.timeseries_repository import (
            PostgresTimeseriesRepository,
        )
        return PostgresTimeseriesRepository(os.environ["DATABASE_URL"].strip())

    def _series(self):
        return _sample_series(self.TABLE, self.SERIES, source="Yahoo Finance")

    def test_sync_catalog_and_get(self):
        repo = self._repo()
        assert repo.sync_catalog([self._series()]) == 1
        row = repo.get_series(_sid(self.TABLE, self.SERIES))
        assert row is not None
        assert row["table_name"] == self.TABLE
        assert row["scope"] == "glob"

    def test_list_series_filters(self):
        repo = self._repo()
        repo.sync_catalog([self._series()])
        assert any(r["series_id"] == _sid(self.TABLE, self.SERIES)
                   for r in repo.list_series(scope="glob", limit=500))

    def test_observations_round_trip(self):
        repo = self._repo()
        repo.sync_catalog([self._series()])
        repo.bulk_upsert_observations(_sid(self.TABLE, self.SERIES), [
            {"dates": "2025-06-16", "value": 1.0},
            {"dates": "2025-06-17", "value": 2.0},
        ])
        points = repo.list_observations(_sid(self.TABLE, self.SERIES))
        assert [p["dates"] for p in points] == ["2025-06-16", "2025-06-17"]
        repo.bulk_upsert_observations(_sid(self.TABLE, self.SERIES),
                                      [{"dates": "2025-06-16", "value": 9.0}])
        assert repo.list_observations(_sid(self.TABLE, self.SERIES))[0]["value"] == 9.0

    def test_prune_empty_keep_is_noop(self):
        # `prune_series` bersifat global (menghapus semua di luar keep_ids), jadi
        # test ini sengaja hanya memakai keep kosong agar tidak menghapus katalog asli.
        repo = self._repo()
        repo.sync_catalog([self._series()])
        assert repo.prune_series(set()) == 0
        assert repo.get_series(_sid(self.TABLE, self.SERIES)) is not None

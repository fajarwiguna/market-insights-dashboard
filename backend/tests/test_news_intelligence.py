"""Uji verifikasi & ekstraksi bukti berita (bagian 3C/3D) serta skenario katalis."""

from __future__ import annotations

from market_report.services.narration import evidence as evidence_module
from market_report.services.narration.providers.base import RawSearchResult


def make(title: str, url: str, *, published: str, tier: str = "global_market_media",
         source: str = "reuters.com", publisher: str = "Reuters",
         topics: tuple[str, ...] = ("indonesian_equity",), query: str = "") -> RawSearchResult:
    return RawSearchResult(title=title, url=url, source=source, published_at=published,
                           summary="Ringkasan konteks pasar.", source_tier=tier, topics=topics,
                           publisher=publisher, query=query)


def test_evidence_records_verification_metadata():
    built = evidence_module.build_evidence(
        [make("IHSG turun setelah MSCI menahan reklasifikasi Indonesia",
              "https://reuters.com/a", published="2026-10-16")],
        report_date="2026-10-16", topics=["indonesian_equity"])
    assert len(built.items) == 1
    item = built.items[0]
    assert item.publisher == "Reuters"
    assert item.verified is True
    assert item.relation == "same_day"
    assert 0.0 < item.confidence <= 1.0


def test_evidence_marks_prior_day_news_as_before():
    built = evidence_module.build_evidence(
        [make("BI menahan suku bunga acuan", "https://reuters.com/b", published="2026-10-15")],
        report_date="2026-10-16", topics=["indonesian_equity"])
    assert built.items[0].relation == "before"


def test_evidence_drops_news_after_report_date_and_low_tier():
    built = evidence_module.build_evidence(
        [make("Berita setelah sesi", "https://reuters.com/c", published="2026-10-17"),
         make("Blog tanpa tier", "https://blog.id/x", published="2026-10-16", tier="secondary",
              source="blog.id", publisher="Blog")],
        report_date="2026-10-16", topics=["indonesian_equity"])
    assert built.items == []
    reasons = {row["reason"] for row in built.dropped}
    assert "tanggal_masa_depan" in reasons
    assert "tier_secondary" in reasons


def test_evidence_quota_uses_publisher_domain_not_aggregator():
    # Tiga item dari satu penerbit: kuota per domain harus memotong yang ketiga,
    # meski URL-nya berbeda (mis. tautan agregator).
    built = evidence_module.build_evidence(
        [make("Berita satu tentang IHSG", "https://news.google.com/rss/articles/1", published="2026-10-16"),
         make("Berita dua tentang IHSG", "https://news.google.com/rss/articles/2", published="2026-10-16"),
         make("Berita tiga tentang IHSG", "https://news.google.com/rss/articles/3", published="2026-10-16")],
        report_date="2026-10-16", topics=["indonesian_equity"], max_per_domain=2)
    assert len(built.items) == 2
    assert "kuota_domain" in {row["reason"] for row in built.dropped}


def test_evidence_ranks_query_matches_higher():
    built = evidence_module.build_evidence(
        [make("Selamat pagi, ini agenda hari ini", "https://reuters.com/agenda",
              published="2026-10-16", topics=("indonesian_equity",)),
         make("IHSG turun karena aksi jual asing", "https://reuters.com/ihsg",
              published="2026-10-16", topics=("indonesian_equity",))],
        report_date="2026-10-16", topics=["indonesian_equity"],
        queries=["katalis IHSG turun"])
    assert built.items[0].title.startswith("IHSG")
    assert built.items[0].query == "" or built.items[0].confidence >= built.items[1].confidence


def test_scenario_msci_like_catalyst_is_kept_with_evidence():
    """IHSG turun setelah pengumuman indeks global: berita terkait harus lolos."""
    built = evidence_module.build_evidence(
        [make("MSCI menahan reklasifikasi, IHSG turun tajam",
              "https://www.cnbcindonesia.com/market/msci-ihsg", published="2026-10-16",
              tier="id_market_media", source="cnbcindonesia.com", publisher="CNBC Indonesia"),
         make("Resep kue lapis legit", "https://www.cnbcindonesia.com/lifestyle/kue",
              published="2026-10-16", tier="id_market_media", source="cnbcindonesia.com",
              publisher="CNBC Indonesia")],
        report_date="2026-10-16", topics=["indonesian_equity"], queries=["katalis IHSG turun"])
    titles = [item.title for item in built.items]
    assert "MSCI menahan reklasifikasi, IHSG turun tajam" in titles
    assert all("kue" not in title.lower() for title in titles[:1])


def test_empty_results_do_not_raise():
    built = evidence_module.build_evidence([], report_date="2026-10-16", topics=["fx"])
    assert built.items == []
    assert built.dropped == []


def test_topic_plan_thresholds_are_configurable():
    numbers = {"fx.usd_idr.change_pct": 0.30}
    assert evidence_module.topic_plan(numbers) == ["fx"]
    stricter = evidence_module.topic_plan(numbers, thresholds={"fx_material_pct": 0.5})
    assert stricter == []

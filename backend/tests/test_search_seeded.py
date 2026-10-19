"""Uji mode `seeded`: pengumpulan tautan, metadata artikel, dan penolakan alamat.

Tidak ada permintaan jaringan: `fetcher` disuntikkan.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from market_report.services.narration.errors import SearchUnavailableError
from market_report.services.narration.providers.search_seeded import (
    SeededSearchProvider,
    canonical_url,
    extract_links,
    load_registry,
    normalise_datetime,
    parse_article,
    parse_rss,
    source_domain,
)

FEED_HTML = """
<html><body>
  <a href="/kanal/market/berita-pasar-hari-ini">Berita pasar hari ini bergerak</a>
  <a href="https://www.bloombergtechnoz.com/kanal/market/berita-pasar-hari-ini">Duplikat</a>
  <a href="/kanal/market/berita-kedua-yang-panjang">Berita kedua yang panjang</a>
  <a href="/kanal/market/berita-ketiga-yang-panjang">Berita ketiga yang panjang</a>
  <a href="https://situs-lain.com/artikel/asing">Situs lain</a>
  <a href="#top">Anchor</a>
  <a href="mailto:redaksi@bloombergtechnoz.com">Email</a>
</body></html>
"""

ARTICLE_HTML = """
<html><head>
  <meta property="og:title" content="Rupiah melemah terbatas" />
  <meta property="article:published_time" content="2026-10-15T17:20:00+07:00" />
  <meta name="description" content="Rupiah melemah tipis di tengah arus keluar asing." />
  <meta property="og:url" content="https://www.bloombergtechnoz.com/kanal/market/berita-pasar-hari-ini?utm_source=feed" />
</head><body><h1>Rupiah melemah terbatas</h1><p>Isi artikel.</p></body></html>
"""

OLD_ARTICLE_HTML = ARTICLE_HTML.replace("2026-10-15", "2026-09-01")

RSS_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>Economy News</title>
  <item>
    <title>Global inflation debate puts BOJ pace in spotlight</title>
    <pubDate>2026-10-16 08:48:47</pubDate>
    <link>https://www.investing.com/news/economy-news/global-inflation-4953375</link>
    <description>&lt;p&gt;BOJ &lt;b&gt;rate hike&lt;/b&gt; pace in focus.&lt;/p&gt;</description>
  </item>
  <item>
    <title>Old story</title>
    <pubDate>2026-09-01 10:00:00</pubDate>
    <link>https://www.investing.com/news/economy-news/old-story-111</link>
    <description>Lama</description>
  </item>
  <item>
    <title>Tanpa tautan</title>
    <pubDate>2026-10-16 09:00:00</pubDate>
  </item>
</channel></rss>
"""

RSS_REGISTRY = {
    "domain_tiers": {"investing.com": "data_portal"},
    "rules": {"deny_host_patterns": ["localhost"]},
    "sources": [
        {"id": "investing", "name": "Investing.com", "tier": "data_portal", "mode": "seed",
         "format": "rss", "topics": ["economy"],
         "urls": ["https://www.investing.com/rss/news_14.rss"]},
    ],
}

REGISTRY = {
    "domain_tiers": {"bloombergtechnoz.com": "id_market_media", "bi.go.id": "official_primary"},
    "rules": {"deny_host_patterns": ["localhost", "127.0.0.1"], "fetch_timeout_seconds": 5},
    "sources": [
        {"id": "bloomberg_technoz", "name": "Bloomberg Technoz", "tier": "id_market_media",
         "mode": "seed", "topics": ["indonesia_macro", "ihsg"],
         "urls": ["https://www.bloombergtechnoz.com/kanal/market/ekonomi"]},
        {"id": "bi", "name": "Bank Indonesia", "tier": "official_primary", "mode": "reference",
         "topics": ["fx"], "urls": ["https://www.bi.go.id/"]},
    ],
}


def fetcher_from(mapping: dict[str, tuple[int, str]]):
    calls: list[str] = []

    def fetch(url: str, timeout: float):
        calls.append(url)
        return mapping.get(url, (404, ""))

    return fetch, calls


def test_repository_registry_is_usable():
    registry = load_registry(Path("backend/config/llm_sources.json"))
    ids = {source["id"] for source in registry["sources"]}
    assert {"bi", "idx", "bps", "ojk", "tradingeconomics", "bloomberg_technoz"} <= ids
    assert registry["domain_tiers"]["bi.go.id"] == "official_primary"
    assert registry["domain_tiers"]["bloombergtechnoz.com"] == "id_market_media"
    assert registry["unverified_urls"], "tautan yang belum diverifikasi harus tercatat"


def test_extract_links_is_domain_scoped_and_deduplicated():
    links = extract_links(FEED_HTML, "https://www.bloombergtechnoz.com/kanal/market/ekonomi", limit=5)
    assert links == [
        "https://www.bloombergtechnoz.com/kanal/market/berita-pasar-hari-ini",
        "https://www.bloombergtechnoz.com/kanal/market/berita-kedua-yang-panjang",
        "https://www.bloombergtechnoz.com/kanal/market/berita-ketiga-yang-panjang",
    ]


def test_canonical_url_drops_tracking_and_fragment():
    assert canonical_url("https://x.com/a/?utm_source=feed&id=1#part") == "https://x.com/a?id=1"
    assert source_domain("https://www.bi.go.id/x") == "bi.go.id"


def test_parse_article_reads_metadata():
    parsed = parse_article(ARTICLE_HTML, "https://www.bloombergtechnoz.com/a")
    assert parsed["title"] == "Rupiah melemah terbatas"
    assert parsed["published_at"] == "2026-10-15T17:20:00+07:00"
    assert parsed["canonical"] == "https://www.bloombergtechnoz.com/kanal/market/berita-pasar-hari-ini"
    assert "arus keluar asing" in parsed["summary"]


def test_normalise_datetime_accepts_common_formats():
    assert normalise_datetime("2026-10-15T17:20:00+07:00") == "2026-10-15"
    assert normalise_datetime("2026-10-15 17:20:00") == "2026-10-15"
    assert normalise_datetime("15/10/2026 17:20") == "2026-10-15"
    assert normalise_datetime("Fri, 16 Oct 2026 08:48:47 +0000") == "2026-10-16"
    assert normalise_datetime("tanpa tanggal") == ""


def test_discover_keeps_only_fresh_articles_from_seed_sources():
    feed = "https://www.bloombergtechnoz.com/kanal/market/ekonomi"
    fresh = "https://www.bloombergtechnoz.com/kanal/market/berita-pasar-hari-ini"
    old = "https://www.bloombergtechnoz.com/kanal/market/berita-kedua-yang-panjang"
    missing = "https://www.bloombergtechnoz.com/kanal/market/berita-ketiga-yang-panjang"
    fetch, calls = fetcher_from({feed: (200, FEED_HTML), fresh: (200, ARTICLE_HTML),
                                 old: (200, OLD_ARTICLE_HTML), missing: (200, "<html></html>")})
    provider = SeededSearchProvider(REGISTRY, fetcher=fetch, max_articles_per_source=3)

    results = provider.discover(topics=["indonesia_macro"], since="2026-10-13", max_items=8)

    assert [row.url for row in results] == [fresh]
    assert results[0].source == "bloombergtechnoz.com"
    assert results[0].source_tier == "id_market_media"
    assert results[0].published_at == "2026-10-15"
    assert "indonesia_macro" in results[0].topics
    assert all(call != "https://www.bi.go.id/" for call in calls), "sumber reference tidak diambil"


def test_discover_skips_topics_without_matching_seed_source():
    fetch, calls = fetcher_from({})
    provider = SeededSearchProvider(REGISTRY, fetcher=fetch)
    provider.discover(topics=["tidak_ada_topik"], since="2026-10-13", max_items=3)
    assert calls == ["https://www.bloombergtechnoz.com/kanal/market/ekonomi"], (
        "tanpa topik yang cocok, semua kanal seed dipakai sebagai cadangan")


def test_denied_host_is_never_fetched():
    registry = dict(REGISTRY)
    registry["sources"] = [{"id": "internal", "tier": "secondary", "mode": "seed", "topics": ["fx"],
                            "urls": ["http://localhost:8000/feed"]}]
    fetch, calls = fetcher_from({})
    provider = SeededSearchProvider(registry, fetcher=fetch)
    assert provider.discover(topics=["fx"], since="2026-10-01", max_items=2) == []
    assert calls == [], "alamat privat harus ditolak sebelum permintaan dikirim"


def test_fetch_failure_on_one_link_does_not_stop_others():
    feed = "https://www.bloombergtechnoz.com/kanal/market/ekonomi"
    fresh = "https://www.bloombergtechnoz.com/kanal/market/berita-pasar-hari-ini"

    def fetch(url: str, timeout: float):
        if url == feed:
            return 200, FEED_HTML
        if url == fresh:
            return 200, ARTICLE_HTML
        raise RuntimeError("koneksi putus")

    provider = SeededSearchProvider(REGISTRY, fetcher=fetch, max_articles_per_source=3)
    results = provider.discover(topics=["indonesia_macro"], since="2026-10-13", max_items=8)
    assert len(results) == 1


def test_provider_without_seed_sources_is_unavailable():
    provider = SeededSearchProvider({"sources": REGISTRY["sources"][1:]}, fetcher=lambda url, t: (200, ""))
    assert provider.available() is False
    assert provider.discover(topics=["fx"], since="2026-10-01", max_items=1) == []


def test_http_error_raises_search_unavailable():
    provider = SeededSearchProvider(REGISTRY, fetcher=lambda url, timeout: (503, ""))
    with pytest.raises(SearchUnavailableError):
        provider._fetch("https://www.bloombergtechnoz.com/kanal/market/ekonomi")


def test_parse_rss_reads_items_without_fetching_articles():
    items = parse_rss(RSS_FEED, "https://www.investing.com/rss/news_14.rss", limit=10)
    assert [row["canonical"] for row in items] == [
        "https://www.investing.com/news/economy-news/global-inflation-4953375",
        "https://www.investing.com/news/economy-news/old-story-111",
    ], "item tanpa tautan harus dilewati"
    assert items[0]["title"] == "Global inflation debate puts BOJ pace in spotlight"
    assert items[0]["published_at"] == "2026-10-16 08:48:47"
    assert items[0]["summary"] == "BOJ rate hike pace in focus."


def test_parse_rss_tolerates_broken_xml():
    assert parse_rss("<rss><channel><item>", "https://x/feed.rss", limit=5) == []


def test_discover_reads_rss_feed_without_fetching_articles():
    feed = "https://www.investing.com/rss/news_14.rss"
    fetch, calls = fetcher_from({feed: (200, RSS_FEED)})
    provider = SeededSearchProvider(RSS_REGISTRY, fetcher=fetch)

    results = provider.discover(topics=["economy"], since="2026-10-13", max_items=5)

    assert [row.url for row in results] == [
        "https://www.investing.com/news/economy-news/global-inflation-4953375"]
    assert results[0].source == "investing.com"
    assert results[0].source_tier == "data_portal"
    assert results[0].published_at == "2026-10-16"
    assert calls == [feed], "artikel tidak boleh diambil ulang dari feed RSS"


def test_repository_registry_points_investing_at_rss():
    registry = load_registry(Path("backend/config/llm_sources.json"))
    investing = next(source for source in registry["sources"] if source["id"] == "investing")
    assert investing["format"] == "rss"
    assert all(url.endswith(".rss") for url in investing["urls"])


# ── penemuan dinamis (mode "query") ─────────────────────────────────

QUERY_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=id"

QUERY_REGISTRY = {
    "domain_tiers": {"cnbcindonesia.com": "id_market_media", "reuters.com": "global_market_media"},
    "rules": {"deny_host_patterns": ["localhost"]},
    "sources": [
        {"id": "google_news_search", "name": "Google News", "tier": "major_media",
         "mode": "query", "format": "rss", "url_template": QUERY_TEMPLATE, "queries_per_run": 2,
         "topics": ["indonesian_equity", "fx"]},
    ],
}

QUERY_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <item>
    <title>IHSG turun, MSCI menahan reklasifikasi Indonesia</title>
    <pubDate>Fri, 16 Oct 2026 03:10:00 GMT</pubDate>
    <link>https://news.google.com/rss/articles/abc123</link>
    <description>IHSG tertekan pengumuman indeks global.</description>
    <source url="https://www.cnbcindonesia.com">CNBC Indonesia</source>
  </item>
</channel></rss>
"""

QUERY_FEED_TWO = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <item>
    <title>Harga cabai naik di pasar tradisional</title>
    <pubDate>Fri, 16 Oct 2026 04:00:00 GMT</pubDate>
    <link>https://news.google.com/rss/articles/zxc</link>
    <description>Bukan berita pasar modal.</description>
    <source url="https://www.reuters.com">Reuters</source>
  </item>
  <item>
    <title>IHSG turun dipicu aksi jual asing</title>
    <pubDate>Fri, 16 Oct 2026 03:30:00 GMT</pubDate>
    <link>https://news.google.com/rss/articles/qwe</link>
    <description>IHSG turun seiring aksi jual asing.</description>
    <source url="https://www.cnbcindonesia.com">CNBC Indonesia</source>
  </item>
</channel></rss>
"""


def test_parse_rss_captures_publisher_source():
    items = parse_rss(QUERY_FEED, QUERY_TEMPLATE, limit=5)
    assert items[0]["source_name"] == "CNBC Indonesia"
    assert items[0]["source_url"] == "https://www.cnbcindonesia.com"


def test_discover_expands_dynamic_queries_and_maps_publisher_tier():
    url = QUERY_TEMPLATE.replace("{query}", "katalis%20IHSG%20turun")
    fetch, calls = fetcher_from({url: (200, QUERY_FEED)})
    provider = SeededSearchProvider(QUERY_REGISTRY, fetcher=fetch)

    results = provider.discover(topics=["indonesian_equity"], since="2026-10-13",
                                max_items=5, queries=["katalis IHSG turun"])

    assert len(results) == 1
    row = results[0]
    # Domain agregator (news.google.com) bukan sumber: yang dipakai penerbit asli.
    assert row.source == "cnbcindonesia.com"
    assert row.source_tier == "id_market_media"
    assert row.publisher == "CNBC Indonesia"
    assert row.query == "katalis IHSG turun"
    assert row.published_at == "2026-10-16"
    assert calls == [url], "satu kueri = satu permintaan pencarian"


def test_discover_ranks_query_matches_first():
    url = QUERY_TEMPLATE.replace("{query}", "katalis%20IHSG%20turun")
    fetch, _calls = fetcher_from({url: (200, QUERY_FEED_TWO)})
    provider = SeededSearchProvider(QUERY_REGISTRY, fetcher=fetch)

    results = provider.discover(topics=["indonesian_equity"], since="2026-10-13",
                                max_items=5, queries=["katalis IHSG turun"])

    assert results[0].title.startswith("IHSG"), "hasil yang cocok kueri harus didahulukan"


def test_discover_without_queries_uses_seed_sources_only():
    provider = SeededSearchProvider(QUERY_REGISTRY, fetcher=lambda url, timeout: (200, QUERY_FEED))
    assert provider.discover(topics=["indonesian_equity"], since="2026-10-13",
                             max_items=5, queries=[]) == []


def test_repository_registry_has_a_dynamic_query_source():
    registry = load_registry(Path("backend/config/llm_sources.json"))
    queries = [source for source in registry["sources"] if source.get("mode") == "query"]
    assert queries, "harus ada minimal satu sumber pencarian dinamis"
    assert all("{query}" in source["url_template"] for source in queries)


def test_publisher_subdomain_uses_registered_parent_tier():
    # Subdomain penerbit harus memakai tier domain induknya, bukan "secondary".
    feed = """<?xml version="1.0" encoding="utf-8"?>
    <rss version="2.0"><channel><item>
      <title>IHSG melemah</title>
      <pubDate>Fri, 16 Oct 2026 03:00:00 GMT</pubDate>
      <link>https://news.google.com/rss/articles/sub</link>
      <source url="https://finance.detik.com">detikFinance</source>
    </item></channel></rss>"""
    registry = {
        "domain_tiers": {"detik.com": "major_media"},
        "rules": {"deny_host_patterns": ["localhost"]},
        "sources": [{"id": "google_news_search", "tier": "major_media", "mode": "query",
                     "format": "rss", "url_template": QUERY_TEMPLATE, "topics": ["indonesian_equity"]}],
    }
    url = QUERY_TEMPLATE.replace("{query}", "katalis%20IHSG%20turun")
    provider = SeededSearchProvider(registry, fetcher=fetcher_from({url: (200, feed)})[0])
    results = provider.discover(topics=["indonesian_equity"], since="2026-10-13", max_items=3,
                                queries=["katalis IHSG turun"])
    assert results[0].source_tier == "major_media"
    assert results[0].source == "finance.detik.com"

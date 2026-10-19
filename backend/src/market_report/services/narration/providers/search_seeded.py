"""Mode `seeded`: bukti diambil dari registry sumber yang ditetapkan pengguna.

Alur: halaman kanal → daftar tautan artikel → ambil artikel yang lolos filter
tanggal → metadata (judul, penerbit, waktu terbit, ringkasan). Hasilnya berbentuk
`RawSearchResult` yang sama seperti mode provider, sehingga sisa pipeline tidak
berubah. Angka dari halaman ini tidak pernah menjadi angka pasar.
"""

from __future__ import annotations

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Callable, Iterable, Sequence
from urllib.parse import quote, urljoin, urlparse, urlunparse

from market_report.services.narration.errors import SearchUnavailableError
from market_report.services.narration.providers.base import RawSearchResult

logger = logging.getLogger(__name__)

Fetcher = Callable[[str, float], tuple[int, str]]
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_BYTES = 2_000_000

_LINK_HINT_RE = re.compile(r"/(20\d{2}|berita|news|artikel|article|post|kanal|tag|read)/", re.IGNORECASE)
_TRACKING_RE = re.compile(r"^(utm_|fbclid|gclid|amp)", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")
_QUERY_STOPWORDS = {"dan", "yang", "untuk", "dari", "pada", "hari", "ini", "the", "of",
                    "dengan", "atau", "ke", "di", "sebagai", "katalis", "penyebab"}


def query_keywords(text: str) -> set[str]:
    """Kata kunci bermakna dari sebuah kueri (untuk memeringkat hasil)."""
    return {word for word in _WORD_RE.findall((text or "").lower())
            if len(word) > 2 and word not in _QUERY_STOPWORDS}


def domain_candidates(domain: str) -> list[str]:
    """Domain dan induknya, dari paling spesifik ke paling umum.

    Dipakai agar subdomain penerbit (mis. finance.detik.com) tetap memakai tier
    domain terdaftar (detik.com) tanpa perlu menuliskan setiap subdomain.
    """
    parts = [part for part in (domain or "").split(".") if part]
    return [".".join(parts[index:]) for index in range(len(parts) - 1)]


def load_registry(path: str | Path) -> dict:
    """Baca registry sumber. Kegagalan apa pun menghasilkan registry kosong."""
    try:
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as error:
        logger.error("Registry sumber tidak terbaca (%s): %s", path, error)
        return {}
    return data if isinstance(data, dict) else {}


def canonical_url(url: str) -> str:
    """Buang fragment dan parameter pelacakan agar dedup stabil."""
    parsed = urlparse(url)
    query = "&".join(part for part in (parsed.query or "").split("&")
                     if part and not _TRACKING_RE.match(part.split("=")[0]))
    return urlunparse((parsed.scheme, parsed.netloc.lower(), parsed.path.rstrip("/"), "", query, ""))


def source_domain(url: str) -> str:
    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def _denied(url: str, deny_patterns: Iterable[str]) -> bool:
    host = urlparse(url).netloc.lower()
    if urlparse(url).scheme not in ("http", "https"):
        return True
    return any(pattern.lower() in host for pattern in deny_patterns)


def _html_meta(html: str, patterns: Sequence[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if match:
            return re.sub(r"\s+", " ", match.group("value")).strip()
    return ""


def parse_article(html: str, url: str) -> dict[str, str]:
    """Ambil metadata artikel dari HTML tanpa mengubah isinya."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")

    def meta(*names: str) -> str:
        for name in names:
            tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
            if tag and tag.get("content"):
                return str(tag["content"]).strip()
        return ""

    title = meta("og:title", "twitter:title") or _html_meta(
        html, [r"<title[^>]*>(?P<value>.*?)</title>", r"<h1[^>]*>(?P<value>.*?)</h1>"])
    published = meta("article:published_time", "datePublished", "date", "pubdate", "og:published_time")
    if not published:
        published = _html_meta(html, [r"<time[^>]*datetime=\"(?P<value>[^\"]+)\"",
                                      r"\"datePublished\"\s*:\s*\"(?P<value>[^\"]+)\""])
    summary = meta("og:description", "description", "twitter:description")
    canonical = meta("og:url") or url
    return {"title": title, "published_at": published, "summary": summary,
            "canonical": canonical_url(canonical)}


def _local(tag: str) -> str:
    """Nama lokal sebuah tag XML tanpa namespace/prefix."""
    return str(tag).rsplit("}", 1)[-1].split(":")[-1].lower()


def _xml_text(node, name: str) -> str:
    for child in node:
        if _local(child.tag) == name and child.text:
            return re.sub(r"\s+", " ", child.text).strip()
    return ""


def _xml_attr(node, name: str, attr: str) -> str:
    for child in node:
        if _local(child.tag) == name and child.get(attr):
            return str(child.get(attr)).strip()
    return ""


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", text or ""))).strip()


def parse_rss(xml_text: str, base_url: str, *, limit: int) -> list[dict[str, str]]:
    """Ambil item dari feed RSS/Atom (RSS 2.0 dan Atom).

    Feed sudah membawa judul, tautan, dan waktu terbit, jadi artikel tidak perlu
    diambil ulang. Ini jalur yang dipakai untuk kanal yang memblokir HTML kanal
    (mis. investing.com /news/* yang dilindungi Cloudflare) tetapi menyajikan RSS.
    """
    try:
        root = ET.fromstring((xml_text or "").strip())
    except ET.ParseError:
        return []
    items = [node for node in root.iter() if _local(node.tag) in ("item", "entry")]
    parsed: list[dict[str, str]] = []
    for item in items[:limit]:
        link = _xml_text(item, "link") or _xml_attr(item, "link", "href")
        if not link:
            continue
        parsed.append({
            "title": _xml_text(item, "title"),
            "canonical": canonical_url(urljoin(base_url, link)),
            "published_at": (_xml_text(item, "pubdate") or _xml_text(item, "published")
                             or _xml_text(item, "updated") or _xml_text(item, "date")),
            "summary": _strip_html(_xml_text(item, "description") or _xml_text(item, "summary")),
            # <source url="...">Nama Penerbit</source>: memisahkan penerbit dari
            # domain agregator (mis. news.google.com) supaya tier tetap benar.
            "source_name": _xml_text(item, "source"),
            "source_url": _xml_attr(item, "source", "url"),
        })
    return parsed


def extract_links(html: str, base_url: str, *, limit: int) -> list[str]:
    """Kumpulkan tautan artikel dari halaman kanal, urut kemunculan, tanpa duplikat."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html or "", "html.parser")
    found: list[str] = []
    seen: set[str] = set()
    base_domain = source_domain(base_url)
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:")):
            continue
        absolute = canonical_url(urljoin(base_url, href))
        if source_domain(absolute) != base_domain or absolute == canonical_url(base_url):
            continue
        if absolute in seen:
            continue
        text = anchor.get_text(" ", strip=True)
        if not _LINK_HINT_RE.search(absolute) and len(text.split()) < 4:
            continue
        seen.add(absolute)
        found.append(absolute)
        if len(found) >= limit:
            break
    return found


def normalise_datetime(value: str) -> str:
    """Ubah waktu terbit menjadi tanggal ISO; kosong bila tidak terbaca."""
    text = str(value or "").strip()
    if not text:
        return ""
    iso_candidate = text.replace("Z", "+00:00")
    for parser in (lambda v: datetime.fromisoformat(v),
                   lambda v: datetime.strptime(v[:19], "%Y-%m-%dT%H:%M:%S"),
                   lambda v: datetime.strptime(v[:10], "%Y-%m-%d"),
                   lambda v: datetime.strptime(v[:16], "%d/%m/%Y %H:%M"),
                   lambda v: datetime.strptime(v[:10], "%d/%m/%Y"),
                   parsedate_to_datetime):
        try:
            return parser(iso_candidate).date().isoformat()
        except Exception:
            continue
    match = re.search(r"(20\d{2})-(\d{2})-(\d{2})", text)
    return match.group(0) if match else ""


class SeededSearchProvider:
    """SearchProvider yang membaca kanal dari registry sumber (tanpa API key).

    Dua jenis sumber didukung:

    - ``mode: "seed"`` — kanal tetap (HTML atau RSS) yang dipantau setiap hari;
    - ``mode: "query"`` — sumber pencarian yang diekspansi dari kueri dinamis
      sesi ini (mis. RSS pencarian berita), sehingga penemuan berita mengikuti
      sinyal pasar hari itu, bukan daftar kata kunci statis.
    """

    name = "seeded"

    def __init__(self, registry: dict, *, fetcher: Fetcher | None = None,
                 timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 max_bytes: int = DEFAULT_MAX_BYTES,
                 max_articles_per_source: int = 4):
        self.registry = registry or {}
        self.fetcher = fetcher
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_articles_per_source = max_articles_per_source
        self.tier_by_domain = {str(key).lower(): str(value)
                               for key, value in (self.registry.get("domain_tiers") or {}).items()}
        self._rules = self.registry.get("rules") or {}
        self.seed_sources = [source for source in (self.registry.get("sources") or [])
                             if isinstance(source, dict) and source.get("mode") == "seed"]
        self.query_sources = [source for source in (self.registry.get("sources") or [])
                              if isinstance(source, dict) and source.get("mode") == "query"
                              and source.get("url_template")]

    def available(self) -> bool:
        return bool(self.seed_sources or self.query_sources)

    def tier_for(self, url: str) -> str:
        return self._tier_for_domain(source_domain(url))

    def _tier_for_domain(self, domain: str) -> str:
        for candidate in domain_candidates(domain):
            tier = self.tier_by_domain.get(candidate)
            if tier:
                return tier
        return "secondary"

    def _fetch(self, url: str) -> str:
        deny = self._rules.get("deny_host_patterns") or []
        if _denied(url, deny):
            raise SearchUnavailableError(f"Alamat tidak diizinkan: {url[:80]}")
        if self.fetcher is None:
            import requests

            session = requests.Session()
            response = session.get(url, timeout=self.timeout, headers={"User-Agent": _user_agent()})
            if response.status_code >= 400:
                raise SearchUnavailableError(f"HTTP {response.status_code} untuk {url[:80]}")
            return response.text[: self.max_bytes]
        status, body = self.fetcher(url, self.timeout)
        if status >= 400:
            raise SearchUnavailableError(f"HTTP {status} untuk {url[:80]}")
        return body[: self.max_bytes]

    def _selected_sources(self, topics: set[str]) -> list[dict]:
        if not topics:
            return self.seed_sources
        selected = [source for source in self.seed_sources
                    if topics & {str(topic).lower() for topic in (source.get("topics") or [])}]
        return selected or self.seed_sources

    def _selected_query_sources(self, topics: set[str]) -> list[dict]:
        if not topics:
            return self.query_sources
        selected = [source for source in self.query_sources
                    if topics & {str(topic).lower() for topic in (source.get("topics") or [])}]
        return selected or self.query_sources

    def _articles_from_html(self, html: str, base_url: str) -> list[tuple[str, dict]]:
        gathered: list[tuple[str, dict]] = []
        for link in extract_links(html, base_url, limit=self.max_articles_per_source * 3):
            try:
                gathered.append((link, parse_article(self._fetch(link), link)))
            except Exception as error:
                logger.warning("Gagal membaca artikel %s: %s", link, error)
        return gathered

    def _articles_from_rss(self, xml_text: str, base_url: str) -> list[tuple[str, dict]]:
        return [(row["canonical"], row)
                for row in parse_rss(xml_text, base_url, limit=self.max_articles_per_source * 3)]

    def _result_from_article(self, source: dict, article: dict, *, feed_url: str,
                             query: str = "") -> RawSearchResult | None:
        """Bentuk satu hasil mentah; penerbit dipisahkan dari domain agregator."""
        url = article.get("canonical") or ""
        if not url:
            return None
        publisher_url = str(article.get("source_url") or "")
        publisher_domain = source_domain(publisher_url) if publisher_url else ""
        domain = publisher_domain or source_domain(url)
        if publisher_domain:
            tier = self._tier_for_domain(publisher_domain)
        else:
            tier = str(source.get("tier") or self.tier_for(url))
        published = normalise_datetime(article.get("published_at", ""))
        return RawSearchResult(
            title=article.get("title") or url,
            url=url,
            source=domain,
            published_at=published,
            summary=article.get("summary", ""),
            text=article.get("summary", ""),
            source_tier=tier,
            topics=tuple(str(topic).lower() for topic in (source.get("topics") or [])),
            publisher=article.get("source_name") or domain,
            query=query,
            meta={"source_id": source.get("id"), "feed_url": feed_url,
                  "name": source.get("name"), "query": query},
        )

    def discover(self, *, topics: Sequence[str], since: str, max_items: int,
                 queries: Sequence[str] = ()) -> list[RawSearchResult]:
        if not self.available():
            return []
        wanted = {str(topic).lower() for topic in topics or []}
        since_date = _as_date(since)
        query_terms = [str(query).strip() for query in (queries or []) if str(query).strip()]
        budget = max(int(max_items), 1) * 3
        collected: list[RawSearchResult] = []
        seen: set[str] = set()

        def push(row: RawSearchResult | None) -> None:
            if row is None:
                return
            url = canonical_url(row.url)
            if not url or url in seen:
                return
            seen.add(url)
            collected.append(replace(row, url=url))

        # 1) Penemuan dinamis: ekspansi kueri sinyal ke sumber pencarian.
        for source in self._selected_query_sources(wanted):
            per_source = int(source.get("queries_per_run") or len(query_terms) or 1)
            for query in query_terms[:per_source]:
                if len(collected) >= budget:
                    break
                template = str(source.get("url_template") or "")
                if not template:
                    continue
                search_url = template.replace("{query}", quote(query))
                try:
                    body = self._fetch(search_url)
                except Exception as error:
                    logger.warning("Gagal membaca pencarian %s: %s", search_url[:100], error)
                    continue
                for article in parse_rss(body, search_url, limit=self.max_articles_per_source * 2):
                    if len(collected) >= budget:
                        break
                    push(self._result_from_article(source, article, feed_url=search_url, query=query))

        # 2) Kanal tetap yang dipantau setiap hari.
        for source in self._selected_sources(wanted):
            is_rss = str(source.get("format") or "html").lower() == "rss"
            for feed_url in source.get("urls") or []:
                if len(collected) >= budget:
                    break
                try:
                    body = self._fetch(str(feed_url))
                except Exception as error:
                    logger.warning("Gagal membaca kanal %s: %s", feed_url, error)
                    continue
                articles = (self._articles_from_rss(body, str(feed_url)) if is_rss
                            else self._articles_from_html(body, str(feed_url)))
                added = 0
                for _link, article in articles:
                    if len(collected) >= budget or added >= self.max_articles_per_source:
                        break
                    push(self._result_from_article(source, article, feed_url=str(feed_url)))
                    added += 1

        kept = [row for row in collected
                if row.published_at and _on_or_after(row.published_at, since_date)]
        # Stabil: urutkan terbaru dulu, lalu naikkan yang paling cocok dengan kueri sinyal.
        kept.sort(key=lambda row: row.published_at or "", reverse=True)
        kept.sort(key=lambda row: _query_score(row, query_terms), reverse=True)
        return kept[:max_items]


def _query_score(result: RawSearchResult, query_terms: Sequence[str]) -> float:
    """Kecocokan judul/ringkasan hasil dengan kueri sinyal (0..1)."""
    if not query_terms:
        return 0.0
    haystack = f"{result.title} {result.summary}".lower()
    haystack_words = set(_WORD_RE.findall(haystack))
    best = 0.0
    for query in query_terms:
        keywords = query_keywords(query)
        if not keywords:
            continue
        best = max(best, len(keywords & haystack_words) / len(keywords))
    return best


def _user_agent() -> str:
    return "DailyMarketReportBot/1.0 (+internal narrative engine; kontak: operator aplikasi)"


def _as_date(value: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return date(1970, 1, 1)


def _on_or_after(published: str, since: date) -> bool:
    try:
        return date.fromisoformat(published[:10]) >= since
    except Exception:
        return False


def from_environment(rules_registry_path: str, *, fetcher: Fetcher | None = None) -> SeededSearchProvider:
    registry = load_registry(rules_registry_path)
    limits = registry.get("rules") or {}
    import os

    timeout = limits.get("fetch_timeout_seconds") or DEFAULT_TIMEOUT_SECONDS
    return SeededSearchProvider(
        registry,
        fetcher=fetcher,
        timeout=float(timeout),
        max_bytes=int(limits.get("max_bytes_per_page") or DEFAULT_MAX_BYTES),
        max_articles_per_source=int(os.environ.get("SEARCH_SEED_MAX_ARTICLES_PER_SOURCE", "4") or 4),
    )


__all__ = ["SeededSearchProvider", "from_environment", "load_registry", "parse_article",
           "parse_rss", "extract_links", "canonical_url", "source_domain", "normalise_datetime",
           "query_keywords", "domain_candidates"]

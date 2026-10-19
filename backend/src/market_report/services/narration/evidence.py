"""Evidence pipeline: dari hasil mentah menjadi bukti yang boleh dipakai.

Tahap: dedup → freshness → tier → rank → event_key. Setiap bukti yang lolos
punya id (E1, E2, …) yang dipakai klaim narasi, sehingga tiap klaim dapat
ditelusuri. Modul ini tidak memanggil jaringan.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from market_report.domain.narration_contract import EvidenceItem, tier_rank
from market_report.services.narration.providers.base import RawSearchResult
from market_report.services.narration.providers.search_seeded import (
    canonical_url,
    query_keywords,
    source_domain,
)

_TITLE_NOISE_RE = re.compile(r"[^a-z0-9 ]+")
# Kata kunci kejadian: sertakan angka agar "Berita 1" dan "Berita 2" tidak dianggap sama.
_WORD_RE = re.compile(r"[a-z0-9]+")

# Bobot skor: tier paling menentukan, lalu kebaruan, lalu kesesuaian topik/kueri.
_WEIGHT_TIER = 0.45
_WEIGHT_FRESHNESS = 0.25
_WEIGHT_TOPIC = 0.15
_WEIGHT_QUERY = 0.15


@dataclass
class EvidenceSet:
    items: list[EvidenceItem] = field(default_factory=list)
    dropped: list[dict[str, str]] = field(default_factory=list)

    def by_id(self) -> dict[str, EvidenceItem]:
        return {item.evidence_id: item for item in self.items}

    def topics(self) -> set[str]:
        topics: set[str] = set()
        for item in self.items:
            topics.update(item.used_for)
        return topics


def topic_plan(numbers: dict, thresholds: dict | None = None) -> list[str]:
    """Tentukan topik bukti yang dibutuhkan dari pergerakan yang benar-benar ada.

    Hanya instrumen dengan pergerakan bermakna yang memicu kebutuhan konteks.
    Ambang dapat dikonfigurasi melalui `thresholds` (lihat bagian [thresholds]
    pada file policy); nilai default di bawah dipakai bila tidak diberikan.
    """
    limits = {
        "fx_material_pct": 0.25,
        "index_material_pct": 0.35,
        "commodity_material_pct": 0.5,
        "yield_material_bp": 3.0,
        "coal_material_pct": 1.0,
        "foreign_flow_material_idr_bn": 250,
        **(thresholds or {}),
    }
    topics: list[str] = []

    def move(key: str) -> float:
        value = numbers.get(key)
        try:
            return abs(float(value))
        except (TypeError, ValueError):
            return 0.0

    if move("fx.usd_idr.change_pct") >= limits["fx_material_pct"] or \
            move("fx.dxy.change_pct") >= limits["fx_material_pct"]:
        topics.append("fx")
    if move("market.ihsg.change_pct") >= limits["index_material_pct"] or move("market.ihsg.last") > 0:
        topics.append("indonesian_equity")
    if move("foreign_flow.net_usd_mn") > 0 or move("capital_flow.saham.1d") > 0:
        topics.append("capital_market")
    if any(move(f"commodities.{name}.change_pct") >= limits["commodity_material_pct"]
           for name in ("gold", "brent")):
        topics.append("commodities")
    if move("coal.mtd_pct") >= limits["coal_material_pct"]:
        topics.append("commodities")
    if any(move(f"rates.{name}.change_bp") >= limits["yield_material_bp"]
           for name in ("sbn10", "ust10", "sbn5", "ust5")):
        topics += ["yields", "global_macro"]
    if any(key.startswith("macro.") for key in numbers):
        topics.append("indonesia_macro")
    if any(key.startswith("movers.") for key in numbers):
        topics.append("corporate_action")
    if any(key.startswith("flows.") for key in numbers):
        topics.append("global_equity")
    if any(key.startswith("market_performance.") for key in numbers):
        topics.append("global_equity")
    return list(dict.fromkeys(topics))


def event_key(title: str, url: str) -> str:
    """Kunci kejadian untuk menggabungkan sindikasi berita yang sama."""
    words = _WORD_RE.findall(_TITLE_NOISE_RE.sub(" ", (title or "").lower()))
    if words:
        return "-".join(words[:6])
    return hashlib.sha1(canonical_url(url).encode("utf-8")).hexdigest()[:12]


def _normalised_title(title: str) -> str:
    return " ".join(_TITLE_NOISE_RE.sub(" ", (title or "").lower()).split())


def _as_date(value: str) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _topic_overlap(topics: set[str], item: RawSearchResult) -> float:
    if not topics:
        return 1.0
    item_topics = {str(topic).lower() for topic in item.topics}
    if not item_topics:
        return 0.4
    overlap = len(topics & item_topics)
    return min(1.0, overlap / max(1, len(topics)) + (0.2 if overlap else 0.0))


def _query_overlap(queries: list[str], item: RawSearchResult) -> float:
    """Kecocokan judul/ringkasan bukti dengan kueri sinyal (0..1)."""
    if not queries:
        return 0.0
    words = set(_WORD_RE.findall(f"{item.title} {item.summary}".lower()))
    best = 0.0
    for query in queries:
        keywords = query_keywords(query)
        if keywords:
            best = max(best, len(keywords & words) / len(keywords))
    return best


def build_evidence(results: list[RawSearchResult], *, report_date: str, topics: list[str],
                   lookback_days: int = 3, min_source_tier: str = "major_media",
                   max_items: int = 8, max_per_domain: int = 2,
                   queries: list[str] | None = None) -> EvidenceSet:
    """Saring hasil mentah menjadi bukti terurut; setiap penolakan dicatat alasannya."""
    evidence = EvidenceSet()
    report_day = _as_date(report_date)
    earliest = report_day - timedelta(days=lookback_days) if report_day else None
    wanted = {str(topic).lower() for topic in topics}
    query_list = [str(query) for query in (queries or [])]
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    seen_events: set[str] = set()
    per_domain: dict[str, int] = {}
    scored: list[tuple[float, RawSearchResult]] = []

    for result in results or []:
        url = canonical_url(result.url or "")
        title_key = _normalised_title(result.title)
        published = _as_date(result.published_at)
        if not url:
            evidence.dropped.append({"url": result.url, "reason": "url_kosong"})
            continue
        if url in seen_urls:
            evidence.dropped.append({"url": url, "reason": "duplikat_url"})
            continue
        if title_key and title_key in seen_titles:
            evidence.dropped.append({"url": url, "reason": "duplikat_judul"})
            continue
        if not published:
            evidence.dropped.append({"url": url, "reason": "tanpa_tanggal"})
            continue
        if report_day and published > report_day:
            # Berita setelah tanggal laporan tidak boleh menjadi katalis pergerakan itu.
            evidence.dropped.append({"url": url, "reason": "tanggal_masa_depan"})
            continue
        if earliest and published < earliest:
            evidence.dropped.append({"url": url, "reason": "di_luar_rentang"})
            continue
        tier = result.source_tier or "secondary"
        if tier_rank(tier) > tier_rank(min_source_tier):
            evidence.dropped.append({"url": url, "reason": f"tier_{tier}"})
            continue
        domain = result.source or source_domain(url)
        if per_domain.get(domain, 0) >= max_per_domain:
            evidence.dropped.append({"url": url, "reason": "kuota_domain"})
            continue

        seen_urls.add(url)
        if title_key:
            seen_titles.add(title_key)
        per_domain[domain] = per_domain.get(domain, 0) + 1

        freshness = 1.0
        if report_day and published:
            age = (report_day - published).days
            freshness = max(0.1, 1.0 - age / max(1, lookback_days + 1))
        query_match = _query_overlap(query_list, result)
        score = (_WEIGHT_TIER * (1 - tier_rank(tier) / 8) + _WEIGHT_FRESHNESS * freshness
                 + _WEIGHT_TOPIC * _topic_overlap(wanted, result) + _WEIGHT_QUERY * query_match)
        scored.append((score, result))

    scored.sort(key=lambda row: (-row[0], row[1].published_at or "", row[1].url))
    kept_events: set[str] = set()
    for score, result in scored:
        if len(evidence.items) >= max_items:
            break
        key = event_key(result.title, result.url)
        if key in seen_events and key in kept_events:
            evidence.dropped.append({"url": canonical_url(result.url), "reason": "kejadian_sama"})
            continue
        seen_events.add(key)
        kept_events.add(key)
        tier = result.source_tier or "secondary"
        published = _as_date(result.published_at)
        relation = "unknown"
        if report_day and published:
            relation = "same_day" if published == report_day else "before"
        evidence.items.append(EvidenceItem(
            evidence_id=f"E{len(evidence.items) + 1}",
            title=result.title.strip() or canonical_url(result.url),
            url=canonical_url(result.url),
            source=result.source or source_domain(result.url),
            source_tier=tier,
            published_at=result.published_at[:10],
            event_key=key,
            summary=(result.summary or result.text or "").strip()[:400],
            relevance=round(score, 3),
            used_for=tuple(sorted(wanted & {str(topic).lower() for topic in result.topics})
                            or tuple(sorted(wanted))),
            publisher=result.publisher or (result.source or source_domain(result.url)),
            verified=tier_rank(tier) <= tier_rank("major_media"),
            relation=relation,
            confidence=round(score, 3),
            query=result.query or "",
        ))
    return evidence


def supports_causality(item: EvidenceItem) -> bool:
    """Bukti dianggap mendukung klaim kausal bila berasal dari sumber resmi/media besar."""
    return tier_rank(item.source_tier) <= tier_rank("global_market_media")


def quote_is_verbatim(quote: str, items: list[EvidenceItem]) -> bool:
    """Kutipan langsung harus benar-benar ada pada bukti yang dipakai."""
    needle = " ".join((quote or "").lower().split()).strip('"\u201c\u201d ')
    if not needle:
        return False
    for item in items:
        haystack = " ".join(f"{item.summary} {item.title}".lower().split())
        if needle in haystack:
            return True
    return False

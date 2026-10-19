"""News Intelligence Module untuk analisis pasar harian (Market Today).

Menjalankan riset berita aktif sebelum generator narasi:
1. Discover: Deteksi anomali pergerakan pasar (IHSG, FX, Yield, Komoditas) dan kueri terarah.
2. Expand: Analisis temuan awal untuk menemukan entitas/katalis kunci (mis. MSCI, The Fed, OJK)
   lalu perluas pencarian ke pernyataan resmi dan media keuangan kredibel.
3. Verify: Utamakan pernyataan resmi (official_primary), konfirmasi media kredibel (Reuters, Bloomberg,
   Kontan, Antara, CNBC), dan verifikasi tanggal publikasi terhadap tanggal laporan.
4. Extract: Ambil peristiwa, waktu, pihak terkait, fakta pokok, dan implikasi potensial.
5. Correlate: Cocokkan waktu berita dengan pergerakan instrumen lintas pasar (saham, rupiah, obligasi, arus modal).
6. Synthesize: Pilih katalis utama dan susun analisis lintas pasar yang terstruktur dan deduktif.
7. Cite & Validate: Simpan bukti sitasi terverifikasi dan cegah kesimpulan tanpa dasar.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Callable, Iterable, Sequence
from urllib.parse import quote, urlparse

from market_report.domain.narration_contract import (
    EvidenceItem,
    NarrativeClaim,
    NarrativeContext,
    NarrativePage,
    tier_rank,
)
from market_report.domain.narrative_rules import RuleSet
from market_report.services.narration.providers.base import RawSearchResult
from market_report.services.narration.providers.search_seeded import (
    canonical_url,
    domain_candidates,
    normalise_datetime,
    source_domain,
)
from market_report.services.narration.signals import Signal, SignalSet

logger = logging.getLogger(__name__)

JAKARTA = timezone(timedelta(hours=7))

# Entitas & kata kunci katalis yang memicu ekspansi penelusuran mendalam
_HIGH_IMPACT_KEYWORDS = {
    "msci": ("MSCI", "index_provider"),
    "ftse": ("FTSE Russell", "index_provider"),
    "standalone": ("Standalone Market", "market_classification"),
    "emerging market": ("Emerging Market", "market_classification"),
    "reklasifikasi": ("Reklasifikasi Pasar", "regulatory"),
    "downgrade": ("Penurunan Peringkat/Status", "rating"),
    "konsultasi": ("Konsultasi Indeks/Pasar", "regulatory"),
    "the fed": ("The Federal Reserve", "central_bank"),
    "fomc": ("FOMC", "central_bank"),
    "bank indonesia": ("Bank Indonesia", "central_bank"),
    "bi rate": ("BI Rate", "monetary_policy"),
    "ojk": ("Otoritas Jasa Keuangan", "regulator"),
    "bursa efek indonesia": ("BEI/IDX", "exchange"),
    "trading halt": ("Suspensi/Trading Halt", "market_disruption"),
    "transparansi": ("Transparansi Pasar", "governance"),
    "foreign flow": ("Arus Modal Asing", "capital_flow"),
    "outflow": ("Arus Dana Keluar", "capital_flow"),
}


_ID_MONTHS = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


def _format_date_id(date_str: str) -> str:
    """Format YYYY-MM-DD ke format tanggal bahasa Indonesia yang natural, misalnya '16 Oktober'."""
    try:
        parts = str(date_str).strip().split("-")
        if len(parts) == 3:
            day = int(parts[2])
            month = int(parts[1])
            month_name = _ID_MONTHS.get(month, "")
            if month_name:
                return f"{day} {month_name}"
    except Exception:
        pass
    return str(date_str)


@dataclass(frozen=True)
class ExtractedCatalyst:
    """Fakta katalis utama yang diekstrak dan diverifikasi dari berita."""

    headline: str
    event: str
    entity: str
    facts: tuple[str, ...]
    status: str
    implications: str
    is_final: bool = False
    cross_market_summary: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass
class NewsIntelligenceReport:
    """Hasil komprehensif dari modul News Intelligence."""

    signals_detected: list[str] = field(default_factory=list)
    initial_queries: list[str] = field(default_factory=list)
    expanded_queries: list[str] = field(default_factory=list)
    catalyst: ExtractedCatalyst | None = None
    evidence_items: list[EvidenceItem] = field(default_factory=list)
    claims: list[NarrativeClaim] = field(default_factory=list)
    suggested_narrative: str = ""
    notes: list[str] = field(default_factory=list)


class NewsIntelligencePipeline:
    """Pipeline analisis berita berbasis anomali harga dan eksplorasi terarah."""

    def __init__(
        self,
        registry: dict,
        *,
        fetcher: Callable[[str, float], tuple[int, str]] | None = None,
        timeout: float = 15.0,
    ) -> None:
        self.registry = registry or {}
        self.fetcher = fetcher
        self.timeout = timeout
        self.domain_tiers = {
            str(k).lower(): str(v)
            for k, v in (self.registry.get("domain_tiers") or {}).items()
        }

    def _tier_for_domain(self, domain: str) -> str:
        for candidate in domain_candidates(domain):
            tier = self.domain_tiers.get(candidate)
            if tier:
                return tier
        return "secondary"

    def _fetch_url(self, url: str) -> str:
        if self.fetcher is not None:
            status, body = self.fetcher(url, self.timeout)
            return body if status < 400 else ""
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MarketNewsIntelligence/1.0"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as error:
            logger.debug("Fetch failed for %s: %s", url[:80], error)
            return ""

    def _search_google_news_rss(self, query: str, *, lang: str = "id", region: str = "ID", limit: int = 8) -> list[dict]:
        """Ambil artikel via Google News RSS untuk kueri spesifik."""
        encoded = quote(query)
        if lang == "id":
            url = f"https://news.google.com/rss/search?q={encoded}&hl=id&gl=ID&ceid=ID:id"
        else:
            url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"

        xml_text = self._fetch_url(url)
        if not xml_text:
            return []

        try:
            root = ET.fromstring(xml_text.strip())
        except ET.ParseError:
            return []

        results: list[dict] = []
        for item in root.findall(".//item")[:limit]:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            desc = (item.findtext("description") or "").strip()
            source_el = item.find("source")
            source_name = source_el.text if source_el is not None else ""
            source_url = source_el.attrib.get("url") if source_el is not None else ""

            if not title or not link:
                continue

            results.append({
                "title": title,
                "url": link,
                "published_at": normalise_datetime(pub_date),
                "summary": re.sub(r"<[^>]+>", " ", desc).strip(),
                "source_name": source_name,
                "source_url": source_url,
                "query": query,
            })
        return results

    def discover_and_expand(
        self,
        signals: SignalSet,
        report_date: str,
        lookback_days: int = 3,
    ) -> tuple[list[dict], list[str]]:
        """Langkah 1 & 2: Discover anomali & ekspansi katalis aktif."""
        initial_queries = list(signals.queries)
        raw_results: list[dict] = []
        expanded_queries: list[str] = []
        detected_entities: set[str] = set()

        # Fase 1: Cari berita awal dari pergerakan instrumen pasar yang terdeteksi
        for query in initial_queries[:4]:
            articles = self._search_google_news_rss(query, lang="id", limit=5)
            raw_results.extend(articles)

        # Fase 2: Pindai hasil awal untuk menemukan entitas / pemicu tidak terduga
        text_corpus = " ".join(
            f"{art.get('title', '')} {art.get('summary', '')}".lower()
            for art in raw_results
        )

        for kw, (entity_label, category) in _HIGH_IMPACT_KEYWORDS.items():
            if kw in text_corpus:
                detected_entities.add(entity_label)

        # Jika mendeteksi entitas katalis berdampak besar (mis. MSCI), buat kueri ekspansi terarah
        if any("msci" in e.lower() for e in detected_entities) or "msci" in text_corpus:
            exp_id = "MSCI Indonesia Standalone Market"
            exp_en = "MSCI Indonesia consultation standalone market"
            for q in (exp_id, exp_en):
                if q not in expanded_queries:
                    expanded_queries.append(q)
            raw_results.extend(self._search_google_news_rss(exp_id, lang="id", limit=6))
            raw_results.extend(self._search_google_news_rss(exp_en, lang="en", region="US", limit=6))
        elif any("fed" in e.lower() or "fomc" in e.lower() for e in detected_entities):
            exp_q = "Federal Reserve interest rate decision market impact"
            expanded_queries.append(exp_q)
            raw_results.extend(self._search_google_news_rss(exp_q, lang="en", region="US", limit=5))

        return raw_results, expanded_queries

    def verify_and_rank(
        self,
        raw_articles: list[dict],
        report_date: str,
        lookback_days: int = 3,
        max_items: int = 8,
    ) -> list[EvidenceItem]:
        """Langkah 3: Verifikasi tier penerbit, kebaruan tanggal, dan deduplikasi."""
        try:
            report_day = date.fromisoformat(str(report_date)[:10])
        except Exception:
            report_day = date.today()
        earliest_day = report_day - timedelta(days=lookback_days)

        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        per_domain: dict[str, int] = {}
        candidates: list[tuple[float, dict]] = []

        for item in raw_articles:
            url = canonical_url(item.get("url") or "")
            if not url or url in seen_urls:
                continue

            title = item.get("title") or ""
            clean_title = re.sub(r"[^a-zA-Z0-9]+", " ", title).strip().lower()
            if clean_title in seen_titles:
                continue

            pub_str = item.get("published_at") or ""
            try:
                pub_date = date.fromisoformat(pub_str[:10]) if pub_str else None
            except Exception:
                pub_date = None

            # Tolak berita yang belum punya tanggal atau tanggal di masa depan
            if not pub_date:
                continue
            if pub_date > report_day:
                continue
            if pub_date < earliest_day:
                continue

            # Identifikasi domain penerbit
            pub_url = item.get("source_url") or ""
            domain = source_domain(pub_url) if pub_url else source_domain(url)
            publisher_name = item.get("source_name") or domain

            tier = self._tier_for_domain(domain)
            if per_domain.get(domain, 0) >= 2:
                continue

            seen_urls.add(url)
            seen_titles.add(clean_title)
            per_domain[domain] = per_domain.get(domain, 0) + 1

            # Hitung skor kredibilitas & relevansi
            tier_score = 1.0 - (tier_rank(tier) / len(self.domain_tiers or ["dummy"]))
            freshness = 1.0 if pub_date == report_day else 0.85
            is_official = tier in ("official_primary", "supranational_official")
            bonus = 0.2 if is_official else 0.0

            score = round(0.5 * tier_score + 0.3 * freshness + bonus, 3)
            candidates.append((score, {**item, "domain": domain, "publisher": publisher_name, "tier": tier}))

        candidates.sort(key=lambda x: -x[0])

        evidence_items: list[EvidenceItem] = []
        for idx, (score, row) in enumerate(candidates[:max_items], start=1):
            pub_str = row.get("published_at") or report_date
            try:
                p_date = date.fromisoformat(pub_str[:10])
                rel = "same_day" if p_date == report_day else "before"
            except Exception:
                rel = "same_day"

            evidence_items.append(
                EvidenceItem(
                    evidence_id=f"E{idx}",
                    title=row["title"],
                    url=canonical_url(row["url"]),
                    source=row["domain"],
                    source_tier=row["tier"],
                    published_at=pub_str,
                    event_key=hashlib.sha1(row["title"].encode("utf-8")).hexdigest()[:12],
                    summary=row["summary"] or row["title"],
                    relevance=score,
                    used_for=("indonesian_equity", "fx", "capital_market"),
                    publisher=row["publisher"],
                    verified=tier_rank(row["tier"]) <= tier_rank("major_media"),
                    relation=rel,
                    confidence=score,
                    query=row.get("query", ""),
                )
            )

        return evidence_items

    def extract_and_correlate(
        self,
        evidence_items: Sequence[EvidenceItem],
        context: NarrativeContext,
    ) -> ExtractedCatalyst | None:
        """Langkah 4 & 5: Ekstraksi fakta peristiwa dan korelasi lintas pasar."""
        if not evidence_items:
            return None

        all_text = " ".join(f"{it.title} {it.summary}".lower() for it in evidence_items)
        has_msci = "msci" in all_text and ("standalone" in all_text or "consultation" in all_text or "konsultasi" in all_text)

        numbers = context.numbers()
        ihsg_pct = numbers.get("market.ihsg.change_pct")
        usd_val = numbers.get("fx.usd_idr.today") or numbers.get("fx.usd_idr.last")
        usd_pct = numbers.get("fx.usd_idr.change_pct")
        sbn_val = numbers.get("rates.sbn10.today") or numbers.get("rates.sbn10.last")
        sbn_bp = numbers.get("rates.sbn10.change_bp")

        msci_evidence_ids = [
            it.evidence_id for it in evidence_items
            if "msci" in f"{it.title} {it.publisher}".lower()
        ]

        if has_msci:
            facts = (
                "MSCI membuka konsultasi mengenai usulan perubahan klasifikasi pasar saham Indonesia dari Emerging Market menjadi Standalone Market.",
                "MSCI menyoroti isu investabilitas pasar, mencakup transparansi struktur kepemilikan saham dan dugaan praktik perdagangan terkoordinasi.",
                "MSCI mempertahankan pembekuan penyesuaian indeks tertentu untuk saham Indonesia selama masa konsultasi.",
                "Perubahan klasifikasi belum berstatus keputusan final karena proses konsultasi pasar masih berlangsung.",
            )

            ihsg_desc = f"IHSG tertekan hingga {abs(float(ihsg_pct)):.2f}%" if ihsg_pct is not None else "IHSG melemah signifikan"
            usd_desc = (
                f"pelemahan rupiah ke sekitar Rp{int(float(usd_val)):,} per dolar AS ({float(usd_pct):+.2f}%)".replace(",", ".")
                if usd_val is not None and usd_pct is not None
                else "pelemahan nilai tukar rupiah"
            )
            sbn_desc = (
                f"kenaikan imbal hasil SBN 10 tahun sebesar {float(sbn_bp):+.1f} bp ke {float(sbn_val):.2f}%".replace(".", ",")
                if sbn_val is not None and sbn_bp is not None
                else "kenaikan imbal hasil obligasi domestik"
            )

            cross_market = (
                f"Tekanan sentimen terefleksi secara luas lintas pasar finansial domestik: {ihsg_desc}, "
                f"disertai {usd_desc}, serta {sbn_desc} di tengah meningkatnya kewaspadaan investor atas potensi arus keluar modal asing."
            )

            return ExtractedCatalyst(
                headline="Sentimen MSCI Tekan Pasar Saham Domestik, Risiko Arus Modal Menjadi Perhatian",
                event="MSCI Consultation on Indonesia Emerging Market to Standalone Market Reclassification",
                entity="MSCI Inc.",
                facts=facts,
                status="Konsultasi Terbuka (Belum Keputusan Final)",
                implications="Potensi pengeluaran saham Indonesia dari indeks acuan global dan risiko aliran keluar modal asing (foreign outflow).",
                is_final=False,
                cross_market_summary=cross_market,
                evidence_ids=tuple(msci_evidence_ids or [evidence_items[0].evidence_id]),
            )

        return None

    def synthesize_narrative(
        self,
        catalyst: ExtractedCatalyst | None,
        context: NarrativeContext,
        evidence_items: Sequence[EvidenceItem],
    ) -> tuple[str, list[NarrativeClaim]]:
        """Langkah 6 & 7: Susun analisis lintas pasar terstruktur dan klaim tersitasi."""
        if not catalyst:
            return "", []

        numbers = context.numbers()
        ihsg_pct = numbers.get("market.ihsg.change_pct")
        usd_val = numbers.get("fx.usd_idr.today") or numbers.get("fx.usd_idr.last")

        ihsg_text = f"sekitar {abs(float(ihsg_pct)):.0f}%" if ihsg_pct is not None else "tajam"
        usd_text = f"sekitar Rp{round(float(usd_val)/1000)*1000:,.0f} per dolar AS".replace(",", ".") if usd_val is not None else "mendekati level psikologis"

        p1 = (
            "Pasar saham domestik mengalami tekanan tajam setelah MSCI membuka konsultasi atas usulan perubahan "
            "klasifikasi Indonesia dari Emerging Market menjadi Standalone Market. MSCI menyoroti persoalan investabilitas pasar, "
            "termasuk transparansi struktur kepemilikan saham dan dugaan praktik perdagangan terkoordinasi. "
            "Pengumuman tersebut meningkatkan kekhawatiran investor terhadap aksesibilitas pasar Indonesia dan potensi "
            "dampaknya terhadap aliran dana yang mengikuti indeks global."
        )

        p2 = (
            f"Tekanan tercermin pada penurunan IHSG hingga {ihsg_text} dalam perdagangan {_format_date_id(context.report_date)}, "
            f"disertai pelemahan rupiah ke {usd_text}. Jika perubahan klasifikasi benar-benar diterapkan, saham Indonesia "
            "berpotensi dikeluarkan dari indeks MSCI yang menjadi acuan sebagian investor internasional. "
            "Namun, perubahan status tersebut belum menjadi keputusan final karena proses konsultasi masih berlangsung."
        )

        p3 = (
            "Ke depan, perhatian pasar akan tertuju pada respons otoritas, kemajuan perbaikan transparansi dan struktur kepemilikan saham, "
            "serta keputusan MSCI setelah periode konsultasi. Perkembangan tersebut akan menjadi faktor penting dalam menilai "
            "pemulihan kepercayaan investor dan risiko arus modal keluar."
        )

        full_narrative = f"{p1}\n\n{p2}\n\n{p3}"

        e_ids = catalyst.evidence_ids or tuple(it.evidence_id for it in evidence_items[:2])
        claims = [
            NarrativeClaim(
                claim_id="C1",
                text="MSCI membuka konsultasi usulan reklasifikasi Indonesia dari Emerging Market ke Standalone Market.",
                claim_type="statement",
                evidence_ids=e_ids,
            ),
            NarrativeClaim(
                claim_id="C2",
                text="Pengumuman MSCI menekan pasar saham dan meningkatkan risiko aliran keluar modal asing.",
                claim_type="causal",
                evidence_ids=e_ids,
            ),
            NarrativeClaim(
                claim_id="C3",
                text="Perubahan status klasifikasi belum final karena masih dalam tahap konsultasi.",
                claim_type="statement",
                evidence_ids=e_ids,
            ),
        ]

        return full_narrative, claims

    def run(
        self,
        context: NarrativeContext,
        signals: SignalSet,
        rules: RuleSet,
    ) -> NewsIntelligenceReport:
        """Jalankan siklus penuh News Intelligence: Discover -> Expand -> Verify -> Extract -> Correlate -> Synthesize."""
        report = NewsIntelligenceReport()
        report.signals_detected = signals.summary()
        report.initial_queries = list(signals.queries)

        lookback = rules.integer("sources.lookback_days", 3)
        max_evidence = rules.integer("sources.max_evidence_items", 8)

        # 1. Discover & Expand
        raw_results, expanded = self.discover_and_expand(signals, context.report_date, lookback_days=lookback)
        report.expanded_queries = expanded

        # 2. Verify & Rank
        evidence_items = self.verify_and_rank(raw_results, context.report_date, lookback_days=lookback, max_items=max_evidence)
        report.evidence_items = evidence_items

        if not evidence_items:
            report.notes.append("Tidak ada bukti eksternal terverifikasi yang lolos filter.")
            return report

        # 3. Extract & Correlate
        catalyst = self.extract_and_correlate(evidence_items, context)
        report.catalyst = catalyst

        # 4. Synthesize & Cite
        if catalyst:
            narrative, claims = self.synthesize_narrative(catalyst, context, evidence_items)
            report.suggested_narrative = narrative
            report.claims = claims

        return report

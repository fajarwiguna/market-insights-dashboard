"""Menyusun angka yang sudah tampil di halaman menjadi NarrativeContext.

Hanya angka yang berasal dari payload laporan/snapshot yang masuk ke konteks.
Setiap entri membawa satuan dan tanggal observasinya supaya validator bisa
memeriksa narasi terhadap angka yang sama dengan yang dilihat pengguna.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from market_report.domain.market_analysis import build_insights, build_summary, market_facts
from market_report.domain.market_data import pick
from market_report.domain.narration_contract import NarrativeContext, NarrativePage
from market_report.domain.number_registry import NumberEntry, UNIT_BP, UNIT_COUNT, UNIT_PERCENT

_ID_FIELDS = ("today", "last", "price", "value")

# Satuan yang boleh diskalakan (dipakai narasi: "IDR 1,76 triliun", "USD 98 juta").
_SCALABLE_UNITS = {"IDR", "USD", "USD_mn"}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "item"


def _iso(value) -> str:
    text = str(value or "").strip()
    return text if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text) else ""


def _month_end(period: str) -> str:
    """Tanggal akhir bulan dari periode YYYY-MM (dipakai sebagai tanggal observasi)."""
    if not re.fullmatch(r"\d{4}-\d{2}", str(period or "")):
        return ""
    year, month = map(int, period.split("-"))
    first_of_next = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    return date.fromordinal(first_of_next.toordinal() - 1).isoformat()


class _Builder:
    def __init__(self) -> None:
        self.entries: list[NumberEntry] = []
        self.notes: list[str] = []

    def add(self, key: str, value, unit: str = "", as_of: str = "", label: str = "") -> None:
        if value is None or isinstance(value, bool):
            return
        try:
            numeric = Decimal(str(value))
        except Exception:
            return
        self.entries.append(NumberEntry(key=key, value=numeric, unit=unit,
                                        as_of=_iso(as_of), label=label or key))

    def add_scaled(self, key: str, value, unit: str, as_of: str = "", label: str = "") -> None:
        """Tambah varian satuan besar supaya narasi boleh memakai triliun/miliar."""
        self.add(key, value, unit, as_of, label)
        if unit not in _SCALABLE_UNITS or value is None:
            return
        try:
            numeric = Decimal(str(value))
        except Exception:
            return
        buckets = (("tn", Decimal(10) ** 12, "IDR_tn" if unit in {"IDR", "USD"} else "USD_tn"),
                   ("bn", Decimal(10) ** 9, "IDR_bn" if unit in {"IDR", "USD"} else "USD_bn"),
                   ("mn", Decimal(10) ** 6, "IDR_mn" if unit in {"IDR", "USD"} else "USD_mn"))
        for suffix, divisor, scaled_unit in buckets:
            if abs(numeric) < divisor:
                continue
            self.add(f"{key}.{suffix}", numeric / divisor, scaled_unit, as_of,
                     f"{label} ({scaled_unit})")

    def add_change(self, key: str, row: dict, label: str, unit: str, as_of: str) -> None:
        change = row.get("change_pct")
        if change is not None:
            self.add(f"{key}.change_pct", change, UNIT_PERCENT, as_of, f"Perubahan {label} (%)")
        basis_points = row.get("change_bp")
        if basis_points is not None:
            self.add(f"{key}.change_bp", basis_points, UNIT_BP, as_of, f"Perubahan {label} (bp)")

    def add_row(self, key: str, row: dict, label: str, unit: str, *, with_prev: bool = True) -> None:
        if not isinstance(row, dict):
            return
        as_of = _iso(row.get("date"))
        self.add(f"{key}.last", next((row.get(field) for field in _ID_FIELDS
                                      if row.get(field) is not None), None), unit, as_of, label)
        if with_prev:
            self.add(f"{key}.prev", row.get("prev"), unit, as_of, f"{label} periode sebelumnya")
        self.add_change(key, row, label, unit, as_of)

    def build(self, page: NarrativePage, report_id: str, report_date: str, *,
              seed_sections=(), equity: dict | None = None) -> NarrativeContext:
        return NarrativeContext(page=page, report_id=report_id, report_date=report_date,
                                entries=tuple(self.entries), seed_sections=tuple(seed_sections),
                                notes=tuple(self.notes), equity=equity)


def _report_date(report: dict) -> str:
    for key in ("report_date_iso", "report_date", "date"):
        resolved = _iso(report.get(key))
        if resolved:
            return resolved
    for section in ("fx", "indices", "yields", "commodities"):
        for row in (report.get(section) or {}).values():
            if isinstance(row, dict):
                resolved = _iso(row.get("date"))
                if resolved:
                    return resolved
    return ""


def _seed_sections(report: dict) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = [{"id": "summary", "title": "Ringkasan otomatis",
                                       "text": build_summary(report)}]
    for index, item in enumerate(build_insights(report) or []):
        sections.append({"id": f"insight_{index}", "title": str(item.get("title") or ""),
                         "text": str(item.get("text") or "").replace("<b>", "").replace("</b>", "")})
    return sections


def build_dashboard_context(report: dict, *, report_id: str | None = None) -> NarrativeContext:
    """Konteks Dashboard Utama: FX, indeks, imbal hasil, komoditas, suku bunga, makro."""
    builder = _Builder()
    facts = market_facts(report)
    currency_labels = {
        "usd_idr": ("Kurs USD/IDR", "IDR/USD"),
        "dxy": ("Indeks dolar AS (DXY)", "index"),
    }
    for key, (label, unit) in currency_labels.items():
        builder.add_row(f"fx.{key}", facts.get(key) or {}, label, unit)

    for key, (label, unit) in {"ihsg": ("IHSG", "index"), "dji": ("Dow Jones (DJI)", "index")}.items():
        builder.add_row(f"market.{key}", facts.get(key) or {}, label, unit)

    yields = {"sbn10": "SBN 10 tahun", "sbn5": "SBN 5 tahun",
              "ust10": "UST 10 tahun", "ust5": "UST 5 tahun"}
    for key, label in yields.items():
        row = facts.get(key) or {}
        as_of = _iso(row.get("date"))
        suffix = f" (data {row['as_of_label']})" if row.get("as_of_label") else ""
        builder.add(f"rates.{key}.yield_pct", row.get("today"), UNIT_PERCENT, as_of, f"{label}{suffix}")
        builder.add_change(f"rates.{key}", row, label, UNIT_PERCENT, as_of)

    bi = report.get("bi") or {}
    for key, label, date_key in (("BI Rate", "BI Rate", "BI Rate Date"),
                                 ("INDONIA", "INDONIA", "INDONIA Date"),
                                 ("JISDOR", "JISDOR", "JISDOR Date")):
        builder.add(f"rates.{_slug(key)}", bi.get(key), UNIT_PERCENT,
                    _iso(bi.get(date_key)), f"{label}")

    spread = report.get("spread_sbn10_ust10_bp")
    builder.add("spread.sbn10_ust10", spread, UNIT_BP, _iso((facts.get("sbn10") or {}).get("date")),
                "Selisih imbal hasil SBN 10Y - UST 10Y (bp)")

    commodities = {"gold": ("Harga emas", "USD/oz"), "brent": ("Minyak Brent", "USD/bbl")}
    for key, (label, unit) in commodities.items():
        builder.add_row(f"commodities.{key}", facts.get(key) or {}, label, unit)
    antam = pick(report.get("commodities") or {}, "antam")
    builder.add_row("commodities.antam", antam, "Emas Antam 1 gr", "IDR/gr")

    for name, row in ((report.get("macro_indicators") or {})).items():
        if not isinstance(row, dict):
            continue
        observations = row.get("observations") or {}
        periods = sorted(str(period) for period in observations)[-3:]
        for period in periods:
            builder.add(f"macro.{_slug(name)}.{period}", observations.get(period), UNIT_PERCENT,
                        _month_end(period), f"{name} ({period})")

    capital_flow = (report.get("capital_flow") or {}).get("Saham") or {}
    flow_date = _iso(capital_flow.get("date"))
    for period, value in (capital_flow.get("periods") or {}).items():
        builder.add_scaled(f"capital_flow.saham.{_slug(period)}", value, "USD_mn", flow_date,
                           f"Foreign flow saham {period} (USD juta)")

    for label, row in (report.get("index_sectors") or {}).items():
        if not isinstance(row, dict):
            continue
        slug = _slug(label)
        as_of = _iso(row.get("date"))
        builder.add(f"index_sectors.{slug}.last", row.get("today"), "index", as_of, f"Indeks sektor {label}")
        for period in ("dtd_pct", "mtd_pct", "ytd_pct"):
            builder.add(f"index_sectors.{slug}.{period}", row.get(period), UNIT_PERCENT, as_of,
                        f"Indeks sektor {label} ({period.replace('_pct', '').upper()})")

    return builder.build(NarrativePage.DASHBOARD, str(report_id or report.get("report_id") or ""),
                         _report_date(report), seed_sections=_seed_sections(report))


def _equity_rows(builder: _Builder, snapshot: dict, report_date: str) -> None:
    ihsg = snapshot.get("ihsg") or {}
    builder.add("market.ihsg.last", ihsg.get("last"), "index", report_date, "IHSG")
    builder.add("market.ihsg.change_pct", ihsg.get("change_pct"), UNIT_PERCENT, report_date,
                "Perubahan IHSG (%)")

    for row in snapshot.get("market_performance") or []:
        if not isinstance(row, dict):
            continue
        slug = _slug(row.get("id") or row.get("label") or "")
        label = str(row.get("label") or row.get("id") or slug)
        as_of = _iso(row.get("date")) or report_date
        builder.add(f"market_performance.{slug}.last", row.get("level"), "index", as_of, f"Level {label}")
        builder.add(f"market_performance.{slug}.change_pct", row.get("change_pct"), UNIT_PERCENT,
                    as_of, f"Perubahan {label} (%)")

    for group, label in (("market_leaders", "penggerak positif"), ("market_laggards", "penggerak negatif")):
        for row in (snapshot.get(group) or [])[:5]:
            if not isinstance(row, dict):
                continue
            ticker = str(row.get("ticker") or "").upper()
            builder.add(f"movers.{_slug(group)}.{_slug(ticker)}.change_pct", row.get("change_pct"),
                        UNIT_PERCENT, report_date, f"Perubahan harga {ticker} (%)")
            builder.add(f"movers.{_slug(group)}.{_slug(ticker)}.contribution", row.get("contribution_points"),
                        "poin", report_date, f"Kontribusi {ticker} ke IHSG (poin, {label})")

    for row in (snapshot.get("sector_contributions") or [])[:6]:
        if not isinstance(row, dict):
            continue
        sector = str(row.get("sector") or "")
        builder.add(f"sectors.{_slug(sector)}.contribution", row.get("contribution_points"), "poin",
                    report_date, f"Kontribusi sektor {sector} (poin)")

    flow = snapshot.get("foreign_flow") or {}
    flow_date = _iso(flow.get("date")) or report_date
    builder.add_scaled("foreign_flow.net_usd_mn", flow.get("net_usd_mn"), "USD_mn", flow_date,
                       "Net foreign flow saham (USD juta)")
    builder.add_scaled("foreign_flow.net_idr", flow.get("net_idr"), "IDR", flow_date,
                       "Net foreign flow saham (IDR)")
    if flow.get("stale") and flow_date:
        builder.notes.append(f"Foreign flow berasal dari observasi {flow_date}, bukan sesi laporan.")

    for row in snapshot.get("foreign_flow_rows") or []:
        if not isinstance(row, dict) or not row.get("country"):
            continue
        country = _slug(row.get("country"))
        as_of = _iso(row.get("date")) or flow_date
        for period in ("daily", "mtd", "ytd", "12m"):
            value = row.get(period)
            if value is None:
                continue
            builder.add_scaled(f"flows.{country}.{period}", value, "USD_mn", as_of,
                               f"Arus ekuitas asing {row.get('country')} ({period}, USD juta)")

    coal = snapshot.get("coal") or {}
    coal_date = _iso(coal.get("date")) or report_date
    builder.add("coal.mtd_pct", coal.get("mtd_pct"), UNIT_PERCENT, coal_date, "Harga batubara (MTD %)")
    builder.add("coal.price", coal.get("price"), "USD/ton", coal_date, "Harga batubara Newcastle (USD/ton)")

    coverage = snapshot.get("coverage") or {}
    builder.add("coverage.valid_count", coverage.get("valid_count"), UNIT_COUNT, report_date,
                "Jumlah saham valid")
    builder.add("coverage.universe_count", coverage.get("universe_count"), UNIT_COUNT, report_date,
                "Jumlah saham di universe")
    ratio = coverage.get("ratio")
    builder.add("coverage.ratio_pct", None if ratio is None else ratio * 100, UNIT_PERCENT,
                report_date, "Kelengkapan data (%)")
    builder.add("coverage.residual_points", coverage.get("residual_points"), "poin", report_date,
                "Selisih estimasi kontribusi terhadap IHSG (poin)")

    sector_rows = [row for row in snapshot.get("market_performance") or []
                   if isinstance(row, dict) and str(row.get("id") or "").startswith("IDX")
                   and row.get("change_pct") is not None]
    if sector_rows:
        rising = sum(1 for row in sector_rows if row["change_pct"] > 0)
        falling = sum(1 for row in sector_rows if row["change_pct"] < 0)
        builder.add("breadth.rising_sectors", rising, UNIT_COUNT, report_date, "Jumlah indeks sektor menguat")
        builder.add("breadth.falling_sectors", falling, UNIT_COUNT, report_date, "Jumlah indeks sektor melemah")
        builder.add("breadth.total_sectors", len(sector_rows), UNIT_COUNT, report_date,
                    "Jumlah indeks sektor yang tersedia")


def build_equity_context(snapshot: dict, report: dict | None = None) -> NarrativeContext:
    """Konteks Equity Market Daily Snapshot: IHSG, sektor, movers, arus asing, batubara."""
    report = report or {}
    report_date = _iso(snapshot.get("report_date")) or _iso(report.get("report_date_iso"))
    builder = _Builder()
    _equity_rows(builder, snapshot, report_date)
    equity_notes = {
        "status": str(snapshot.get("status") or ""),
        "methodology": str(snapshot.get("methodology") or ""),
        "sector_methodology": str(snapshot.get("sector_methodology") or ""),
        "coverage_note": "Kontribusi poin adalah estimasi, bukan bobot resmi IHSG.",
    }
    seed = snapshot.get("narratives")
    if not seed:
        try:
            from market_report.domain.equity_snapshot import enrich_equity_indicators

            seed = enrich_equity_indicators(snapshot, report).get("narratives") or []
        except Exception:  # pragma: no cover - seed bersifat opsional
            seed = []
    seed_sections = [
        {"id": str(item.get("id") or f"section_{index}"), "title": str(item.get("title") or ""),
         "text": str(item.get("text") or "")}
        for index, item in enumerate(seed or []) if isinstance(item, dict)
    ]
    return builder.build(NarrativePage.EQUITY_SNAPSHOT, str(snapshot.get("report_id") or ""),
                         report_date, seed_sections=seed_sections, equity=equity_notes)

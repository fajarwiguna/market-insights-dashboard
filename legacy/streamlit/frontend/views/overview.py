"""Kartu angka utama dan patokan bunga."""

import streamlit as st

from domain.market_analysis import market_facts
from frontend.components import chips_html, kpi_card, section_head, tone_legend
from presentation.colors import COLOR_DOWN, COLOR_UP, COLOR_WARN
from presentation.formatting import (
    _delta_bp, _delta_label, fmt_bp, fmt_num, fmt_pct, spread_word, tone_of,
)
from presentation.sparklines import sparkline_values
from frontend.components import sparkline_svg


def _spark_for(report: dict, snapshot: dict, label: str, tone: str) -> str:
    """Mini-trend untuk kartu angka kunci; warna mengikuti nada (tone) kartunya."""
    warna = {"good": COLOR_UP, "bad": COLOR_DOWN, "warn": COLOR_WARN}.get(tone, "#94a3b8")
    return sparkline_svg(sparkline_values(report, snapshot, label), warna)


def _render_kpi_card(report: dict, snapshot: dict, kartu: tuple, big: bool = False) -> None:
    """Render satu kartu angka kunci + mini-trendnya."""
    label, value, delta, tone, note = tuple(kartu)[:5]
    st.markdown(
        kpi_card(label, value, delta, tone, note, _spark_for(report, snapshot, label, tone), big=big),
        unsafe_allow_html=True,
    )


def _render_patokan_bunga(f: dict) -> None:
    """Baris chip: patokan bunga & kurs referensi resmi (BI Rate, INDONIA, JISDOR)."""
    keping = []
    for label, nilai, tampil, ket in (
        ("BI Rate", f["bi_rate"], lambda v: f"{fmt_num(v, 2)}%",
         "Patokan bunga kredit, KPR, dan deposito"),
        ("INDONIA", f["indonia"], lambda v: f"{fmt_num(v, 2)}%",
         "Bunga pinjam-meminjam antar bank semalam"),
        ("JISDOR", f["jisdor"], lambda v: f"Rp{fmt_num(v, 0)}",
         "Kurs referensi dolar AS versi Bank Indonesia"),
    ):
        if nilai is not None:
            keping.append({"label": label, "value": tampil(nilai), "note": ket, "tone": "flat"})
    if keping:
        st.markdown(chips_html(keping), unsafe_allow_html=True)
        st.caption("Angka ini tidak berubah harian seperti kurs — biasanya diperbarui Bank Indonesia "
                   "pada rapat kebijakan suku bunga.")


def render_kpis(report: dict, snapshot: dict | None = None) -> None:
    """
    Empat angka utama dalam kartu besar, empat angka pendukung dalam kartu biasa.
    Versi lama menumpuk sembilan kartu penuh; kini cukup dua baris empat kolom
    supaya bagian ini tetap ringan dan tidak tenggelam.
    """
    section_head("Angka Kunci Hari Ini", "Indikator")
    f = market_facts(report)
    snap = snapshot or {}
    usd, dxy, ihsg = f["usd_idr"], f["dxy"], f["ihsg"]
    sbn10, ust10, gold, brent = f["sbn10"], f["ust10"], f["gold"], f["brent"]
    spread_kata, spread_tone = spread_word(f["spread"])

    utama = [
        ("USD/IDR", f"Rp{fmt_num(usd.get('today'), 0)}",
         _delta_label(usd.get("change_pct"), "Rupiah melemah", "Rupiah menguat"),
         tone_of(usd.get("change_pct"), higher_is_better=False, threshold=0.15),
         "Harga 1 dolar AS dalam Rupiah. Naik berarti Rupiah melemah."),
        ("IHSG (bursa RI)", fmt_num(ihsg.get("today"), 2),
         _delta_label(ihsg.get("change_pct"), "naik", "turun"),
         tone_of(ihsg.get("change_pct"), higher_is_better=True, threshold=0.05),
         "Rata-rata harga saham di Bursa Efek Indonesia."),
        ("Imbal hasil SBN 10 tahun", f"{fmt_num(sbn10.get('today'), 2)}%" if sbn10.get("today") is not None else "–",
         _delta_bp(sbn10.get("change_bp")),
         tone_of(sbn10.get("change_bp"), higher_is_better=False, threshold=0.5),
         "Bunga surat utang negara RI tenor 10 tahun. Turun berarti harga obligasi naik."),
        ("Selisih SBN–UST 10Y", f"{fmt_num(f['spread'], 0)} bp" if f["spread"] is not None else "–",
         spread_kata.split(" — ")[0], spread_tone,
         "Selisih imbal hasil obligasi RI dan AS. Makin sempit, Indonesia dinilai relatif lebih aman."),
    ]
    for col, kartu in zip(st.columns(4, gap="large"), utama):
        with col:
            _render_kpi_card(report, snap, kartu, big=True)

    st.write("")

    pendamping = [
        ("DXY (indeks dolar)", fmt_num(dxy.get("today"), 2),
         _delta_label(dxy.get("change_pct"), "Dolar AS menguat", "Dolar AS melemah"),
         tone_of(dxy.get("change_pct"), higher_is_better=False, threshold=0.15),
         "Kekuatan dolar AS terhadap mata uang utama dunia (bukan hanya Rupiah)."),
        ("Imbal hasil UST 10 tahun", f"{fmt_num(ust10.get('today'), 2)}%" if ust10.get("today") is not None else "–",
         _delta_bp(ust10.get("change_bp")), "flat",
         "Bunga surat utang AS 10 tahun — pembanding utama imbal hasil global."),
        ("Emas (USD/ons)", fmt_num(gold.get("today"), 2),
         _delta_label(gold.get("change_pct"), "naik", "turun"), "flat",
         "Harga emas dunia; naik biasanya karena investor mencari aset aman."),
        ("Brent (USD/barel)", fmt_num(brent.get("today"), 2),
         _delta_label(brent.get("change_pct"), "naik", "turun"), "warn",
         "Minyak mentah dunia; naik menaikkan biaya energi & transportasi."),
    ]
    for col, kartu in zip(st.columns(4, gap="large"), pendamping):
        with col:
            _render_kpi_card(report, snap, kartu)

    st.write("")
    _render_patokan_bunga(f)
    tone_legend()


# ── Render: tabel detail ─────────────────────────────────────

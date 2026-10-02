"""Ringkasan pasar dan dampak praktis untuk pembaca."""

import streamlit as st

from domain.market_analysis import build_impacts, build_insights, build_summary
from frontend.components import esc, section_head


IKON_SOROTAN = (
    ("rupiah", "💱"), ("kurs", "💱"), ("selisih", "📐"), ("spread", "📐"),
    ("suku bunga", "🏦"), ("bi rate", "🏦"), ("bursa", "📈"), ("saham", "📈"),
    ("obligasi", "🧾"), ("tabungan", "🧾"), ("barang sehari-hari", "🛒"), ("emas", "🥇"),
)


def _ikon(judul: str) -> str:
    """Ikon kecil pada kartu supaya halaman mudah dipindai mata."""
    j = str(judul).lower()
    for kata, ikon in IKON_SOROTAN:
        if kata in j:
            return ikon
    return "🔎"


def _kartu_sorotan(ins: dict, gaya: str = "") -> None:
    """Satu kartu sorotan: ikon + judul + angka + artinya untuk pembaca awam."""
    cls = "mt-sum " + ins.get("tone", "flat")
    st.markdown(
        f'<div class="{cls}"{gaya}><span class="ttl">{_ikon(ins["title"])} {esc(ins["title"])}</span>'
        f'{ins["text"]}<span class="dampak">Artinya: {esc(ins["dampak"])}</span></div>',
        unsafe_allow_html=True,
    )


def render_headline(report: dict) -> None:
    """
    Satu bagian pengganti "Ringkasan" + "Sorotan": paragraf pembuka lalu tiga kartu
    sorotan berjajar. Dua bagian terpisah dengan tumpukan kartu penuh membuat
    halaman terasa seperti laporan cetak.
    """
    section_head("Insight Hari Ini", "baca ini dulu")
    st.markdown(f'<div class="mt-note">{esc(build_summary(report))}</div>', unsafe_allow_html=True)
    st.write("")

    sorotan = build_insights(report)
    kolom = st.columns(max(min(len(sorotan), 3), 1), gap="large", vertical_alignment="top")
    for col, ins in zip(kolom, sorotan[:3]):
        with col:
            _kartu_sorotan(ins)

    sisa = sorotan[3:]
    if sisa:
        with st.expander(f"Sorotan lain hari ini ({len(sisa)})", expanded=False):
            for ins in sisa:
                _kartu_sorotan(ins, gaya=' style="margin-bottom:10px;height:auto"')


def render_impacts(report: dict) -> None:
    """Dampak praktis dalam kartu berjajar tiga — tanpa nomor bagian agar tidak kaku."""
    section_head("Apa Artinya untuk Anda", "dampak praktis")
    items = build_impacts(report)
    for i in range(0, len(items), 3):
        kolom = st.columns(3, gap="large", vertical_alignment="top")
        for col, item in zip(kolom, items[i:i + 3]):
            with col:
                st.markdown(
                    f'<div class="mt-card"><span class="ttl">{_ikon(item["title"])} {esc(item["title"])}</span>'
                    f'{esc(item["text"])}</div>',
                    unsafe_allow_html=True,
                )

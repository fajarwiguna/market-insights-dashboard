"""
Streamlit Dashboard — Daily Market Report

Tampilan bergaya "ruang baca": lapang, sedikit bagian, hierarki yang jelas, dan
grafik yang benar-benar bergerak. Angka tetap sama seperti laporan aslinya dan
bahasa tetap sederhana supaya pembaca tanpa latar belakang ekonomi bisa membaca.

Susunan halaman (tanpa nomor bagian — penandanya pil kecil + judul besar):
    1. Header berisi angka paling penting
    2. Insight Hari Ini   (paragraf ringkasan + 3 kartu sorotan)
    3. Apa Artinya untuk Anda (dampak praktis)
    4. Angka Kunci        (4 kartu besar + 4 kartu pendukung + patokan bunga)
    5. Grafik Bergerak Langsung (angka langsung, bisa disegarkan otomatis)
    6. Detail Pasar       (tab: kurs, saham, obligasi, komoditas)
    7. Glosarium & cara membaca, unduh PDF, dan (opsional) sumber data

Dua sumber angka sengaja dibedakan:
  - snapshot harian (data/report_data.json) → kartu, tabel, PDF: konsisten
  - harga terkini dari Yahoo Finance        → grafik: berubah saat disegarkan

Run:  streamlit run src/app.py
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from domain.market_analysis import (
    build_market_status, market_facts, market_sentiment,
)
from domain.market_data import find_key
from frontend.appearance import render_appearance_editor
from frontend.components import chips_html, esc
from frontend.footer import render_footer
from frontend.header import render_header
from frontend.sidebar import render_sidebar
from frontend.theme import load_css
from frontend.views.download import render_download as render_pdf_download
from frontend.views.glossary import render_glossary
from frontend.views.market_details import (
    render_market_details,
)
from frontend.views.market_monitor import INTERVAL_LANGSUNG, render_market_monitor
from frontend.views.overview import render_kpis
from frontend.views.sources import render_sources as render_data_sources
from frontend.views.summary import render_headline, render_impacts
from presentation.charts import (
    FX_QUOTE_NAMES, deret_harga, gabung_sumbu, make_fx_chart, make_rate_diff_chart,
)
from presentation.formatting import _waktu_lokal
from services import export_service, history_service, report_service
from services.live_service import LIVE_SPOT, fetch_live_prices, pasang_angka_langsung

DATA_DIR = ROOT.parent / "data"
CHART_DIR = ROOT.parent / "charts"
REPORT_DIR = ROOT.parent / "reports"
LIVE_TTL_DETIK = 45
HISTORI_SBN = DATA_DIR / "history_sbn.json"

st.set_page_config(
    page_title="Market Today | Daily Report",
    page_icon="src/image.png",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ═══════════════════════════════════════════════════════════
st.markdown(load_css(), unsafe_allow_html=True)


def load_report() -> dict | None:
    return report_service.load_report()


def load_snapshot() -> dict:
    return report_service.load_snapshot()


@st.cache_data(ttl=LIVE_TTL_DETIK, show_spinner=False)
def angka_langsung(nonce: int = 0) -> dict:
    """Ambil harga intraday; nonce menjadi kunci untuk melewati cache saat diminta."""
    return fetch_live_prices()


def riwayat_sbn() -> list[dict]:
    """Riwayat imbal hasil SBN 10 tahun yang dikumpulkan aplikasi sendiri."""
    return history_service.load_sbn_history(HISTORI_SBN)


def kumpulkan_riwayat_sbn(report: dict) -> list[dict]:
    """
    PHEI hanya menampilkan angka terakhir, jadi garis SBN pada grafik akan selamanya
    datar kalau aplikasinya tidak menyimpan sendiri angka harian itu. Fungsi ini
    menambahkan/memperbarui satu titik per tanggal setiap kali data dimuat, sehingga
    dalam beberapa hari grafik punya kurva SBN yang sebenarnya.
    """
    if report.get("is_demo"):
        return history_service.load_sbn_history(HISTORI_SBN)
    sbn = market_facts(report)["sbn10"]
    nilai = sbn.get("today")
    tanggal = sbn.get("date")
    return history_service.record_sbn_history(nilai, tanggal, HISTORI_SBN)


def render_charts(report: dict, sbn_hist: list[dict]) -> None:
    """Hubungkan monitor grafik dengan layanan data dan status halaman."""
    render_market_monitor(
        report, sbn_hist,
        get_live=angka_langsung,
        apply_live_data=pasang_angka_langsung,
        build_status=build_market_status,
        render_chips=chips_html,
        format_time=_waktu_lokal,
        escape=esc,
        live_ttl=LIVE_TTL_DETIK,
    )


@st.cache_data(ttl=900, show_spinner=False)
def pdf_bytes(report_json: str, sbn_json: str) -> tuple[bytes, str]:
    """
    Susun PDF dari angka yang SEDANG TAMPIL, lengkap dengan grafik yang sama
    dengan layar (make_rate_diff_chart). Hasil dikembalikan sebagai byte sehingga
    halaman bisa menawarkannya lewat st.download_button tanpa menulis file.

    Cache memakai isi data sebagai kunci: PDF hanya disusun ulang bila angkanya
    benar-benar berubah, bukan setiap kali ada interaksi.
    """
    return export_service.build_report_pdf(report_json, sbn_json)


def render_download(report: dict, sbn_hist: list[dict]) -> None:
    render_pdf_download(
        report, sbn_hist, pdf_builder=pdf_bytes, refresh_data=run_live_pipeline,
        report_dir=REPORT_DIR, escape=esc,
    )


def render_sources(report: dict) -> None:
    render_data_sources(report)


def run_live_pipeline():
    return report_service.run_live_pipeline()


auto_fetch, show_technical = render_sidebar(run_live_pipeline, load_report, esc)


# ── Load data: pakai snapshot terakhir; ambil otomatis hanya bila belum ada
report = load_report()
if report is None:
    if auto_fetch:
        with st.spinner("Belum ada snapshot data — mengambil data terbaru …"):
            try:
                report = run_live_pipeline()
            except Exception as e:
                st.error(f"Gagal mengambil data terbaru: {e}")
                st.stop()
    else:
        st.warning("Belum ada data. Klik **🔄 Perbarui data dari sumber (live)** di sidebar.")
        st.stop()

is_live = not report.get("is_demo", False)
if not is_live:
    st.info(
        "Mode **DEMO**: angka pada halaman ini hanya contoh. Klik "
        "**🔄 Perbarui data dari sumber (live)** di sidebar untuk memakai data pasar sebenarnya."
    )

# ═══════════════════════════════════════════════════════════
# RENDER HALAMAN
# Urutan mengikuti cara orang membaca: inti → artinya → angka kunci → grafik
# bergerak → detail per instrumen (bertab) → lampiran. Tanpa garis pemisah
# dan nomor bagian: ruang putih menggantikan penanda laporan.
# ═══════════════════════════════════════════════════════════
snapshot = load_snapshot()                 # riwayat harian untuk mini-trend di kartu angka
sbn_hist = kumpulkan_riwayat_sbn(report)   # riwayat SBN 10Y dikumpulkan per hari

status_pasar = build_market_status(report)
sentimen = market_sentiment(status_pasar)[0] if status_pasar else "belum dapat disimpulkan"
render_header(
    report.get("report_date", "—"),
    _waktu_lokal(report.get("source_snapshot"), "%d %b %Y · %H:%M WIB"),
    sentimen,
    demo=not is_live,
)
render_headline(report)
render_impacts(report)
render_kpis(report, snapshot)
render_charts(report, sbn_hist)
render_market_details(report)
render_glossary()
render_download(report, sbn_hist)

if show_technical:
    render_sources(report)

render_footer()

# Panel kustomisasi tampilan (client-side, tidak mengubah file sumber)
render_appearance_editor()

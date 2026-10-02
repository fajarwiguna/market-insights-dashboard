"""Tabel detail kurs, indeks, obligasi, dan komoditas."""

import pandas as pd
import streamlit as st

from frontend.components import section_head
from market_report.presentation.formatting import _delta_bp, arrow, fmt_num, fmt_pct
from market_report.presentation.market_metadata import COMMODITY_NOTES, YIELD_NOTES


def _fx_decimals(rate) -> int:
    """Jumlah desimal yang wajar agar angka kurs tetap mudah dibaca."""
    if rate is None:
        return 2
    n = abs(float(rate))
    return 0 if n >= 10_000 else (1 if n >= 1_000 else 2)


def _pct_arrow(chg) -> str:
    return f"{arrow(chg)} {fmt_pct(chg)}" if chg is not None else "–"


def render_fx_table(report: dict) -> None:
    """
    Tabel kurs. Kolom dirampingkan: kolom 'Sebelumnya' (untuk verifikasi) dipindah
    ke unduhan PDF, dan kolom keterangan digabung ke kolom 'Artinya'.
    """
    fx = report.get("fx") or {}
    rows = []
    for name, v in fx.items():
        if not isinstance(v, dict):
            continue
        rate, chg = v.get("today"), v.get("change_pct")
        is_dxy = name.upper().startswith("DXY")
        if chg is None:
            arah = "– belum ada data pembanding"
        elif abs(chg) <= 0.005:
            arah = "▬ relatif stabil"
        elif is_dxy:
            arah = f"{arrow(chg)} indeks dolar {'menguat' if chg > 0 else 'melemah'}"
        else:
            arah = f"{arrow(chg)} Rupiah {'melemah' if chg > 0 else 'menguat'}"
        rows.append({
            "Kurs": name,
            "Hari ini": fmt_num(rate, _fx_decimals(rate)),
            "Perubahan": _pct_arrow(chg),
            "Artinya": arah,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("Angka menunjukkan berapa Rupiah untuk 1 unit mata uang asing; naik berarti Rupiah "
                   "melemah. Sumber: Yahoo Finance Chart API. Penutupan hari sebelumnya tersedia di PDF.")
    else:
        st.info("Data kurs belum tersedia pada snapshot ini.")


def render_indices_table(report: dict) -> None:
    """Tabel indeks pasar saham — kolom minimal: level, perubahan, artinya."""
    idx = report.get("indices") or {}
    rows = []
    for name, v in idx.items():
        if not isinstance(v, dict):
            continue
        chg = v.get("change_pct")
        if chg is None:
            arah = "– belum ada data pembanding"
        elif abs(chg) <= 0.005:
            arah = "▬ relatif stabil"
        else:
            arah = f"{arrow(chg)} {'naik' if chg > 0 else 'turun'}"
        rows.append({
            "Indeks": name,
            "Level": fmt_num(v.get("today"), 2),
            "Perubahan": _pct_arrow(chg),
            "Artinya": arah,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("Level indeks = rata-rata harga saham di bursa tersebut. Naik = pasar menguat, "
                   "turun = pasar melemah secara umum.")
    else:
        st.info("Data indeks belum tersedia pada snapshot ini.")


def render_yields_table(report: dict) -> None:
    """Tabel imbal hasil obligasi — jenis instrumen disatukan agar tidak jadi kolom terpisah."""
    yld = report.get("yields") or {}
    rows = []
    for name, v in yld.items():
        if not isinstance(v, dict):
            continue
        low = name.lower()
        if "sbsn" in low or "pbs" in low:
            jenis = YIELD_NOTES["sbsn"]
        elif "treasury" in low or "ust" in low:
            jenis = YIELD_NOTES["treasury"]
        elif "sbn" in low or "fr0" in low:
            jenis = YIELD_NOTES["sbn"]
        else:
            jenis = "Instrumen pasar uang / obligasi"
        if v.get("series"):
            jenis += f" · seri {v['series']}"
        rows.append({
            "Instrumen": name,
            "Jenis": jenis,
            "Hari ini": f"{fmt_num(v.get('today'), 2)}%",
            "Perubahan": _delta_bp(v.get("change_bp")) or "–",
            "Per tanggal": v.get("as_of_label") or v.get("date") or "–",
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("Imbal hasil = bunga tahunan bila obligasi dipegang sampai jatuh tempo; 1 bp = 0,01%. "
                   "Yield naik biasanya berarti harga obligasi turun. Data PHEI bisa tertanggal satu hari "
                   "dari data kurs/saham karena perbedaan waktu publikasi.")
    else:
        st.info("Data imbal hasil belum tersedia pada snapshot ini.")


def render_commodities_table(report: dict) -> None:
    """Tabel harga komoditas dunia."""
    comm = report.get("commodities") or {}
    rows = []
    for name, v in comm.items():
        if not isinstance(v, dict):
            continue
        low = name.lower()
        if "gold" in low:
            keterangan = COMMODITY_NOTES["Gold"]
        elif "brent" in low:
            keterangan = COMMODITY_NOTES["Brent"]
        elif "wti" in low:
            keterangan = COMMODITY_NOTES["WTI"]
        else:
            keterangan = "Harga komoditas dunia"
        rows.append({
            "Komoditas": name,
            "Hari ini": fmt_num(v.get("today"), 2),
            "Perubahan": _pct_arrow(v.get("change_pct")),
            "Catatan": keterangan,
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption("Satuan mengikuti sumber data: emas dalam USD/ons, minyak dalam USD/barel. Naik biasanya "
                   "menekan biaya energi, transportasi, dan harga barang sehari-hari.")
    else:
        st.info("Data komoditas belum tersedia pada snapshot ini.")


def render_market_details(report: dict) -> None:
    """
    Empat tabel detail dijadikan satu bagian bertab. Sebagai bagian terpisah,
    keempat tabel membuat halaman panjang dan penuh — persis kesan "laporan".
    """
    section_head("Detail Pasar", "angka lengkap per instrumen",
                 hint="Pilih tab sesuai instrumen yang Anda cari.")
    tab_fx, tab_idx, tab_yld, tab_komoditas = st.tabs(
        ["💱 Nilai Tukar", "📈 Pasar Saham", "🏛️ Imbal Hasil Obligasi", "🛢️ Komoditas"])
    with tab_fx:
        render_fx_table(report)
    with tab_idx:
        render_indices_table(report)
    with tab_yld:
        render_yields_table(report)
    with tab_komoditas:
        render_commodities_table(report)

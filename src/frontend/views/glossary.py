"""Glosarium dan panduan membaca laporan pasar."""

import pandas as pd
import streamlit as st

from frontend.components import section_head


GLOSSARY = {
    "USD/IDR": "Berapa Rupiah yang dibutuhkan untuk menukar 1 Dolar AS. Angka naik = Rupiah melemah (barang impor jadi lebih mahal). Angka turun = Rupiah menguat.",
    "DXY": "Indeks kekuatan Dolar AS terhadap sekumpulan mata uang utama dunia (bukan hanya Rupiah). Naik = dolar menguat, biasanya menekan mata uang negara berkembang.",
    "Yield": "Imbal hasil — perkiraan keuntungan tahunan (dalam %) bila obligasi dipegang sampai jatuh tempo. Yield naik biasanya berarti harga obligasi turun.",
    "Spread": "Selisih imbal hasil obligasi Indonesia (SBN) dan Amerika Serikat (UST) pada tenor yang sama. Makin lebar, makin besar 'kompensasi risiko' yang diminta investor untuk memegang surat utang Indonesia.",
    "BI Rate": "Suku bunga acuan Bank Indonesia. Menjadi patokan bunga KPR, kredit, dan deposito di bank-bank Indonesia.",
    "INDONIA": "Bunga pinjam-meminjam antar bank (semalam) di Indonesia — cermin likuiditas harian perbankan.",
    "IHSG": "Indeks Harga Saham Gabungan — cerminan pergerakan rata-rata harga saham di Bursa Efek Indonesia.",
    "Poin basis (bp)": "Satuan kecil untuk perubahan suku bunga. 1 bp = 0,01%. Jadi 25 bp sama dengan 0,25%.",
    "SBN": "Surat Berharga Negara — surat utang yang diterbitkan pemerintah Indonesia (contoh seri FR).",
    "SBSN (sukuk negara)": "Surat utang negara berbasis syariah (contoh seri PBS).",
    "UST": "US Treasury — surat utang pemerintah Amerika Serikat. Dipakai sebagai patokan bunga global dan aset 'aman'.",
    "JISDOR": "Kurs referensi Dolar AS terhadap Rupiah yang diterbitkan Bank Indonesia tiap hari kerja.",
    "Dow Jones (DJI)": "Indeks 30 perusahaan besar Amerika Serikat; sering dipakai sebagai penanda arah pasar global.",
}

# Nama panjang instrument (dipakai di tabel agar tidak hanya berupa kode)


def glossary_markdown() -> None:
    """Glosarium dalam bentuk tabel dua kolom yang mudah dibaca."""
    rows = pd.DataFrame(
        [{"Istilah": term, "Arti sederhana": desc} for term, desc in GLOSSARY.items()]
    )
    st.dataframe(rows, width="stretch", hide_index=True, height=430)
    st.caption("Contoh: jika menulis 25 bp, artinya 25 × 0,01% = 0,25%.")


def render_glossary() -> None:
    """Kamus istilah dan cara membaca — dua hal yang biasanya dicari pembaca baru."""
    section_head("Glossarium Istilah & Cara Membaca", "kamus singkat",
                 hint="Bagian penutup yang paling sering dibutuhkan pembaca baru. Bisa dicari (Ctrl+F) "
                      "atau diurutkan dengan klik judul kolom.")
    tab_kamus, tab_cara = st.tabs(["📖 Glosarium istilah", "ℹ️ Cara membaca laporan (30 detik)"])
    with tab_kamus:
        glossary_markdown()
    with tab_cara:
        st.markdown(
            "- **Urutan baca yang disarankan:** *Intinya Hari Ini* → *Apa Artinya untuk Anda* → "
            "*Angka Kunci* → *Grafik Bergerak Langsung* → *Detail Pasar*.\n"
            "- **\"Naik\" belum tentu buruk.** Pada kurs, naik berarti Rupiah melemah. Pada saham, "
            "naik berarti harga saham menguat.\n"
            "- **Arti warna:** hijau = cenderung menguntungkan, merah = cenderung memberatkan, "
            "abu-abu = relatif stabil.\n"
            "- **bp (poin basis):** satuan kecil untuk bunga; 1 bp = 0,01%. Jadi 25 bp = 0,25%.\n"
            "- **Perubahan harian** dihitung terhadap penutupan hari perdagangan sebelumnya, "
            "bukan terhadap awal tahun.\n"
            "- **Angka langsung vs snapshot:** bagian *Grafik Bergerak Langsung* mengambil harga "
            "terkini dari sumber, sedangkan kartu, tabel, dan PDF memakai snapshot laporan agar "
            "tetap konsisten satu hari penuh.\n"
            "- **Tanggal data bisa berbeda:** data PHEI (obligasi) dan Bank Indonesia kadang satu hari "
            "lebih lama daripada kurs/saham. Kolom \"per tanggal\" menunjukkan tanggal datanya."
        )

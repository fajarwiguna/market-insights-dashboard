"""Catatan sumber dan penggunaan dashboard."""

import streamlit as st


def render_footer() -> None:
    st.markdown("---")
    st.markdown(
        '<div class="mt-foot">Semua angka diambil otomatis dari data publik: Yahoo Finance Chart API '
        '(kurs, indeks, surat utang AS, komoditas) = end-of-day/last trade, PHEI (imbal hasil SBN & SBSN) '
        '= Harga Pasar Wajar harian, Bank Indonesia (BI Rate, INDONIA, JISDOR), dan open.er-api.com '
        '(kurs cadangan). Angka dapat berubah setelah sumber resmi memperbarui data. '
        'Materi ini bersifat informatif, bukan saran investasi.</div>',
        unsafe_allow_html=True,
    )

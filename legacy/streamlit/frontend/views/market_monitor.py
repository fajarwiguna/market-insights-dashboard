"""Monitor grafik live pada dashboard."""

import matplotlib.pyplot as plt
import streamlit as st

from frontend.components import section_head
from presentation.charts import deret_harga, make_fx_chart, make_rate_diff_chart


INTERVAL_LANGSUNG = {
    "Manual (hanya saat tombol ditekan)": 0,
    "Setiap 30 detik": 30,
    "Setiap 1 menit": 60,
    "Setiap 5 menit": 300,
}


def render_market_monitor(
    report: dict,
    sbn_hist: list[dict],
    *,
    get_live,
    apply_live_data,
    build_status,
    render_chips,
    format_time,
    escape,
    live_ttl: int = 45,
) -> None:
    """
    Papan grafik "langsung".

    Berbeda dengan bagian lain, angka di sini diambil ulang dari sumber (bukan
    dari snapshot harian), sehingga grafiknya benar-benar bergerak setiap kali
    disegarkan. Bungkusannya memakai st.fragment agar penyegaran cukup menjalankan
    ulang bagian grafik saja, bukan seluruh halaman.
    """
    section_head("Live Market Monitor", "angka diperbarui otomatis")

    st.session_state.setdefault("nonce_langsung", 0)

    @st.fragment(run_every=60 or None)
    def papan_live():
        # Pada mode DEMO angka laporan hanya contoh — jangan ditimpa harga nyata.
        langsung = ({"_error": "mode demo"} if report.get("is_demo")
                    else get_live(st.session_state.nonce_langsung))
        view, diperbarui = apply_live_data(report, langsung)
        deret_ust = deret_harga(langsung.get("yields|US Treasury 10 Tahun") or {})
        if deret_ust:
            view["history_ust10"] = deret_ust
        stempel = format_time(view.get("live_at"), "%H:%M:%S")

        baris, tombol = st.columns([4.2, 1], gap="small", vertical_alignment="center")
        with baris:
            if diperbarui:
                lencana = ('<span class="mt-live-badge"><span class="mt-live-dot"></span>DATA LANGSUNG</span>'
                           f'<span class="lbl">{len(diperbarui)} instrumen</span>'
                           f'<span class="nilai">diperbarui pukul {stempel}</span>')
            else:
                lencana = ('<span class="mt-live-badge idle"><span class="mt-live-dot"></span>'
                           'SNAPSHOT LAPORAN</span>'
                           f'<span class="lbl">{escape(format_time(view.get("source_snapshot"), "%H:%M:%S"))}</span>'
                           '<span class="nilai">Sumber langsung tidak terjangkau — memakai angka laporan</span>')
            st.markdown(f'<div class="mt-live-bar">{lencana}</div>', unsafe_allow_html=True)
        with tombol:
            if st.button("🔄 Perbarui sekarang", width="stretch",
                         help="Ambil ulang angka dari sumber (tidak perlu me-refresh halaman)."):
                st.session_state.nonce_langsung += 1
                st.rerun()

        st.markdown(render_chips(build_status(view), segar=bool(diperbarui)),
                    unsafe_allow_html=True)

        tab_spread, tab_kurs = st.tabs(["📊 Selisih imbal hasil RI–AS", "💱 Pergerakan kurs"])
        with tab_spread:
            fig = make_rate_diff_chart(view, sbn_hist=sbn_hist, live_at=stempel)
            st.pyplot(fig, width="stretch")
            plt.close(fig)
            st.caption("Batang hijau = selisih (spread) imbal hasil RI–AS dalam poin basis. Makin lebar, makin "
                       "besar imbal hasil tambahan yang diminta investor untuk memegang surat utang Indonesia.")
        with tab_kurs:
            fig = make_fx_chart(view.get("fx") or {}, live_at=stempel)
            st.pyplot(fig, width="stretch")
            plt.close(fig)
            st.caption("Angka positif (merah) = Rupiah melemah terhadap mata uang tersebut; "
                       "angka negatif (hijau) = Rupiah menguat.")

        st.caption("Sumber angka langsung: Yahoo Finance Chart API (harga terakhir yang tersedia). "
                   "Imbal hasil SBN tetap dari PHEI dan hanya terbit sekali per hari.")

    papan_live()

"""Sidebar dashboard: status snapshot, pembaruan, dan sumber."""

from datetime import datetime

import streamlit as st


def render_sidebar(run_live_pipeline, load_report, esc):
    with st.sidebar:
        st.markdown("### 📈 Market Today")
        st.caption("Daily Market Report — angka pasar dengan penjelasan bahasa sederhana.")

        status = load_report() or {}
        if status.get("is_demo"):
            mode, warna = "DEMO (angka contoh)", "#b45309"
        elif status:
            mode, warna = "SNAPSHOT (data nyata)", "#0f766e"
        else:
            mode, warna = "belum ada data", "#b91c1c"
        st.markdown(
            '<div class="mt-src" style="font-size:.8rem;border-left-color:' + warna + '">'
            f'<b>Mode data:</b> {esc(mode)}<br>'
            f'<b>Tanggal laporan:</b> {esc(status.get("report_date", "–"))}<br>'
            f'<b>Snapshot:</b> {esc(status.get("source_snapshot", "–"))}'
            "</div>",
            unsafe_allow_html=True,
        )

        st.divider()
        auto_fetch = st.checkbox("Ambil data otomatis bila snapshot belum ada", value=True)
        if st.button("🔄 Perbarui data dari sumber (live)", type="primary", width="stretch"):
            with st.spinner("Mengambil data Yahoo + PHEI + Bank Indonesia …"):
                try:
                    run_live_pipeline()
                    st.success("Data berhasil diperbarui.")
                except Exception as e:
                    st.error(f"Gagal memperbarui data: {e}")
            st.rerun()

        st.divider()
        show_technical = st.toggle("Tampilkan bagian teknis (sumber data)", value=True,
                                   help="Matikan bila halaman hanya ditujukan untuk pembaca non-teknis.")
        st.caption("Bagian teknis = rincian sumber, kode instrument, dan waktu pengambilan data.")

        st.divider()
        st.markdown("**Sumber utama**")
        st.caption(
            "• Yahoo Finance Chart API (kurs, indeks, surat utang AS, komoditas)\n"
            "\n• PHEI — Harga Pasar Wajar & Imbal Hasil (SBN, SBSN)\n"
            "\n• Bank Indonesia — Indikator (BI Rate, INDONIA, JISDOR)\n"
            "\n• open.er-api.com (cadangan kurs)"
        )
        st.caption("💡 Grafik di bagian **Grafik Bergerak Langsung** mengambil harga terkini dari Yahoo Finance; "
                   "kartu, tabel, dan PDF memakai snapshot di atas.")
        st.caption(f"Jam halaman: {datetime.now().strftime('%d %b %Y %H:%M')} WIB")
        st.divider()
        st.caption("🎨 Pengaturan tampilan (ukuran teks, warna aksen, mode gelap) ada di tombol "
                   "pojok kanan bawah halaman.")
    return auto_fetch, show_technical

"""Kontrol unduh PDF dan arsip laporan."""

import json

import streamlit as st

from frontend.components import section_head


def render_download(report: dict, sbn_hist: list[dict], *, pdf_builder, refresh_data, report_dir, escape) -> None:
    """
    Unduhan PDF.

    Versi lama hanya menawarkan file lama yang tersimpan di runtime/reports/ — bisa
    jadi bertanggal jauh lebih lama daripada angka di layar. Sekarang PDF selalu
    disusun dari objek `report` yang sedang dirender di halaman ini.
    """
    section_head("Unduh Laporan (PDF)", "versi cetak",
                 hint="PDF disusun dari angka yang sedang tampil di halaman ini (termasuk grafik yang sama), "
                      "sehingga isinya selalu sama dengan yang Anda lihat di layar.")
    stempel = str(report.get("source_snapshot") or report.get("generated_at") or "")[:16].replace("T", " ")

    with st.spinner("Menyiapkan PDF dari angka yang tampil …"):
        try:
            isi, nama = pdf_builder(json.dumps(report, default=str), json.dumps(sbn_hist))
        except Exception as e:
            st.error(f"Gagal menyiapkan PDF: {e}")
            return

    col_dl, col_info = st.columns([1, 2.1], gap="large", vertical_alignment="center")
    with col_dl:
        st.download_button("📄 Unduh PDF", isi, file_name=nama, mime="application/pdf",
                           width="stretch", type="primary")
        st.caption(f"{nama} · snapshot {stempel}")
    with col_info:
        st.markdown(
            f'<div class="mt-src">PDF memuat angka snapshot yang sama dengan bagian atas halaman: kurs, '
            f'indeks saham, imbal hasil obligasi, BI Rate, dan grafik selisih imbal hasil '
            f'(per <b>{escape(stempel)}</b>). Angka yang bergerak di bagian <b>Grafik Bergerak Langsung</b> '
            'tidak ikut disertakan — silakan screenshot bagian itu bila perlu angka terkini.</div>',
            unsafe_allow_html=True,
        )

    aksi = st.columns([1, 1], gap="large")
    with aksi[0]:
        if st.button("🔄 Ambil data terbaru, lalu perbarui PDF", width="stretch",
                     help="Antrekan pipeline live; seluruh halaman diperbarui setelah worker selesai."):
            with st.spinner("Mengambil data terbaru dari sumber …"):
                try:
                    result = refresh_data()
                    if result.get("mode") == "queued":
                        st.session_state["market_refresh_job_id"] = result["job"]["job_id"]
                        st.info("Pembaruan dimasukkan ke antrean worker. PDF dapat disusun ulang setelah laporan selesai.")
                        return
                    st.rerun()
                except Exception as e:
                    st.error(f"Gagal mengambil data terbaru: {e}")
    with aksi[1]:
        if st.button("💾 Simpan salinan ke runtime/reports/", width="stretch",
                     help="Simpan PDF yang sama ke runtime/reports/ sebagai arsip."):
            path = report_dir / nama
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(isi)
                st.success(f"Tersimpan: {path.name}")
            except Exception as e:
                st.error(f"Gagal menyimpan: {e}")

    lama = sorted((p for p in report_dir.glob("Daily_Market_Update_*.pdf") if p.name != nama),
                  reverse=True) if report_dir.exists() else []
    if lama:
        st.caption(f"Arsip PDF lain di runtime/reports/: {', '.join(p.name for p in lama[:3])}"
                   f"{' …' if len(lama) > 3 else ''} — bukan yang diunduh lewat tombol di atas.")

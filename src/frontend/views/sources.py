"""Panel verifikasi sumber dan tanggal data."""

import streamlit as st

from frontend.components import section_head


def render_sources(report: dict) -> None:
    """Bagian teknis: sumber per instrumen, tanggal data, dan catatan verifikasi."""
    section_head("Sumber Data & Metode", "bagian teknis",
                 hint="Rincian asal setiap angka. Bagian ini opsional dibaca — disiapkan untuk "
                      "keperluan verifikasi.")
    for src in (report.get("sources") or []):
        section = src.get("section", "Sumber")
        jumlah = len(src.get("items") or [])
        label = f"{section}" + (f" — {jumlah} instrumen" if jumlah else "")
        with st.expander(label, icon="🔎"):
            with st.container(border=True):
                if src.get("primary"):
                    st.markdown(f"**Sumber utama:** {src['primary']}")
                if src.get("url"):
                    st.markdown(f"**Tautan:** [{src['url']}]({src['url']})")
                if src.get("as_of_label"):
                    st.markdown(f"**Per tanggal:** {src['as_of_label']}")
                if src.get("page_title"):
                    st.markdown(f"**Judul halaman:** {src['page_title']}")
                if src.get("fetched_at"):
                    st.markdown(f"**Diambil pada:** {src['fetched_at']}")
                if src.get("backup"):
                    st.markdown(f"**Cadangan / pembanding:** {src['backup']} "
                                f"(per {src.get('backup_as_of', '–')})")
                if src.get("note"):
                    st.markdown(f"**Catatan:** {src['note']}")
                if "BI Rate" in section:
                    st.markdown(
                        f"- BI Rate: **{src.get('bi_rate')}%** (tanggal: {src.get('bi_rate_date') or '–'})\n"
                        f"- INDONIA: **{src.get('indonia')}** (tanggal: {src.get('indonia_date') or '–'})\n"
                        f"- JISDOR: **{src.get('jisdor')}** (tanggal: {src.get('jisdor_date') or '–'})"
                    )
                items = src.get("items") or []
                if items:
                    baris = ["**Rincian per instrumen:**"]
                    for it in items:
                        teks = f"- `{it.get('field')}` ← {it.get('source') or src.get('primary')}"
                        if it.get("as_of"):
                            teks += f" | per **{it['as_of']}**"
                        if it.get("series"):
                            teks += f" | seri `{it['series']}`"
                        if it.get("ttm"):
                            teks += f" | tenor {it['ttm']} tahun"
                        baris.append(teks)
                    st.markdown("\n".join(baris))
                if not any((src.get("primary"), src.get("url"), items)):
                    st.markdown("Tidak ada metadata tambahan untuk bagian ini.")

    phei_meta = report.get("phei_meta") or {}
    if phei_meta.get("as_of_label"):
        st.info(
            f"**Kurva imbal hasil PHEI** yang dipakai pada laporan ini adalah "
            f"**{phei_meta['as_of_label']}** — sumber: {phei_meta.get('source_name')} "
            f"({phei_meta.get('url')})."
        )

"""Header laporan pada bagian atas dashboard."""

import html

import streamlit as st


def render_header(report_date: str, snapshot_time: str, sentiment: str, *, demo: bool = False) -> None:
    """Tampilkan identitas laporan dan status snapshot tanpa mengulang KPI."""
    mode = "DEMO" if demo else "SNAPSHOT"
    badge_class = "demo" if demo else "live"
    badge = f'<span class="mt-badge {badge_class}">{mode}</span>'
    st.markdown(
        '<div class="mt-hero">'
        '<div class="mt-eyebrow">DAILY MARKET REPORT</div>'
        f'<div class="mt-title">Market Today {badge}</div>'
        '<div class="mt-hero-sub">Kondisi pasar keuangan per '
        f'<b>{html.escape(str(report_date))}</b> · snapshot {html.escape(str(snapshot_time))}'
        '<div style="margin-top:10px;font-size:.84rem;color:#d6efec">'
        f'Sentimen pasar: <b style="color:#fff">{html.escape(str(sentiment))}</b></div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

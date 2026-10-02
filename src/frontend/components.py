"""Komponen tampilan kecil yang digunakan oleh beberapa bagian halaman."""

import html

import streamlit as st


def esc(value) -> str:
    """Escape nilai sebelum disisipkan ke HTML."""
    return html.escape(str(value))


def section_head(title: str, tag: str = "", hint: str = "") -> None:
    """
    Judul bagian tanpa nomor (kesan laporan berkurang): pil label kecil,
    judul besar, lalu satu baris petunjuk cara membacanya.
    """
    tag_html = f'<span class="mt-tag">{esc(tag)}</span>' if tag else ""
    st.markdown(
        f'<div class="mt-sec"><div class="mt-sec-top">'
        f'<h3>{esc(title)}</h3>{tag_html}'
        f"</div></div>",
        unsafe_allow_html=True,
    )
    if hint:
        st.markdown(f'<div class="mt-hint">{hint}</div>', unsafe_allow_html=True)


def chips_html(items: list[dict], segar: bool = False) -> str:
    """Baris chip angka — dipakai papan status, papan angka langsung, dan patokan bunga."""
    kelas = "mt-chip segar" if segar else "mt-chip"
    kotak = "".join(
        f'<div class="{kelas} {esc(it.get("tone", "flat"))}">'
        f'<div class="c-lbl"><span class="mt-dot-s"></span>{esc(it["label"])}</div>'
        f'<div class="c-val">{esc(it["value"])}</div>'
        f'<div class="c-note">{esc(it.get("note", ""))}</div><div class="c-bar"></div></div>'
        for it in items
    )
    return f'<div class="mt-strip">{kotak}</div>'


def sparkline_svg(values, color: str = "#0f766e", width: int = 118, height: int = 30) -> str:
    """
    Mini-trend SVG (bagian dari kartu), tanpa file gambar — jadi tetap tajam
    dan ringan. Dihilangkan otomatis bila datanya kurang dari 2 titik.
    """
    vals = [float(v) for v in (values or []) if v is not None]
    if len(vals) < 2:
        return ""
    lo, hi = min(vals), max(vals)
    span = (hi - lo) or 1.0
    pad = 3.0
    n = len(vals)
    titik = []
    for i, v in enumerate(vals):
        x = pad + i * (width - 2 * pad) / (n - 1)
        y = (height - pad) - (v - lo) / span * (height - 2 * pad)
        titik.append((x, y))
    garis = " ".join(f"{x:.1f},{y:.1f}" for x, y in titik)
    area = f"{titik[0][0]:.1f},{height - pad:.1f} {garis} {titik[-1][0]:.1f},{height - pad:.1f}"
    return (
        f'<div class="mt-spark"><svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
        f'preserveAspectRatio="none" role="img" aria-label="mini trend">'
        f'<polygon points="{area}" fill="{color}" opacity="0.12"/>'
        f'<polyline points="{garis}" fill="none" stroke="{color}" stroke-width="1.8" '
        f'stroke-linejoin="round" stroke-linecap="round"/></svg></div>'
    )


# ═══════════════════════════════════════════════════════════
# ANGKA LANGSUNG (intraday) — agar grafik ikut berubah saat disegarkan
# Tabel & PDF tetap memakai snapshot laporan; hanya modul grafik yang memakai
# angka "detik ini" sehingga angkanya benar-benar bergerak ketika disegarkan.
# ═══════════════════════════════════════════════════════════


def kpi_card(label: str, value: str, delta: str = "", tone: str = "flat",
             note: str = "", spark: str = "", big: bool = False) -> str:
    """Kartu angka kunci: label kecil, angka besar, pil perubahan, catatan arti, mini-trend."""
    delta_html = f'<div class="dlt {tone}">{esc(delta)}</div>' if delta else ""
    note_html = f'<div class="note">{note}</div>' if note else ""
    return (
        f'<div class="mt-kpi {esc(tone)}{" big" if big else ""}"><div class="lbl">{esc(label)}</div>'
        f'<div class="val">{esc(value)}</div>{delta_html}{note_html}{spark or ""}</div>'
    )


def tone_legend() -> None:
    """Keterangan arti warna — penting agar pembaca awam tidak menebak."""
    st.markdown(
        '<div class="mt-legend">'
        '<i><span class="mt-dot good"></span>Hijau = cenderung menguntungkan / membaik</i>'
        '<i><span class="mt-dot bad"></span>Merah = cenderung memberatkan / memburuk</i>'
        '<i><span class="mt-dot flat"></span>Abu-abu = relatif stabil</i>'
        "</div>",
        unsafe_allow_html=True,
    )


# ═══════════════════════════════════════════════════════════
# ANALISIS OTOMATIS — menerjemahkan angka menjadi kalimat biasa
# ═══════════════════════════════════════════════════════════

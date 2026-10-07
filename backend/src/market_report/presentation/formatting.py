"""Format angka pasar agar konsisten di kartu, tabel, dan narasi."""

from datetime import datetime


def fmt_num(v, decimals=2):
    if v is None:
        return "–"
    try:
        return f"{float(v):,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def fmt_pct(v, decimals=2):
    if v is None:
        return "–"
    sign = "+" if v > 0 else ""
    return f"{sign}{float(v):.{decimals}f}%"


def fmt_bp(v):
    if v is None:
        return "–"
    sign = "+" if v > 0 else ""
    return f"{sign}{float(v):.1f} bp"


def fmt_mag(v, decimals=2) -> str:
    """
    Besaran perubahan tanpa tanda plus/minus — dipakai di dalam kalimat yang
    sudah menyebut arahnya (mis. 'Rupiah menguat 0.90%', bukan 'menguat +0.90%').
    """
    if v is None:
        return "–"
    return f"{abs(float(v)):.{decimals}f}%"


def arrow(chg, threshold=0.02) -> str:
    """Arah pergerakan sebagai simbol: naik / turun / hampir tidak bergerak."""
    if chg is None:
        return "–"
    if chg > threshold:
        return "▲"
    if chg < -threshold:
        return "▼"
    return "▬"


def tone_of(chg, higher_is_better: bool = True, threshold: float = 0.02) -> str:
    """
    Terjemahkan arah angka menjadi makna warna:
    good = menguntungkan, bad = memberatkan, flat = relatif stabil.
    """
    if chg is None:
        return "flat"
    if abs(chg) <= threshold:
        return "flat"
    naik = chg > 0
    if naik == higher_is_better:
        return "good"
    return "bad"


def spread_word(spread) -> tuple[str, str]:
    """Terjemahkan besaran spread SBN–UST menjadi kata + tone warna."""
    if spread is None:
        return "belum tersedia", "flat"
    if spread < 250:
        return "relatif sempit", "good"
    if spread <= 450:
        return "tergolong sedang", "flat"
    return "relatif lebar", "warn"


# ── Kepingan tampilan (HTML) ─────────────────────────────────

def _delta_bp(chg_bp) -> str:
    """Label perubahan dalam poin basis, mis. '▼ -4,1 bp'."""
    if chg_bp is None:
        return ""
    return f"{arrow(chg_bp, 0.05)} {fmt_bp(chg_bp)}"


def _waktu_lokal(iso, format: str = "%d %b %Y %H:%M:%S") -> str:
    """Ubah stempel waktu ISO dari sumber menjadi teks lokal yang mudah dibaca."""
    if not iso:
        return "–"
    try:
        return datetime.fromisoformat(str(iso)).astimezone().strftime(format)
    except Exception:
        return str(iso)


def _delta_label(chg, kata_naik: str, kata_turun: str) -> str:
    """Label perubahan ringkas, mis. '▼ -0,90% · Rupiah menguat'."""
    if chg is None:
        return ""
    kata = kata_naik if chg > 0.02 else (kata_turun if chg < -0.02 else "stabil")
    return f"{arrow(chg)} {fmt_pct(chg)} · {kata}"

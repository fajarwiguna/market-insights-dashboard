"""Pengolahan deret harga dan pembuat grafik pasar."""

from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np

from market_report.presentation.colors import (
    CHART_GRID, COLOR_DOWN, COLOR_SPREAD, COLOR_UP, COLOR_SBN, COLOR_UST,
)


def _pick(data: dict, *needles: str, exclude: tuple[str, ...] = ()) -> dict:
    """Ambil baris instrumen dengan mencocokkan kata pada nama kunci."""
    if not isinstance(data, dict):
        return {}
    for key, value in data.items():
        name = str(key).lower()
        if all(word.lower() in name for word in needles) and not any(word.lower() in name for word in exclude):
            return value if isinstance(value, dict) else {}
    return {}


FX_QUOTE_NAMES = {
    "USD": "Dolar AS", "JPY": "Yen Jepang", "EUR": "Euro",
    "CNY": "Yuan China", "SAR": "Riyal Saudi", "GBP": "Pound Inggris",
}

def _chart_style() -> None:
    """Gaya chart seragam: bersih, tanpa bingkai berlebih, angka mudah dibaca."""
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": CHART_GRID,
        "axes.labelcolor": "#334155",
        "text.color": "#0f172a",
        "xtick.color": "#64748b",
        "ytick.color": "#64748b",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.color": CHART_GRID,
        "grid.linewidth": 0.8,
        # Tanpa tanda centang: angka jadi bersih dan tidak terbaca sebagai minus
        "xtick.major.size": 0,
        "ytick.major.size": 0,
    })


# ── Riwayat harian untuk grafik ──────────────────────────────

def deret_harga(q: dict) -> list[dict]:
    """Riwayat penutupan harian dari sumber langsung, dengan titik terakhir = harga terkini."""
    deret = [{"date": str(h.get("date"))[:10], "close": float(h["close"])}
             for h in (q.get("history") or []) if isinstance(h, dict) and h.get("close") is not None]
    kini = q.get("meta_price")
    if kini is not None and deret:
        tanggal = str(q.get("date") or datetime.now().strftime("%Y-%m-%d"))[:10]
        if deret[-1]["date"] == tanggal:
            deret[-1]["close"] = float(kini)          # hari yang sama: pakai harga terkini
        else:
            deret.append({"date": tanggal, "close": float(kini)})
    return deret


def gabung_sumbu(ust: list[dict], sbn: list[dict]) -> tuple[list[str], list, list]:
    """
    Susun satu sumbu tanggal untuk dua deret harian. Tanggal yang belum punya angka
    diisi dengan angka terakhir (forward fill) supaya garis tidak terpotong; satu
    sisi boleh kosong lebih dulu (mis. SBN belum terbit di hari pertama).
    """
    peta_u = {h["date"]: h["close"] for h in ust}
    peta_s = {h["date"]: h["close"] for h in sbn}
    tanggal = sorted(set(peta_u) | set(peta_s))[-12:]
    deret_u, deret_s, terakhir_u, terakhir_s = [], [], None, None
    for t in tanggal:
        if t in peta_u:
            terakhir_u = peta_u[t]
        if t in peta_s:
            terakhir_s = peta_s[t]
        deret_u.append(terakhir_u)
        deret_s.append(terakhir_s)
    return tanggal, deret_u, deret_s


def make_rate_diff_chart(report: dict, sbn_hist: list[dict] | None = None,
                         live_at: str | None = None):
    """
    SBN 10Y (Indonesia) vs UST 10Y (AS) + batang selisih (spread) dalam bp.

    Args:
        report: laporan yang dipakai (boleh sudah ditimpa angka langsung).
        sbn_hist: riwayat SBN harian yang dikumpulkan aplikasi — tanpanya garis SBN
                  datar karena PHEI hanya merilis satu angka terakhir.
        live_at : stempel waktu angka langsung, ditulis kecil di kaki grafik.
    """
    _chart_style()
    yld = report.get("yields") or {}
    sbn10 = _pick(yld, "sbn", "10", exclude=("sbsn", "fr0")).get("today")
    ust10 = _pick(yld, "treasury", "10").get("today")

    tanggal, ust_vals, sbn_vals = gabung_sumbu(report.get("history_ust10") or [], sbn_hist or [])
    if not tanggal:  # riwayat benar belum ada → tampilkan nilai terakhir saja
        tanggal, ust_vals, sbn_vals = ["hari ini"], [ust10], [sbn10]
    if ust10 is not None:
        ust_vals[-1] = float(ust10)   # titik terakhir = angka yang tampil di kartu
    if sbn10 is not None:
        sbn_vals[-1] = float(sbn10)

    label_tanggal = [t[5:].replace("-", "/") for t in tanggal]
    punya_u = [i for i, v in enumerate(ust_vals) if v is not None]
    punya_s = [i for i, v in enumerate(sbn_vals) if v is not None]
    keduanya = [i for i in range(len(tanggal)) if ust_vals[i] is not None and sbn_vals[i] is not None]
    catatan = (
        "Riwayat SBN disusun dari angka PHEI yang tersimpan otomatis setiap laporan dibuka."
        if len(punya_s) > 1 else
        "Garis SBN masih datar: PHEI hanya merilis satu angka terakhir, jadi riwayatnya "
        "terkumpul otomatis setelah laporan beberapa kali dibuka."
    )

    fig, ax1 = plt.subplots(figsize=(10, 4.6))
    x = np.arange(len(tanggal))

    if punya_s:
        if len(punya_s) == 1:   # baru satu angka PHEI → garis putus-putus sebagai level
            level = sbn_vals[punya_s[0]]
            awal = x[punya_u[0]] if punya_u else 0
            ax1.plot([awal, x[punya_s[0]]], [level, level], color=COLOR_SBN, linewidth=2.2,
                     linestyle=(0, (4, 3)), alpha=0.8, label="SBN 10Y — obligasi Indonesia")
            ax1.plot([x[punya_s[0]]], [level], color=COLOR_SBN, marker="o", markersize=6.5,
                     zorder=5, clip_on=False)
        else:
            ax1.plot([x[i] for i in punya_s], [sbn_vals[i] for i in punya_s],
                     color=COLOR_SBN, linewidth=2.4, marker="o", markersize=5.5,
                     label="SBN 10Y — obligasi Indonesia")
    if punya_u:
        ax1.plot([x[i] for i in punya_u], [ust_vals[i] for i in punya_u],
                 color=COLOR_UST, linewidth=2.4, marker="o", markersize=5.5,
                 label="UST 10Y — obligasi Amerika Serikat")
    ax1.set_ylabel("Imbal hasil tahunan (%)", fontsize=9.5)
    nilai_y = [v for v in ust_vals + sbn_vals if v is not None] or [0.0]
    ax1.set_ylim(min(nilai_y) - 0.2, max(nilai_y) + 0.3)

    ax2 = None
    if keduanya:
        ax2 = ax1.twinx()
        spreads = [(sbn_vals[i] - ust_vals[i]) * 100 for i in keduanya]
        ax2.bar([x[i] for i in keduanya], spreads, width=0.34, color=COLOR_SPREAD, alpha=0.32,
                edgecolor=COLOR_SPREAD, linewidth=0.6, label="Selisih (spread) dalam bp")
        ax2.set_ylabel("Selisih (poin basis / bp)", fontsize=9.5)
        ax2.set_ylim(0, max(spreads) * 1.45)
        ax2.grid(False)
        ax2.annotate(f"{spreads[-1]:.0f} bp", (x[keduanya[-1]], spreads[-1]),
                     textcoords="offset points", xytext=(0, 9), ha="center",
                     fontsize=10, fontweight="bold", color="#1b5e20")

    ax1.set_xticks(x)
    ax1.set_xticklabels(label_tanggal, fontsize=9)   # label pendek (09/22) tak perlu diputar
    ax1.set_xlim(-0.45, len(tanggal) - 0.55)          # beri ruang agar batang terakhir tidak menempel tepi
    ax1.set_title("Selisih Imbal Hasil Obligasi RI vs AS (tenor 10 tahun)",
                  fontsize=12, fontweight="bold", pad=30, color="#0f172a")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels() if ax2 else ([], [])
    # Legenda diletakkan di atas sumbu agar tidak menutupi garis SBN / batang spread
    ax1.legend(h1 + h2, l1 + l2, loc="lower left", bbox_to_anchor=(0, 1.005), ncol=3,
               fontsize=8.5, frameon=False, handlelength=2.6, columnspacing=1.8)
    ekor = f" · angka per {live_at}" if live_at else ""
    fig.text(0.5, -0.02,
             f"{catatan} Sumber: PHEI (SBN) & Yahoo Finance (UST). 1 bp = 0,01%{ekor}.",
             ha="center", fontsize=7.5, style="italic", color="#64748b")
    fig.tight_layout()
    return fig


def make_fx_chart(fx: dict, live_at: str | None = None):
    """
    Perubahan harian kurs terhadap Rupiah, diurutkan dari yang paling bergerak.
    Warna mengikuti dampaknya ke Rupiah: positif (Rp melemah) = merah,
    negatif (Rp menguat) = hijau.
    """
    _chart_style()
    baris = []
    for k, v in (fx or {}).items():
        if k.upper().startswith("DXY"):  # bukan kurs Rupiah → tidak diikutkan
            continue
        chg = (v or {}).get("change_pct")
        if chg is None:
            continue
        nama = FX_QUOTE_NAMES.get(k.split("/")[0].upper(), k.split("/")[0])
        baris.append((f"{k}  ({nama})", float(chg)))

    if not baris:
        fig, ax = plt.subplots(figsize=(7, 2.2))
        ax.text(0.5, 0.5, "Data perubahan kurs belum tersedia", ha="center", va="center", fontsize=9)
        ax.axis("off")
        return fig

    baris.sort(key=lambda b: b[1])          # terkecil (Rupiah menguat) di bawah
    labels = [b[0] for b in baris]
    values = [b[1] for b in baris]
    colors = [COLOR_DOWN if v > 0 else (COLOR_UP if v < 0 else "#94a3b8") for v in values]

    fig, ax = plt.subplots(figsize=(10, 2.8 + 0.24 * len(labels)))
    y = np.arange(len(labels))
    ax.barh(y, values, color=colors, height=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=9.5)
    ax.axvline(0, color="#94a3b8", linewidth=0.9)
    ax.set_xlabel("Perubahan harian (%)", fontsize=9.5)
    ax.set_title("Pergerakan Kurs terhadap Rupiah", fontsize=12, fontweight="bold",
                 pad=12, color="#0f172a")
    ax.grid(axis="y", visible=False)
    pad = max(max(abs(v) for v in values) * 0.06, 0.03)
    for i, v in enumerate(values):
        ax.text(v + (pad if v >= 0 else -pad), i, f"{v:+.2f}%", va="center",
                ha="left" if v >= 0 else "right", fontsize=9, fontweight="bold", color="#334155")
    ax.set_xlim(min(values) - 3 * pad, max(values) + 3 * pad)
    ekor = f" Angka per {live_at}." if live_at else ""
    fig.text(0.5, -0.05,
             "Hijau = Rupiah menguat, Merah = Rupiah melemah. DXY (indeks dolar AS) tidak diikutkan "
             f"karena bukan kurs Rupiah.{ekor}",
             ha="center", fontsize=7.5, style="italic", color="#64748b")
    fig.tight_layout()
    return fig



# ── Render: angka kunci ──────────────────────────────────────

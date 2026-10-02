"""
Generate charts for the daily market report.
Primary chart: Rate Differential (SBN 10Y vs UST 10Y + Spread bars)
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Optional, List, Dict

import matplotlib.pyplot as plt
import numpy as np

from market_report.services.history_service import load_sbn_history, source_date_iso

CHART_DIR = Path(__file__).resolve().parents[3] / "charts"
CHART_DIR.mkdir(exist_ok=True)
DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _cari(data, *kata, exclude=()):
    """Ambil satu baris data berdasarkan kata kunci nama instrument (toleran)."""
    for key, val in (data or {}).items():
        low = str(key).lower()
        if all(k.lower() in low for k in kata) and not any(e.lower() in low for e in exclude):
            return val if isinstance(val, dict) else {}
    return {}


def seri_dari_snapshot(path=None, *, report: dict | None = None) -> tuple[list[str], list[float], list[float]]:
    """
    Deret SBN 10Y & UST 10Y dari snapshot laporan — data nyata, bukan contoh.

    UST memakai riwayat harian (history_ust10), SBN memakai angka PHEI terakhir
    yang dikumpulkan per tanggal di data/history_sbn.json. Bila SBN hanya punya
    satu titik, nilainya maju- dan mundur-diteruskan supaya garis tetap utuh
    (dan diberi catatan di kaki grafik).

    Returns: (label_tanggal, seri_sbn, seri_ust) — kosong bila snapshot belum ada.
    """
    if report is None:
        snap = Path(path or (DATA_DIR / "report_data.json"))
        if not snap.exists():
            return [], [], []
        try:
            report = json.loads(snap.read_text(encoding="utf-8"))
        except Exception:
            return [], [], []

    yld = report.get("yields") or {}
    sbn_row = _cari(yld, "sbn", "10", exclude=("sbsn", "fr0"))
    sbn10 = sbn_row.get("today")
    ust10 = _cari(yld, "treasury", "10").get("today")
    iso = str(report.get("report_date_iso") or "")

    peta_sbn = {
        str(point.get("date"))[:10]: float(point["close"])
        for point in load_sbn_history()
        if point.get("date") is not None and point.get("close") is not None
    }
    sbn_date = source_date_iso(sbn_row.get("date"))
    if sbn_date is None and report.get("is_demo"):
        sbn_date = iso
    if sbn10 is not None and sbn_date:
        peta_sbn[sbn_date] = float(sbn10)

    hist = [h for h in (report.get("history_ust10") or []) if h.get("close") is not None]
    if not hist and ust10 is not None:
        hist = [{"date": iso, "close": ust10}]
    if not hist:
        return [], [], []

    tanggal, sbn, ust = [], [], []
    for h in hist[-8:]:
        d = str(h.get("date"))[:10]
        tanggal.append(f"{d[5:7]}/{d[8:10]}" if len(d) >= 10 else d)
        ust.append(float(h["close"]))
        sbn.append(peta_sbn.get(d))

    # Maju-teruskan nilai SBN ke belakang, lalu ke depan, agar garis tidak terputus
    pertama = next((v for v in sbn if v is not None), None)
    if pertama is None:
        # Tidak ada tanggal SBN yang cocok dengan jendela UST (PHEI terbit satu kali
        # sehari): pakai nilai SBN terakhir sebagai level untuk seluruh jendela.
        sbn = [float(sbn10)] * len(ust) if sbn10 is not None else []
    else:
        terakhir = pertama
        for i, v in enumerate(sbn):
            if v is not None:
                terakhir = v
            sbn[i] = float(terakhir)
    return tanggal, sbn, ust


def _style():
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })


def generate_rate_differential_chart(
    sbn_series: Optional[List[float]] = None,
    ust_series: Optional[List[float]] = None,
    dates: Optional[List[str]] = None,
    title: str = "Rate Differential",
    catatan: str = "",
) -> Path:
    """
    Create a dual-axis chart:
    - Left axis: SBN 10Y (red) & UST 10Y (blue) yields
    - Right axis: Spread in bp (green bars)

    Tanpa argumen seri, data diambil dari snapshot laporan (`seri_dari_snapshot`).
    """
    _style()

    # Tanpa argumen: pakai data nyata dari snapshot laporan. Angka contoh TIDAK
    # pernah digambar — lebih baik kosong daripada menampilkan data palsu.
    if not dates or not sbn_series or not ust_series:
        t, s, u = seri_dari_snapshot()
        dates = dates or t
        sbn_series = sbn_series or s
        ust_series = ust_series or u
    if not (dates and sbn_series and ust_series):
        raise ValueError(
            "Data untuk grafik belum tersedia. Jalankan pipeline lebih dulu "
            "(python backend/src/market_report/run_pipeline.py) atau teruskan sbn_series/ust_series/dates."
        )
    sbn_series = list(sbn_series)
    while len(sbn_series) < len(ust_series):   # samakan panjang dengan deret UST
        sbn_series.append(sbn_series[-1])
    sbn_series = sbn_series[:len(ust_series)]
    dates = list(dates)[:len(ust_series)]

    spread = [(s - u) * 100 for s, u in zip(sbn_series, ust_series)]

    fig, ax1 = plt.subplots(figsize=(11, 5.5))

    x = np.arange(len(dates))
    color_sbn = "#E53935"   # red
    color_ust = "#1E88E5"   # blue
    color_spread = "#66BB6A"  # green

    # Lines
    ax1.plot(x, sbn_series, color=color_sbn, linewidth=2.2, marker="o", markersize=5, label="SBN 10Y")
    ax1.plot(x, ust_series, color=color_ust, linewidth=2.2, marker="o", markersize=5, label="UST 10Y")
    ax1.set_ylabel("Yield (%)", fontsize=10)
    ax1.set_ylim(min(min(sbn_series), min(ust_series)) - 0.15,
                 max(max(sbn_series), max(ust_series)) + 0.15)

    # Spread bars on secondary axis
    ax2 = ax1.twinx()
    bars = ax2.bar(x, spread, width=0.45, color=color_spread, alpha=0.7, label="Spread (bps)")
    ax2.set_ylabel("Spread (bps)", fontsize=10)
    ax2.set_ylim(min(spread) - 15, max(spread) + 25)

    # Annotate last spread
    for i, (xi, s) in enumerate(zip(x, spread)):
        ax2.annotate(f"{s:.0f} bps", (xi, s), textcoords="offset points",
                     xytext=(0, 6), ha="center", fontsize=8, color="#2E7D32")

    ax1.set_xticks(x)
    ax1.set_xticklabels(dates, fontsize=9)
    ax1.set_title(title, fontsize=13, fontweight="bold", pad=12)

    # Combined legend
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", frameon=True, fontsize=9)

    # Footer note — kedua baris diberi jarak vertikal agar tidak bertumpuk.
    last_sbn, last_ust, last_sp = sbn_series[-1], ust_series[-1], spread[-1]
    fig.text(0.5, 0.022,
             f"Latest: SBN 10Y {last_sbn:.2f}% | UST 10Y {last_ust:.2f}% | Spread {last_sp:.0f} bps",
             ha="center", fontsize=8, style="italic", color="#555")
    fig.text(0.5, -0.008,
             catatan or "Sumber: PHEI (SBN) & Yahoo Finance (UST). 1 bp = 0,01%.",
             ha="center", fontsize=7, style="italic", color="#777")

    plt.tight_layout(rect=[0, 0.07, 1, 1])
    out = CHART_DIR / "rate_differential.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"Chart saved -> {out}")   # ASCII: konsol Windows (cp1252) tidak bisa cetak "→"
    return out


def generate_fx_bar_chart(fx_data: Dict) -> Path:
    """Simple horizontal bar of % change for FX."""
    _style()
    labels, values, colors = [], [], []
    for k, v in fx_data.items():
        chg = (v or {}).get("change_pct")
        if chg is None:      # belum ada penutupan pembanding → dilewati
            continue
        labels.append(k)
        values.append(float(chg))
        colors.append("#E53935" if chg < 0 else "#43A047")

    if not labels:           # tidak ada yang bisa digambar — jangan tampilkan sumbu kosong
        raise ValueError("Tidak ada data perubahan kurs untuk digambar (semua baris belum punya "
                         "penutupan pembanding).")

    fig, ax = plt.subplots(figsize=(8, 3.5))
    y_pos = np.arange(len(labels))
    ax.barh(y_pos, values, color=colors, height=0.55)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels)
    ax.axvline(0, color="black", linewidth=0.8)
    ax.set_xlabel("Change %")
    ax.set_title("Exchange Rate Daily Change %", fontsize=12, fontweight="bold")
    for i, v in enumerate(values):
        ax.text(v + (0.02 if v >= 0 else -0.02), i, f"{v:+.2f}%",
                va="center", ha="left" if v >= 0 else "right", fontsize=9)
    plt.tight_layout()
    out = CHART_DIR / "fx_change.png"
    fig.savefig(out, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return out


if __name__ == "__main__":
    out = generate_rate_differential_chart()
    snap = DATA_DIR / "report_data.json"
    if snap.exists():   # grafik kurs memakai data nyata bila snapshot tersedia
        generate_fx_bar_chart(json.loads(snap.read_text(encoding="utf-8")).get("fx", {}))
    print("Chart:", out)

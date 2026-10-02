"""
Unit test untuk logika "angka langsung" (live) pada dashboard.

Bagian grafik dashboard mengambil harga terkini dari sumber (bukan snapshot
harian) supaya grafiknya benar-benar berubah saat disegarkan. Modul ini menguji
logika penggabungan angka itu tanpa jaringan:

  1. pasang_angka_langsung — menimpa angka snapshot dengan harga terkini,
     menyimpan nilai lama, serta menghitung ulang persentase/bp dan spread,
  2. deret_harga          — riwayat harian + titik harga terkini,
  3. gabung_sumbu         — penyatuan dua deret pada satu sumbu tanggal,
  4. kumpulkan_riwayat_sbn— pengumpulan riwayat SBN harian (satu titik per tanggal),
  5. kedua pembuat grafik — harus tetap jalan walau datanya sangat sedikit.

Jalankan:
    python tests/test_live.py
"""

from __future__ import annotations
import json
import sys
import tempfile
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore")

# Konsol Windows sering cp1252 — paksa UTF-8 agar teks beraksen aman dicetak
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

import matplotlib                                # noqa: E402
matplotlib.use("Agg")

import app                                       # noqa: E402  (dashboard diimpor sebagai modul)
import matplotlib.pyplot as plt                  # noqa: E402


GAGAL: list[str] = []


def cek(nama: str, kondisi: bool, pesan: str = "") -> None:
    print(f"{'OK  ' if kondisi else 'FAIL'}: {nama}{'' if kondisi else ' -> ' + pesan}")
    if not kondisi:
        GAGAL.append(nama)


def _ada_pesan(fig, kata: str) -> bool:
    """Cari teks pesan di figure: baik fig.text maupun teks di dalam sumbu."""
    semua = [t.get_text() for t in fig.texts]
    for ax in fig.axes:
        semua += [t.get_text() for t in ax.texts]
    return any(kata in t for t in semua)


def laporan_minimal() -> dict:
    """Laporan tiruan seukuran data asli (nilai disengaja agar mudah dicek)."""
    return {
        "report_date_iso": "2026-09-29",
        "fx": {
            "USD/IDR": {"today": 17_000.0, "prev": 17_100.0, "change_pct": -0.58,
                        "date": "2026-09-28", "source": "Yahoo Finance Chart API — USDIDR=X"},
            "DXY": {"today": 98.0, "prev": 98.2, "change_pct": -0.20, "date": "2026-09-28"},
        },
        "indices": {"IHSG (ID)": {"today": 6_700.0, "prev": 6_680.0, "change_pct": 0.30}},
        "yields": {
            "US Treasury 10 Tahun": {"today": 4.20, "prev": 4.15, "change_bp": 5.0},
            "ID SBN 10 Tahun": {"today": 7.00, "prev": 6.99, "change_bp": 1.0,
                                "date": "2026-09-28"},
        },
        "commodities": {"Gold (USD/oz)": {"today": 3_000.0, "prev": 2_980.0, "change_pct": 0.67}},
        "spread_sbn10_ust10_bp": 280.0,
        "history_ust10": [{"date": "2026-09-27", "close": 4.10}, {"date": "2026-09-28", "close": 4.15}],
    }


# ── 1. pasang_angka_langsung ────────────────────────────────────
def test_pasang_angka_langsung() -> None:
    laporan = laporan_minimal()
    langsung = {
        "_fetched_at": "2026-09-29T09:30:00+00:00",
        "fx|USD/IDR": {"last": 17_050.0, "prev": 17_000.0, "meta_price": 17_040.0,
                       "date": "2026-09-29", "history": [{"date": "2026-09-27", "close": 17_100.0}]},
        "yields|US Treasury 10 Tahun": {"last": 4.30, "prev": 4.20, "meta_price": 4.30,
                                        "date": "2026-09-29", "history": []},
        "fx|EUR/IDR": {"last": 19_000.0},   # tidak ada di laporan → harus diabaikan
    }
    view, diperbarui = app.pasang_angka_langsung(laporan, langsung)

    usd = view["fx"]["USD/IDR"]
    cek("harga terkini dipakai (meta_price diutamakan)", usd["today"] == 17_040.0, str(usd["today"]))
    cek("snapshot lama disimpan sebagai pembanding", usd["snapshot_today"] == 17_000.0)
    cek("persentase dihitung ulang vs penutupan sebelumnya",
        abs(usd["change_pct"] - 0.2353) < 0.001, str(usd["change_pct"]))
    cek("penutupan sebelumnya ikut diperbarui", usd["prev"] == 17_000.0)
    cek("penanda data langsung ada", usd.get("live") is True)
    cek("baris tak dikenal tidak ditambah", "EUR/IDR" not in view["fx"], str(list(view["fx"])))

    ust = view["yields"]["US Treasury 10 Tahun"]
    cek("perubahan bp dihitung ulang untuk imbal hasil",
        abs(ust["change_bp"] - 10.0) < 0.01, str(ust["change_bp"]))

    cek("spread dihitung ulang dari angka terkini",
        view["spread_sbn10_ust10_bp"] == 270.0, str(view["spread_sbn10_ust10_bp"]))
    cek("stempel waktu pengambilan tersimpan", view["live_at"] == "2026-09-29T09:30:00+00:00")
    cek("daftar instrumen yang berubah dikembalikan",
        set(diperbarui) == {"USD/IDR", "US Treasury 10 Tahun"}, str(diperbarui))
    cek("laporan asli tidak ikut berubah", laporan["fx"]["USD/IDR"]["today"] == 17_000.0)
    cek("DXY tidak berubah (tidak ada di sumber langsung)",
        view["fx"]["DXY"]["today"] == 98.0 and view["fx"]["DXY"].get("live") is None)

    # Jalur cadangan saat sumber tidak terjangkau: angka laporan harus tetap utuh
    view2, diperbarui2 = app.pasang_angka_langsung(laporan, {"_error": "jaringan mati"})
    cek("gagal ambil sumber → tidak ada instrumen yang ditandai berubah", diperbarui2 == [],
        str(diperbarui2))
    cek("gagal ambil sumber → angka laporan tetap dipakai",
        view2["fx"]["USD/IDR"]["today"] == 17_000.0 and view2["live_at"] is None)
    cek("alasan kegagalan tersimpan untuk ditampilkan", view2["live_error"] == "jaringan mati")


# ── 2. deret_harga ──────────────────────────────────────────────
def test_deret_harga() -> None:
    sama = app.deret_harga({"history": [{"date": "2026-09-27", "close": 4.10},
                                        {"date": "2026-09-28", "close": 4.15}],
                            "meta_price": 4.25, "date": "2026-09-28"})
    cek("tanggal sama → titik terakhir diganti harga terkini",
        sama[-1] == {"date": "2026-09-28", "close": 4.25}, str(sama))

    baru = app.deret_harga({"history": [{"date": "2026-09-28", "close": 4.15}],
                            "meta_price": 4.30, "date": "2026-09-29"})
    cek("tanggal baru → titik baru ditambahkan",
        len(baru) == 2 and baru[-1]["date"] == "2026-09-29", str(baru))

    cek("riwayat kosong ditangani tanpa error", app.deret_harga({"history": []}) == [])



# ── 3. gabung_sumbu ─────────────────────────────────────────────
def test_gabung_sumbu() -> None:
    ust = [{"date": "2026-09-25", "close": 4.10}, {"date": "2026-09-26", "close": 4.15},
           {"date": "2026-09-27", "close": 4.12}]
    sbn = [{"date": "2026-09-25", "close": 7.00}, {"date": "2026-09-27", "close": 7.05}]
    tanggal, val_u, val_s = app.gabung_sumbu(ust, sbn)
    cek("sumbu tanggal = gabungan kedua deret", len(tanggal) == 3 and tanggal[0] == "2026-09-25")
    cek("nilai SBN diteruskan maju", val_s == [7.00, 7.00, 7.05], str(val_s))
    cek("nilai UST lengkap", val_u == [4.10, 4.15, 4.12], str(val_u))

    tanggal2, u2, s2 = app.gabung_sumbu([{"date": "2026-09-20", "close": 4.0}],
                                        [{"date": "2026-09-26", "close": 7.0}])
    cek("satu sisi boleh kosong lebih dulu (SBN belum terbit)", s2 == [None, 7.0], str(s2))
    cek("sisi yang punya riwayat tetap terisi penuh", u2 == [4.0, 4.0], str(u2))
    cek("tanggal tetap urut", tanggal2 == ["2026-09-20", "2026-09-26"], str(tanggal2))


# ── 4. kumpulkan_riwayat_sbn ────────────────────────────────────
def test_riwayat_sbn() -> None:
    asli = app.HISTORI_SBN
    with tempfile.TemporaryDirectory() as tmp:
        app.HISTORI_SBN = Path(tmp) / "history_sbn.json"
        laporan = laporan_minimal()
        laporan["report_date_iso"] = "2026-09-28"
        app.kumpulkan_riwayat_sbn(laporan)
        laporan["report_date_iso"] = "2026-09-29"
        app.kumpulkan_riwayat_sbn(laporan)
        riwayat = app.riwayat_sbn()
        cek("tanggal laporan tidak menggandakan observasi SBN yang sama",
            [h["date"] for h in riwayat] == ["2026-09-28"], str(riwayat))

        laporan["yields"]["ID SBN 10 Tahun"]["today"] = 7.10
        laporan["yields"]["ID SBN 10 Tahun"]["date"] = "29-Sep-2026"
        app.kumpulkan_riwayat_sbn(laporan)
        isi = json.loads(app.HISTORI_SBN.read_text(encoding="utf-8"))
        cek("tanggal publikasi PHEI dinormalisasi dan dicatat",
            len(isi) == 2 and isi[-1]["date"] == "2026-09-29"
            and abs(isi[-1]["close"] - 7.10) < 1e-6, str(isi))
    app.HISTORI_SBN = asli


# ── 5. pembuat grafik ───────────────────────────────────────────
def test_grafik() -> None:
    laporan = laporan_minimal()
    riwayat = [{"date": "2026-09-27", "close": 7.00}, {"date": "2026-09-28", "close": 7.00},
               {"date": "2026-09-29", "close": 7.00}]

    fig = app.make_rate_diff_chart(laporan, sbn_hist=riwayat, live_at="16:45:01")
    cek("grafik imbal hasil terbentuk", fig is not None and len(fig.axes) >= 2, str(len(fig.axes)))
    cek("stempel waktu live masuk ke kaki grafik", any("16:45:01" in t.get_text() for t in fig.texts))
    plt.close(fig)

    fig = app.make_fx_chart(laporan["fx"], live_at="16:45:01")
    cek("grafik kurs terbentuk (DXY tidak diikutkan)", len(fig.axes[0].patches) == 1,
        str(len(fig.axes[0].patches)))
    plt.close(fig)

    # Jalur cadangan: data sangat sedikit / kosong tidak boleh membuat error
    fig = app.make_rate_diff_chart({}, sbn_hist=None, live_at=None)
    cek("grafik imbal hasil tetap jalan tanpa riwayat", fig is not None)
    plt.close(fig)
    fig = app.make_rate_diff_chart({"yields": {}}, sbn_hist=[{"date": "2026-09-29", "close": 7.0}])
    cek("grafik imbal hasil jalan dengan satu titik riwayat", fig is not None)
    plt.close(fig)
    fig = app.make_fx_chart({})
    cek("grafik kurs menampilkan pesan bila data kosong", _ada_pesan(fig, "belum tersedia"))
    plt.close(fig)
    fig = app.make_fx_chart({"USD/IDR": {"change_pct": None}})
    cek("grafik kurs melewati baris tanpa data", _ada_pesan(fig, "belum tersedia"))
    plt.close(fig)


def main() -> int:
    for fungsi in (test_pasang_angka_langsung, test_deret_harga, test_gabung_sumbu,
                   test_riwayat_sbn, test_grafik):
        print(f"\n— {fungsi.__name__} —")
        fungsi()
    print("\nHASIL:", "FAIL" if GAGAL else "PASS")
    return 1 if GAGAL else 0


if __name__ == "__main__":
    raise SystemExit(main())

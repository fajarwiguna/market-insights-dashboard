"""
Unit test untuk PDF laporan — memastikan file yang diunduh dashboard berisi
angka yang SEDANG TAMPIL, bukan file lama di folder reports/ dan bukan grafik
dengan angka hard-coded.

Yang diuji:
  1. build_pdf dengan `stream` menghasilkan byte PDF valid + nama file ikut tanggal laporan.
  2. Isi PDF memuat angka kunci dashboard (kurs, IHSG, SBN, UST, spread, tanggal, stempel).
  3. PDF mengikuti perubahan data (bukan file basi yang tersimpan).
  4. Grafik PDF memakai fungsi yang sama dengan grafik di layar.
  5. seri_dari_snapshot() memakai angka snapshot, bukan angka contoh hard-coded.
  6. build_pdf tanpa `stream` tetap menulis file ke disk (dipakai CLI).

Jalankan:
    python tests/test_pdf.py
"""

from __future__ import annotations
import base64
import io
import re
import sys
import tempfile
import warnings
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
warnings.filterwarnings("ignore")

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # pragma: no cover
    pass

import matplotlib                            # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt               # noqa: E402

import app                                   # noqa: E402
import charts                                # noqa: E402
from report_pdf import build_pdf             # noqa: E402


GAGAL: list[str] = []


def cek(nama: str, kondisi: bool, pesan: str = "") -> None:
    print(f"{'OK  ' if kondisi else 'FAIL'}: {nama}{'' if kondisi else ' -> ' + pesan}")
    if not kondisi:
        GAGAL.append(nama)


def teks_pdf(isi: bytes) -> str:
    """Tarik teks dari stream ASCII85+Flate milik ReportLab."""
    halaman = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", isi, re.S):
        try:
            mentah = zlib.decompress(base64.a85decode(m.group(1).strip(), adobe=True))
        except Exception:
            continue
        if b"BT" in mentah or b"Tf" in mentah:      # hanya stream isi halaman
            halaman.append(mentah.decode("latin-1"))
    semua = " ".join(re.findall(r"\((?:\\.|[^()\\])*\)", " ".join(halaman)))
    return semua.replace("\\(", "(").replace("\\)", ")")


def laporan_uji(nilai_usd: float, hari: str = "2026-09-29") -> dict:
    """Laporan tiruan dengan satu angka yang dapat diacak untuk uji pengikatan data."""
    return {
        "report_date": "29 September 2026",
        "report_date_iso": hari,
        "source_snapshot": "2026-09-29T15:31:10.865564",
        "fx": {"USD/IDR": {"today": nilai_usd, "prev": nilai_usd - 15, "change_pct": 0.08}},
        "indices": {"IHSG (ID)": {"today": 6_124.95, "prev": 6_147.6, "change_pct": -0.37}},
        "yields": {
            "US Treasury 10 Tahun": {"today": 5.24, "prev": 5.184, "change_bp": 5.6},
            "ID SBN 10 Tahun": {"today": 7.1483, "prev": 7.1293, "change_bp": 1.9,
                                "as_of_label": "per 28-September-2026"},
        },
        "bi": {"BI Rate": 5.75, "INDONIA": 5.75, "JISDOR": 17_762},
        "commodities": {"Gold (USD/oz)": {"today": 4_100.0, "prev": 4_090.0, "change_pct": 0.24}},
        "spread_sbn10_ust10_bp": 190.8,
        "history_ust10": [{"date": "2026-09-27", "close": 5.18}, {"date": "2026-09-28", "close": 5.24}],
    }



# ── 1–2. byte PDF valid + isi sesuai angka yang tampil ───────────
def test_pdf_sesuai_laporan() -> None:
    laporan = laporan_uji(17_965.0)
    isi, nama = build_pdf(laporan, stream=io.BytesIO())

    cek("PDF terbentuk", len(isi) > 5_000, f"{len(isi)} byte")
    cek("PDF valid (header %PDF)", isi.startswith(b"%PDF"), repr(isi[:8]))
    cek("nama file mengikuti tanggal laporan", nama == "Daily_Market_Update_20260929.pdf", nama)

    teks = teks_pdf(isi)
    cek("judul memakai tanggal laporan", "29 September 2026" in teks, teks[:80])
    cek("stempel waktu snapshot tercetak", "15:31" in teks)
    for label, nilai in (("USD/IDR", "17,965.000"), ("IHSG", "6,124.95"),
                         ("SBN 10Y", "7.15"), ("UST 10Y", "5.24"), ("spread", "191 bp")):
        cek(f"angka {label} ada di PDF ({nilai})", nilai in teks)
    cek("grafik ikut disertakan (bukan dilewati)", "Rate Differential" in teks)
    cek("tidak ada sumber data yang tidak dipakai", "yfinance" not in teks.lower())


# ── 3. PDF mengikuti perubahan data (bukan file basi) ────────────
def test_pdf_ikut_perubahan_data() -> None:
    a, nama_a = build_pdf(laporan_uji(17_965.0), stream=io.BytesIO())
    b, nama_b = build_pdf(laporan_uji(18_500.0), stream=io.BytesIO())
    cek("kurs baru ikut terbaca di PDF", "18,500.000" in teks_pdf(b))
    cek("kurs lama tidak bocor ke PDF baru", "17,965.000" not in teks_pdf(b))
    cek("isi PDF benar-benar berubah", a != b)
    cek("nama file sama (tanggal laporan sama)", nama_a == nama_b)

    c, nama_c = build_pdf(laporan_uji(17_965.0, hari="2026-09-30"), stream=io.BytesIO())
    cek("nama file ikut tanggal laporan terbaru", nama_c == "Daily_Market_Update_20260930.pdf", nama_c)


# ── 4. grafik PDF sama dengan grafik di layar ────────────────────
def test_grafik_pdf_sama_dengan_layar() -> None:
    laporan = laporan_uji(17_965.0)
    sbn_hist = [{"date": "2026-09-27", "close": 7.12}, {"date": "2026-09-29", "close": 7.1483}]
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "rate_differential.png"
        fig = app.make_rate_diff_chart(laporan, sbn_hist=sbn_hist)
        fig.savefig(png, dpi=120, bbox_inches="tight")
        plt.close(fig)
        cek("grafik dashboard bisa disimpan sebagai PNG", png.exists() and png.stat().st_size > 5_000)

        isi, _ = build_pdf(laporan, chart_path=png, stream=io.BytesIO())
        cek("PDF menerima grafik yang diberikan", len(isi) > 20_000, f"{len(isi)} byte")


# ── 5. deret grafik memakai data snapshot, bukan angka contoh ─────
def test_deret_dari_snapshot() -> None:
    tanggal, sbn, ust = charts.seri_dari_snapshot()
    if not tanggal:
        cek("snapshot tersedia untuk diuji", False, "data/report_data.json tidak terbaca")
        return
    laporan = app.load_report() or {}
    f = app.market_facts(laporan)
    cek("deret diambil dari snapshot (bukan hard-coded)",
        abs(ust[-1] - float(f["ust10"]["today"])) < 0.01, f"ust terakhir {ust[-1]}")
    cek("deret SBN memakai nilai PHEI terbaru",
        len(sbn) == len(ust) and abs(sbn[-1] - float(f["sbn10"]["today"])) < 0.001, str(sbn[-2:]))
    cek("tidak ada angka contoh lama (UST 4,60)",
        not any(abs(u - 4.60) < 0.001 for u in ust), str([round(u, 2) for u in ust]))

    png = charts.generate_rate_differential_chart()   # tanpa argumen → wajib pakai data nyata
    cek("grafik tanpa argumen tetap ter-render dari snapshot", Path(png).exists())
    cek("grafik tidak memakai seri contoh hard-coded",
        charts.seri_dari_snapshot()[2] != [4.55, 4.62, 4.70, 4.65, 4.58, 4.52, 4.55, 4.60])

    kosong = charts.seri_dari_snapshot(path=ROOT / "data" / "tidak_ada.json")
    cek("snapshot hilang → seri kosong (bukan data palsu)", kosong == ([], [], []), str(kosong))


# ── 6. jalur tulis-ke-disk tetap berfungsi (CLI) ─────────────────
def test_tulis_ke_disk() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tujuan = Path(tmp) / "laporan.pdf"
        hasil = build_pdf(laporan_uji(17_965.0), out_path=tujuan)
        cek("build_pdf mengembalikan Path saat menulis ke disk", isinstance(hasil, Path), str(type(hasil)))
        cek("file tersimpan", tujuan.exists() and tujuan.stat().st_size > 5_000)
        cek("isi file valid", tujuan.read_bytes().startswith(b"%PDF"))


# ── 7. modul PDF tidak boleh mengimpor app (lindungi CachedWidgetWarning) ─
def test_pdf_tidak_import_app() -> None:
    """
    report_pdf TIDAK boleh mengimpor app.py.

    Streamlit menjalankan app.py sebagai __main__, jadi `import app` dari dalam
    pdf_bytes() (fungsi ber-@st.cache_data) akan mengeksekusi ulang seluruh skrip
    lalu memicu CachedWidgetWarning. Grafik harus dibuat oleh pemanggil lalu
    diteruskan lewat chart_path / fx_chart_path.
    """
    import ast
    sumber = (ROOT / "src" / "report_pdf.py").read_text(encoding="utf-8")
    impor: set[str] = set()
    for simpul in ast.walk(ast.parse(sumber)):
        if isinstance(simpul, ast.Import):
            impor.update(a.name.split(".")[0] for a in simpul.names)
        elif isinstance(simpul, ast.ImportFrom) and simpul.module:
            impor.add(simpul.module.split(".")[0])
    cek("report_pdf tidak mengimpor app", "app" not in impor, str(sorted(impor)))
    cek("report_pdf tidak mengimpor charts", "charts" not in impor, str(sorted(impor)))

    # Path grafik opsional tetap diterima dan tidak membuat PDF gagal.
    isi, _ = build_pdf(laporan_uji(17_965.0), fx_chart_path=None, stream=io.BytesIO())
    cek("fx_chart_path=None aman (grafik kurs dilewati)",
        isi.startswith(b"%PDF") and "Pergerakan Kurs" not in teks_pdf(isi))
    cek("isi tetap utuh tanpa grafik kurs tambahan", len(isi) > 5_000, f"{len(isi)} byte")


def main() -> int:
    for fungsi in (test_pdf_sesuai_laporan, test_pdf_ikut_perubahan_data,
                   test_grafik_pdf_sama_dengan_layar, test_deret_dari_snapshot,
                   test_tulis_ke_disk, test_pdf_tidak_import_app):
        print(f"\n— {fungsi.__name__} —")
        fungsi()
    print("\nHASIL:", "FAIL" if GAGAL else "PASS")
    return 1 if GAGAL else 0


if __name__ == "__main__":
    raise SystemExit(main())

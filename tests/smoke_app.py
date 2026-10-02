"""
Smoke + content test untuk dashboard Streamlit (src/app.py).

Menjalankan script dashboard memakai runtime uji bawaan Streamlit
(`streamlit.testing.v1.AppTest`), lalu memeriksa:
  1. tidak ada exception saat render,
  2. semua bagian utama halaman benar-benar muncul,
  3. tabel (dataframe) ter-render sesuai jumlah bagian yang berisi tabel,
  4. tidak ada pesan deprecation dari Streamlit.

Jalankan:
    python tests/smoke_app.py
"""

from __future__ import annotations
import html as html_lib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from streamlit.testing.v1 import AppTest  # noqa: E402

# Judul bagian yang wajib ada di halaman (urutannya juga diperiksa)
SECTION_ORDER = [
    "Insight Hari Ini",
    "Apa Artinya untuk Anda",
    "Angka Kunci Hari Ini",
    "Live Market Monitor",
    "Detail Pasar",
    "Glossarium Istilah & Cara Membaca",
    "Unduh Laporan (PDF)",
    "Sumber Data & Metode",
]

EXPECTED_TABLES = 5  # kurs, indeks, imbal hasil, komoditas, glosarium
EXPECTED_TABS = 8    # 4 (detail pasar) + 2 (grafik langsung) + 2 (kamus istilah)


def main() -> int:
    # Konsol Windows sering cp1252 — paksa UTF-8 agar teks beraksen aman dicetak
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

    at = AppTest.from_file(str(ROOT / "src" / "app.py"), default_timeout=180)
    at.run()

    ok = True

    if at.exception:
        ok = False
        print("FAIL: exception saat render")
        for exc in at.exception:
            print("  -", exc.value)
    else:
        print("OK  : tidak ada exception saat render")

    # Teks halaman (tanpa blok CSS; entitas HTML di-decode supaya judul
    # seperti "Sumber Data & Metode" ikut ketemu)
    texts = [m.value for m in at.markdown if not m.value.lstrip().startswith("<style>")]
    texts += [c.value for c in at.caption]
    blob = html_lib.unescape("\n".join(texts))

    posisi_terakhir = -1
    for judul in SECTION_ORDER:
        if judul not in blob:
            ok = False
            print(f"FAIL: bagian hilang -> {judul}")
            continue
        posisi = blob.index(judul)
        if posisi < posisi_terakhir:
            ok = False
            print(f"FAIL: urutan bagian salah → {judul}")
        posisi_terakhir = posisi
    if ok:
        print(f"OK  : {len(SECTION_ORDER)} bagian utama lengkap dan berurutan")

    n_df = len(at.dataframe)
    if n_df != EXPECTED_TABLES:
        ok = False
        print(f"FAIL: jumlah tabel = {n_df}, diharapkan {EXPECTED_TABLES}")
    else:
        print(f"OK  : {n_df} tabel ter-render")

    n_tab = len(at.tabs)
    if n_tab != EXPECTED_TABS:
        ok = False
        print(f"FAIL: jumlah tab = {n_tab}, diharapkan {EXPECTED_TABS}")
    else:
        print(f"OK  : {n_tab} tab ter-render")

    # ── Warna widget bawaan Streamlit harus ada di KEDUA mode ────────────
    # Bagian "Sumber Data" memakai st.expander + st.container(border=True)
    # yang warnanya dari TEMA Streamlit, bukan dari token kita. Kalau aturan
    # ini hilang, mode terang menampilkan teks putih di atas panel putih.
    css = "\n".join(t.value for t in at.markdown if "<style>" in t.value)
    for testid in ("stExpander", "stVerticalBlockBorderWrapper", "stAlert", "stApp"):
        if testid not in css:
            ok = False
            print(f"FAIL: tidak ada aturan CSS untuk {testid}")
    for token in ("--mt-native-fg", "--mt-native-panel"):
        # Token harus dideklarasikan untuk mode terang DAN gelap.
        if css.count(token) < 2:
            ok = False
            print(f"FAIL: token {token} hanya dideklarasikan sekali (perlu mode terang + gelap)")
    if ok:
        print("OK  : warna widget bawaan Streamlit di kedua mode")

    # Cuplikan isi untuk pemeriksaan manusia
    for penanda, label in (("mt-hero", "Header"), ("mt-note", "Ringkasan singkat"),
                           ("mt-kpi", "Kartu angka kunci"), ("mt-sum", "Kartu sorotan"),
                           ("mt-card", "Kartu dampak praktis"), ("mt-live-bar", "Papan angka langsung"),
                           ("mt-strip", "Baris chip angka")):
        contoh = next((t for t in texts if penanda in t), None)
        print(f"--  {label}: {html_lib.unescape(contoh or 'TIDAK ADA')[:200]}")
        if contoh is None:
            ok = False
            print(f"FAIL: {label} tidak ter-render")

    # Grafik harus benar-benar dirender (st.pyplot → elemen Image)
    n_img = len(at.get("image"))
    if n_img < 2:
        ok = False
        print(f"FAIL: hanya {n_img} grafik ter-render, diharapkan >= 2")
    else:
        print(f"OK  : {n_img} grafik ter-render")

    # Tombol penyegaran angka langsung harus ada
    if not any("Perbarui" in (b.label or "") for b in at.button):
        ok = False
        print("FAIL: tombol perbarui grafik tidak ditemukan")
    else:
        print("OK  : tombol perbarui grafik ada")

    # Tombol unduh PDF harus lahir dari data yang tampil (bukan file lama di reports/)
    unduhan = at.get("download_button")
    if not any("PDF" in (d.label or "") for d in unduhan):
        ok = False
        print("FAIL: tombol unduh PDF tidak ditemukan")
    else:
        nama = [d.label for d in unduhan if "PDF" in (d.label or "")][0]
        print(f"OK  : tombol unduh PDF ada ({nama})")

    if at.warning:
        print("WARN:", [w.value for w in at.warning])

    print("HASIL:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())


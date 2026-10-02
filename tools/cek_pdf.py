"""
Alat bantu developer: cetak teks per halaman dari PDF laporan.

Dipakai untuk memeriksa hasil redesign tampilan tanpa harus membuka PDF.
Jalankan:  python tools/cek_pdf.py
"""
from __future__ import annotations
import base64
import io
import json
import re
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from report_pdf import build_pdf                     # noqa: E402


def stream_isi(pdf: bytes) -> list[bytes]:
    """Kembalikan isi stream yang sudah didekompresi, sesuai urutan halaman."""
    keluar: list[bytes] = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        try:
            keluar.append(zlib.decompress(base64.a85decode(m.group(1).strip(),
                                                             adobe=True)))
        except Exception:
            continue
    return keluar


def teks_halaman(isi: bytes) -> str:
    """Gabungkan literal teks ( ... )Tj dari satu stream halaman."""
    potongan = re.findall(rb"\((?:\\.|[^()\\])*\)", isi)
    return " ".join(p[1:-1].decode("latin-1") for p in potongan)


def main() -> None:
    laporan = json.loads((ROOT / "data" / "report_data.json").read_text(encoding="utf-8"))
    pdf, nama = build_pdf(laporan, stream=io.BytesIO())
    (ROOT / "_cek.pdf").write_bytes(pdf)
    print(f"{nama}  —  {len(pdf):,} byte")

    for i, isi in enumerate(stream_isi(pdf), start=1):
        if b"BT" not in isi:
            continue
        print(f"\n===== HALAMAN {i} =====")
        print(teks_halaman(isi))


if __name__ == "__main__":
    main()

"""
Daily Market Update — laporan pasar harian dalam format PDF.

Tampilan disusun sebagai laporan korporat: kop dengan bar aksen, kartu angka
kunci, tabel tanpa garis vertikal, grafik berbingkai, dan footer bernomor
halaman. Seluruh angka diambil dari objek `report` yang sama dengan dashboard,
sehingga PDF yang diunduh selalu cocok dengan yang terlihat di layar.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import datetime
from functools import partial
from typing import Dict, Any, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, Flowable, KeepTogether, CondPageBreak, HRFlowable
)

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"
CHART_DIR = Path(__file__).resolve().parent.parent / "charts"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REPORT_DIR.mkdir(exist_ok=True)

# ── Token desain: satu sumber warna & ukuran agar semua halaman seragam ──
# Nilainya sengaja sama dengan design token CSS di dashboard (app.py) supaya
# PDF dan tampilan layar terasa satu produk.
INK = colors.HexColor("#0f172a")        # judul & header tabel
BODY = colors.HexColor("#334155")       # teks isi
MUTED = colors.HexColor("#64748b")      # keterangan
FAINT = colors.HexColor("#94a3b8")      # catatan kecil
ACCENT = colors.HexColor("#0f766e")     # warna merek
ACCENT_DARK = colors.HexColor("#0b5c55")
ACCENT_SOFT = colors.HexColor("#e8f5f3")
SURFACE = colors.HexColor("#ffffff")
ZEBRA = colors.HexColor("#f8fafc")      # selang-seling baris tabel
BORDER = colors.HexColor("#e3e8ee")
GOOD = colors.HexColor("#15803d")       # naik
BAD = colors.HexColor("#b91c1c")        # turun
AMBER = colors.HexColor("#b45309")      # perlu diwaspadai

# Geometri halaman (A4 = 210 x 297 mm)
MARGIN_X = 14 * mm
MARGIN_TOP = 17 * mm
MARGIN_BOTTOM = 16 * mm
LEBAR = A4[0] - 2 * MARGIN_X            # lebar area konten
JEDA_KARTU = 2.6 * mm
LEBAR_KARTU = (LEBAR - 4 * JEDA_KARTU) / 5


def _fmt_num(v, decimals=2, prefix="", suffix=""):
    if v is None:
        return "–"
    try:
        return f"{prefix}{float(v):,.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct(v, decimals=2):
    if v is None:
        return "–"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.{decimals}f}%"


def _fmt_bp(v):
    if v is None:
        return "–"
    sign = "+" if v > 0 else ""
    return f"{sign}{v:.1f} bp"


def _jam_snapshot(report: Dict[str, Any]) -> str:
    """Waktu pengambilan data laporan, ditulis pendek di kop PDF."""
    snap = str(report.get("source_snapshot") or report.get("generated_at") or "")
    try:
        return datetime.fromisoformat(snap).strftime("%d %B %Y %H:%M")
    except Exception:
        return "–"


def _arah(nilai, kata_naik: str, kata_turun: str) -> str:
    """Pilih kata arah: naik / turun / hampir tidak berubah."""
    if nilai is None:
        return ""
    if nilai > 0.02:
        return kata_naik
    if nilai < -0.02:
        return kata_turun
    return "hampir tidak berubah"


def _cari(data: Dict[str, Any], *kata: str, exclude: tuple = ()) -> Dict[str, Any]:
    """Ambil baris data berdasarkan kata kunci nama instrument (toleran)."""
    for key, val in (data or {}).items():
        low = str(key).lower()
        if all(k.lower() in low for k in kata) and not any(e.lower() in low for e in exclude):
            return val if isinstance(val, dict) else {}
    return {}


def _teks_bersih(teks) -> str:
    """
    Rapikan teks sumber data sebelum dicetak.

    Nama pustaka internal tidak boleh bocor ke dokumen yang dibaca pembaca
    (mis. "yfinance" ditulis sebagai nama yang dikenal pembaca pasar).
    """
    if not teks:
        return ""
    return re.sub(r"\s+", " ", str(teks)).strip().replace("yfinance", "Yahoo Finance")


def _warna_arah(nilai, *, naik_baik: bool = True) -> Optional[colors.Color]:
    """
    Warna untuk sebuah angka perubahan, atau None bila dianggap datar.

    naik_baik=True  -> naik = hijau, turun = merah (saham, yield, spread)
    naik_baik=False -> naik = merah, turun = hijau (kurs: rupiah melemah = merah)
    """
    if nilai is None:
        return None
    if nilai > 0.02:
        return GOOD if naik_baik else BAD
    if nilai < -0.02:
        return BAD if naik_baik else GOOD
    return None


class PanahNaikTurun(Flowable):
    """
    Panah segitiga kecil penanda arah perubahan.

    Digambar sebagai vektor, bukan karakter Unicode, karena font dasar
    ReportLab (Helvetica) tidak menyediakan glyph segitiga — memakai teks
    akan tampil kotak kosong di sebagian pembaca PDF.
    """

    def __init__(self, arah: int, warna: colors.Color, lebar: float = 3.1 * mm,
                 tinggi: float = 3.4 * mm):
        super().__init__()
        self.arah = arah                  # 1 naik, -1 turun, 0 datar
        self.warna = warna
        self.lebar = lebar
        self.tinggi = tinggi

    def wrap(self, availWidth, availHeight):
        return self.lebar, self.tinggi

    def draw(self):
        c = self.canv
        c.setFillColor(self.warna)
        c.setStrokeColor(self.warna)
        c.setLineWidth(0)
        if self.arah == 0:                 # garis datar
            c.rect(0, self.tinggi * 0.42, self.lebar, self.tinggi * 0.20,
                   stroke=0, fill=1)
            return
        if self.arah > 0:                  # segitiga menunjuk ke atas
            p = c.beginPath()
            p.moveTo(0, 0)
            p.lineTo(self.lebar, 0)
            p.lineTo(self.lebar / 2, self.tinggi)
        else:                              # segitiga menunjuk ke bawah
            p = c.beginPath()
            p.moveTo(0, self.tinggi)
            p.lineTo(self.lebar, self.tinggi)
            p.lineTo(self.lebar / 2, 0)
        p.close()
        c.drawPath(p, stroke=0, fill=1)


def _arah_panah(nilai) -> int:
    """Ubah angka perubahan menjadi arah panah: 1 naik, -1 turun, 0 datar."""
    if nilai is None:
        return 0
    if nilai > 0.02:
        return 1
    if nilai < -0.02:
        return -1
    return 0


def _gambar_tertentu(path: Path, lebar: float, tinggi_maks: float) -> Optional[Image]:
    """
    Muat gambar dengan rasio aspek ASLI (tidak diregangkan) dan muat ke dalam
    kotak (lebar x tinggi_maks).

    ReportLab memaksa lebar & tinggi yang diberikan, jadi gambar bisa ikut
    gepeng. Di sini ukuran diturunkan dari ukuran berkas PNG itu sendiri.
    """
    try:
        iw, ih = ImageReader(str(path)).getSize()
    except Exception:
        return None
    if not iw or not ih:
        return None
    skala = min(lebar / iw, tinggi_maks / ih)
    img = Image(str(path))
    img.drawWidth = iw * skala
    img.drawHeight = ih * skala
    img.hAlign = "CENTER"
    return img


class KanvasLaporan(pdfcanvas.Canvas):
    """
    Canvas yang menggambar kerangka halaman: bar aksen atas, kepala halaman,
    footer, dan nomor halaman "Halaman X dari Y".

    Jumlah halaman baru diketahui setelah seluruh dokumen selesai, jadi tiap
    halaman disimpan dulu (dict state) lalu digambar ulang di save() — pola
    standar ReportLab untuk mencetak nomor halaman beserta totalnya.
    """

    def __init__(self, *args, **kwargs):
        self._judul = kwargs.pop("judul", "Daily Market Update")
        self._sub_judul = kwargs.pop("sub_judul", "")
        self._sumber = kwargs.pop("sumber", "")
        super().__init__(*args, **kwargs)
        self._halaman_tersimpan: list[dict] = []

    def showPage(self):
        self._halaman_tersimpan.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._halaman_tersimpan)
        for nomor, state in enumerate(self._halaman_tersimpan, start=1):
            self.__dict__.update(state)
            self._gambar_kerangka(nomor, total)
            super().showPage()
        super().save()

    def _gambar_kerangka(self, nomor: int, total: int) -> None:
        c = self
        lebar, tinggi = A4

        # Bar aksen tipis di tepi atas — penanda merek di setiap halaman.
        c.setFillColor(ACCENT)
        c.rect(0, tinggi - 3.2 * mm, lebar, 3.2 * mm, stroke=0, fill=1)

        # Kepala halaman berjalan (halaman 2+), supaya halaman yang terpisah
        # dari cover tetap jelas milik laporan ini.
        if nomor > 1:
            c.setFont("Helvetica-Bold", 7.4)
            c.setFillColor(ACCENT)
            c.drawString(MARGIN_X, tinggi - MARGIN_TOP + 1.5 * mm, self._judul.upper())
            c.setFont("Helvetica", 7.4)
            c.setFillColor(FAINT)
            c.drawRightString(lebar - MARGIN_X, tinggi - MARGIN_TOP + 1.5 * mm,
                              self._sub_judul)
            c.setStrokeColor(BORDER)
            c.setLineWidth(0.5)
            c.line(MARGIN_X, tinggi - MARGIN_TOP - 0.8 * mm,
                   lebar - MARGIN_X, tinggi - MARGIN_TOP - 0.8 * mm)

        # Footer: garis pemisah + sumber kiri, nomor halaman kanan.
        garis_y = MARGIN_BOTTOM - 5.5 * mm
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.5)
        c.line(MARGIN_X, garis_y, lebar - MARGIN_X, garis_y)

        c.setFont("Helvetica", 6.8)
        c.setFillColor(FAINT)
        if self._sumber:
            c.drawString(MARGIN_X, garis_y - 4.2 * mm, self._sumber)

        c.setFont("Helvetica-Bold", 7.2)
        c.setFillColor(MUTED)
        c.drawRightString(lebar - MARGIN_X, garis_y - 4.2 * mm,
                          f"Halaman {nomor} dari {total}")


def summary_text(report: Dict[str, Any]) -> str:
    """
    Ringkasan 3–5 kalimat dalam bahasa sederhana, memakai angka yang sama
    dengan tabel di bawahnya (tanpa menghilangkan makna aslinya).
    """
    fx = report.get("fx") or {}
    usd = _cari(fx, "usd/idr")
    ihsg = _cari(report.get("indices") or {}, "ihsg")
    yld = report.get("yields") or {}
    sbn10 = _cari(yld, "sbn", "10", exclude=("sbsn", "fr0"))
    ust10 = _cari(yld, "treasury", "10")
    spread = report.get("spread_sbn10_ust10_bp")
    bi_rate = (report.get("bi") or {}).get("BI Rate")

    kalimat = []
    if usd.get("today") is not None:
        chg = usd.get("change_pct")
        if chg is None:
            kalimat.append(f"Kurs Rupiah berada di {_fmt_num(usd['today'], 0, prefix='Rp')} per dolar AS.")
        else:
            arah = "menguat" if chg < 0 else ("melemah" if chg > 0 else "nyaris tidak berubah")
            kalimat.append(
                f"Rupiah ditutup di {_fmt_num(usd['today'], 0, prefix='Rp')} per dolar AS, "
                f"{arah} {abs(chg):.2f}% dibanding penutupan sebelumnya."
            )
    if ihsg.get("today") is not None:
        chg = ihsg.get("change_pct")
        kalimat.append(
            f"IHSG {_arah(chg, 'naik', 'turun')} {abs(chg):.2f}% ke {_fmt_num(ihsg['today'], 2)}."
            if chg is not None else f"IHSG berada di {_fmt_num(ihsg['today'], 2)}."
        )
    if sbn10.get("today") is not None:
        bp = sbn10.get("change_bp")
        ekor = f" (data {sbn10.get('as_of_label')})" if sbn10.get("as_of_label") else ""
        kalimat.append(
            f"Imbal hasil SBN 10 tahun {_arah(bp, 'naik', 'turun')} {abs(bp):.1f} bp menjadi "
            f"{_fmt_num(sbn10['today'], 2)}%{ekor}."
            if bp is not None else f"Imbal hasil SBN 10 tahun {_fmt_num(sbn10['today'], 2)}%{ekor}."
        )
    if ust10.get("today") is not None and ust10.get("change_bp") is not None:
        kalimat.append(
            f"Imbal hasil surat utang AS (UST) 10 tahun {_arah(ust10['change_bp'], 'naik', 'turun')} "
            f"{abs(ust10['change_bp']):.1f} bp menjadi {_fmt_num(ust10['today'], 2)}%."
        )
    if spread is not None:
        if spread < 250:
            kata = "relatif sempit, artinya risiko Indonesia dinilai lebih rendah"
        elif spread <= 450:
            kata = "tergolong sedang"
        else:
            kata = "relatif lebar, artinya investor meminta kompensasi risiko lebih besar"
        kalimat.append(f"Selisih imbal hasil RI–AS sebesar {_fmt_num(spread, 0)} bp ({kata}).")
    if bi_rate is not None:
        kalimat.append(
            f"BI Rate berada di {_fmt_num(bi_rate, 2)}% — acuan bunga kredit, KPR, dan deposito perbankan."
        )
    kalimat.append(
        "Makna kolom: Today = nilai terakhir, Prev = penutupan sebelumnya, "
        "Change % = perubahan harian, bp = poin basis (1 bp = 0,01%)."
    )
    return " ".join(kalimat)


def _gaya_dokumen() -> Dict[str, ParagraphStyle]:
    """
    Satu set gaya teks untuk seluruh PDF.

    Font dasar ReportLab (Helvetica) sengaja dipakai agar teks tetap bisa
    dicari & disalin pembaca, dan agar ukuran berkas tetap kecil.
    """
    styles = getSampleStyleSheet()
    baru = {
        "Judul": ParagraphStyle("Judul", fontName="Helvetica-Bold", fontSize=19,
                                leading=22, textColor=INK, spaceAfter=1.6 * mm),
        "SubJudul": ParagraphStyle("SubJudul", fontName="Helvetica", fontSize=9,
                                   leading=12, textColor=MUTED),
        "Seksi": ParagraphStyle("Seksi", fontName="Helvetica-Bold", fontSize=11.5,
                                leading=14, textColor=INK),
        "KartuLabel": ParagraphStyle("KartuLabel", fontName="Helvetica-Bold", fontSize=6.6,
                                     leading=8.4, textColor=ACCENT),
        "KartuNilai": ParagraphStyle("KartuNilai", fontName="Helvetica-Bold", fontSize=12.5,
                                     leading=14.5, textColor=INK),
        "KartuSub": ParagraphStyle("KartuSub", fontName="Helvetica", fontSize=6.6,
                                   leading=8.4, textColor=MUTED),
        "Th": ParagraphStyle("Th", fontName="Helvetica-Bold", fontSize=7.4,
                             leading=9.2, textColor=colors.white),
        "Td": ParagraphStyle("Td", fontName="Helvetica", fontSize=8,
                             leading=10.4, textColor=BODY),
        "TdAngka": ParagraphStyle("TdAngka", fontName="Helvetica", fontSize=8,
                                  leading=10.4, textColor=BODY, alignment=TA_RIGHT),
        "TdArah": ParagraphStyle("TdArah", fontName="Helvetica-Bold", fontSize=8,
                                 leading=10.4, textColor=BODY, alignment=TA_RIGHT),
        "Ringkasan": ParagraphStyle("Ringkasan", fontName="Helvetica", fontSize=8.7,
                                    leading=12.6, textColor=INK, alignment=TA_JUSTIFY),
        "Catatan": ParagraphStyle("Catatan", fontName="Helvetica-Oblique", fontSize=7.2,
                                  leading=9.6, textColor=MUTED),
        "Sumber": ParagraphStyle("Sumber", fontName="Helvetica", fontSize=6.9,
                                 leading=9, textColor=FAINT),
    }
    for style in baru.values():
        styles.add(style)
    return styles


def _kepala_seksi(gaya, nomor: str, judul: str, sub: str = "") -> Table:
    """Kepala seksi bernomor: kotak nomor beraksen + judul + keterangan."""
    lencana = Table([[Paragraph(nomor, ParagraphStyle(
        "Lencana", fontName="Helvetica-Bold", fontSize=9.5, textColor=colors.white,
        alignment=TA_CENTER, leading=12))]], colWidths=[7.4 * mm], rowHeights=[7.4 * mm])
    lencana.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    isi = Paragraph(judul, gaya["Seksi"])
    if sub:
        isi = Paragraph(f"{judul}<br/><font size=7.4 color='#64748b'>{sub}</font>",
                        gaya["Seksi"])
    t = Table([[lencana, isi]], colWidths=[11 * mm, LEBAR - 11 * mm])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LINEBELOW", (0, 0), (-1, -1), 0.8, colors.HexColor("#d8e2e0")),
    ]))
    return t


def _kartu_angka(gaya, label: str, nilai: str, delta: str = "", arah: int = 0,
                 warna: Optional[colors.Color] = None,
                 lebar: Optional[float] = None,
                 ukuran_nilai: Optional[float] = None) -> Table:
    """
    Kartu angka kunci: label kecil, nilai besar, dan perubahan berarah.

    `arah` 1 = naik, -1 = turun, 0 = tanpa panah.
    `ukuran_nilai` dipakai untuk nilai berupa teks panjang (mis. status spread)
    supaya tetap muat di dalam kartu.
    """
    lebar = lebar or LEBAR_KARTU
    gaya_nilai = gaya["KartuNilai"]
    if ukuran_nilai:
        gaya_nilai = ParagraphStyle("NilaiKecil", parent=gaya_nilai,
                                    fontSize=ukuran_nilai, leading=ukuran_nilai * 1.2)
    baris: list = [
        [Paragraph(label.upper(), gaya["KartuLabel"])],
        [Paragraph(nilai, gaya_nilai)],
    ]
    if delta:
        isi_delta = Table(
            [[PanahNaikTurun(arah, warna or MUTED, lebar=2.8 * mm, tinggi=3.0 * mm),
              Paragraph(delta, ParagraphStyle(
                  "DeltaKartu", fontName="Helvetica-Bold", fontSize=6.8,
                  leading=8.6, textColor=warna or MUTED))]],
            colWidths=[3.6 * mm, None])
        isi_delta.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        baris.append([isi_delta])

    t = Table(baris, colWidths=[lebar])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("LINEABOVE", (0, 0), (-1, 0), 2.4, warna or ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 4.2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4.2),
        ("TOPPADDING", (0, 0), (-1, 0), 4.6),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 4.6),
        ("TOPPADDING", (0, 1), (-1, -1), 1.4),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 1.0),
    ]))
    return t


def _tabel_pasar(gaya, judul_kolom: list, baris: list, lebar_kolom: list,
                 baris_kunci: tuple = ()) -> Table:
    """
    Tabel data pasar: header gelap, selang-seling baris, tanpa garis vertikal.

    `baris_kunci` = indeks baris yang ditonjolkan (mis. USD/IDR, SBN 10Y)
    supaya pembaca cepat menemukan angka yang paling sering dicari.
    """
    data = [[Paragraph(h, gaya["Th"]) for h in judul_kolom]]
    for sel in baris:
        data.append([s if hasattr(s, "wrap") else Paragraph(str(s), gaya["Td"])
                     for s in sel])
    t = Table(data, colWidths=lebar_kolom, repeatRows=1, hAlign="LEFT")
    gaya_tabel = [
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, 0), 5.4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5.4),
        ("TOPPADDING", (0, 1), (-1, -1), 4.2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 4.2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE, colors.HexColor("#f7f9fa")]),
        # Hanya garis horizontal tipis — grid penuh membuat tabel terasa berat.
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, ACCENT),
    ]
    for i in baris_kunci:
        gaya_tabel.append(("BACKGROUND", (0, i + 1), (-1, i + 1), ACCENT_SOFT))
    t.setStyle(TableStyle(gaya_tabel))
    return t


def build_pdf(
    report: Dict[str, Any] = None,
    chart_path: Optional[Path] = None,
    out_path: Optional[Path] = None,
    stream=None,
    fx_chart_path: Optional[Path] = None,
) -> "Path | tuple[bytes, str]":
    """
    Susun PDF Daily Market Update.

    Grafik TIDAK dibuat di sini. Modul ini tidak mengimpor modul lain yang
    bisa memuat UI (mis. app.py) — pemanggil yang menggambar grafiknya lalu
    meneruskan path-nya, supaya isi PDF selalu sama dengan yang tampil.

    Args:
        report      : data laporan. Kalau None, dibaca dari data/report_data.json.
        chart_path  : PNG grafik selisih imbal hasil. Kalau None, pakai
                      charts/rate_differential.png bila ada; bila tidak ada,
                      bagian grafik dilewati (tidak pernah diisi angka contoh).
        out_path    : tujuan tulis di disk. Diabaikan bila `stream` diisi.
        stream      : bila diisi (mis. io.BytesIO()), PDF tidak ditulis ke disk
                      dan byte-nya dikembalikan sebagai (bytes, nama_file).
        fx_chart_path: PNG grafik pergerakan kurs (opsional). Bila None atau
                      berkasnya tidak ada, seksi grafik kurs dilewati.

    Returns:
        Path bila ditulis ke disk, atau (bytes, nama_file) bila `stream` dipakai.
    """
    if report is None:
        with open(DATA_DIR / "report_data.json", encoding="utf-8") as f:
            report = json.load(f)

    date_str = report.get("report_date", datetime.now().strftime("%d %B %Y"))
    # Nama file mengikuti TANGGAL LAPORAN, bukan tanggal saat PDF dibuat.
    hari = str(report.get("report_date_iso") or datetime.now().strftime("%Y-%m-%d"))
    nama_file = f"Daily_Market_Update_{hari.replace('-', '')}.pdf"
    buf = stream
    if stream is None:
        out_path = Path(out_path) if out_path else (REPORT_DIR / nama_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        buf = str(out_path)          # ReportLab menulis langsung ke berkas

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN_X,
        rightMargin=MARGIN_X,
        topMargin=MARGIN_TOP,
        bottomMargin=MARGIN_BOTTOM,
        title="Market Today — Daily Market Update",
        author="Daily Market Report Automation",
        subject=f"Ringkasan pasar harian per {date_str}",
        creator="Daily Market Report Automation",
    )
    gaya = _gaya_dokumen()
    story: list = []

    # ══ KOP ═══════════════════════════════════════════════════════════════
    kop = Table(
        [[Paragraph("Market Today", gaya["Judul"]),
          Paragraph(f"<b>{date_str}</b><br/>"
                    f"<font size=7.4 color='#64748b'>Snapshot {_jam_snapshot(report)}</font>",
                    ParagraphStyle("Tanggal", fontName="Helvetica", fontSize=9.5,
                                   leading=12.5, textColor=INK, alignment=TA_RIGHT))]],
        colWidths=[LEBAR * 0.58, LEBAR * 0.42])
    kop.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LINEBELOW", (0, 0), (-1, -1), 1.6, ACCENT),
    ]))
    story += [
        kop,
        Spacer(1, 3 * mm),
        Paragraph("Ringkasan harian pergerakan nilai tukar, pasar saham, obligasi, "
                  "dan kebijakan moneter.", gaya["SubJudul"]),
        Spacer(1, 5 * mm),
    ]

    # ══ KARTU ANGKA KUNCI ════════════════════════════════════════════════
    fx = report.get("fx") or {}
    idx = report.get("indices") or {}
    yld = report.get("yields") or {}
    usd = _cari(fx, "usd/idr")
    ihsg = _cari(idx, "ihsg")
    sbn10 = _cari(yld, "sbn", "10", exclude=("sbsn", "fr0"))
    ust10 = _cari(yld, "treasury", "10")
    spread = report.get("spread_sbn10_ust10_bp")

    kartu = [
        # Kurs dibaca dari sisi rupiah: angka positif = rupiah melemah (merah).
        _kartu_angka(gaya, "USD / IDR", _fmt_num(usd.get("today"), 3),
                     _fmt_pct(usd.get("change_pct")), _arah_panah(usd.get("change_pct")),
                     _warna_arah(usd.get("change_pct"), naik_baik=False)),
        _kartu_angka(gaya, "IHSG", _fmt_num(ihsg.get("today"), 2),
                     _fmt_pct(ihsg.get("change_pct")), _arah_panah(ihsg.get("change_pct")),
                     _warna_arah(ihsg.get("change_pct"))),
        _kartu_angka(gaya, "SBN 10Y", _fmt_num(sbn10.get("today"), 2, suffix="%"),
                     _fmt_bp(sbn10.get("change_bp")), _arah_panah(sbn10.get("change_bp")),
                     _warna_arah(sbn10.get("change_bp"))),
        _kartu_angka(gaya, "UST 10Y", _fmt_num(ust10.get("today"), 2, suffix="%"),
                     _fmt_bp(ust10.get("change_bp")), _arah_panah(ust10.get("change_bp")),
                     _warna_arah(ust10.get("change_bp"))),
        _kartu_angka(gaya, "Spread SBN–UST", _fmt_num(spread, 0, suffix=" bp"),
                     "", 0, ACCENT),
    ]
    baris_kartu = Table([kartu], colWidths=[LEBAR_KARTU] * 5, hAlign="LEFT")
    baris_kartu.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), JEDA_KARTU),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [
        baris_kartu,
        Spacer(1, 2.2 * mm),
        Paragraph("Warna mengikuti dampak ke rupiah: hijau = menguat, "
                  "merah = melemah. 1 bp = 0,01%.", gaya["Catatan"]),
        Spacer(1, 5 * mm),
    ]

    # ══ RINGKASAN EKSEKUTIF ══════════════════════════════════════════════
    ringkas = Table(
        [["", [Paragraph("Ringkasan Singkat", ParagraphStyle(
            "JudulKotak", fontName="Helvetica-Bold", fontSize=9.2, leading=12,
            textColor=ACCENT_DARK, spaceAfter=1.4 * mm)),
            Paragraph(summary_text(report), gaya["Ringkasan"])]]],
        colWidths=[2.4 * mm, LEBAR - 2.4 * mm])
    ringkas.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), ACCENT),
        ("BACKGROUND", (1, 0), (1, 0), ACCENT_SOFT),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (0, 0), 0),
        ("RIGHTPADDING", (0, 0), (0, 0), 0),
        ("TOPPADDING", (0, 0), (0, 0), 0),
        ("BOTTOMPADDING", (0, 0), (0, 0), 0),
        ("LEFTPADDING", (1, 0), (1, 0), 7),
        ("RIGHTPADDING", (1, 0), (1, 0), 7),
        ("TOPPADDING", (1, 0), (1, 0), 6),
        ("BOTTOMPADDING", (1, 0), (1, 0), 6.5),
    ]))
    story += [
        ringkas,
        Spacer(1, 1.8 * mm),
        Paragraph("Cara membaca: tanda + berarti naik, tanda - berarti turun. "
                  "Angka obligasi (PHEI) dapat tertinggal satu hari dari kurs/saham "
                  "karena waktu publikasi.", gaya["Catatan"]),
        Spacer(1, 5 * mm),
    ]

    # ===== Exchange Rate =====
    story += [Spacer(1, 1 * mm),
              _kepala_seksi(gaya, "1", "Exchange Rate", "Nilai tukar terhadap Rupiah"),
              Spacer(1, 2.6 * mm)]
    fx_baris, fx_kunci = [], []
    for i, (name, v) in enumerate(fx.items()):
        desimal = 3 if "IDR" in name else 2
        chg = v.get("change_pct")
        # Kolom perubahan diberi warna + panah; angka positif = rupiah melemah.
        sel_arah = Paragraph(
            f'<font color="#{(_warna_arah(chg, naik_baik=False) or MUTED).hexval()[2:]}">'
            f"{_fmt_pct(chg)}</font>", gaya["TdArah"])
        fx_baris.append([
            Paragraph(name, ParagraphStyle("Nm", parent=gaya["Td"],
                                          fontName="Helvetica-Bold", textColor=INK)),
            Paragraph(_fmt_num(v.get("today"), desimal), gaya["TdAngka"]),
            Paragraph(_fmt_num(v.get("prev"), desimal), gaya["TdAngka"]),
            sel_arah,
        ])
        if "USD" in name.upper():
            fx_kunci.append(i)
    story += [
        _tabel_pasar(gaya, ["Pasangan", "Today", "Prev", "Change %"],
                     fx_baris, [LEBAR - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm],
                     baris_kunci=tuple(fx_kunci)),
        Spacer(1, 1.8 * mm),
        Paragraph("Today = nilai terakhir · Prev = penutupan sebelumnya · "
                  "Change % = perubahan harian. Angka positif berarti rupiah melemah.",
                  gaya["Catatan"]),
        Spacer(1, 4.5 * mm),
    ]

    # ===== Financial Market (Indices) =====
    story += [CondPageBreak(60 * mm),
              _kepala_seksi(gaya, "2", "Financial Market", "Indeks saham utama"),
              Spacer(1, 2.6 * mm)]
    idx_baris, idx_kunci = [], []
    for i, (name, v) in enumerate(idx.items()):
        chg = v.get("change_pct")
        idx_baris.append([
            Paragraph(name, ParagraphStyle("Nm", parent=gaya["Td"],
                                           fontName="Helvetica-Bold", textColor=INK)),
            Paragraph(_fmt_num(v.get("today"), 2), gaya["TdAngka"]),
            Paragraph(_fmt_num(v.get("prev"), 2), gaya["TdAngka"]),
            Paragraph(f'<font color="#{(_warna_arah(chg) or MUTED).hexval()[2:]}">'
                      f"{_fmt_pct(chg)}</font>", gaya["TdArah"]),
        ])
        if "IHSG" in name.upper():
            idx_kunci.append(i)
    story += [
        _tabel_pasar(gaya, ["Indeks", "Today", "Prev", "Change %"],
                     idx_baris, [LEBAR - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm],
                     baris_kunci=tuple(idx_kunci)),
        Spacer(1, 4.5 * mm),
    ]
    # ===== Yield =====
    story += [CondPageBreak(60 * mm),
              _kepala_seksi(gaya, "3", "Yield", "Imbal hasil obligasi (perubahan dalam bp)"),
              Spacer(1, 2.6 * mm)]
    yld_baris, yld_kunci = [], []
    for i, (name, v) in enumerate(yld.items()):
        chg = v.get("change_bp")
        sel_nama = name
        if v.get("as_of_label"):
            sel_nama = f'{name}<br/><font size=6.4 color="#94a3b8">{v["as_of_label"]}</font>'
        yld_baris.append([
            Paragraph(sel_nama, ParagraphStyle("Nm", parent=gaya["Td"],
                                               fontName="Helvetica-Bold", textColor=INK)),
            Paragraph(_fmt_num(v.get("today"), 2, suffix="%"), gaya["TdAngka"]),
            Paragraph(_fmt_num(v.get("prev"), 2, suffix="%"), gaya["TdAngka"]),
            Paragraph(f'<font color="#{(_warna_arah(chg) or MUTED).hexval()[2:]}">'
                      f"{_fmt_bp(chg)}</font>", gaya["TdArah"]),
        ])
        if "sbn" in name.lower() and "10" in name and "sbsn" not in name.lower():
            yld_kunci.append(i)
        elif "treasury" in name.lower() and "10" in name:
            yld_kunci.append(i)
    story += [
        _tabel_pasar(gaya, ["Instrumen", "Today", "Prev", "Change"],
                     yld_baris, [LEBAR - 3 * 30 * mm, 30 * mm, 30 * mm, 30 * mm],
                     baris_kunci=tuple(yld_kunci)),
        Spacer(1, 1.8 * mm),
        Paragraph("Imbal hasil obligasi Indonesia (PHEI) terbit sekali per hari, "
                  "jadi bisa tertinggal satu hari dari kurs dan saham.", gaya["Catatan"]),
        Spacer(1, 4.5 * mm),
    ]

    # ===== Kebijakan Moneter (BI) =====
    bi = report.get("bi") or {}
    story += [_kepala_seksi(gaya, "4", "Monetary Policy", "Bank Indonesia"),
              Spacer(1, 2.6 * mm)]
    # Status spread memakai ambang yang sama dengan ringkasan bahasa sederhana,
    # supaya angka dan penjelasannya tidak berbeda arti.
    if spread is None:
        status_spread = "–"
    elif spread < 250:
        status_spread = "Relatif sempit"
    elif spread <= 450:
        status_spread = "Terolong sedang"
    else:
        status_spread = "Relatif lebar"
    kartu_bi = [
        _kartu_angka(gaya, "BI Rate", _fmt_num(bi.get("BI Rate"), 2, suffix="%"),
                     "", 0, ACCENT),
        _kartu_angka(gaya, "INDONIA", _fmt_num(bi.get("INDONIA"), 4, suffix="%"),
                     "", 0, ACCENT),
        _kartu_angka(gaya, "JISDOR", _fmt_num(bi.get("JISDOR"), 0), "", 0, ACCENT),
        # Label & statusnya berupa teks panjang, jadi font-nya dikecilkan
        # supaya tetap satu baris di dalam kartu.
        _kartu_angka(gaya, "Spread SBN10Y–UST10Y", status_spread, "", 0, AMBER,
                     ukuran_nilai=9.6),
    ]
    lebar_bi = (LEBAR - JEDA_KARTU * 3) / 4
    baris_bi = Table([kartu_bi], colWidths=[lebar_bi] * 4, hAlign="LEFT")
    baris_bi.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), JEDA_KARTU),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [
        baris_bi,
        Spacer(1, 2.2 * mm),
        Paragraph("BI Rate = acuan bunga kredit, KPR, dan deposito perbankan. "
                  "INDONIA = average interbank overnight rate. "
                  "JISDOR = kurs transaksi BI antar bank.", gaya["Catatan"]),
        Spacer(1, 4.5 * mm),
    ]
    # ===== Komoditas =====
    kom = report.get("commodities") or {}
    if kom:
        story += [CondPageBreak(55 * mm),
                  _kepala_seksi(gaya, "5", "Commodities", "Harga komoditas internasional"),
                  Spacer(1, 2.6 * mm)]
        kom_baris = []
        for name, v in kom.items():
            chg = v.get("change_pct")
            kom_baris.append([
                Paragraph(name, ParagraphStyle("Nm", parent=gaya["Td"],
                                              fontName="Helvetica-Bold", textColor=INK)),
                Paragraph(_fmt_num(v.get("today"), 2), gaya["TdAngka"]),
                Paragraph(_fmt_num(v.get("prev"), 2), gaya["TdAngka"]),
                Paragraph(f'<font color="#{(_warna_arah(chg) or MUTED).hexval()[2:]}">'
                          f"{_fmt_pct(chg)}</font>", gaya["TdArah"]),
            ])
        story += [
            _tabel_pasar(gaya, ["Komoditas", "Today", "Prev", "Change %"],
                         kom_baris, [LEBAR - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm]),
            Spacer(1, 4.5 * mm),
        ]

    # ===== Grafik: Rate Differential =====
    story += [CondPageBreak(80 * mm),
              _kepala_seksi(gaya, "6", "Rate Differential",
                            "SBN 10Y vs UST 10Y dan selisihnya (spread)"),
              Spacer(1, 3 * mm)]
    chart_file = Path(chart_path) if chart_path else (CHART_DIR / "rate_differential.png")
    gambar = _gambar_tertentu(chart_file, LEBAR - 6 * mm, 74 * mm) if chart_file.exists() \
        else None
    if gambar is not None:
        bingkai = Table([[gambar]], colWidths=[LEBAR])
        bingkai.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        story += [bingkai, Spacer(1, 1.8 * mm)]
    else:
        story += [Paragraph(
            "<i>(Grafik tidak disertakan — jalankan pipeline agar grafik dibuat "
            "dari data terbaru.)</i>", gaya["Catatan"]), Spacer(1, 2 * mm)]
    story += [Paragraph(
        "Sumber grafik: PHEI (SBN) &amp; Yahoo Finance (UST). "
        "1 bp = 0,01%.", gaya["Sumber"]), Spacer(1, 5 * mm)]

    # ===== Grafik: Pergerakan Kurs Terhadap Rupiah =====
    # Grafik kedua opsional. Pemanggil yang menggambarnya (dashboard/CLI) lalu
    # meneruskan path-nya, agar isi PDF sama persis dengan yang tampil di layar.
    fx_chart = Path(fx_chart_path) if fx_chart_path else None
    gambar_fx = (_gambar_tertentu(fx_chart, LEBAR - 6 * mm, 62 * mm)
                 if fx_chart is not None and fx_chart.exists() else None)
    if gambar_fx is not None:
        story += [CondPageBreak(70 * mm),
                  _kepala_seksi(gaya, "7", "Pergerakan Kurs",
                                "Perubahan harian terhadap Rupiah"),
                  Spacer(1, 3 * mm)]
        bingkai_fx = Table([[gambar_fx]], colWidths=[LEBAR])
        bingkai_fx.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
            ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
            ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 3 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3 * mm),
        ]))
        story += [bingkai_fx, Spacer(1, 1.8 * mm)]
        story += [Paragraph(
            "Merah = rupiah melemah, hijau = rupiah menguat. "
            "Sumber: Yahoo Finance.", gaya["Sumber"]), Spacer(1, 4.5 * mm)]

    # ===== Sumber Data & Metode =====
    story += [CondPageBreak(45 * mm),
              _kepala_seksi(gaya, "8", "Sumber Data & Metode"),
              Spacer(1, 2.6 * mm)]
    story += [Paragraph(
        "Metode: perubahan harian dihitung terhadap penutupan hari perdagangan "
        "sebelumnya. Angka obligasi Indonesia berasal dari PHEI yang terbit sekali "
        "per hari sehingga dapat tertinggal satu hari dari kurs dan saham.",
        gaya["Sumber"]), Spacer(1, 3 * mm)]

    # Ringkasan sumber per kelompok instrumen, diambil dari data laporan
    # (bukan teks manual) agar selalu sesuai dengan data yang ditampilkan.
    baris_sumber = []
    for bagian in (report.get("sources") or []):
        utama = _teks_bersih(bagian.get("primary"))
        if not utama:
            continue
        baris_sumber.append([
            Paragraph(_teks_bersih(bagian.get("section")),
                      ParagraphStyle("Nm", parent=gaya["Td"],
                                     fontName="Helvetica-Bold", textColor=INK)),
            Paragraph(utama, gaya["Td"]),
        ])
    if baris_sumber:
        story += [
            _tabel_pasar(gaya, ["Kelompok Instrumen", "Sumber"], baris_sumber,
                         [62 * mm, LEBAR - 62 * mm]),
            Spacer(1, 3 * mm),
        ]

    story += [Paragraph(
        "Laporan ini disusun otomatis dari data snapshot dan hanya untuk "
        "keperyuan umum — bukan nasihat investasi, rekomendasi, atau ajakan "
        "bertransaksi.", gaya["Sumber"])]
    story += [Spacer(1, 3 * mm)]

    kanvas = partial(
        KanvasLaporan,
        judul="Market Today",
        sub_judul=date_str,
        sumber=f"Data per {date_str} · snapshot {_jam_snapshot(report)}",
    )
    doc.build(story, canvasmaker=kanvas)
    if stream is not None:
        return buf.getvalue(), nama_file
    print(f"PDF saved -> {out_path}")   # ASCII: konsol Windows (cp1252) tidak bisa cetak "→"
    return out_path


if __name__ == "__main__":
    build_pdf()




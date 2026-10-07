"""PDF renderers for Daily Market Report.

`build_pdf` creates the standard one-page A4 executive brief. The earlier
full-report layout remains available through `build_detailed_pdf`. Both use
values from the selected report version.
"""

from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from functools import partial
from typing import Dict, Any, Optional
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, Flowable, CondPageBreak, PageBreak
)

from market_report.config import chart_directory, market_data_directory, report_artifact_directory
from market_report.presentation.pdf_charts import (
    GoldPricesChart,
    RateDifferentialChart,
    chart_heading,
)

REPORT_DIR = report_artifact_directory()
CHART_DIR = chart_directory()
DATA_DIR = market_data_directory()
REPORT_DIR.mkdir(parents=True, exist_ok=True)

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
        value = f"{float(v):,.{decimals}f}"
        value = value.replace(",", "\0").replace(".", ",").replace("\0", ".")
        return f"{prefix}{value}{suffix}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct(v, decimals=2):
    if v is None:
        return "–"
    sign = "+" if v > 0 else ""
    angka = _fmt_num(abs(v), decimals)
    return f"{sign}{angka}%" if v >= 0 else f"-{angka}%"


def _fmt_bp(v):
    if v is None:
        return "–"
    sign = "+" if v > 0 else ""
    angka = _fmt_num(abs(v), 1)
    return f"{sign}{angka} bp" if v >= 0 else f"-{angka} bp"


def _jam_snapshot(report: Dict[str, Any]) -> str:
    """Waktu pengambilan data laporan, ditulis pendek di kop PDF."""
    snap = str(report.get("source_snapshot") or report.get("generated_at") or "")
    try:
        waktu = datetime.fromisoformat(snap)
        if waktu.tzinfo is not None:
            waktu = waktu.astimezone(timezone(timedelta(hours=7)))
        return f"{_tanggal_id(waktu)} {waktu:%H:%M} WIB"
    except Exception:
        return "–"


_BULAN_ID = ("Januari", "Februari", "Maret", "April", "Mei", "Juni",
             "Juli", "Agustus", "September", "Oktober", "November", "Desember")


def _tanggal_id(value: date) -> str:
    return f"{value.day} {_BULAN_ID[value.month - 1]} {value.year}"


def _tanggal_laporan(report: Dict[str, Any]) -> str:
    iso = str(report.get("report_date_iso") or "")[:10]
    try:
        return _tanggal_id(date.fromisoformat(iso))
    except ValueError:
        return str(report.get("report_date") or _tanggal_id(date.today()))


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

    naik_baik=True  -> naik = hijau, turun = merah (saham dan komoditas)
    naik_baik=False -> naik = merah, turun = hijau (kurs: rupiah melemah = merah)
    """
    if nilai is None:
        return None
    if nilai > 0.02:
        return GOOD if naik_baik else BAD
    if nilai < -0.02:
        return BAD if naik_baik else GOOD
    return None


def _warna_yield(nilai) -> Optional[colors.Color]:
    """Yield naik menekan harga obligasi; yield turun mendorong harganya."""
    if nilai is None or abs(nilai) <= 0.02:
        return None
    return BAD if nilai > 0 else GOOD


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
        page_text = f"Halaman {nomor} dari {total}" if total > 1 else "Ringkasan 1 halaman"
        c.drawRightString(lebar - MARGIN_X, garis_y - 4.2 * mm, page_text)


def summary_text(report: Dict[str, Any]) -> str:
    """Tiga sorotan ringkas untuk halaman pembuka laporan."""
    fx = report.get("fx") or {}
    usd = _cari(fx, "usd/idr")
    ihsg = _cari(report.get("indices") or {}, "ihsg")
    yld = report.get("yields") or {}
    sbn10 = _cari(yld, "sbn", "10", exclude=("sbsn", "fr0"))
    spread = report.get("spread_sbn10_ust10_bp")

    kalimat = []
    if usd.get("today") is not None:
        chg = usd.get("change_pct")
        if chg is None:
            kalimat.append(f"Kurs Rupiah berada di {_fmt_num(usd['today'], 0, prefix='Rp')} per dolar AS.")
        else:
            arah = "menguat" if chg < 0 else ("melemah" if chg > 0 else "hampir tidak berubah")
            kalimat.append(
                f"Rupiah ditutup di {_fmt_num(usd['today'], 0, prefix='Rp')} per dolar AS, "
                f"{arah} {_fmt_num(abs(chg), 2)}% dari penutupan sebelumnya."
            )
    if ihsg.get("today") is not None:
        chg = ihsg.get("change_pct")
        kalimat.append(
            f"IHSG {_arah(chg, 'naik', 'turun')} {_fmt_num(abs(chg), 2)}% ke {_fmt_num(ihsg['today'], 0)}."
            if chg is not None else f"IHSG berada di {_fmt_num(ihsg['today'], 0)}."
        )
    if sbn10.get("today") is not None:
        bp = sbn10.get("change_bp")
        arah = _arah(bp, "naik", "turun") if bp is not None else ""
        keterangan = f" {arah} {_fmt_num(abs(bp), 1)} bp" if arah else ""
        tanggal_data = f", data {sbn10['as_of_label']}" if sbn10.get("as_of_label") else ""
        kalimat.append(f"Yield SBN 10 tahun {_fmt_num(sbn10['today'], 2)}%{keterangan}{tanggal_data}.")
    if spread is not None and len(kalimat) < 3:
        kalimat.append(f"Spread SBN 10 tahun terhadap UST 10 tahun {_fmt_num(spread, 0)} bp.")
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
        "KartuLabel": ParagraphStyle("KartuLabel", fontName="Helvetica-Bold", fontSize=7.4,
                                     leading=9.2, textColor=ACCENT),
        "KartuNilai": ParagraphStyle("KartuNilai", fontName="Helvetica-Bold", fontSize=14.5,
                                     leading=17, textColor=INK),
        "KartuSub": ParagraphStyle("KartuSub", fontName="Helvetica", fontSize=7.8,
                                   leading=9.6, textColor=MUTED),
        "Th": ParagraphStyle("Th", fontName="Helvetica-Bold", fontSize=8.5,
                             leading=10.2, textColor=colors.white),
        "Td": ParagraphStyle("Td", fontName="Helvetica", fontSize=8.8,
                             leading=11, textColor=BODY),
        "TdAngka": ParagraphStyle("TdAngka", fontName="Helvetica", fontSize=8.8,
                                  leading=11, textColor=BODY, alignment=TA_RIGHT),
        "TdArah": ParagraphStyle("TdArah", fontName="Helvetica-Bold", fontSize=8.8,
                                 leading=11, textColor=BODY, alignment=TA_RIGHT),
        "Ringkasan": ParagraphStyle("Ringkasan", fontName="Helvetica", fontSize=9.2,
                                    leading=13.2, textColor=INK),
        "Catatan": ParagraphStyle("Catatan", fontName="Helvetica", fontSize=8,
                                  leading=10.4, textColor=MUTED),
        "Sumber": ParagraphStyle("Sumber", fontName="Helvetica", fontSize=8,
                                 leading=10.4, textColor=MUTED),
        "BriefHeading": ParagraphStyle("BriefHeading", fontName="Helvetica-Bold", fontSize=10.5,
                                        leading=12.5, textColor=INK),
        "InsightTitle": ParagraphStyle("InsightTitle", fontName="Helvetica-Bold", fontSize=9.2,
                                       leading=11.2, textColor=INK),
        "InsightBody": ParagraphStyle("InsightBody", fontName="Helvetica", fontSize=8.4,
                                      leading=10.5, textColor=BODY),
        "SupportLabel": ParagraphStyle("SupportLabel", fontName="Helvetica-Bold", fontSize=7.1,
                                       leading=8.5, textColor=MUTED),
        "SupportValue": ParagraphStyle("SupportValue", fontName="Helvetica-Bold", fontSize=11.5,
                                       leading=13.2, textColor=INK),
        "SupportChange": ParagraphStyle("SupportChange", fontName="Helvetica-Bold", fontSize=7.3,
                                        leading=8.8, textColor=MUTED),
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
    Kartu angka kunci: label kecil, nilai besar, dan perubahan persentase/bp.

    `arah` tetap diterima untuk kompatibilitas dengan pemanggil lama.
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
        baris.append([Paragraph(delta, ParagraphStyle(
            "DeltaKartu", fontName="Helvetica-Bold", fontSize=7.8,
            leading=9.6, textColor=warna or MUTED))])

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
        ("TOPPADDING", (0, 0), (-1, 0), 4.5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4.5),
        ("TOPPADDING", (0, 1), (-1, -1), 3.2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3.2),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [SURFACE, colors.HexColor("#f7f9fa")]),
        # Hanya garis horizontal tipis — grid penuh membuat tabel terasa berat.
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, BORDER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.9, ACCENT),
    ]
    for i in baris_kunci:
        gaya_tabel.append(("BACKGROUND", (0, i + 1), (-1, i + 1), ACCENT_SOFT))
    t.setStyle(TableStyle(gaya_tabel))
    return t


def build_detailed_pdf(
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
        report      : data laporan. Kalau None, dibaca dari runtime/data/report_data.json.
        chart_path  : PNG grafik selisih imbal hasil. Kalau None, pakai
                      runtime/charts/rate_differential.png bila ada; bila tidak ada,
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

    date_str = _tanggal_laporan(report)
    # Nama file mengikuti TANGGAL LAPORAN, bukan tanggal saat PDF dibuat.
    hari = str(report.get("report_date_iso") or datetime.now().strftime("%d-%m-%Y"))
    nama_file = f"Market Update {hari.replace('-', '')}.pdf"
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
        title="Market Today - Ringkasan Pasar Harian",
        author="Market Today",
        subject=f"Ringkasan pasar harian per {date_str}",
        creator="Daily Market Report Automation",
    )
    gaya = _gaya_dokumen()
    story: list = []

    # ══ KOP ═══════════════════════════════════════════════════════════════
    kop = Table(
        [[Paragraph("Market Today", gaya["Judul"]),
          Paragraph(f"<b>{date_str}</b><br/>"
                    f"<font size=8 color='#64748b'>Diperbarui {_jam_snapshot(report)}</font>",
                    ParagraphStyle("Tanggal", fontName="Helvetica", fontSize=9.5,
                                   leading=13.5, textColor=INK, alignment=TA_RIGHT))]],
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
        Paragraph("Pasar Indonesia dan global · ringkasan, tren, dan data utama",
                  gaya["SubJudul"]),
        Spacer(1, 3.5 * mm),
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
        _kartu_angka(gaya, "USD / IDR", _fmt_num(usd.get("today"), 0),
                     _fmt_pct(usd.get("change_pct")), _arah_panah(usd.get("change_pct")),
                     _warna_arah(usd.get("change_pct"), naik_baik=False)),
        _kartu_angka(gaya, "IHSG", _fmt_num(ihsg.get("today"), 0),
                     _fmt_pct(ihsg.get("change_pct")), _arah_panah(ihsg.get("change_pct")),
                     _warna_arah(ihsg.get("change_pct"))),
        _kartu_angka(gaya, "SBN 10Y", _fmt_num(sbn10.get("today"), 2, suffix="%"),
                     _fmt_bp(sbn10.get("change_bp")), _arah_panah(sbn10.get("change_bp")),
                     _warna_yield(sbn10.get("change_bp"))),
        _kartu_angka(gaya, "UST 10Y", _fmt_num(ust10.get("today"), 2, suffix="%"),
                     _fmt_bp(ust10.get("change_bp")), _arah_panah(ust10.get("change_bp")),
                     _warna_yield(ust10.get("change_bp"))),
        _kartu_angka(gaya, "Spread SBN vs UST", _fmt_num(spread, 0, suffix=" bp"),
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
        Paragraph("Rupiah melemah = merah · saham turun = merah · yield naik = merah "
                  "karena harga obligasi bergerak berlawanan.", gaya["Catatan"]),
        Spacer(1, 3 * mm),
    ]

    # ══ RINGKASAN EKSEKUTIF ══════════════════════════════════════════════
    ringkas = Table(
        [["", [Paragraph("Sorotan pasar", ParagraphStyle(
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
        Paragraph("Angka obligasi PHEI dapat memakai tanggal observasi lebih awal "
                  "daripada data kurs dan saham.", gaya["Catatan"]),
        Spacer(1, 3 * mm),
    ]

    # ===== Grafik: Rate Differential =====
    story += [CondPageBreak(80 * mm),
              _kepala_seksi(gaya, "1", "Imbal Hasil dan Spread",
                            "Perbandingan obligasi pemerintah Indonesia dan AS"),
              Spacer(1, 3 * mm)]
    chart_file = Path(chart_path) if chart_path else (CHART_DIR / "rate_differential.png")
    gambar = _gambar_tertentu(chart_file, LEBAR - 6 * mm, 68 * mm) if chart_file.exists() \
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
        "Sumber: PHEI dan Yahoo Finance. Satu bp = 0,01 poin persentase.",
        gaya["Sumber"]), Spacer(1, 2.5 * mm)]

    # ===== Grafik: Pergerakan Kurs Terhadap Rupiah =====
    # Grafik kedua opsional. Pemanggil yang menggambarnya (dashboard/CLI) lalu
    # meneruskan path-nya, agar isi PDF sama persis dengan yang tampil di layar.
    fx_chart = Path(fx_chart_path) if fx_chart_path else None
    gambar_fx = (_gambar_tertentu(fx_chart, LEBAR - 6 * mm, 54 * mm)
                 if fx_chart is not None and fx_chart.exists() else None)
    if gambar_fx is not None:
        story += [CondPageBreak(70 * mm),
                  _kepala_seksi(gaya, "2", "Pergerakan Kurs",
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
            "Merah menandakan Rupiah melemah; hijau menandakan Rupiah menguat. "
            "Sumber: Yahoo Finance.", gaya["Sumber"]), Spacer(1, 4.5 * mm)]

    story.append(PageBreak())

    # ===== Exchange Rate =====
    story += [Spacer(1, 1 * mm),
              _kepala_seksi(gaya, "3", "Nilai Tukar", "Kurs terhadap Rupiah"),
              Spacer(1, 2.6 * mm)]
    fx_baris, fx_kunci = [], []
    for i, (name, v) in enumerate(fx.items()):
        desimal = 0
        chg = v.get("change_pct")
        # Pasangan IDR bergerak berlawanan dengan nilai Rupiah; DXY adalah indeks dolar.
        warna_perubahan = (_warna_arah(chg) if name.upper().startswith("DXY")
                           else _warna_arah(chg, naik_baik=False))
        sel_arah = Paragraph(
            f'<font color="#{(warna_perubahan or MUTED).hexval()[2:]}">'
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
        _tabel_pasar(gaya, ["Pasangan", "Terakhir", "Sebelumnya", "Perubahan"],
                     fx_baris, [LEBAR - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm],
                     baris_kunci=tuple(fx_kunci)),
        Spacer(1, 1.8 * mm),
        Paragraph("Perubahan positif pada pasangan kurs berarti Rupiah melemah. "
                  "DXY mengukur nilai dolar AS terhadap sekeranjang mata uang.",
                  gaya["Catatan"]),
        Spacer(1, 4.5 * mm),
    ]

    # ===== Financial Market (Indices) =====
    story += [CondPageBreak(60 * mm),
              _kepala_seksi(gaya, "4", "Pasar Saham", "Indeks utama"),
              Spacer(1, 2.6 * mm)]
    idx_baris, idx_kunci = [], []
    for i, (name, v) in enumerate(idx.items()):
        chg = v.get("change_pct")
        idx_baris.append([
            Paragraph(name, ParagraphStyle("Nm", parent=gaya["Td"],
                                           fontName="Helvetica-Bold", textColor=INK)),
            Paragraph(_fmt_num(v.get("today"), 0), gaya["TdAngka"]),
            Paragraph(_fmt_num(v.get("prev"), 0), gaya["TdAngka"]),
            Paragraph(f'<font color="#{(_warna_arah(chg) or MUTED).hexval()[2:]}">'
                      f"{_fmt_pct(chg)}</font>", gaya["TdArah"]),
        ])
        if "IHSG" in name.upper():
            idx_kunci.append(i)
    story += [
        _tabel_pasar(gaya, ["Indeks", "Terakhir", "Sebelumnya", "Perubahan"],
                     idx_baris, [LEBAR - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm],
                     baris_kunci=tuple(idx_kunci)),
        Spacer(1, 4.5 * mm),
    ]
    # ===== Yield =====
    story += [CondPageBreak(60 * mm),
              _kepala_seksi(gaya, "5", "Imbal Hasil Obligasi", "Perubahan dalam poin basis (bp)"),
              Spacer(1, 2.6 * mm)]
    yld_baris, yld_kunci = [], []
    for i, (name, v) in enumerate(yld.items()):
        chg = v.get("change_bp")
        sel_nama = name
        if v.get("as_of_label"):
            sel_nama = f'{name}<br/><font size=7.8 color="#64748b">Data {v["as_of_label"]}</font>'
        yld_baris.append([
            Paragraph(sel_nama, ParagraphStyle("Nm", parent=gaya["Td"],
                                               fontName="Helvetica-Bold", textColor=INK)),
            Paragraph(_fmt_num(v.get("today"), 2, suffix="%"), gaya["TdAngka"]),
            Paragraph(_fmt_num(v.get("prev"), 2, suffix="%"), gaya["TdAngka"]),
            Paragraph(f'<font color="#{(_warna_yield(chg) or MUTED).hexval()[2:]}">'
                      f"{_fmt_bp(chg)}</font>", gaya["TdArah"]),
        ])
        if "sbn" in name.lower() and "10" in name and "sbsn" not in name.lower():
            yld_kunci.append(i)
        elif "treasury" in name.lower() and "10" in name:
            yld_kunci.append(i)
    story += [
        _tabel_pasar(gaya, ["Instrumen", "Terakhir", "Sebelumnya", "Perubahan"],
                     yld_baris, [LEBAR - 3 * 30 * mm, 30 * mm, 30 * mm, 30 * mm],
                     baris_kunci=tuple(yld_kunci)),
        Spacer(1, 1.8 * mm),
        Paragraph("Yield naik (merah) berarti harga obligasi turun; yield turun (hijau) "
                  "berarti harga obligasi naik. Data PHEI terbit sekali sehari.", gaya["Catatan"]),
        Spacer(1, 4.5 * mm),
    ]

    story.append(PageBreak())

    # ===== Kebijakan Moneter (BI) =====
    bi = report.get("bi") or {}
    story += [_kepala_seksi(gaya, "6", "Kebijakan Moneter", "Bank Indonesia"),
              Spacer(1, 2.6 * mm)]
    # Status spread memakai ambang yang sama dengan ringkasan bahasa sederhana,
    # supaya angka dan penjelasannya tidak berbeda arti.
    if spread is None:
        status_spread = "–"
    elif spread < 250:
        status_spread = "Relatif sempit"
    elif spread <= 450:
        status_spread = "Tergolong sedang"
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
        _kartu_angka(gaya, "Spread SBN/UST", status_spread, "", 0, AMBER,
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
        Paragraph("BI Rate menjadi acuan suku bunga. INDONIA adalah rata-rata "
                  "suku bunga pinjaman antarbank tenor semalam. "
                  "JISDOR = kurs transaksi BI antar bank.", gaya["Catatan"]),
        Spacer(1, 4.5 * mm),
    ]
    # ===== Komoditas =====
    kom = report.get("commodities") or {}
    if kom:
        story += [CondPageBreak(55 * mm),
                  _kepala_seksi(gaya, "7", "Komoditas", "Harga komoditas internasional"),
                  Spacer(1, 2.6 * mm)]
        kom_baris = []
        for name, v in kom.items():
            chg = v.get("change_pct")
            kom_baris.append([
                Paragraph(name, ParagraphStyle("Nm", parent=gaya["Td"],
                                              fontName="Helvetica-Bold", textColor=INK)),
                Paragraph(_fmt_num(v.get("today"), 0), gaya["TdAngka"]),
                Paragraph(_fmt_num(v.get("prev"), 0), gaya["TdAngka"]),
                Paragraph(f'<font color="#{(_warna_arah(chg) or MUTED).hexval()[2:]}">'
                          f"{_fmt_pct(chg)}</font>", gaya["TdArah"]),
            ])
        story += [
            _tabel_pasar(gaya, ["Komoditas", "Terakhir", "Sebelumnya", "Perubahan"],
                         kom_baris, [LEBAR - 3 * 34 * mm, 34 * mm, 34 * mm, 34 * mm]),
            Spacer(1, 4.5 * mm),
        ]

    # ===== Sumber Data & Metode =====
    story += [CondPageBreak(45 * mm),
              _kepala_seksi(gaya, "8", "Sumber Data dan Metode"),
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
        "keperluan umum — bukan nasihat investasi, rekomendasi, atau ajakan "
        "bertransaksi.", gaya["Sumber"])]
    story += [Spacer(1, 3 * mm)]

    kanvas = partial(
        KanvasLaporan,
        judul="Market Today",
        sub_judul=date_str,
        sumber=f"Tanggal laporan {date_str} · diperbarui {_jam_snapshot(report)}",
    )
    doc.build(story, canvasmaker=kanvas)
    if stream is not None:
        return buf.getvalue(), nama_file
    print(f"PDF saved -> {out_path}")   # ASCII: konsol Windows (cp1252) tidak bisa cetak "→"
    return out_path


def _brief_paragraph_text(value: Any) -> str:
    """Hilangkan markup internal dan escape teks sebelum dimasukkan ke Paragraph."""
    text = re.sub(r"</?b>", "", str(value or ""), flags=re.IGNORECASE)
    return escape(_teks_bersih(text))


def _brief_insights(report: Dict[str, Any]) -> list[dict]:
    """Pilih tiga insight yang paling mudah dipahami pembaca laporan harian."""
    from market_report.domain.market_analysis import build_insights

    available = build_insights(report)
    preferred = (
        "Nilai tukar Rupiah",
        "Pasar saham (IHSG)",
        "Selisih imbal hasil RI–AS (spread)",
    )
    selected = []
    for title in preferred:
        item = next((row for row in available if row.get("title") == title), None)
        if item is not None:
            selected.append(item)
    for item in available:
        if item not in selected and len(selected) < 3:
            selected.append(item)
    return selected[:3]


def _brief_insight_card(gaya, item: dict) -> Table:
    tone = item.get("tone")
    tone_color = {"good": GOOD, "bad": BAD, "warn": AMBER}.get(tone, ACCENT)
    tone_background = {
        "good": colors.HexColor("#eef8f1"),
        "bad": colors.HexColor("#fff1f0"),
        "warn": colors.HexColor("#fff8e8"),
    }.get(tone, colors.HexColor("#f4f7f7"))
    content = [
        [Paragraph(_brief_paragraph_text(item.get("title")), gaya["InsightTitle"])],
        [Paragraph(_brief_paragraph_text(item.get("text")), gaya["InsightBody"])],
    ]
    if item.get("dampak"):
        impact_style = ParagraphStyle(
            "BriefImpact", fontName="Helvetica-Oblique", fontSize=7.5,
            leading=9.2, textColor=MUTED,
        )
        content.append([Paragraph(_brief_paragraph_text(item["dampak"]), impact_style)])
    card = Table(content, colWidths=[LEBAR - 3 * mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), tone_background),
        ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
        ("LINEBEFORE", (0, 0), (0, -1), 2.2, tone_color),
        ("LEFTPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 2.0 * mm),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.0 * mm),
        ("TOPPADDING", (0, 1), (-1, -1), 0.8 * mm),
    ]))
    return card


def _brief_support_card(gaya, label: str, value, *, decimals: int = 0,
                        suffix: str = "", change=None,
                        higher_is_better: bool = True) -> Table:
    label_paragraph = Paragraph(escape(label), gaya["SupportLabel"])
    value_paragraph = Paragraph(_fmt_num(value, decimals, suffix=suffix), gaya["SupportValue"])
    content = [[label_paragraph], [value_paragraph]]
    tone = _warna_arah(change, naik_baik=higher_is_better) if change is not None else ACCENT
    if change is not None:
        change_style = ParagraphStyle(
            "BriefSupportChange", parent=gaya["SupportChange"],
            textColor=tone or MUTED,
        )
        content.append([Paragraph(_fmt_pct(change), change_style)])
    card = Table(content, colWidths=[LEBAR / 3 - 2.4 * mm])
    card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), SURFACE),
        ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
        ("LINEABOVE", (0, 0), (-1, 0), 1.8, tone or ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, 0), 1.6 * mm),
        ("TOPPADDING", (0, 1), (-1, -1), 0.5 * mm),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 1.7 * mm),
    ]))
    return card


def build_pdf(
    report: Dict[str, Any] = None,
    chart_path: Optional[Path] = None,
    out_path: Optional[Path] = None,
    stream=None,
    fx_chart_path: Optional[Path] = None,
) -> "Path | tuple[bytes, str]":
    """Buat executive brief satu halaman dengan susunan editorial yang ringkas."""
    if report is None:
        with open(DATA_DIR / "report_data.json", encoding="utf-8") as source:
            report = json.load(source)

    date_str = _tanggal_laporan(report)
    report_day = str(report.get("report_date_iso") or datetime.now().strftime("%Y-%m-%d"))
    filename = f"Market Update {report_day.replace('-', '')}.pdf"
    target = stream
    if stream is None:
        out_path = Path(out_path) if out_path else REPORT_DIR / filename
        out_path.parent.mkdir(parents=True, exist_ok=True)
        target = str(out_path)

    doc = SimpleDocTemplate(
        target, pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
        topMargin=13 * mm, bottomMargin=MARGIN_BOTTOM,
        title="Market Today - Ringkasan Pasar Harian", author="Market Today",
        subject=f"Ringkasan pasar harian per {date_str}", creator="Market Today",
    )
    fx = report.get("fx") or {}
    indices = report.get("indices") or {}
    yields = report.get("yields") or {}
    commodities = report.get("commodities") or {}
    usd = _cari(fx, "usd/idr")
    ihsg = _cari(indices, "ihsg")
    sbn10 = _cari(yields, "sbn", "10", exclude=("sbsn", "fr0"))
    ust10 = _cari(yields, "treasury", "10")

    body = ParagraphStyle("ExecBody", fontName="Helvetica", fontSize=7.8,
                          leading=9.6, textColor=BODY)
    body_small = ParagraphStyle("ExecSmall", parent=body, fontSize=7.1, leading=8.6,
                                textColor=MUTED)
    body_bold = ParagraphStyle("ExecBold", parent=body, fontName="Helvetica-Bold",
                               textColor=INK)
    white_heading = ParagraphStyle("ExecWhiteHeading", fontName="Helvetica-Bold",
                                   fontSize=8.7, leading=10.2, textColor=colors.white)

    def p(text, style=body):
        return Paragraph(_brief_paragraph_text(text), style)

    def band(title: str, width: float) -> Table:
        table = Table([[Paragraph(escape(title), white_heading)]], colWidths=[width])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), ACCENT),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.4 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2.4 * mm),
            ("TOPPADDING", (0, 0), (-1, -1), 1.6 * mm),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6 * mm),
        ]))
        return table

    def panel(title: str, content, width: float) -> Table:
        table = Table([[band(title, width)], [content]], colWidths=[width])
        table.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, 0), 0),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
            ("LEFTPADDING", (0, 1), (-1, -1), 2 * mm),
            ("RIGHTPADDING", (0, 1), (-1, -1), 2 * mm),
            ("TOPPADDING", (0, 1), (-1, -1), 2.3 * mm),
            ("BOTTOMPADDING", (0, 1), (-1, -1), 2.3 * mm),
        ]))
        return table

    def show_value(value, kind: str) -> str:
        if not isinstance(value, (int, float)):
            return "-"
        if kind == "yield":
            return f"{_fmt_num(value, 2)}%"
        if kind == "decimal":
            return _fmt_num(value, 2)
        if kind in ("fx", "index"):
            return _fmt_num(value, 0 if kind == "fx" else 0)
        return _fmt_num(value, 0 if abs(value) >= 100 else 2)

    def delta_for(row: dict, kind: str) -> tuple[str, colors.Color]:
        if kind == "yield":
            value = row.get("change_bp")
            return _fmt_bp(value), (_warna_yield(value) or MUTED)
        value = row.get("change_pct")
        return _fmt_pct(value), (_warna_arah(value, naik_baik=kind != "fx") or MUTED)

    # Cover line and report headline.
    brand = ParagraphStyle("ExecBrand", fontName="Helvetica-Bold", fontSize=12,
                           leading=14, textColor=ACCENT_DARK)
    date_style = ParagraphStyle("ExecDate", fontName="Helvetica-Bold", fontSize=8.2,
                                leading=10.4, alignment=TA_RIGHT, textColor=INK)
    header = Table([[
        Paragraph("MARKET TODAY<br/><font size=6.5 color='#64748b'>DAILY MARKET INTELLIGENCE</font>", brand),
        Paragraph(f"RINGKASAN PASAR HARIAN<br/><font size=8>{escape(date_str)}</font>", date_style),
    ]], colWidths=[LEBAR * 0.59, LEBAR * 0.41])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
        ("LINEBELOW", (0, 0), (-1, -1), 1.3, ACCENT),
    ]))

    usd_change, ihsg_change = usd.get("change_pct"), ihsg.get("change_pct")
    usd_direction = "melemah" if isinstance(usd_change, (int, float)) and usd_change > 0 else "menguat"
    ihsg_direction = "menguat" if isinstance(ihsg_change, (int, float)) and ihsg_change > 0 else "melemah"
    if usd.get("today") is not None and ihsg.get("today") is not None:
        headline = f"Rupiah {usd_direction.capitalize()}, IHSG {ihsg_direction.capitalize()}"
    elif usd.get("today") is not None:
        headline = f"Rupiah {usd_direction.capitalize()}"
    elif ihsg.get("today") is not None:
        headline = f"IHSG {ihsg_direction.capitalize()}"
    else:
        headline = "Ringkasan Pasar Hari Ini"
    headline_style = ParagraphStyle("ExecHeadline", fontName="Helvetica-Bold", fontSize=24,
                                    leading=27, textColor=INK)
    summary_style = ParagraphStyle("ExecSummary", fontName="Helvetica", fontSize=8.7,
                                   leading=11.5, textColor=BODY)
    headline_block = [
        Paragraph(escape(headline), headline_style),
        Spacer(1, 0.8 * mm),
        Paragraph(escape(summary_text(report) or "Pergerakan pasar utama dan indikator ekonomi terbaru."), summary_style),
    ]

    # Three clear KPIs; text-only changes keep the values easy to scan.
    def kpi(label: str, value: str, change: str, accent, change_color, fill, width: float) -> Table:
        label_style = ParagraphStyle(f"KpiLabel{label}", fontName="Helvetica-Bold",
                                     fontSize=7.6, leading=9.1, textColor=accent)
        value_style = ParagraphStyle(f"KpiValue{label}", fontName="Helvetica-Bold",
                                     fontSize=20, leading=23, textColor=INK)
        change_style = ParagraphStyle(f"KpiChange{label}", fontName="Helvetica-Bold",
                                      fontSize=7.8, leading=9.2, textColor=change_color)
        table = Table([[Paragraph(escape(label.upper()), label_style)],
                       [Paragraph(value, value_style)],
                       [Paragraph(escape(change), change_style)]], colWidths=[width])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), fill), ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
            ("LINEBEFORE", (0, 0), (0, -1), 2, accent),
            ("LEFTPADDING", (0, 0), (-1, -1), 2.8 * mm),
            ("RIGHTPADDING", (0, 0), (-1, -1), 1.8 * mm),
            ("TOPPADDING", (0, 0), (-1, 0), 1.5 * mm),
            ("TOPPADDING", (0, 1), (-1, -1), 0.6 * mm),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 1.5 * mm),
        ]))
        return table

    def kpi_delta(row: dict, kind: str) -> tuple[str, colors.Color]:
        value, tone = delta_for(row, kind)
        return (f"DtD {value}", tone) if value != "-" else ("Perubahan harian belum tersedia", MUTED)

    kpi_width = LEBAR / 3
    usd_delta, usd_tone = kpi_delta(usd, "fx")
    ihsg_delta, ihsg_tone = kpi_delta(ihsg, "index")
    sbn_delta, sbn_tone = kpi_delta(sbn10, "yield")
    kpis = Table([[
        kpi("Kurs dolar AS", f"Rp{_fmt_num(usd.get('today'), 0)}", usd_delta,
            ACCENT, usd_tone, ACCENT_SOFT, kpi_width - 2 * mm),
        kpi("Pasar saham", _fmt_num(ihsg.get("today"), 0), ihsg_delta,
            GOOD, ihsg_tone, colors.HexColor("#edf7f0"), kpi_width - 2 * mm),
        kpi("Obligasi pemerintah", f"{_fmt_num(sbn10.get('today'), 2)}%", sbn_delta,
            AMBER, sbn_tone, colors.HexColor("#fff7e8"), kpi_width - 2 * mm),
    ]], colWidths=[kpi_width] * 3)
    kpis.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # Market drivers as three short editorial columns.
    insights = _brief_insights(report)[:3]
    driver_style = ParagraphStyle("DriverText", fontName="Helvetica", fontSize=7.2,
                                  leading=8.8, textColor=BODY)
    driver_title_style = ParagraphStyle("DriverTitle", fontName="Helvetica-Bold",
                                        fontSize=7.7, leading=9.2, textColor=ACCENT_DARK)
    driver_cells = []
    for number, item in enumerate(insights, start=1):
        driver_cells.append(Table([
            [Paragraph(f"<font color='#0f766e'><b>{number:02d}</b></font>  "
                       f"{_brief_paragraph_text(item.get('title'))}", driver_title_style)],
            [Paragraph(_brief_paragraph_text(item.get("text")), driver_style)],
        ], colWidths=[LEBAR / 3 - 4 * mm]))
    if not driver_cells:
        driver_cells = [[p("Sorotan pasar belum tersedia.", body_small)]]
    drivers = Table([driver_cells], colWidths=[LEBAR / 3] * 3)
    drivers.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBEFORE", (1, 0), (-1, -1), 0.6, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))

    # Compact market table with previous close, latest value, and daily move.
    market_specs = [
        ("USD/IDR", usd, "fx"), ("DXY", _cari(fx, "dxy"), "decimal"),
        ("IHSG", ihsg, "index"), ("Dow Jones", _cari(indices, "dji"), "index"),
        ("UST 10 tahun", ust10, "yield"), ("SBN 10 tahun", sbn10, "yield"),
        ("SBN 5 tahun", _cari(yields, "sbn", "5", exclude=("sbsn", "fr0")), "yield"),
    ]
    market_rows = [[p("Indikator", body_bold), p("Sebelum", body_bold),
                    p("Terakhir", body_bold), p("DtD", body_bold)]]
    for label, row, kind in market_specs:
        if not isinstance(row, dict) or row.get("today") is None:
            continue
        delta, tone = delta_for(row, kind)
        delta_style = ParagraphStyle(f"Delta{label}", parent=body_bold, alignment=TA_RIGHT, textColor=tone)
        market_rows.append([p(label), p(show_value(row.get("prev"), kind)),
                            p(show_value(row.get("today"), kind), body_bold),
                            Paragraph(escape(delta), delta_style)])
    gutter_width = 4 * mm
    left_width = (LEBAR - gutter_width) * 0.535
    left_inner = left_width - 4 * mm
    market_table = Table(market_rows, colWidths=[left_inner * .34, left_inner * .21,
                                                left_inner * .23, left_inner * .22], repeatRows=1)
    market_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT),
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafb")]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 1.2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.4 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.4 * mm),
    ]))
    market_panel = panel("DATA PASAR", market_table, left_width)

    # Three practical implications, as available in the report payload.
    impacts = report.get("impacts") or []
    if not impacts:
        from market_report.domain.market_analysis import build_impacts
        impacts = build_impacts(report)
    impact_rows = []
    right_width = LEBAR - gutter_width - left_width
    right_inner = right_width - 4 * mm
    impact_title = ParagraphStyle("ImpactTitleCompact", fontName="Helvetica-Bold",
                                  fontSize=7.5, leading=9, textColor=INK)
    impact_text = ParagraphStyle("ImpactTextCompact", fontName="Helvetica",
                                 fontSize=7, leading=8.7, textColor=BODY)
    for item in impacts[:3]:
        impact_rows.append([
            Paragraph(_brief_paragraph_text(item.get("title")), impact_title),
            Paragraph(_brief_paragraph_text(item.get("text")), impact_text),
        ])
    if not impact_rows:
        impact_rows = [[p("Dampak pasar belum tersedia.", body_small), p("")]]
    impact_table = Table(impact_rows, colWidths=[right_inner * .36, right_inner * .64])
    impact_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -2), 0.4, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 1.2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.9 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.9 * mm),
    ]))
    impacts_panel = panel("MAKNA BAGI BISNIS", impact_table, right_width)
    primary_grid = Table([[market_panel, "", impacts_panel]],
                         colWidths=[left_width, gutter_width, right_width])
    primary_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # Monthly macro table uses only published observations; unreleased months stay blank.
    try:
        report_date = date.fromisoformat(report_day[:10])
    except ValueError:
        report_date = date.today()
    month_keys = []
    year, month = report_date.year, report_date.month
    for _ in range(3):
        month_keys.insert(0, f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    month_names = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
    macro = report.get("macro_indicators") or {}
    macro_specs = [
        ("Fed Funds", "FED Fund Rate (%)"), ("BI Rate", "BI Rate (%)"),
        ("Inflasi Indonesia YoY", "Inflasi Indonesia YoY (%)"), ("M2 YoY", "M2 (% YoY)"),
        ("Kredit perbankan YoY", "Kredit/Pembiayaan (% YoY) - BI"), ("DPK YoY", "DPK (% YoY) - BI"),
    ]
    macro_rows = [[p("Indikator", body_bold)] + [p(month_names[int(key[5:7]) - 1], body_bold) for key in month_keys]]
    for label, key in macro_specs:
        observations = (macro.get(key) or {}).get("observations") or {}
        macro_rows.append([p(label)] + [
            p(f"{_fmt_num(observations[period], 2)}%" if observations.get(period) is not None else "-")
            for period in month_keys
        ])
    secondary_available = LEBAR - gutter_width
    macro_width = secondary_available * .51
    macro_inner = macro_width - 4 * mm
    macro_table = Table(macro_rows, colWidths=[macro_inner * .46] + [macro_inner * .18] * 3)
    macro_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT_SOFT), ("LINEBELOW", (0, 0), (-1, -1), 0.35, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafb")]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 1.2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.3 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.3 * mm),
    ]))
    macro_panel = panel("INDIKATOR EKONOMI", macro_table, macro_width)

    global_specs = [
        ("DXY", _cari(fx, "dxy"), "dxy"), ("Emas spot (US$/ons)", _cari(commodities, "gold"), "gold"),
        ("Emas Antam 1 gr", _cari(commodities, "emas", "antam"), "antam"),
        ("Minyak Brent (US$/barel)", _cari(commodities, "brent"), "brent"),
        ("Batu bara Newcastle", _cari(commodities, "coal"), "commodity"),
        ("CPO", _cari(commodities, "cpo"), "commodity"),
    ]
    global_rows = []
    for label, row, kind in global_specs:
        if not isinstance(row, dict) or row.get("today") is None:
            continue
        value = row["today"]
        if kind == "antam":
            value_text = f"Rp{_fmt_num(value, 0)}"
        elif kind in ("gold", "brent"):
            value_text = f"US${_fmt_num(value, 0)}"
        elif kind == "dxy":
            value_text = f"{_fmt_num(value, 2)} indeks"
        else:
            value_text = f"{_fmt_num(value, 0)} {row.get('unit') or ''}".strip()
        delta, _ = delta_for(row, "fx" if kind == "dxy" else "index" if kind == "index" else "commodity")
        global_rows.append([p(label), p(value_text, body_bold), p(delta, body_small)])
    if not global_rows:
        global_rows = [[p("Data lintas aset belum tersedia.", body_small), p(""), p("")]]
    global_width = secondary_available - macro_width
    global_inner = global_width - 4 * mm
    global_table = Table(global_rows, colWidths=[global_inner * .47, global_inner * .35, global_inner * .18])
    global_table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -2), 0.35, BORDER),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, colors.HexColor("#f8fafb")]),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.2 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 1.2 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.7 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.7 * mm),
    ]))
    global_panel = panel("PASAR GLOBAL & KOMODITAS", global_table, global_width)
    secondary_grid = Table([[macro_panel, "", global_panel]],
                           colWidths=[macro_width, gutter_width, global_width])
    secondary_grid.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    guide = Table([[
        Paragraph("CARA MEMBACA", ParagraphStyle("GuideLabelExec", fontName="Helvetica-Bold",
                  fontSize=7.1, leading=8.5, textColor=ACCENT_DARK)),
        Paragraph("USD/IDR naik berarti Rupiah melemah. Yield obligasi naik biasanya menekan harga obligasi. 1 bp = 0,01 poin persentase.",
                  ParagraphStyle("GuideTextExec", fontName="Helvetica", fontSize=6.8,
                                 leading=8.2, textColor=INK)),
    ]], colWidths=[LEBAR * .19, LEBAR * .81])
    guide.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), ACCENT_SOFT), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBEFORE", (1, 0), (1, 0), .8, ACCENT),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.3 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.3 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.8 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8 * mm),
    ]))
    disclaimer = Table([[
        Paragraph("<b>Informasi ini merupakan referensi pasar dan bukan jaminan hasil investasi.</b><br/>"
                  "Nilai mengikuti observasi terakhir dari sumber data; periode yang belum dirilis ditampilkan sebagai tanda kosong.",
                  ParagraphStyle("DisclaimerExec", fontName="Helvetica", fontSize=6.4,
                                 leading=7.8, textColor=BODY))
    ]], colWidths=[LEBAR])
    disclaimer.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff6df")),
        ("BOX", (0, 0), (-1, -1), .45, colors.HexColor("#f0d79f")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2.4 * mm), ("RIGHTPADDING", (0, 0), (-1, -1), 2.4 * mm),
        ("TOPPADDING", (0, 0), (-1, -1), 1.6 * mm), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.6 * mm),
    ]))

    story = [
        header, Spacer(1, 2.4 * mm), *headline_block, Spacer(1, 2.8 * mm), kpis,
        Spacer(1, 3 * mm), band("APA YANG MENGGERAKKAN PASAR?", LEBAR), drivers,
        Spacer(1, 3 * mm), primary_grid, Spacer(1, 3 * mm), secondary_grid,
        Spacer(1, 2.8 * mm), guide, Spacer(1, 2.2 * mm), disclaimer,
    ]

    canvas = partial(
        KanvasLaporan, judul="Market Today", sub_judul=date_str,
        sumber=f"Market Today | Disusun {_jam_snapshot(report)} | Data mengikuti observasi terakhir sumber.",
    )
    doc.build(story, canvasmaker=canvas)
    if stream is not None:
        return target.getvalue(), filename
    print(f"PDF saved -> {out_path}")
    return out_path


if __name__ == "__main__":
    build_pdf()

"""Penyusunan fakta, ringkasan, dan dampak dari data pasar."""

from market_report.domain.market_data import pick
from market_report.presentation.formatting import _delta_bp, fmt_mag, fmt_num, fmt_pct, spread_word, tone_of


def market_facts(report: dict) -> dict:
    """
    Ambil semua angka penting sekali saja. Pencarian nama instrument dibuat
    toleran (berdasarkan kata kunci) supaya tetap jalan walau label sumber
    data sedikit berubah.
    """
    fx = report.get("fx") or {}
    yld = report.get("yields") or {}
    idx = report.get("indices") or {}
    comm = report.get("commodities") or {}
    bi = report.get("bi") or {}

    return {
        "usd_idr": pick(fx, "usd/idr"),
        "dxy": pick(fx, "dxy"),
        "ihsg": pick(idx, "ihsg"),
        "dji": pick(idx, "dji"),
        "sbn10": pick(yld, "sbn", "10", exclude=("sbsn", "fr0")),
        "sbn5": pick(yld, "sbn", "5", exclude=("sbsn", "fr0")),
        "ust10": pick(yld, "treasury", "10"),
        "ust5": pick(yld, "treasury", "5"),
        "gold": pick(comm, "gold"),
        "brent": pick(comm, "brent"),
        "bi_rate": bi.get("BI Rate"),
        "indonia": bi.get("INDONIA"),
        "jisdor": bi.get("JISDOR"),
        "spread": report.get("spread_sbn10_ust10_bp"),
    }


def _arah(kata_naik: str, kata_turun: str, nilai) -> str:
    """Pilih kata arah: naik / turun / hampir tidak berubah."""
    if nilai is None:
        return "bergerak"
    if nilai > 0.02:
        return kata_naik
    if nilai < -0.02:
        return kata_turun
    return "hampir tidak berubah"


def build_summary(report: dict) -> str:
    """Ringkasan satu paragraf: angka tetap akurat, bahasanya sehari-hari."""
    f = market_facts(report)
    kalimat: list[str] = []

    usd = f["usd_idr"].get("today")
    chg = f["usd_idr"].get("change_pct")
    if usd is not None:
        if chg is None:
            kalimat.append(f"Kurs Rupiah berada di Rp{fmt_num(usd, 0)} per dolar AS.")
        else:
            arah = "menguat" if chg < 0 else ("melemah" if chg > 0 else "nyaris tidak berubah")
            kalimat.append(
                f"Rupiah ditutup di Rp{fmt_num(usd, 0)} per dolar AS, {arah} "
                f"{fmt_mag(chg)} dibanding hari sebelumnya."
            )

    ihsg = f["ihsg"]
    if ihsg.get("today") is not None and ihsg.get("change_pct") is not None:
        c = ihsg["change_pct"]
        kalimat.append(
            f"Di bursa saham, IHSG {_arah('naik', 'turun', c)} {fmt_mag(c)} "
            f"ke {fmt_num(ihsg['today'], 2)}."
        )

    for kunci, label in (("sbn10", "SBN 10 tahun"), ("ust10", "obligasi AS / UST 10 tahun")):
        row = f[kunci]
        if row.get("today") is None:
            continue
        bp = row.get("change_bp")
        as_of = row.get("as_of_label")
        ekor = f" (data {as_of})" if as_of else ""
        if bp is None:
            kalimat.append(f"Imbal hasil {label} {fmt_num(row['today'], 2)}%{ekor}.")
        else:
            kalimat.append(
                f"Imbal hasil {label} {_arah('naik', 'turun', bp)} {abs(float(bp)):.1f} bp "
                f"menjadi {fmt_num(row['today'], 2)}%{ekor}."
            )

    if f["spread"] is not None:
        kata, _ = spread_word(f["spread"])
        kalimat.append(f"Selisih imbal hasil RI–AS {fmt_num(f['spread'], 0)} bp, {kata}.")

    if f["bi_rate"] is not None:
        kalimat.append(f"Suku bunga acuan Bank Indonesia (BI Rate) berada di {fmt_num(f['bi_rate'], 2)}%.")

    komoditas = []
    for kunci, nama in (("gold", "Harga emas"), ("brent", "minyak Brent")):
        row = f[kunci]
        if row.get("change_pct") is not None:
            c = row["change_pct"]
            komoditas.append(f"{nama} {_arah('naik', 'turun', c)} {fmt_mag(c)}")
    if komoditas:
        kalimat.append(" dan ".join(komoditas) + ".")

    if not kalimat:
        return "Data hari ini belum lengkap untuk menyusun ringkasan otomatis."

    return " ".join(kalimat)



def build_insights(report: dict) -> list[dict]:
    """Sorotan utama hari ini: judul, angka, dan artinya dalam bahasa sehari-hari."""
    f = market_facts(report)
    out: list[dict] = []

    usd = f["usd_idr"].get("today")
    chg = f["usd_idr"].get("change_pct")
    if usd is not None:
        if chg is None:
            out.append({
                "title": "Nilai tukar Rupiah", "tone": "flat",
                "text": f"Kurs berada di <b>Rp{fmt_num(usd, 0)}</b> per dolar AS.",
                "dampak": "Data pembanding hari sebelumnya belum ada, jadi arah harian belum bisa dihitung.",
            })
        elif chg > 0.15:
            out.append({
                "title": "Nilai tukar Rupiah", "tone": "warn",
                "text": (f"Rupiah <b>melemah {fmt_pct(chg)}</b> menjadi "
                         f"<b>Rp{fmt_num(usd, 0)}</b> per dolar AS."),
                "dampak": ("Barang impor, tiket & penginapan luar negeri, dan cicilan utang "
                           "berdenominasi dolar jadi relatif lebih mahal."),
            })
        elif chg < -0.15:
            out.append({
                "title": "Nilai tukar Rupiah", "tone": "good",
                "text": (f"Rupiah <b>menguat {fmt_mag(chg)}</b> menjadi "
                         f"<b>Rp{fmt_num(usd, 0)}</b> per dolar AS."),
                "dampak": ("Menguntungkan importir dan siapa pun yang punya kewajiban dalam dolar AS; "
                           "biaya belanja luar negeri relatif lebih ringan."),
            })
        else:
            out.append({
                "title": "Nilai tukar Rupiah", "tone": "flat",
                "text": f"Rupiah bergerak tipis ({fmt_pct(chg)}) di <b>Rp{fmt_num(usd, 0)}</b> per dolar AS.",
                "dampak": "Harga barang impor relatif tidak berubah hari ini.",
            })

    if f["spread"] is not None:
        kata, tone = spread_word(f["spread"])
        out.append({
            "title": "Selisih imbal hasil RI–AS (spread)", "tone": tone,
            "text": f"Spread SBN 10Y vs UST 10Y sebesar <b>{fmt_num(f['spread'], 0)} bp</b> ({kata}).",
            "dampak": ("Makin lebar selisih ini, makin besar 'kompensasi risiko' yang diminta investor "
                       "untuk memegang surat utang Indonesia dibanding Amerika Serikat."),
        })

    if f["bi_rate"] is not None:
        out.append({
            "title": "Suku bunga acuan (BI Rate)", "tone": "flat",
            "text": f"BI Rate berada di <b>{fmt_num(f['bi_rate'], 2)}%</b>.",
            "dampak": ("Ini patokan bunga KPR, kredit, dan deposito perbankan. Kalau kreditmu berbunga "
                       "mengambang, level ini ikut memengaruhi besar cicilan."),
        })

    ihsg = f["ihsg"]
    if ihsg.get("change_pct") is not None:
        c = ihsg["change_pct"]
        out.append({
            "title": "Pasar saham (IHSG)", "tone": tone_of(c, higher_is_better=True),
            "text": (f"IHSG {_arah('naik', 'turun', c)} <b>{fmt_mag(c)}</b> ke "
                     f"<b>{fmt_num(ihsg['today'], 2)}</b>."),
            "dampak": ("Menggambarkan arah rata-rata harga saham di Bursa Efek Indonesia; naik biasanya "
                       "berarti investor lebih optimistis, turun berarti lebih berhati-hati."),
        })

    dxy = f["dxy"]
    if dxy.get("change_pct") is not None and abs(dxy["change_pct"]) > 0.3:
        c = dxy["change_pct"]
        out.append({
            "title": "Kekuatan dolar AS (DXY)", "tone": tone_of(c, higher_is_better=False),
            "text": f"Indeks dolar AS {_arah('naik', 'turun', c)} <b>{fmt_pct(c)}</b>.",
            "dampak": ("DXY mengukur dolar terhadap mata uang utama dunia (bukan hanya Rupiah). "
                       "Dolar yang lebih kuat umumnya menekan mata uang negara berkembang."),
        })

    komoditas = []
    for kunci, nama in (("gold", "Emas"), ("brent", "Minyak Brent")):
        row = f[kunci]
        c = row.get("change_pct")
        if c is not None:
            komoditas.append(f"{nama} {_arah('naik', 'turun', c)} {fmt_mag(c)}")
    if komoditas:
        out.append({
            "title": "Harga komoditas", "tone": "flat",
            "text": ", ".join(komoditas) + ".",
            "dampak": ("Emas naik biasanya menandakan investor mencari aset aman; minyak naik menaikkan "
                       "biaya energi & transportasi sehingga bisa menekan inflasi."),
        })

    if not out:
        out.append({
            "title": "Belum ada sorotan", "tone": "flat",
            "text": "Data hari ini belum lengkap untuk menyusun sorotan otomatis.",
            "dampak": "Coba jalankan pembaruan data dari sidebar.",
        })
    return out[:5]


def build_impacts(report: dict) -> list[dict]:
    """Dampak praktis untuk pembaca non-ekonom: apa yang mungkin mereka rasakan."""
    f = market_facts(report)
    chg = f["usd_idr"].get("change_pct")
    out: list[dict] = []

    if chg is None:
        teks = "Belum ada data perubahan kurs hari ini."
    elif chg > 0.15:
        teks = ("Rupiah sedang melemah, jadi barang impor dan biaya perjalanan ke luar negeri "
                "cenderung naik, sementara nilai tabungan dalam Rupiah turun bila diukur dengan dolar.")
    elif chg < -0.15:
        teks = ("Rupiah sedang menguat, jadi belanja barang impor dan perjalanan ke luar negeri "
                "relatif lebih murah dibanding hari sebelumnya.")
    else:
        teks = "Pergerakan kurs sangat kecil, jadi pengaruhnya ke harga barang relatif tidak terasa hari ini."
    out.append({"title": "Belanja & perjalanan ke luar negeri", "text": teks})

    if f["bi_rate"] is not None:
        out.append({
            "title": "Cicilan kredit, KPR, dan deposito",
            "text": (f"BI Rate ada di {fmt_num(f['bi_rate'], 2)}%. Angka ini acuan bank. Selama tidak berubah, "
                     "bunga kredit dan deposito umumnya stabil; bila BI Rate turun, bunga kredit biasanya "
                     "menyusul turun (dengan jeda waktu), dan sebaliknya bila BI Rate naik."),
        })

    if f["spread"] is not None and f["sbn10"].get("today") is not None:
        kata, _ = spread_word(f["spread"])
        ust = f["ust10"].get("today")
        pembanding = f" dibanding {fmt_num(ust, 2)}% pada surat utang AS" if ust is not None else ""
        out.append({
            "title": "Tabungan, obligasi, dan sukuk",
            "text": (f"Surat utang negara Indonesia menawarkan imbal hasil "
                     f"{fmt_num(f['sbn10']['today'], 2)}%{pembanding}. Selisihnya {fmt_num(f['spread'], 0)} bp "
                     f"({kata}) — menarik untuk pemburu pendapatan tetap, tetapi tetap membawa risiko harga "
                     "dan nilai tukar."),
        })

    komoditas = []
    for kunci, nama, efek in (("brent", "minyak Brent", "biaya bahan bakar dan transportasi"),
                              ("gold", "emas", "harga emas batangan/perhiasan")):
        row = f[kunci]
        c = row.get("change_pct")
        if c is not None and abs(c) > 0.5:
            komoditas.append(f"{nama} {'naik' if c > 0 else 'turun'} {fmt_mag(c)} — memengaruhi {efek}")
    if komoditas:
        out.append({
            "title": "Harga barang sehari-hari",
            "text": "; ".join(komoditas) + ".",
        })

    return out


# ── Render: header, ringkasan, sorotan, dampak ───────────────
# ── Papan status pasar (ringkas, sekali lihat) ───────────────
def build_market_status(report: dict) -> list[dict]:
    """
    Ringkas tiap kelas aset menjadi status singkat (menguat/melemah/stabil).
    Semua nilai diambil dari data yang sama dengan tabel di bawah, jadi tidak
    ada penilaian yang tidak berdasar.
    """
    f = market_facts(report)
    out: list[dict] = []

    usd = f["usd_idr"]
    if usd.get("today") is not None:
        tone = tone_of(usd.get("change_pct"), higher_is_better=False, threshold=0.15)
        kata = {"good": "Rupiah menguat", "bad": "Rupiah melemah", "flat": "Rupiah stabil"}[tone]
        out.append({"label": "Rupiah (USD/IDR)", "value": f"Rp{fmt_num(usd.get('today'), 0)}",
                    "note": f"{kata} {fmt_pct(usd.get('change_pct'))}", "tone": tone})

    ihsg = f["ihsg"]
    if ihsg.get("change_pct") is not None:
        tone = tone_of(ihsg.get("change_pct"), higher_is_better=True, threshold=0.10)
        kata = {"good": "Saham naik", "bad": "Saham turun", "flat": "Saham stabil"}[tone]
        out.append({"label": "Saham (IHSG)", "value": fmt_num(ihsg.get("today"), 2),
                    "note": f"{kata} {fmt_pct(ihsg.get('change_pct'))}", "tone": tone})

    sbn = f["sbn10"]
    if sbn.get("change_bp") is not None:
        tone = tone_of(sbn.get("change_bp"), higher_is_better=False, threshold=0.5)
        kata = {"good": "Imbal hasil turun", "bad": "Imbal hasil naik", "flat": "Imbal hasil stabil"}[tone]
        out.append({"label": "Obligasi RI (SBN 10Y)", "value": f"{fmt_num(sbn.get('today'), 2)}%",
                    "note": f"{kata} {_delta_bp(sbn.get('change_bp'))}", "tone": tone})

    if f["spread"] is not None:
        kata, tone = spread_word(f["spread"])
        out.append({"label": "Selisih RI–AS", "value": f"{fmt_num(f['spread'], 0)} bp",
                    "note": kata.split(" — ")[0].capitalize(), "tone": tone})

    dxy = f["dxy"]
    if dxy.get("change_pct") is not None:
        tone = tone_of(dxy.get("change_pct"), higher_is_better=False, threshold=0.15)
        kata = {"good": "Dolar mengendur", "bad": "Dolar menguat", "flat": "Dolar stabil"}[tone]
        out.append({"label": "Kekuatan dolar (DXY)", "value": fmt_num(dxy.get("today"), 2),
                    "note": f"{kata} {fmt_pct(dxy.get('change_pct'))}", "tone": tone})

    brent = f["brent"]
    if brent.get("change_pct") is not None:
        c = brent["change_pct"]
        tone = "bad" if c > 0.5 else ("good" if c < -0.5 else "flat")
        kata = {"good": "Minyak turun", "bad": "Minyak naik", "flat": "Minyak stabil"}[tone]
        out.append({"label": "Minyak (Brent)", "value": fmt_num(brent.get("today"), 2),
                    "note": f"{kata} {fmt_pct(c)}", "tone": tone})

    return out


def market_sentiment(items: list[dict]) -> tuple[str, str]:
    """Simpulkan nada keseluruhan dari status per kelas aset."""
    skor = sum(1 if i["tone"] == "good" else (-1 if i["tone"] in ("bad", "warn") else 0) for i in items)
    if skor >= 2:
        return "cenderung positif", "good"
    if skor <= -2:
        return "cenderung negatif", "bad"
    return "campuran / netral", "flat"

"""
Periksa kontras teks widget bawaan Streamlit pada mode terang & gelap.

Widget seperti st.expander, st.container(border=True), dan st.info memakai
warna dari TEMA Streamlit, bukan dari token CSS aplikasi. Kalau tema itu
tidak sejalan dengan mode tampilan, teksnya bisa putih di atas putih.

Skrip ini menjalankan dashboard sungguhan, membuka bagian "Sumber Data",
lalu MENGUKUR rasio kontras WCAG tiap teks terhadap latar induknya di kedua
mode. Jalankan:  python tools_cek_kontras.py
"""
from __future__ import annotations
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PORT = 8599
URL = f"http://localhost:{PORT}"

# Ambang WCAG: 4.5 untuk teks normal, 3.0 untuk teks besar (>=18.66px tebal).
AMBANG_NORMAL = 4.5

# Warna latar Streamlit yang muncul sebagai "putih" dan tidak boleh dipakai
# sebagai warna teks di mode terang.
PUTIH = (255, 255, 255)


def luminance(rgb: tuple[int, int, int]) -> float:
    """Luminance relatif (formula WCAG 2.1)."""
    channel = []
    for nilai in rgb:
        c = nilai / 255
        channel.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channel
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def kontras(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    """Rasio kontras antara dua warna."""
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# JS yang dijalankan di browser: cari teks yang kontrasnya rendah.
UKURAN_JS = r"""
(selector) => {
  const out = [];
  const parse = (c) => {
    const m = c.match(/rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?\)/);
    if (!m) return null;
    return [ +m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4] ];
  };
  const bgOf = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c[3] > 0.05) return c;
      n = n.parentElement;
    }
    return [255, 255, 255, 1];
  };
  document.querySelectorAll(selector).forEach((el) => {
    const txt = (el.innerText || "").trim();
    if (!txt || txt.length > 90) return;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none") return;
    if (el.offsetParent === null && cs.position !== "fixed") return;
    const fg = parse(cs.color);
    if (!fg) return;
    const bg = bgOf(el);
    out.push({ text: txt.slice(0, 60), fg: fg.slice(0, 3), bg: bg.slice(0, 3) });
  });
  return out;
}
"""


OPEN_SUMBER = """() => {
    const box = document.querySelector('[data-testid="stCheckbox"] label');
    if (box && box.getAttribute('data-selected') !== 'true') box.click();
}"""

BUKA_EXPANDER = """() => {
    // Buka expander milik bagian "Sumber Data" (bukan "Sorotan lain hari ini").
    const semua = [...document.querySelectorAll('[data-testid="stExpander"] summary')];
    const target = semua.find(s => /sumber|exchange|yield|komoditas|indeks|commodities|financial/i
                                       .test(s.innerText || ''));
    if (target) target.click();
}"""

SCROLL_SUMBER = """() => {
    const semua = [...document.querySelectorAll('[data-testid="stExpander"]')];
    const target = semua.find(e => /sumber|exchange|yield|komoditas|indeks|commodities|financial/i
                                       .test(e.innerText || ''));
    if (target) target.scrollIntoView({ block: 'start' });
    else if (semua.length) semua[semua.length - 1].scrollIntoView({ block: 'start' });
}"""


def cek_semua(page, mode: str) -> list[tuple]:
    """
    Kembalikan daftar teks dengan kontras < ambang untuk sebuah mode.

    Mode dipasang lewat localStorage lalu halaman dimuat ulang, sehingga
    alur pengguna sungguhan ikut teruji (termasuk MutationObserver yang
    menyetel ulang class `__mt_dark` setiap Streamlit render ulang).
    """
    page.evaluate(
        "m => localStorage.setItem('__mt_mode', m === 'dark' ? 'dark' : 'light')", mode)
    page.reload(wait_until="domcontentloaded")
    page.wait_for_selector('[data-testid="stExpander"]', timeout=60_000)
    page.wait_for_timeout(2000)

    page.evaluate(OPEN_SUMBER)
    page.wait_for_timeout(2500)
    page.evaluate(BUKA_EXPANDER)
    page.wait_for_timeout(800)

    buruk: list[tuple] = []
    for sel in ('[data-testid="stExpander"] summary',
                '[data-testid="stExpanderDetails"] p',
                '[data-testid="stVerticalBlockBorderWrapper"] p',
                '[data-testid="stAlert"] p'):
        for item in page.evaluate(UKURAN_JS, sel) or []:
            r = kontras(tuple(item["fg"]), tuple(item["bg"]))
            if r < AMBANG_NORMAL:
                buruk.append((mode, sel.split('"')[1], item["text"],
                              tuple(item["fg"]), tuple(item["bg"]), r))
    return buruk

def main() -> int:
    proses = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "src" / "app.py"),
         "--server.port", str(PORT), "--server.headless", "true",
         "--browser.gatherUsageStats", "false"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        proses.terminate()
        print("playwright belum terpasang: pip install playwright")
        return 1

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1400, "height": 1000})
            # Tunggu server Streamlit siap sebelum membuka halaman.
            siap = False
            for _ in range(60):
                try:
                    page.goto(URL, wait_until="domcontentloaded", timeout=5_000)
                    siap = True
                    break
                except Exception:
                    time.sleep(1)
            if not siap:
                print("FAIL: server Streamlit tidak siap")
                return 1
            page.wait_for_selector('[data-testid="stExpander"]', timeout=60_000)
            page.wait_for_timeout(1500)
            page.evaluate(OPEN_SUMBER)
            page.wait_for_timeout(3000)

            semua: list = []
            for mode in ("light", "dark"):
                semua += cek_semua(page, mode)
                page.evaluate(SCROLL_SUMBER)
                page.wait_for_timeout(500)
                page.screenshot(path=str(ROOT / f"_cek_{mode}.png"))
            browser.close()

        print("=== Pemeriksaan kontras widget (Sumber Data) ===")
        if not semua:
            print("OK  : semua teks punya kontras >= 4.5:1 di kedua mode")
            return 0
        print(f"FAIL: {len(semua)} teks kurang kontras")
        for mode, sel, teks, fg, bg, r in semua[:15]:
            print(f"  [{mode:5}] {sel}")
            print(f"          fg={fg} bg={bg} -> {r:.2f}:1  teks={teks!r}")
        return 1
    finally:
        proses.terminate()
        try:
            proses.wait(timeout=10)
        except Exception:
            proses.kill()


if __name__ == "__main__":
    raise SystemExit(main())

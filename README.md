# Daily Market Report — Dashboard & Automation

Pipeline otomatis untuk **Market Today** (FX, indices, yield SBN/SBSN, BI Rate, spread, chart Rate Differential).

```
Market Data (yfinance + PHEI + BI)
        ↓
Python (fetch + calculate daily change)
        ↓
Generate Charts
        ↓
Streamlit Dashboard  +  PDF Report
```

---

## Acuan proyek

- [Project Brief](PROJECT_BRIEF.md): tujuan produk, pengguna, fitur, data, pengalaman pengguna, operasional, roadmap, dan kriteria keberhasilan.
- [Rancangan migrasi](project_migration.md): arah arsitektur dan rencana migrasi bertahap.

README ini berisi panduan instalasi dan penggunaan teknis. Kondisi produk serta progres pengembangan dirangkum dalam Project Brief.

## 1. Instalasi

Python 3.10 atau lebih baru diperlukan. Buat virtual environment, lalu pasang dependensi
(Streamlit 1.50 atau lebih baru diperlukan untuk fragment dan API tampilan yang dipakai):

### Windows (PowerShell)

```bash
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Dependencies utama: `streamlit`, `yfinance`, `pandas`, `matplotlib`, `reportlab`, `beautifulsoup4`, `requests`.

### Penyimpanan laporan dan riwayat versi

Secara default, aplikasi tetap memakai JSON lokal. Setiap laporan yang diterbitkan disimpan
sebagai versi di `data/report_data_versions/`, sedangkan `data/report_data.json` menunjuk
versi aktif. Riwayat SBN juga diarahkan ke repository yang sama. Untuk mulai memakai
PostgreSQL, salin `.env.example` menjadi `.env`, isi kredensial database, lalu impor data
lokal dengan:

```powershell
python src/migrate_reports_to_postgres.py
python -m streamlit run src/app.py
```

Skrip migrasi menerapkan schema pada berkas `migrations/` secara otomatis. `DATABASE_URL`
dipakai oleh layanan laporan untuk membaca dan menerbitkan versi. Tanpa
variabel tersebut, layanan memakai repository JSON. Lakukan backup data JSON sebelum impor;
skrip mempertahankan semua versi arsip yang memiliki ID, mengimpor hingga 30 titik riwayat
SBN, dan menjadikan laporan aktif lokal sebagai versi aktif terakhir.
Seluruh kolom tanggal pada tabel PostgreSQL memakai nama `dates`.

Untuk menerapkan perubahan schema tanpa mengimpor ulang snapshot lokal, jalankan:

```powershell
python src/apply_schema_migrations.py
```

Perintah ini aman dijalankan berulang. `migrate_reports_to_postgres.py` tetap dipakai
untuk impor awal karena perintah tersebut juga dapat menjadikan snapshot lokal sebagai
laporan aktif database.

### API dan worker (tahap transisi)

FastAPI dapat dijalankan berdampingan dengan Streamlit. API memuat konfigurasi `.env` yang
sama dan membaca repository laporan yang sama:

```powershell
python -m uvicorn api.main:app --app-dir src --host 127.0.0.1 --port 8000
```

- `GET http://127.0.0.1:8000/api/v1/reports/latest` — laporan aktif.
- `GET http://127.0.0.1:8000/api/v1/reports/{report_id}` — versi tertentu.
- `GET http://127.0.0.1:8000/api/v1/instruments/{instrument_id}/history?from=2026-01-01&to=2026-12-31` — riwayat instrumen.
- `GET http://127.0.0.1:8000/api/v1/market/live` — kutipan live dengan cache 30 detik per proses.
- `POST http://127.0.0.1:8000/api/v1/refresh-jobs` — antrekan refresh (Bearer `API_OPERATOR_TOKEN`).
- `GET http://127.0.0.1:8000/api/v1/jobs/{job_id}` — status dan rangkaian event job.
- `GET http://127.0.0.1:8000/health` — status proses API.
- `GET http://127.0.0.1:8000/docs` — dokumentasi interaktif.

ID riwayat yang tersedia: `sbn-10y`, `us-10y`, `us-5y`, `usd-idr`, `eur-idr`, `cny-idr`,
`jpy-idr`, `dxy`, `ihsg`, `dji`, `gold`, `brent`, dan `wti`. Instrumen yang dikenal tetapi
belum memiliki seri tersimpan mengembalikan daftar titik kosong.

API baca memerlukan header `Authorization: Bearer <API_READ_TOKEN>`. Isi token acak di `.env`
(dapat dibuat dengan `python -c "import secrets; print(secrets.token_urlsafe(32))"`). Simpan
token di server pemanggil, bukan di kode browser. Endpoint refresh memakai token terpisah
`API_OPERATOR_TOKEN`; permintaan duplikat memakai kembali job yang masih antre atau berjalan.

Jalankan worker dalam terminal/proses terpisah:

```powershell
python src/worker/main.py
```

Worker memproses satu refresh pada satu waktu, mencoba ulang kegagalan hingga tiga kali,
memperpanjang lease setiap 30 detik, dan memulihkan job setelah lease dua menit kedaluwarsa.
Worker lama yang kehilangan kepemilikan tidak dapat menerbitkan laporan.
Setelah report terbit, worker juga mencoba menyimpan PDF laporan ke `reports/`; kegagalan
PDF dicatat di log dan tidak membatalkan laporan yang sudah berhasil diterbitkan.
Saat `DATABASE_URL` diatur, tombol refresh dashboard dan perintah CLI live memasukkan job
ke antrean ini. Jalankan worker agar permintaan diproses; setelah status berhasil, muat ulang
dashboard untuk melihat laporan terbaru. Mode tanpa PostgreSQL mempertahankan refresh lokal.

---

## 2. Menjalankan Dashboard (Streamlit)

```bash
python -m streamlit run src/app.py
```

Browser akan terbuka di **http://localhost:8501**.
Jika menggunakan virtual environment, aktifkan dahulu seperti langkah instalasi di atas.

### Isi sidebar

| Kontrol | Kegunaan |
|---------|----------|
| **Status data** | Menampilkan mode (**LIVE** / **DEMO**), tanggal laporan, dan waktu snapshot yang sedang tampil. |
| **🔄 Perbarui data dari sumber (live)** | Mengambil data dari Yahoo, PHEI, dan BI, menghitung ulang, lalu memuat ulang halaman. Perlu koneksi internet yang mengizinkan akses ke sumber-sumber tersebut. |
| **Ambil data otomatis bila snapshot belum ada** | Kalau `data/report_data.json` belum ada, dashboard mengambil data sendiri saat pertama dibuka. |
| **Tampilkan bagian teknis (sumber data)** | Dimatikan bila halaman hanya dipresentasikan ke pembaca non-teknis (menyembunyikan bagian Sumber Data & Metode). |

### Cara agar data selalu ter-update di dashboard

1. Buka sidebar → cek **status data** (mode dan waktu snapshot).
2. Klik tombol **🔄 Perbarui data dari sumber (live)**.
3. Jika minimal dua instrumen berhasil dibaca, laporan disimpan dan halaman dimuat ulang. Jika data tidak cukup, aplikasi menampilkan pesan gagal dan tetap memakai laporan terakhir.

Saat aplikasi dijalankan di lingkungan yang membatasi akses jaringan (misalnya sandbox),
semua sumber live dapat gagal dengan `WinError 10013`. Jalankan Streamlit dari terminal
yang memiliki akses internet, lalu gunakan tombol pembaruan di sidebar.

### Mode terang & gelap

Panel **🎨 Kustomisasi tampilan** (ikon palet di kanan atas) menyediakan tombol
**☀️ Terang / 🌙 Gelap**, pengatur skala teks, dan pilihan warna aksen. Pilihan
disimpan di `localStorage`, jadi mode gelap tidak hilang saat Streamlit
me-render ulang halaman (mis. ketika expander dibuka).

Widget bawaan Streamlit — `st.expander`, `st.container(border=True)`, dan
`st.info` / `st.error` — warnanya berasal dari **tema Streamlit**, bukan dari
token aplikasi. Karena itu tiap warna ditulis eksplisit di kedua mode lewat
token `--mt-native-*`. Tanpa itu, mode terang akan menampilkan teks putih di
atas panel putih — termasuk di bagian **Sumber Data & Metode**.

Setiap latar bertumpuk (`stApp`, `stAppViewContainer`, `stMain`) juga
diikutkan agar tidak ada panel putih tertinggal di tengah mode gelap.

Untuk memastikan, jalankan:

```bash
python tools_cek_kontras.py   # mengukur rasio kontras WCAG di kedua mode
```

---

## 3. Susunan halaman & cara membacanya

Halaman disusun mengikuti cara orang membaca: **inti lebih dulu, detail kemudian** — dan memakai
**jarak putih + tab** supaya tidak terasa seperti laporan bertumpuk. Bagian tidak lagi diberi
nomor; tiap bagian ditandai pil kecil + judul besar.

| Bagian | Isi |
|--------|-----|
| **Header** | Angka paling penting (Rupiah, IHSG, SBN 10Y, spread SBN–UST) + sentimen harian. |
| **Insight Hari Ini** | Satu paragraf ringkasan otomatis, lalu 3 kartu sorotan (angka + artinya). Sisanya dilipat di "Sorotan lain hari ini". |
| **Apa Artinya untuk Anda** | Dampak praktis: belanja luar negeri, cicilan/kredit, tabungan & obligasi, harga barang. |
| **Angka Kunci Hari Ini** | 4 kartu besar (USD/IDR, IHSG, SBN 10Y, spread) + 4 kartu pendukung (DXY, UST 10Y, emas, Brent) + baris chip BI Rate / INDONIA / JISDOR. |
| **Grafik** | Dua grafik dengan **angka yang diambil ulang otomatis** + tombol **🔄 Perbarui sekarang**. |
| **Detail Pasar** | Empat tabel dalam tab: Nilai Tukar, Pasar Saham, Imbal Hasil Obligasi, Komoditas. |
| **Glossarium Istilah & Cara Membaca** | Kamus istilah + panduan membaca 30 detik (bertab). |
| **Unduh Laporan (PDF)** | PDF disusun dari angka yang sedang tampil (tombol 📄 Unduh PDF), plus tombol ambil data terbaru & simpan arsip. |
| **Sumber Data & Metode** | Bagian teknis (opsional): sumber per instrumen, seri, dan waktu pengambilan data. |

### Tampilan PDF

PDF disusun sebagai laporan korporat 3 halaman, memakai design token yang sama
dengan dashboard agar terlihat satu produk:

| Bagian | Isi |
|--------|-----|
| **Kop** | Bar aksen di tepi atas, judul *Market Today*, tanggal laporan + jam snapshot. |
| **Angka Kunci** | Lima kartu (USD/IDR, IHSG, SBN 10Y, UST 10Y, Spread) dengan nilai besar dan perubahan berwarna. |
| **Ringkasan Singkat** | Call-out dengan bar aksen kiri; versi bahasa sederhana untuk pembaca non-ekonom. |
| **Sesi 1–5** | Tabel bernomor: Exchange Rate, Financial Market, Yield, Monetary Policy, Commodities. |
| **Sesi 6–7** | Grafik *Rate Differential* dan *Pergerakan Kurs*, masing-masing berbingkai + caption sumber. |
| **Sesi 8** | Tabel sumber per kelompok instrumen, catatan metode, dan disclaimer. |
| **Setiap halaman** | Kepala halaman berjalan, footer sumber, dan nomor **Halaman X dari Y**. |

Detail yang disengaja:
- **Warna mengikuti arah dampak.** Pada kurs, angka positif berarti rupiah melemah
  sehingga merah; pada saham dan imbal hasil, naik = hijau.
- **Panah arah digambar sebagai vektor**, bukan karakter Unicode, karena font
  dasar PDF tidak menyediakan glyph segitiga.
- **Grafik tidak diregangkan** — ukuran diambil dari berkas PNG itu sendiri.
- **Font tetap Helvetica** agar teks bisa dicari/dicopy dan ukuran berkas kecil.
- **Metadata PDF** (judul, penulis, subjek) ikut diisi agar rapi di file manager.
- **`report_pdf` tidak mengimpor `app.py`.** Modul PDF tidak menggambar grafik
  sendiri; pemanggil menggambarnya lalu meneruskan path-nya lewat
  `chart_path` / `fx_chart_path`. Alasannya: Streamlit menjalankan `app.py`
  sebagai `__main__`, sehingga `import app` dari dalam fungsi ber-`@st.cache_data`
  akan mengeksekusi ulang seluruh skrip dan memicu `CachedWidgetWarning`.

### Angka langsung (grafik yang benar-benar bergerak)

Bagian **Grafik Bergerak Langsung** memakai angka yang **diambil ulang dari Yahoo Finance**
(intraday), bukan snapshot harian — sehingga angkanya berubah setiap kali disegarkan.

| Kontrol | Kegunaan |
|---------|----------|
| **Segarkan otomatis** | `Manual` (hanya saat tombol ditekan) / `30 detik` / `1 menit` / `5 menit`. Penyegaran berjalan di `st.fragment`, jadi hanya bagian grafik yang dirender ulang, bukan seluruh halaman. |
| **🔄 Perbarui sekarang** | Mengambil angka baru seketika (menambah `nonce`, sehingga cache 45 detik dilewati). |
| **Papan status chip** | Angka per kelas aset; baris atas menuliskan jumlah instrumen yang ter-update dan pukul waktunya, atau **SNAPSHOT LAPORAN** bila sumber sedang tidak terjangkau (grafik lalu memakai angka laporan). |

Dua sumber angka sengaja dibedakan agar tidak saling bertentangan:

- **Snapshot harian** (`data/report_data.json`) → header, kartu angka kunci, seluruh tabel, PDF.
- **Harga terkini** (Yahoo Finance) → grafik saja, dengan stempel waktu di kaki grafik.

Riwayat SBN 10Y dikumpulkan sendiri oleh dashboard di `data/history_sbn.json` (satu titik per
tanggal, maksimum 30 hari). Karena PHEI hanya menerbitkan satu angka terakhir, garis SBN di
grafik dulu selalu datar; setelah beberapa hari dashboard dibuka, garisnya menjadi kurva sungguhan.

Prinsip keterbacaan lain yang tetap berlaku:

- **Warna punya arti yang konsisten**: hijau = cenderung menguntungkan, merah = cenderung memberatkan, abu-abu = relatif stabil.
- **Arah selalu ditulis dengan kata**, bukan hanya simbol: "▲ Rupiah melemah", "▼ Rupiah menguat", "▬ relatif stabil".
- **bp dijelaskan**: 1 bp = 0,01%.
- **Tanggal data ditampilkan** (data PHEI/BI bisa satu hari lebih lama dari kurs/saham).

### Pengaturan tampilan (opsional, tanpa mengubah data)

Klik tombol **🎨** di pojok kanan bawah halaman:

- **Ukuran teks** — Kecil / Normal / Besar (berguna untuk presentasi proyektor).
- **Warna aksen** — Teal / Biru / Ungu / Cokelat.
- **Mode tampilan** — Terang / Gelap.

Pengaturan ini hanya menyuntikkan CSS/JS ke browser saat itu: tidak disimpan ke file, cookie, atau data. Refresh halaman = kembali ke tampilan asli.

Data yang di-update:
- USD/IDR, DXY, EUR/IDR, CNY/IDR, JPY/IDR, SAR/IDR  
- IHSG, DJI  
- US Treasury 5Y / 10Y  
- Yield curve SBN + benchmark SBSN (dari [PHEI](https://www.phei.co.id/Data/HPW-dan-Imbal-Hasil))  
- BI Rate, INDONIA (Bank Indonesia)  
- Spread SBN 10Y − UST 10Y  
- Chart Rate Differential & FX Change %

Setelah live fetch, file berikut ikut ter-update:
- `data/snapshot.json` — raw data
- `data/report_data.json` — angka siap report
- `charts/rate_differential.png` (dari data snapshot, bukan angka contoh)
- `reports/Daily_Market_Update_YYYYMMDD.pdf` — nama file memakai tanggal laporan; file yang diunduh
  dashboard dibuat on-the-fly dari angka yang tampil (tidak memakai file lama di folder ini)

---

## 4. CLI Pipeline (tanpa Streamlit)

```bash
# Demo (angka sample)
python src/run_pipeline.py --demo

# PostgreSQL: masukkan refresh ke antrean worker
python src/run_pipeline.py

# Mode JSON lokal saja: pakai snapshot yang sudah ada (cepat, offline)
python src/run_pipeline.py --no-fetch
```

Dalam mode PostgreSQL, perintah live mengantrekan refresh lalu keluar; worker harus
berjalan terpisah. Worker menyimpan PDF laporan ke `reports/` setelah laporan berhasil
diterbitkan. Dalam mode JSON lokal, CLI tetap menjalankan pipeline dan membuat keluaran
secara langsung.

Output CLI mode JSON lokal:
- Console summary (USD/IDR, DXY, yield, BI Rate, spread)
- PDF di `reports/`
- Chart di `charts/`

---

## 5. Agar data selalu update otomatis (tanpa klik manual)

Dashboard **tidak** fetch sendiri setiap detik. Agar data selalu fresh, jalankan pipeline secara berkala.

### Opsi A — Cron (Linux / macOS)

Edit crontab:

```bash
crontab -e
```

Contoh: update setiap hari kerja jam **16:30 WIB** (setelah pasar tutup):

```cron
30 16 * * 1-5  cd /path/ke/daily_market_report && /usr/bin/python3 src/run_pipeline.py >> logs/pipeline.log 2>&1
```

Lalu buka dashboard kapan saja — data sudah terisi dari cron, jadi tidak perlu klik apa pun di sidebar.

### Opsi B — Task Scheduler (Windows)

1. Buka **Task Scheduler** → Create Basic Task.
2. Trigger: Daily, jam 16:30.
3. Action: Start a program  
   - Program: `python`  
   - Arguments: `src/run_pipeline.py`  
   - Start in: folder `daily_market_report`

### Opsi C — Auto-refresh di dalam Streamlit (opsional)

Tambahkan di sidebar interval auto-rerun (contoh setiap 30 menit) dengan fragment / `st.rerun` + timer. Untuk produksi, lebih aman menjalankan cron (pipeline menyimpan snapshot ke `data/report_data.json`) lalu membiarkan dashboard menampilkan snapshot tersebut — sumber data (yfinance / PHEI) tidak dibebani permintaan berulang.

### Opsi D — Deploy online

- **Streamlit Community Cloud**: push repo, set main file `src/app.py`.  
  Untuk data live, gunakan tombol **🔄 Perbarui data dari sumber (live)** di sidebar atau schedule job terpisah (GitHub Actions) yang commit/update `data/report_data.json`.
- **Server sendiri**: `streamlit run src/app.py --server.port 8501` + reverse proxy (nginx) + cron pipeline.

---

## 6. Struktur folder

```
daily_market_report/
├── requirements.txt
├── README.md                 ← file ini
├── .gitignore                ← mengecualikan cache, data lokal, grafik, dan PDF hasil generate
├── src/
│   ├── app.py                ← Streamlit dashboard (tampilan utama)
│   ├── fetch_data.py         ← ambil data (yfinance, PHEI, BI)
│   ├── calculate.py          ← hitung change % / bp / spread
│   ├── charts.py             ← Rate Differential + FX chart
│   ├── report_pdf.py         ← generate PDF (+ ringkasan bahasa sederhana)
│   ├── run_pipeline.py       ← entry point CLI
│   ├── domain/               ← pencarian instrumen dan analisis pasar
│   ├── services/             ← pipeline laporan, data live, riwayat, dan ekspor PDF
│   ├── presentation/         ← format angka, metadata, warna, dan grafik
│   └── frontend/             ← tema, komponen, sidebar, header, aset CSS, dan tampilan per bagian
├── tests/
│   ├── smoke_app.py          ← uji cepat: render dashboard & cek bagian halaman
│   ├── test_live.py          ← uji logika angka langsung (overlay, riwayat, grafik)
│   ├── test_pipeline.py      ← uji validasi, penerbitan snapshot, dan pemisahan demo
│   └── test_pdf.py           ← uji PDF: isi PDF = angka yang tampil di dashboard
├── data/
│   ├── snapshot.json         ← raw fetch terakhir (lokal, tidak dilacak Git)
│   ├── report_data.json      ← data siap tampil di dashboard (lokal, tidak dilacak Git)
│   └── history_sbn.json      ← riwayat SBN 10Y berdasarkan tanggal publikasi (lokal)
├── charts/
│   └── *.png                 ← grafik hasil generate (lokal, tidak dilacak Git)
└── reports/
    └── *.pdf                 ← arsip PDF hasil generate (lokal, tidak dilacak Git)
```

Data pasar, riwayat, grafik, dan laporan PDF adalah keluaran lokal yang dikecualikan
oleh `.gitignore`. Simpan salinan di lokasi lain bila ingin mengarsipkannya atau
memindahkannya ke komputer lain.

### Uji cepat setelah mengubah tampilan

```bash
python tests/smoke_app.py   # render dashboard & cek isi halaman  → HASIL: PASS
python tests/test_live.py   # cek logika angka langsung & grafik  → HASIL: PASS
python tests/test_pipeline.py # cek penerbitan snapshot & isolasi demo → HASIL: PASS
python tests/test_pdf.py    # cek isi PDF = angka yang tampil      → HASIL: PASS
python tools_cek_pdf.py     # cetak teks PDF per halaman (untuk cek tampilan)
python tools_cek_kontras.py # ukur kontras teks di mode terang & gelap
```

`tools_cek_kontras.py` menjalankan dashboard sungguhan di browser, membuka
bagian **Sumber Data**, lalu mengukur rasio kontras WCAG tiap teks terhadap
latar induknya pada kedua mode. Ini menangkap kasus "teks putih di atas
panel putih" yang tidak terlihat dari screenshot biasa.

`smoke_app.py` menjalankan dashboard di runtime uji Streamlit lalu memeriksa: tidak ada error,
8 bagian halaman muncul berurutan, 5 tabel + 8 tab ter-render, 2 grafik benar-benar dirender,
tombol perbarui grafik ada, dan cuplikan teks tiap kartu.

`test_live.py` tidak butuh internet: ia menguji penggabungan angka langsung (harga terkini vs
snapshot), penghitungan ulang persentase/bp/spread, pembentukan deret harian, pengumpulan riwayat
SBN, jalur cadangan saat sumber tidak terjangkau, dan kedua pembuat grafik.

---

## 7. Sumber data

| Data | Sumber | Keterangan |
|------|--------|------------|
| FX, DXY, IHSG, DJI, US yields | Yahoo Finance (`yfinance`) | Real-time / delayed |
| SBN & SBSN yields | [PHEI HPW & Imbal Hasil](https://www.phei.co.id/Data/HPW-dan-Imbal-Hasil) | Update harian |
| BI Rate, INDONIA, JISDOR | Bank Indonesia | BI Rate setelah RDG; INDONIA harian |
| Gold / Oil | yfinance (`GC=F`, `CL=F`) | Logam Mulia ada CAPTCHA → fallback yfinance |
| Commodities lain | TradingEconomics / investing.com | Best-effort |

---

## 8. Tips operasional

1. **Setelah pasar tutup** (sekitar 16:00–17:00 WIB) → klik **🔄 Perbarui data dari sumber (live)** di sidebar, atau jalankan `python src/run_pipeline.py`.
2. Siang hari / presentasi → biarkan dashboard memakai snapshot terakhir (tidak perlu klik perbarui data) agar cepat dan stabil.
3. Jika PHEI atau BI lambat/error, pipeline tetap jalan dengan data yfinance; yield SBN bisa kosong sampai scraper sukses lagi.
4. PDF terbaru bisa di-download langsung dari tombol di bawah dashboard.
5. Jangan share `data/snapshot.json` ke publik jika berisi data internal; file ini hanya cache lokal.

---

## 9. Troubleshooting

| Masalah | Solusi |
|---------|--------|
| Data pasar kosong / pembaruan ditolak | Periksa pesan error dan `data/snapshot.json`; pastikan terminal memiliki akses internet ke Yahoo Finance dan PHEI, lalu klik **🔄 Perbarui data dari sumber (live)** lagi. Pembaruan dengan kurang dari dua instrumen berhasil ditolak agar tidak menimpa laporan yang ada. |
| Hanya sebagian instrumen yang muncul | Sumber berbeda dapat gagal secara terpisah. Cek bagian **Sumber Data & Metode** dan `data/snapshot.json`, lalu coba pembaruan lagi. |
| BI Rate / INDONIA / JISDOR tampak lama | Jika halaman BI tidak merespons, pipeline memakai angka cadangan; periksa tanggal pada bagian Sumber Data & Metode. |
| Perlu melihat data contoh | Jalankan `python src/run_pipeline.py --demo` hanya untuk demonstrasi lokal. Mode demo mengganti `data/report_data.json`. |
| Pembaruan data gagal | Cek koneksi dan akses jaringan ke sumber; coba lagi. Dashboard mempertahankan laporan terakhir yang berhasil disimpan. |
| Tampilan terasa berubah / tidak nyaman dibaca | Klik tombol **🎨** di pojok kanan bawah → **↺ Kembalikan tampilan asli**, atau refresh halaman (pengaturan tampilan tidak disimpan) |
| Perlu memastikan tampilan tidak rusak setelah diubah | Jalankan `python tests/smoke_app.py` (harus berakhir `HASIL: PASS`) |
| Chart tidak muncul | Pastikan `matplotlib` terinstall; jalankan pipeline sekali |
| Grafik tidak berubah saat disegarkan | Klik **🔄 Perbarui sekarang** (melempar cache), atau turunkan **Segarkan otomatis** ke 30 detik. Bila lencana tetap **SNAPSHOT LAPORAN**, sumber sedang tidak terjangkau — grafik memakai angka laporan |
| Angka grafik berbeda dari kartu/tabel | Itu memang disengaja: grafik memakai harga terkini, kartu & tabel memakai snapshot laporan agar konsisten satu hari penuh |
| PDF yang diunduh berbeda dari layar | PDF disusun dari `report` yang sedang dirender, jadi keduanya sama. Yang berbeda hanya **Grafik Bergerak Langsung** (harga intraday) — PDF memakai snapshot. Nama file mengikuti `report_date_iso` |
| PDF lama muncul di folder `reports/` | Itu arsip hasil run sebelumnya. Tombol 📄 selalu memakai angka terkini; arsip lain hanya disebut sebagai catatan |
| Port 8501 dipakai | `streamlit run src/app.py --server.port 8502` |

---

## 10. Ringkasan alur “data selalu update”

```
Setiap hari (manual atau cron)
        │
        ▼
python src/run_pipeline.py     ← fetch live + calculate + chart + PDF
        │
        ▼
data/report_data.json ter-update
        │
        ▼
streamlit run src/app.py
  → Sidebar: cek status data; klik "🔄 Perbarui data dari sumber (live)" bila ingin angka real-time
  → Dashboard menampilkan angka & chart terbaru
  → Download PDF dari tombol di bawah
```

Dengan cara di atas, dashboard selalu menampilkan data ter-update tanpa harus mengisi angka manual.

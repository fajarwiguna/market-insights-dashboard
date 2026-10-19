# Rancangan: LLM Narator untuk Dashboard & Equity Snapshot

> **SUPERSEDED (2026-10-16):** dokumen ini digantikan oleh
> `docs/LLM_NARRATIVE_ENGINE_BLUEPRINT.md` (blueprint lengkap, 22 bagian).
> Disimpan hanya sebagai jejak keputusan awal.

> Status: rancangan untuk ditinjau, bukan implementasi.
> Tujuan: memberi “otak” narasi yang menyusun ringkasan, insight, dan komentar
> pasar dari angka dashboard yang sudah ditampilkan, plus konteks pasar terkini
> lewat web search.

## 1.Apa yang ingin diselesaikan

Saat ini:

- ringkasan dan insight dibangun dari template/fungsi statis
  (`market_report/domain/market_analysis.py`, `report_pdf.py`, dan komponen
  dashboard frontend);
- equity snapshot masih mengandalkan data contoh dan editor manual di browser;
- sistem belum punya mekanisme contextual search atau pembentukan narasi yang
  lebih dinamis, tapi **angka tetap harus tetap angka dashboard.

Yang diinginkan pengguna:

- LLM dapat membaca angka utama yang sudah ditampilkan di dashboard/equity,
- LLM dapat mencari kondisi pasar/ekonomi terkini (web search),
- LLM menyusun narasi yang relevan untuk dashboard utama dan equity snapshot,
- ada batasan/rule yang tertulis dalam file markdown dan harus dipatuhi.

## 2.Prinsip utama

1. Angka utama tetap diambil dari data dashboard/report yang sudah ada.
   LLM tidak boleh “mengarang” angka.
2. Web search hanya untuk konteks, bukan untuk mengganti data pasar yang sudah
   disimpan di sistem.
3. Semua narasi hasil LLM harus dapat dilacak asal-usulnya (data apa yang
   dibaca, konteks search apa yang dipakai, batasan apa yang dipatuhi).
4. Rule dan limit ditulis dalam file markdown, bukan hanya di kode.
5. Backend tetap jadi tempat pembentukan narasi agar frontend tidak perlu
   memanggil LLM/search secara langsung dari klien.

## 3. Cara LLM “membaca” angka utama

Proposal alur:

1. Frontend/dashboard meminta ringkasan/insight dari backend.
2. Backend mengambil data laporan terakhir (`getLatestReport`, `market_facts`,
   `instrument_history`, dll.) yang sudah ada.
3. Backend membentuk **konteks angka yang aman** yang akan diberikan ke LLM:
   - nilai utama (mis. USD/IDR, IHSG, SBN 10Y, UST 10Y, emas, brent, BI Rate,
     indeks global tertentu),
   - perubahan (change/difference),
   - tanggal observasi masing-masing,
   - sumber per angka (jika tersedia),
   - informasi yang relevan untuk equity jika narasi equity diminta.
4. Konteks ini tidak berisi semua data mentah, hanya yang relevan dan sudah
   distandarisasi.

Hal yang penting: **LLM mendapat angka yang sama yang ditampilkan di dashboard**,
bukan angka tambahan rahasia atau angka yang belum diverifikasi.

## 4.Posisi web search

Web search digunakan untuk:

- situasi pasar terkini (mis. berita/kalender ekonomi yang relevan),
- konteks tambahan yang tidak tersedia dari snapshot/report hari ini,
- pembanding bahasa/narasi jika diperlukan.

Batas yang disepakati secara konseptual:

- search dilakukan di backend, bukan di browser,
- hasil search tidak boleh mengubah angka dashboard,
- hanya sebagian hasil yang relevan dipakai sebagai konteks narasi,
- sumber search harus dicatat (judul/sumber/waktu) jika dipakai dalam narasi.

Jika ada rule di file markdown yang melarang atau membatasi search pada kali
tertentu, sistem harus mematuhi rule itu.

## 5.Model LLM sebagai “otak narasi”

Cara berpikir sistem:

- input: (a) angka dashboard/equity yang sudah distandarisasi, (b) konteks
  search/situasi pasar yang relevan
- tugas: menyusun ringkasan, insight, dan/atau komentar untuk dashboard
  utama atau equity snapshot
- output: teks narasi + metadata pendukung (mis. sumber konteks yang dipakai,
  jenis narasi, tanggal)

Sebaiknya:

- ada fungsi/service khusus yang hanya bertugas menyiapkan prompt dan
  memvalidasi output,
- fungsi ini berada di backend, misalnya di area
  `market_report/services/narration_service.py` atau ekstensi dari domain
  `market_report/domain`,
- ada pemisahan antara pengambilan data dan pembentukan narasi,
- ada rule engine atau validasi terpisah yang memastikan output tidak
  melanggar limit.

## 6.Rule dan limit yang harus dipatuhi

Rancangan ini mengasumsikan rule ditulis dalam file markdown yang bisa dibaca
 sistem, misalnya file baru khusus untuk “naluri/petunjuk LLM” atau sebagai
 bagian dari dokumen kebijakan yang sudah ada.

Contoh kategori rule yang perlu ada:

### 6.1 Batas angka
- LLM tidak boleh membuat/mengarang angka utama.
- Jika angka tidak ada, LLM harus menyatakan tidak tahu/memarkan sesuai
  konvensi, bukan menebak.
- LLM hanya boleh menggunakan angka yang diberikan melalui konteks yang telah
  disaring.

### 6.2 Batas kutipan
- Jika search dipakai, kutipan/fakta yang dipakai harus diidentifikasi
  sumbernya.
- Larangan memakai pernyataan tanpa sumber yang bisa ditelusuri.

### 6.3 Batas topik
- LLM hanya membahas topik yang relevan dengan instrumen/data yang dimiliki.
- Tidak boleh menyimpulkan hal di luar data yang ada.
- Tidak boleh menampilkan prediksi yang dipositioning sebagai fakta.

### 6.4 Batas gaya/format
- Bahasa dan struktur narasi harus sesuai standar yang ditulis di markdown
  (panjang, nada, cara menyebut satuan, cara menyebut periode, dll.).
- Aturan tampilan angka harus konsisten dengan formatting yang sudah ada.

### 6.5 Batas waktu/a veröffentlichung
- Narasi harus menyebut tanggal observasi dan/atau waktu publikasi jika
  relevan, sesuai konteks yang diberikan.
- Batasan freshness data harus tetap dipatuhi (mis. data utama masih harus
  mematuhi aturan usia data yang berlaku di project).

### 6.6 Batas hak akses/privasi
- LLM tidak boleh diekspos ke klien tanpa kontrol yang sesuai.
- API/search/LLM key tidak boleh bocor ke frontend.

## 7.Posisi file markdown sebagai hakim

File markdown harus berfungsi sebagai:

1. tempat menulis “aturan bermain” untuk LLM,
2. tempat menulis batasan yang bisa diverifikasi/dicek oleh kode,
3. tempat menentukan kapan fitur boleh dipakai, kapan tidak,
4. tempat mendokumentasikan kontrak antara “input yang boleh diberikan ke LLM”
   dan “output yang boleh ditampilkan ke pengguna.

Saran penempatan:

- bisa satu file khusus, misalnya di root docs atau di backend/docs,
- atau bagian baru dalam PROJECT_BRIEF.md / dokumen kebijakan lain yang sudah
  ada, tergantung keputusan struktur dokumen project.

Yang penting: **satu sumber kebenaran untuk rule**, dan kode harus bisa
mengacu ke file itu.

## 8.Contoh alur kerja yang diusulkan

### 8.1 Alur dashboard utama
1. request ringkasan/insight
2. ambil laporan terbaru + fakta utama
3. ambil konteks search jika diperlukan dan diizinkan
4. bangun prompt terstruktur dari angka + konteks + rule ringkas
5. panggil LLM
6. validasi output: tidak ada angka yang dicipta, tidak ada klaim tanpa
   konteks, tidak melanggar rule
7. kembalikan ke frontend

### 8.2 Alur equity snapshot
Mirip, tapi konteksnya berfokus pada:
- headline equity,
- indeks/sector yang relevan,
- arus modal/foreign flow jika tersedia,
- batubara/komoditas pendukung jika relevan,
- konteks pasar saham/global jika diminta.

## 9.Pending issues (masih perlu keputusan)

1. File markdown untuk rule: nama, lokasi, dan struktur konten.
2. Model LLM dan cara autentikasinya: apakah pakai provider tertentu,
   apakah key disimpan di environment, apakah ada fallback jika LLM gagal.
3. Scope web search yang diizinkan vs tidak diizinkan untuk kasus tertentu.
4. Cara pembatasan biaya/pemakaian: apakah ada batas pemanggilan per laporan,
   per hari, atau per request.
5. Cara menangani kegagalan LLM: apakah sistem turun ke narasi statis/placeholder.
6. Seberapa banyak nilai yang diberikan ke LLM per request.
7. Apakah narasi LLM boleh masuk langsung ke laporan terbit, atau hanya ke
   tampilan dashboard/equity saja.

## 10.Rekomendasi tahap depan

Sebelum implementasi nyata:

1. Tentukan dulu file rule dan isinya (ini bisa jadi kunci review).
2. Tentukan API/provider LLM dan cara penyimpanan kuncinya.
3. Tentukan scope search yang diizinkan.
4. Tentukan contract: input apa yang masuk ke LLM, output apa yang boleh
   ditampilkan.
5. Buat fungsi pembungkus di backend yang mematuhi rule dan bisa dikembangkan
   perlahan.

## 11.Kontrak sederhana yang bisa ditulis di markdown

Contoh bentuk kontrak yang bisa disepakati:

- “LL hanya boleh membaca angka yang berasal dari laporan/dashboard yang sudah
  tersimpan.”
- “LL tidak boleh membuat angka berjalan, prediksi, atau pernyataan faktual
  tanpa sumber.”
- “Web search hanya untuk konteks yang relevan dan harus dicatat sumbernya.”
- “Jika rule di file ini bertentangan dengan kode, file ini menjadi acuan
  utama untuk perilaku fitur ini.”

## Catatan penutup

Rancangan ini belum menetapkan provider LLM, key, atau implementasi API
tertentu. Ia hanya menyusun batasan tanggung jawab, alur umum, dan posisi
file markdown sebagai pengendali perilaku LLM.

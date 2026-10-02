**Dokumen kerja sementara untuk migrasi bertahap ke FastAPI + Next.js.** Peta struktur proyek akhir pada bagian 2 menjadi acuan saat pemindahan kode. Simpan dokumen ini sampai semua tahap migrasi selesai dan struktur akhir diverifikasi; setelah itu pindahkan ringkasan yang masih diperlukan ke dokumentasi permanen dan hapus berkas ini sesuai arahan pemilik proyek.

Status implementasi berubah sejak rancangan awal: fondasi layanan, PostgreSQL, API, antrean refresh, dan worker telah dibuat. Lihat `PROJECT_BRIEF.md` untuk status produk dan roadmap terkini.

Asumsi kerja: aplikasi digunakan oleh tim internal, sebagian besar aktivitas berupa membaca laporan, dan pembaruan data dilakukan oleh operator atau scheduler. Rancangan ini menjadi peta migrasi; implementasi berjalan bertahap.

**1\. Arsitektur tujuan**

| Komponen | Pilihan | Tanggung jawab |
|---|---|---|
| Frontend | Next.js + TypeScript | Dashboard, tabel, grafik interaktif, pengaturan tampilan, dan unduhan |
| Backend | FastAPI | Kontrak API, validasi input, autentikasi, dan pemanggilan layanan aplikasi |
| Inti aplikasi | Python | Perhitungan pasar, analisis, kualitas data, dan penyusunan laporan |
| Penyimpanan | PostgreSQL | Snapshot, observasi, riwayat, status pekerjaan, dan versi laporan |
| Proses pekerjaan | Worker Python terpisah | Pengambilan sumber, pembaruan laporan, grafik, dan PDF |
| Penyimpanan berkas | Direktori persisten, kemudian object storage bila diperlukan | Arsip PDF dan respons sumber |
| Antarmuka transisi | Streamlit | MVP yang berjalan sampai frontend pengganti siap |

Backend tetap menjadi satu aplikasi modular. Worker memakai modul bisnis yang sama dengan API.

```
This Mermaid diagram uses features the terminal renderer doesn't support.
flowchart TD
    USER[Pengguna] --> WEB[Next.js]
    WEB --> API[FastAPI]
    OLD[Streamlit selama transisi] --> API

    API --> CORE[Layanan aplikasi dan domain Python]
    CORE --> DB[(PostgreSQL)]

    API --> JOB[Pekerjaan pembaruan atau ekspor]
    JOB --> WORKER[Worker Python]
    WORKER --> CORE
    WORKER --> SOURCE[Yahoo / PHEI / BI]
    WORKER --> FILES[Arsip sumber dan PDF]
```

FastAPI mendukung pemisahan endpoint melalui router modular. Next.js dapat memisahkan tampilan awal di server dari komponen interaktif di browser. Ini cocok untuk laporan yang dibaca terlebih dahulu, kemudian tabel dan grafik yang digunakan secara interaktif. [Dokumentasi FastAPI (https://fastapi.tiangolo.com/tutorial/bigger-applications/)](<https://fastapi.tiangolo.com/tutorial/bigger-applications/>), [dokumentasi Next.js (https://nextjs.org/docs/app/getting-started/server-and-client-components)](<https://nextjs.org/docs/app/getting-started/server-and-client-components>).

**2\. Struktur proyek yang dituju**

Struktur ini dibangun bertahap; modul dipindahkan setelah perilakunya memiliki pengujian.

```
daily_market_report/
├── backend/
│   ├── pyproject.toml
│   ├── src/market_report/
│   │   ├── domain/
│   │   │   ├── models.py
│   │   │   ├── calculations.py
│   │   │   └── analysis.py
│   │   ├── application/
│   │   │   ├── report_service.py
│   │   │   ├── refresh_service.py
│   │   │   └── export_service.py
│   │   ├── infrastructure/
│   │   │   ├── providers/
│   │   │   ├── repositories/
│   │   │   └── rendering/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   ├── schemas/
│   │   │   └── dependencies.py
│   │   ├── worker/
│   │   └── config.py
│   ├── migrations/
│   └── tests/
├── web/
│   ├── src/app/
│   ├── src/features/
│   │   ├── dashboard/
│   │   ├── market-monitor/
│   │   └── reports/
│   ├── src/components/
│   ├── src/lib/api/
│   └── tests/
├── legacy/streamlit/
├── deploy/
└── docs/
```

Pemetaan kode sekarang:

| Kode sekarang | Arah perubahan |
|---|---|
| `domain/market_analysis.py` | Pisahkan perhitungan/penilaian dari format angka dan HTML |
| `calculate.py` | Jadikan pembentukan laporan fungsi tanpa penulisan berkas |
| `fetch_data.py` | Pecah menjadi adapter Yahoo, PHEI, BI, dan sumber cadangan |
| `services/report_service.py` | Menjadi alur publikasi laporan bersama |
| `services/history_service.py` | Menyimpan observasi melalui repository |
| `report_pdf.py` dan pembuat grafik | Tetap Python; dipanggil oleh layanan ekspor |
| `frontend/` | Dipertahankan sebagai frontend Streamlit selama transisi |
| `app.py` | Menjadi pemanggil layanan atau API dengan tanggung jawab tampilan |

**3\. Kontrak data sebelum frontend baru**

Frontend baru harus menerima data terstruktur, bukan HTML atau hasil format angka dari backend.

Model utama:

| Model | Isi penting |
|---|---|
| `Instrument` | ID tetap, nama tampilan, kategori, satuan, kode sumber |
| `Observation` | Nilai, nilai pembanding, tanggal sumber, sumber, status kualitas |
| `Report` | ID laporan, versi schema, tanggal laporan, waktu dibuat, daftar observasi |
| `Insight` | Jenis analisis, instrumen terkait, arah, tingkat dampak, teks tanpa HTML |
| `Job` | Jenis pekerjaan, status, waktu mulai/selesai, percobaan, hasil atau error |
| `Artifact` | ID laporan, jenis berkas, lokasi, waktu dibuat |

Aturan yang perlu ditetapkan:

- Nilai kosong tetap `null`, bukan `"–"` atau `0`.
- `change_pct` dan `change_bp` memiliki satuan yang jelas.
- Tanggal berlaku sumber dibedakan dari waktu pengambilan.
- Timestamp disimpan dengan timezone; tampilan menggunakan Asia/Jakarta.
- Status data membedakan **tersedia, kedaluwarsa, fallback, dan tidak tersedia**.
- Ambang kedaluwarsa berbeda untuk BI Rate, kurs, dan yield harian.
- Data demo memiliki penanda dan lokasi penyimpanan terpisah.

Adapter sementara mengubah model ini ke bentuk `dict` lama agar Streamlit tetap bekerja.

**4\. Alur pembaruan yang konsisten**

Pembaruan berjalan sebagai satu pekerjaan:

```
Terima permintaan
→ Buat job
→ Ambil data sumber
→ Normalisasi dan validasi
→ Hitung laporan
→ Simpan versi baru
→ Aktifkan versi laporan secara transaksi
→ Tandai job selesai
```

Laporan aktif hanya berubah setelah seluruh tahap publikasi berhasil. Data pendukung, ringkasan, dan PDF selalu mengacu pada `report_id` yang sama.

Untuk pekerjaan bersamaan:

- Hanya satu pembaruan sumber yang aktif pada satu waktu.
- Permintaan berulang dapat mengembalikan job yang sedang berjalan.
- Worker memiliki batas percobaan dan mekanisme pemulihan setelah berhenti.
- Pengguna tetap membaca laporan terakhir selama pembaruan berlangsung.

Pengambilan data dan pembuatan PDF ditempatkan di worker terpisah karena perlu status serta pemulihan yang persisten. `BackgroundTasks` FastAPI tidak dijadikan mekanisme utama pekerjaan tersebut. [Panduan pekerjaan background FastAPI (https://fastapi.tiangolo.com/tutorial/background-tasks/)](<https://fastapi.tiangolo.com/tutorial/background-tasks/>).

**5\. API awal**

| Endpoint | Fungsi |
|---|---|
| `GET /api/v1/reports/latest` | Mengembalikan laporan aktif beserta ID versinya |
| `GET /api/v1/reports/{report_id}` | Membaca versi laporan tertentu |
| `GET /api/v1/instruments/{id}/history` | Riwayat instrumen dengan rentang tanggal |
| `GET /api/v1/market/live` | Data live beserta waktu dan status sumber |
| `POST /api/v1/refresh-jobs` | Meminta pembaruan; mengembalikan `202` dan ID job |
| `GET /api/v1/jobs/{job_id}` | Memeriksa status pembaruan atau ekspor |
| `POST /api/v1/reports/{report_id}/exports` | Meminta PDF untuk versi laporan tertentu |
| `GET /api/v1/artifacts/{artifact_id}` | Mengunduh hasil ekspor |

Pembaca memperoleh akses laporan. Operator memperoleh izin pembaruan. API mengatur izin ini meskipun tombolnya juga disembunyikan oleh frontend.

**6\. Rancangan frontend pengganti**

Konsep produk sekarang dipertahankan: ringkasan → dampak → angka kunci → grafik → detail → unduhan.

Frontend baru menyediakan:

- Header berisi tanggal laporan, waktu sumber, dan status kualitas.
- Kartu KPI serta insight menggunakan komponen yang konsisten.
- Grafik interaktif dengan tooltip dan pilihan rentang.
- Tabel yang dapat dicari dan diurutkan.
- Status pembaruan tanpa memblokir halaman.
- Pengaturan tema dan ukuran teks.
- Tampilan loading, data kosong, data parsial, dan sumber gagal.
- Unduhan yang menyebut versi laporan dan waktu datanya.

Pembacaan awal laporan menggunakan server component. Grafik, filter, tema, dan polling menggunakan client component. Polling menjadi mekanisme awal pembaruan tampilan; intervalnya ditetapkan berdasarkan frekuensi data sumber.

**7\. Tahapan migrasi**

| Tahap | Hasil yang dikerjakan | Kriteria selesai |
|---|---|---|
| **1 — Stabilkan inti** | Satukan jalur dashboard/CLI, pisahkan demo, buat model dan fixture | Perhitungan dapat diuji tanpa Streamlit atau jaringan |
| **2 — Konsistensi penyimpanan** | Repository, PostgreSQL, migrasi data lokal, versi laporan | Snapshot dan observasi aktif konsisten; kegagalan tidak mengganti laporan aktif |
| **3 — FastAPI** | Endpoint baca, schema, otorisasi, pengujian kontrak | API dan Streamlit menghasilkan angka sama untuk `report_id` yang sama |
| **4 — Worker** | Pembaruan terpisah, scheduler, status job, ekspor | Refresh tetap berjalan tanpa halaman terbuka dan dapat pulih setelah worker berhenti |
| **5 — Next.js versi baca** | Ringkasan, KPI, tabel, sumber, dan tampilan responsif | Tampilan baru setara dengan fitur baca MVP |
| **6 — Fitur interaktif** | Grafik live, refresh operator, PDF, tema | Seluruh alur utama lulus pengujian menyeluruh |
| **7 — Peralihan** | Pilot pengguna, pemantauan, pengalihan alamat utama | Frontend baru memenuhi kriteria penerimaan dan jalur kembali tersedia |

Pada tahap 3–4, Streamlit diarahkan ke layanan yang sama, lalu ke API. Setelah itu, hanya worker yang menerbitkan pembaruan. Ini mencegah frontend lama dan baru menjadi dua penulis yang memiliki aturan berbeda.

**8\. Deployment dan kriteria peralihan**

Deployment awal menggunakan satu lingkungan dengan layanan web, API, worker, dan database. Reverse proxy menyediakan satu alamat aplikasi serta jalur `/api`. Database dan arsip memakai penyimpanan persisten. Next.js juga mendukung deployment pada server sendiri. [Panduan self-hosting Next.js (https://nextjs.org/docs/app/guides/self-hosting)](<https://nextjs.org/docs/app/guides/self-hosting>).

Sebelum peralihan, wajib tersedia:

- Pengujian domain, parser sumber, API, dan alur pengguna dengan fixture tetap.
- Pemeriksaan kesamaan angka antara dashboard lama, frontend baru, dan PDF.
- Log pekerjaan, status sumber, serta pemantauan umur data.
- Backup database dan pemeriksaan pemulihan.
- Autentikasi yang sesuai lingkungan internal, serta izin pembaruan.
- Versi dependensi yang dikunci dan pipeline CI.
- Pengujian beban berdasarkan target jumlah pengguna yang disepakati.

Rollback frontend dilakukan dengan mengembalikan alamat utama ke Streamlit. Keduanya tetap memakai API dan data yang sama, sehingga rollback tidak membutuhkan penyalinan data balik.


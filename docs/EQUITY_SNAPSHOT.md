# Data otomatis Equity Snapshot

Halaman `/equity-snapshot` membaca snapshot terakhir melalui Next.js `/api/equity/snapshot` dan API internal `/api/v1/equity/latest`. Token baca tetap di server. Backend mengambil data dengan Python yfinance; browser tidak mengunduh ratusan saham.

Refresh pipeline/worker yang sudah ada kini mengambil data equity juga. Scheduler memakai `REFRESH_TIMES` dan `REFRESH_TIMEZONE` yang sudah tersedia; gunakan slot sesudah 17:00 Asia/Jakarta untuk laporan sesi yang baru selesai. Sebelum 17:00, candle hari ini dikecualikan. Pada hari libur, tanggal laporan mengikuti sesi IHSG terakhir yang tersedia. Indeks luar negeri memakai dua sesi terakhir hingga tanggal laporan, dengan tanggal masing-masing di payload.

Untuk refresh equity saja dari root proyek (PowerShell):

```powershell
$env:PYTHONPATH = 'backend/src'
.\.venv\Scripts\python.exe -m market_report.services.equity_snapshot_service
```

Snapshot disimpan atomik di `runtime/data/equity_snapshot.json`, dengan versi di `runtime/data/equity_versions/`. Kegagalan refresh tidak menggantikan snapshot valid sebelumnya. Data tidak tersedia ditampilkan `—`, bukan nol atau contoh lama. Refresh browser mengembalikan data snapshot; perubahan analis bersifat sementara.

## Kontribusi poin adalah estimasi

Yahoo tidak memberikan bobot resmi atau kontribusi poin IHSG. Universe menggunakan saham EQUITY berkode empat huruf dari screener exchange JKT; ini belum merupakan validasi konstituen IHSG resmi. Per saham:

`poin = IHSG penutupan sebelumnya × (harga sebelumnya × shares outstanding / total kapitalisasi sebelumnya saham valid) × return harian`

Shares outstanding adalah proxy terkini dari Yahoo, bukan seri historis saham beredar/free float. Coverage mengukur kelengkapan saham dalam universe Yahoo yang ditemukan, bukan coverage bobot resmi IHSG. Payload mencatat jumlah saham, pengecualian, kelengkapan penemuan, selisih total estimasi terhadap perubahan IHSG aktual, serta status keanggotaan belum terverifikasi. Harga atau saham beredar hilang, sesi tidak cocok, dan stock split pada sesi laporan dikecualikan. Ranking menggunakan nilai sebelum pembulatan, mengambil positif terbesar dan negatif paling rendah, maksimal sepuluh masing-masing; return nol tidak masuk.

Sektor adalah klasifikasi Yahoo, bukan pemetaan IDX-IC. Override metadata opsional di `runtime/data/equity_registry.json` memakai objek per ticker, misalnya `{"ABCD":{"eligible":false},"EFGH":{"sector":"Energy"}}`. Registry diterapkan saat penemuan universe harian; hapus cache `equity_universe.json` jika ingin perubahan berlaku pada refresh hari yang sama. Harga tetap dari yfinance.

Daftar Market Performance tetap 19 indeks. Untuk indeks sektor tanpa histori chart, backend memakai quote yfinance bertanggal sesi laporan dan previous close quote tersebut. Quote sesi lain ditolak. Simbol yang tidak tersedia tetap ada dengan `—`; tanggal setiap indeks dapat dilihat dengan hover baris. yfinance tidak menyediakan foreign flow negara, inflasi Indonesia, ataupun benchmark batubara yang sesuai gambar; bagian tersebut sengaja kosong/default faktual dan bisa dilengkapi analis.

## Edit dan PDF

Edit membuka semua teks. Ctrl+B/I/U memformat seleksi tanpa toolbar. Usulan saham tersedia di bawah dokumen saat mode edit, berdasarkan kontribusi dan sektor penggerak; klik menambahkan kalimat faktual ke narasi, atau ketik/hapus kode secara langsung. Sorotan emas mengikuti kode saham yang benar-benar ada dalam paragraf narasi, termasuk teks dengan format inline. Simpan mengunci DOM yang sudah diedit. Download mengambil DOM terbaru walaupun belum Simpan. Kontrol, usulan, dan catatan coverage berada di luar area ekspor; ukuran dan alur ekspor satu halaman A4 sebelumnya dipertahankan.

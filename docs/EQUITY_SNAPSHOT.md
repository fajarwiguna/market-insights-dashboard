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

Daftar Market Performance tetap 19 indeks. Untuk indeks sektor tanpa histori chart, backend memakai quote yfinance bertanggal sesi laporan dan previous close quote tersebut. Quote sesi lain ditolak. Simbol yang tidak tersedia tetap ada dengan `—`; tanggal setiap indeks dapat dilihat dengan hover baris.

Jika hasil unduhan equity tidak cukup untuk indeks sektor, adapter membaca `index_sectors` pada laporan utama sebagai fallback dengan pemetaan kode IDX-IC tetap. Level dan DtD harus valid dan tanggal harus tepat sama dengan sesi equity; WtD/MtD/YtD tidak digunakan sebagai DtD. Data equity yang sudah lengkap untuk sesi tersebut dipertahankan. Narasi sektoral memakai perubahan indeks sektor ketika sebelas indeks tersedia.

Saat refresh intraday membuat quote laporan utama lebih baru dari sesi dokumen, fallback membaca dua tanggal tepat dari `_source_snapshot._index_sector_history`: tanggal penutupan dokumen dan sesi IHSG sebelumnya. DtD dihitung dari kedua close tersebut; quote intraday dan baseline akhir tahun tidak dipakai sebagai pembanding harian. Pipeline menyertakan histori ini saat membentuk snapshot equity, sehingga refresh berikutnya mempertahankan nilai sektor. Perubahan kode backend memerlukan restart API/worker jika proses berjalan tanpa reload.

Sumber tambahan disetujui untuk dua indikator: foreign flow memakai `capital_flow.Saham` BEI pada laporan aktif, sedangkan batubara memakai `commodities["Coal (Newcastle)"].mtd_pct` dari seri futures yang sudah diperbarui. API equity menggabungkan indikator laporan aktif saat dibaca, sehingga update Newcastle tidak memerlukan pengambilan ulang seluruh saham. Angka bertanggal setelah sesi equity ditolak. Foreign flow yang lebih lama tetap ditampilkan dengan tanggal dan penjelasan observasi terakhir. Konversi USD juta ke IDR menggunakan kurs histori tepat pada tanggal transaksi; jika tidak ada, tetap tampil USD. Foreign flow 1W bergulir tidak diperlakukan sebagai WTD. Sumber tambahan ikut dicantumkan di footer PDF; inflasi dan negara asing lain tetap kosong bila tidak tersedia.

## Foreign flow lintas negara

Pengguna menyetujui penggunaan sumber publik dengan frekuensi berbeda. Pipeline menyimpan observasi dan metadata sumber dalam `international_equity_flows` pada snapshot laporan. API menggabungkan data dengan sesi equity tanpa mengambil sumber eksternal pada setiap GET. Angka yang bertanggal setelah sesi equity dikecualikan.

| Negara | Sumber | Frekuensi dan cakupan |
|---|---|---|
| China | SAFE, time-series Balance of Payments, quarterly USD | Kuartalan; net portfolio equity dan investment fund shares pada liabilities, tidak termasuk FDI |
| Japan | MOF International Transactions in Securities | Mingguan; inbound equity dan investment fund shares dari designated major investors |
| Malaysia | MalaysiaStock.Biz, statistik awal Bursa | Harian; net foreign trading, tidak termasuk amendemen transaksi |
| United States | Treasury TIC/FRED, `FORLTEQTYNET99996` | Bulanan; net foreign purchases saham dan fund shares AS |
| Indonesia | BEI melalui capital flow laporan utama | Harian; seri sebelumnya dipertahankan |

Sesuai pilihan pengguna, tabel hanya menampilkan `Country`, `Date`, `Daily`, `WTD`, `MTD`, `QTD`, `YTD`, dan `12M`. Nama negara ditampilkan tanpa penanda frekuensi; kolom `Latest` dan catatan frekuensi di bawah tabel tidak ditampilkan. Nilai yang tidak tersedia ditampilkan sebagai `-`. Frekuensi, sumber, dan metodologi tetap disimpan dalam metadata backend. `Date` adalah akhir periode observasi, bukan waktu pengunduhan. MtD/QtD/YtD dihitung hingga tanggal masing-masing negara, bukan otomatis hingga tanggal headline IHSG. Seri bulanan memerlukan semua bulan pembanding; seri kuartalan memerlukan semua kuartal pembanding. `12M` menggunakan 12 bulan atau empat kuartal penuh. Jepang tidak dipecah menjadi Daily/WtD/MtD karena minggu yang melintasi batas kalender tidak dapat dialokasikan dari total mingguan saja.

Semua nilai tabel dalam USD juta. Malaysia dikonversi memakai kurs Yahoo USD/MYR pada tanggal transaksi; Jepang memakai rata-rata observasi USD/JPY dalam minggu terkait. Hasil konversi merupakan nilai konversi aplikasi, bukan seri USD resmi penyedia. Jika kurs yang sesuai tidak tersedia, observasi tidak dimasukkan. Coverage Malaysia yang pendek tidak digunakan sebagai YtD atau 12M. Definisi cakupan tiap negara berbeda dan bukan pengganti seri Bloomberg yang seragam.

Cache sumber dan kurs berada di `runtime/data/international_flow/`. Kegagalan pengambilan mempertahankan observasi sebelumnya beserta tanggalnya dan metadata `fetch_failed`; tidak menghasilkan nol. Untuk memuat perubahan frontend dalam mode produksi, hentikan launcher dan jalankan kembali `run-production.ps1` agar build, API, dan worker diperbarui bersama.

## Edit dan PDF

Narasi otomatis memakai gaya laporan analis: perubahan IHSG dan sesi sebelumnya, perbandingan inflasi antarbulan yang tersedia, arus asing beserta perubahan arah jika datanya mendukung, serta saham penggerak dan perubahan harga batubara. Nama penyedia dan penjelasan metode tidak dimasukkan ke paragraf; tetap ada dalam metadata/footer. Profit taking, agenda rilis, El Nino, atau jadwal rebalancing tidak disimpulkan dari harga saja dan dapat ditambahkan analis melalui editor. Angka/tanggal dalam contoh referensi tidak digunakan sebagai angka laporan berjalan.

Nama Company pada kedua tabel Market Movers mengikuti format tampilan Bloomberg: awalan legal PT dipindahkan ke akhir, tanda kurung Persero dirapikan, dan Tbk dipertahankan sebelum PT. Alias per ticker di `COMPANY_DISPLAY_NAMES` pada `frontend/src/lib/equity-snapshot.ts` menangani nama khusus, termasuk BBCA dan TLKM sesuai pilihan analis. Ini format tampilan/alias, bukan pengambilan direktori nama resmi Bloomberg; nama asli Yahoo tetap tersimpan dalam snapshot.

Edit membuka semua teks. Ctrl+B/I/U memformat seleksi tanpa toolbar. Usulan saham tersedia di bawah dokumen saat mode edit, berdasarkan kontribusi dan sektor penggerak; klik menambahkan kalimat faktual ke narasi, atau ketik/hapus kode secara langsung. Sorotan emas mengikuti kode saham yang benar-benar ada dalam paragraf narasi, termasuk teks dengan format inline. Simpan mengunci DOM yang sudah diedit. Download mengambil DOM terbaru walaupun belum Simpan. Kontrol, usulan, dan catatan coverage berada di luar area ekspor; ukuran dan alur ekspor satu halaman A4 sebelumnya dipertahankan.

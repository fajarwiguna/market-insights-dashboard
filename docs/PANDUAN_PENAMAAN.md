# REFERENCE GUIDE
## Panduan Penamaan Tabel dan Series Database
### Standar untuk Daily Market Report (PostgreSQL)

**Pola utama**
`{cakupan}_{Subjek}_{sumber}_{frekuensi}` (nama tabel)
`{wilayah}_{indikator}_{rincian}` (nama series / kolom)

**Versi 3.0 · 14 Oktober 2026**

---

## DATA GOVERNANCE | STANDAR PENAMAAN TABEL DAN SERIES

### 1. Standar Inti

Nama tabel harus menjawab empat pertanyaan tanpa membuka kode: **cakupan wilayahnya**,
**data apa yang disimpan**, **dari sumber mana**, dan **pada grain waktu apa**.
Nama kolom melanjutkannya ke tingkat series: **wilayah mana**, **indikator apa**,
dan **rincian yang mana**.

**Pola:** `{cakupan}_{Subjek}_{sumber}_{frekuensi}` — tepat empat komponen.

> **Perubahan pada Versi 3.0.** Versi 2.0 ditulis untuk SQL Server/Azure SQL dan
> katalog `meta_timeseries` yang lebih luas (±332 tabel). Versi ini diselaraskan
> dengan yang **sudah diterapkan** di project ini: PostgreSQL, katalog
> `meta_table` + `meta_timeseries`, dan **20 tabel fisik wide** yang dibangun dari
> `market_report/services/timeseries_catalog.py` (`PIPELINE_SERIES`).

**Keputusan utama**
Frekuensi mengikuti grain observasi atau publikasi data, bukan jadwal job. Job harian
yang memantau rilis bulanan tetap memakai suffix `_m`.

#### 1.1 Komponen nama tabel

| Komponen   | Format     | Fungsi                                              | Contoh     |
|------------|------------|------------------------------------------------------|------------|
| cakupan    | lowercase  | Cakupan wilayah data. Wajib, dari registry §2.1.      | `natl`     |
| Subjek     | PascalCase | Subjek atau ukuran utama yang disimpan.              | `SbnYield` |
| sumber     | lowercase  | Kode kanal akuisisi satu kata, dari registry §2.2.   | `phei`     |
| frekuensi  | 1 huruf    | Grain waktu data, dari registry §2.3.                | `d`        |

#### 1.2 Aturan wajib

1. Gunakan tepat empat komponen, dipisah satu underscore.
2. Tulis Subjek dalam PascalCase tanpa spasi atau underscore tambahan.
3. Tulis cakupan, sumber, dan kode frekuensi seluruhnya lowercase.
4. Gunakan huruf dan angka ASCII; tanpa spasi, tanda hubung, titik, atau karakter khusus.
5. **Nama tabel wajib dikutip di SQL** bila mengandung huruf besar, mis.
   `DROP TABLE IF EXISTS "glob_Commodity_yahoo_d"`. Tanpa kutip, PostgreSQL melipat
   nama ke lowercase dan pernyataan akan "skipping" tanpa efek.
6. Jangan memasukkan kata teknis seperti `table`, `data`, `master`, `final`, `new`,
   atau `temp` ke nama tabel produksi.

---

### 2. Registry

Registry berikut adalah rujukan tunggal. Nilai baru harus didaftarkan sekali dan
dipakai konsisten.

#### 2.1 Kode cakupan

Ditetapkan di `timeseries_catalog.SCOPES` dan ditegakkan lewat `CHECK` pada
`meta_table.scope`.

| Kode   | Cakupan                      | Kapan digunakan                                       | Contoh tabel                      |
|--------|------------------------------|-------------------------------------------------------|-----------------------------------|
| `glob` | Global atau lintas negara    | Data negara lain atau agregat dunia.                  | `glob_EquityFlow_fred_m`          |
| `natl` | Nasional Indonesia           | Satu angka untuk seluruh Indonesia.                   | `natl_Rates_bi_d`                 |
| `prov` | Provinsi                     | Series per provinsi.                                  | `prov_AcehCpi_ceic_m` *           |
| `reg`  | Kabupaten (Dati II)          | Series per kabupaten.                                 | `reg_JatengGrdpIndustry_ceic_y` * |
| `muni` | Kota                         | Series khusus kota.                                   | `muni_PmaKota_ceic_q` *           |
| `meta` | Metadata dan tabel pendukung | Tabel bantu, bukan data observasi.                    | `meta_date_idx_d`                 |

\* Belum ada di pipeline; nilainya disediakan untuk katalog `meta_timeseries.xlsx`
yang lebih luas.

#### 2.2 Kode sumber

Sumber punya **dua lapis**, dan keduanya wajib konsisten:

- **Kode ringkas** (satu kata, tanpa underscore) dipakai di **nama tabel**, karena
  ia bagian dari identifier. Ditetapkan di `timeseries_catalog.SOURCE_CODES`.
- **Nama penerbit** dipakai di **kolom `source`** pada `meta_table` dan
  `meta_timeseries`, sesuai panduan §8. Ditetapkan di `timeseries_catalog.SOURCE_NAMES`.

| Kode (nama tabel) | Nama penerbit (kolom `source`) | Kanal akuisisi |
|-------------------|--------------------------------|----------------|
| `bi`    | Bank Indonesia      | Portal/SEKI Bank Indonesia                          |
| `idx`   | IDX                 | Portal IDX (net foreign flow, kalender hari bursa)  |
| `djppr` | DJPPR               | Portal DJPPR Kementerian Keuangan (SBN)             |
| `phei`  | PHEI                | Portal PHEI (yield curve SBN)                       |
| `antam` | Antam               | Harga emas Antam / Logam Mulia                      |
| `yahoo` | Yahoo Finance       | Yahoo chart API via `yfinance` (FX, indeks, yield, komoditas) |
| `te`    | Trading Economics   | Trading Economics                                   |
| `erapi` | open.er-api.com     | Kurs cadangan                                       |
| `safe`  | SAFE                | State Administration of Foreign Exchange (Tiongkok) |
| `moj`   | MOF Japan           | Ministry of Finance Japan                           |
| `bm`    | Bursa Malaysia      | Bursa Malaysia                                      |
| `fred`  | FRED                | Federal Reserve Economic Data                       |

> **Catatan.** `bbg`, `ceic`, `xls`, dan `web` **tidak dipakai**: pipeline tidak
> pernah mengambil data dari Bloomberg/CEIC maupun workbook manual. Kode sumber
> mengikuti sumber fetch yang benar-benar dipakai, bukan label vendor di berkas meta.

#### 2.3 Kode frekuensi

Ditetapkan di `timeseries_catalog.FREQUENCIES` dan ditegakkan lewat `CHECK` pada
`meta_table.frequency`.

| Kode | Arti      | Kapan digunakan                                      |
|------|-----------|------------------------------------------------------|
| `d`  | Daily     | Satu observasi per hari atau publikasi harian.       |
| `w`  | Weekly    | Satu observasi per minggu atau publikasi mingguan.   |
| `m`  | Monthly   | Satu observasi per bulan atau publikasi bulanan.     |
| `q`  | Quarterly | Satu observasi per kuartal.                          |
| `y`  | Yearly    | Satu observasi per tahun.                            |

---

### 3. Penamaan Series (Kolom)

Tabel berbentuk **wide**: satu kolom `dates` sebagai primary key, lalu satu kolom per
series. Nama kolom karena itu menjadi identitas series dan mengikuti pola:

```
{wilayah}_{indikator}_{rincian}[_{subrincian}]
```

- Seluruh nama kolom lowercase, dipisah underscore, hanya huruf dan angka ASCII.
- Unsur pertama menunjukkan wilayah atau entitas, mis. `id`, `us`, `cn`, `my`.
- Nama kolom tidak boleh berubah setelah dipakai; rincian baru menjadi kolom baru.

Contoh yang berlaku: `id_bi_rate`, `idx_composite`, `us_gov_10yr`, `my_cpo`,
`cn_inbound_equity_flow`, `crude_oil_brent_price`.

---

### 4. Identitas Series (`series_id`)

`meta_timeseries.id` = **nama tabel tanpa underscore** + `_` + **nama series tanpa
underscore**, dihitung oleh `timeseries_catalog.series_id_for()`.

```
glob_Monetary_yahoo_d + usd_idr               -> globMonetaryyahood_usdidr
natl_FinancialMarket_yahoo_d + idx_composite  -> natlFinancialMarketyahood_idxcomposite
```

`series_id` dipakai pipeline untuk menulis observasi; kolomnya unik di `meta_timeseries`.

---

### 5. Metadata Wajib

Nama saja tidak cukup. Setiap tabel dan series terdaftar di katalog agar dapat
ditemukan dan dijelaskan tanpa membuka kode.

| Objek             | Level                | Kolom |
|-------------------|----------------------|-------|
| `meta_table`      | Satu baris per tabel | `id`, `table_name`, `table_title`, `scope`, `source`, `frequency`, `table_type`, `organizational_access` |
| `meta_timeseries` | Satu baris per series| `id`, `table_name`, `series_name`, `series_id`, `data_type`, `description`, `unit`, `source`, `tag` |

- Kolom `table` pada panduan lama dinamai **`table_name`** karena `table` adalah
  reserved keyword SQL yang harus dikutip di setiap query.
- `source` diisi **nama penerbit** (§2.2), bukan kode ringkas.
- `unit` mengikuti notasi katalog: `IDR`, `USD mn`, `%`, `index`, `Unit`.
- `tag` memakai `x` bila tidak ada tema khusus.

Metadata ini ditulis `sync_to_database()` -> `repository.sync_catalog()` dari
`PIPELINE_SERIES`, sekaligus membuat tabel fisik dan kolomnya secara idempoten
(`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).

---

### 6. Validasi Nama

#### 6.1 Pola regex

```
Tabel  : ^(glob|natl|prov|reg|muni|meta)\d*_[A-Z][A-Za-z0-9]*_[a-z][a-z0-9]*_[dwmqy]$
Series : ^[a-z][a-z0-9]*(_[a-z0-9]+)+$
```

Implementasi Python ada di `timeseries_catalog.py`, dan pemeriksaannya dijalankan
oleh `backend/tests/test_timeseries_integration.py` (`TestNamingGuide`).

#### 6.2 Pemeriksaan sebelum nama disetujui

1. Kode cakupan sesuai tingkat wilayah dan terdaftar di §2.1.
2. Subjek memakai PascalCase dan tidak mengandung istilah teknis.
3. Kode sumber terdaftar di §2.2 dan dipakai konsisten di nama tabel **dan** kolom `source`.
4. Kode frekuensi sesuai grain observasi, bukan jadwal job.
5. Nama tabel dan seluruh kolom lolos regex.
6. `series_id` unik dan sama dengan hasil `series_id_for()`.
7. Nama tidak memakai istilah sementara (`temp`, `new`, `final`, `v2`, `backup`).

---

#### 6.3 Contoh tidak sesuai

| Tidak sesuai | Masalah | Perbaikan |
|---|---|---|
| `natl_sbn_yield_phei_d` | Subjek memakai snake_case | `natl_SbnYield_phei_d` |
| `natl_SbnYield_PHEI_d` | Kode sumber uppercase | `natl_SbnYield_phei_d` |
| `natl_SbnYield_phei_daily` | Frekuensi bukan kode satu huruf | `natl_SbnYield_phei_d` |
| `natl_phei_SbnYield_d` | Urutan komponen salah | `natl_SbnYield_phei_d` |
| `glob_yahoo_wti` | Subjek tidak PascalCase dan tidak menjelaskan isi | `glob_Commodity_yahoo_d` |
| `trading_economics_cpo` | Kode sumber lebih dari satu kata | `glob_Commodity_te_d` |
| `natl_FinancialMarket_bbg_d` | Sumber tidak sesuai akuisisi sebenarnya (bukan Bloomberg) | `natl_FinancialMarket_yahoo_d` |
| `id bi rate` | Nama kolom memakai spasi | `id_bi_rate` |
| `ta-125_index` | Nama kolom memakai tanda hubung | `ta125_index` |
| `DROP TABLE glob_Commodity_yahoo_d` | Identifier PascalCase tidak dikutip | `DROP TABLE "glob_Commodity_yahoo_d"` |

---

### 7. Prosedur Rename Tabel yang Sudah Ada

Rename tabel atau kolom adalah perubahan schema.

1. Konfirmasi environment dan schema target; pastikan nama tujuan belum dipakai.
2. Tampilkan preview mapping read-only dan minta persetujuan spesifik.
3. Jalankan migrasi baru (`NNN_*.sql`) — **jangan mengubah migrasi yang sudah diterapkan**.
4. Karena nama tabel memakai PascalCase, kutip identifier di setiap pernyataan SQL.
5. Perbarui `timeseries_catalog.py` pada change set yang sama, lalu jalankan
   `sync_to_database()` agar `meta_table`/`meta_timeseries` ikut menyesuaikan dan
   baris yatim dipangkas (`prune_series` juga membersihkan `meta_table` tanpa series).
6. Verifikasi: jumlah baris, PK `dates`, kolom, dan regex nama.

---

### 8. Pengecualian Tercatat

| Objek | Pengecualian | Alasan |
|---|---|---|
| `meta_date_idx_d` | Subjek `date` lowercase, tidak lolos regex tabel | Pengecualian legacy dari katalog `meta_timeseries.xlsx` (panduan §6 versi 2.0). Dibekukan sampai ada change set rename yang disetujui. |

---

### 9. Daftar Tabel yang Berlaku (20 tabel - 54 series)

Dihasilkan langsung dari `timeseries_catalog.PIPELINE_SERIES`.

| Tabel | Cakupan | Sumber (kolom `source`) | Frek. | Jml series |
|---|---|---|---|---|
| `glob_FinancialMarket_yahoo_d` | `glob` | Yahoo Finance | `d` | 10 |
| `glob_Monetary_yahoo_d` | `glob` | Yahoo Finance | `d` | 5 |
| `glob_Commodity_yahoo_d` | `glob` | Yahoo Finance | `d` | 3 |
| `natl_FinancialMarket_yahoo_d` | `natl` | Yahoo Finance | `d` | 12 |
| `natl_StockFlow_idx_d` | `natl` | IDX | `d` | 1 |
| `natl_BondFlow_djppr_d` | `natl` | DJPPR | `d` | 1 |
| `meta_date_idx_d` | `meta` | IDX | `d` | 1 |
| `glob_Commodity_te_d` | `glob` | Trading Economics | `d` | 3 |
| `glob_Rates_te_d` | `glob` | Trading Economics | `d` | 1 |
| `glob_Monetary_erapi_d` | `glob` | open.er-api.com | `d` | 1 |
| `natl_Macro_te_m` | `natl` | Trading Economics | `m` | 2 |
| `natl_Commodity_antam_d` | `natl` | Antam | `d` | 1 |
| `natl_SbnYield_phei_d` | `natl` | PHEI | `d` | 2 |
| `natl_Rates_bi_d` | `natl` | Bank Indonesia | `d` | 3 |
| `natl_Monetary_bi_m` | `natl` | Bank Indonesia | `m` | 2 |
| `natl_Macro_bi_m` | `natl` | Bank Indonesia | `m` | 2 |
| `glob_EquityFlow_safe_m` | `glob` | SAFE | `m` | 1 |
| `glob_EquityFlow_moj_m` | `glob` | MOF Japan | `m` | 1 |
| `glob_EquityFlow_bm_m` | `glob` | Bursa Malaysia | `m` | 1 |
| `glob_EquityFlow_fred_m` | `glob` | FRED | `m` | 1 |

---

### 10. Tata Kelola Standar

1. Registry cakupan, sumber, dan frekuensi menjadi rujukan tunggal.
2. Nama baru direview sebelum DDL, pipeline, atau dashboard dibuat.
3. Perubahan menyimpan mapping lama ke baru, memperbarui metadata, query, dan data catalog.
4. Pengecualian hanya boleh dipakai bila didokumentasikan dan disetujui pemilik standar.
5. Panduan ditinjau ulang setiap kali cakupan, sumber, atau frekuensi baru masuk katalog.

---

### Riwayat Revisi

| Versi | Tanggal            | Perubahan |
|-------|--------------------|-----------|
| 1.0   | 14 September 2026  | Standar awal untuk tabel nasional: pola `natl_{Subjek}_{sumber}_{frekuensi}`, registry empat sumber, dan prosedur rename. |
| 2.0   | 18 September 2026  | Cakupan diperluas ke `glob`, `prov`, `reg`, `muni`, `meta`; frekuensi `m` ditambahkan; penamaan series, pemecahan tabel, dan metadata wajib diatur. |
| 3.0   | 14 Oktober 2026    | Diselaraskan dengan implementasi project: PostgreSQL; katalog `meta_table` + `meta_timeseries` (kolom `table_name`); sumber dua lapis (kode di nama tabel, nama penerbit di kolom `source`); `bbg`/`ceic`/`xls`/`web` dihapus karena tidak ada akuisisi tersebut; 20 tabel wide terdaftar; aturan kutip identifier untuk nama PascalCase. |

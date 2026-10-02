# Runtime data

Direktori ini menampung keluaran lokal yang dibuat aplikasi:

- `data/`: snapshot sumber, laporan aktif, versi laporan, dan riwayat SBN.
- `charts/`: grafik pipeline.
- `reports/`: arsip PDF dan artefak laporan.

Isi subdirektori dikecualikan dari Git. Buat backup berkala untuk data atau arsip yang perlu
dipertahankan. API dan worker harus memakai lokasi artefak yang sama melalui `REPORT_ARTIFACT_DIR`.

# News Intelligence & Narrative Catalysts

Dokumen ini merangkum pipeline yang membuat narasi harian menjelaskan **katalis**,
bukan sekadar mengulang angka indikator. Semua tahap bersifat deterministik kecuali
satu panggilan LLM di akhir; kegagalan tahap mana pun menurunkan kualitas narasi,
bukan menggagalkan publikasi.

## Alur

```
payload laporan ──▶ 1. deteksi sinyal ──▶ 2. kueri pencarian dinamis
                                              │
                    4. penilaian relevansi ◀─┴─▶ 3. verifikasi & ekstraksi
                                              │
                                     5. narasi LLM + validasi ──▶ laporan/PDF
```

1. **Deteksi sinyal** — `services/narration/signals.py`. Dari angka yang sudah tampil
   (`NarrativeContext.numbers()`), dicari instrumen yang bergerak material. Ambang
   per jenis instrumen dibaca dari policy `[thresholds]` (persen untuk indeks/FX/komoditas,
   basis poin untuk imbal hasil, miliar Rupiah untuk arus dana asing). Deteksi juga
   mencatat divergensi arah (mis. SBN naik sementara UST turun).
2. **Kueri dinamis** — kueri diturunkan dari sinyal itu sendiri
   (`katalis <instrumen> <arah>`), bukan dari daftar kata kunci statis. Jumlah kueri
   dibatasi `max_query_count` dan `queries_per_signal`.
3. **Penemuan & verifikasi** — `providers/search_seeded.py`. Sumber `mode: "seed"`
   adalah kanal tetap; sumber `mode: "query"` (mis. `google_news_search`) diekspansi
   dari kueri di atas melalui `url_template` yang memuat `{query}`. Untuk setiap item,
   penerbit diambil dari `<source url=...>` sehingga tier dinilai dari domain penerbit,
   bukan domain agregator. `evidence.build_evidence()` menyaring tanggal (berita
   sesudah tanggal laporan dibuang), tier minimum, duplikat, dan kuota per domain, lalu
   menandai tiap bukti dengan `publisher`, `verified`, `relation` (`before`/`same_day`),
   dan `confidence`.
4. **Penilaian relevansi** — skor bukti menggabungkan tier sumber, kebaruan, kesesuaian
   topik, dan kecocokan dengan kueri sinyal. Hasil terurut dipakai untuk memilih bukti.
5. **Narasi** — prompt (`prompt_builder.py`) menyertakan blok `<market_signals>` (apa
   yang bergerak dan kueri yang dijalankan) dan hanya mengizinkan klaim katalis yang
   punya `evidence_id`. Bila tidak ada bukti, narasi diminta menyatakan katalis belum
   terkonfirmasi, bukan mengarang.

## Konfigurasi

- Ambang sinyal: `docs/llm_rules.md` bagian `[thresholds]` (tanpa mengubah kode).
- Sumber bukti & tier domain: `backend/config/llm_sources.json`
  (`domain_tiers`, `sources`, `mode`, `format`, `url_template`).
- Provider search: `SEARCH_PROVIDER=seeded` (default). Semua permintaan mengikuti satu
  jalur yang sama, sehingga provider lain dapat ditambahkan tanpa mengubah engine.

## Prinsip yang dijaga

- Angka pasar **hanya** berasal dari payload halaman; angka dari web tidak pernah
  menjadi angka pasar.
- Berita pada/atau sebelum tanggal laporan tidak dianggap penyebab; narasi memakai
  penghubung aman (mis. "seiring", "di tengah"), bukan klaim sebab-akibat pasti.
- Kegagalan pencarian/verifikasi tidak menggagalkan publikasi: laporan tetap terbit
  dengan narasi deterministik yang sudah ada.

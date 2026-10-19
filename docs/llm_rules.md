# LLM Narrative Rules — Daily Market Report

> policy_version: 1
> File ini adalah **policy layer** untuk LLM Narrative Engine (Dashboard Utama,
> Equity Market Daily Snapshot, dan PDF laporan terbit). Engine membaca file ini
> sebelum menghasilkan narasi. Bila isi file ini bertentangan dengan kode, file ini
> yang menang: kode hanya boleh lebih ketat, tidak boleh lebih longgar.
>
> Cara mengubah: edit nilai di bawah ini. Setiap perubahan mengubah `rules_hash`
> sehingga cache narasi lama otomatis tidak dipakai lagi. Kode tidak perlu diubah.
>
> Aturan yang **tidak bisa** dilonggarkan lewat file ini (dipaksakan kode):
> larangan menciptakan/menebak angka, larangan memakai angka web sebagai angka pasar,
> larangan tanggal masa depan, dan kewajiban sumber untuk klaim eksternal.
> Menuliskan nilai `false` pada aturan tersebut akan diabaikan dan dicatat sebagai warning.

## [global]
- language: id
- tone: objective
- style: professional
- max_paragraphs: 3
- deductive: true
- forbid_promotional_language: true
- forbid_personal_opinion: true
- forbid_hyperbole: true

## [numbers]
- authoritative_source: application_payload
- never_invent: true
- never_estimate: true
- never_round: true
- preserve_units: true
- preserve_sign: true
- preserve_dates: true
- allow_derived_arithmetic: false
- allow_display_rounding: true
- reject_on_mismatch: true
- require_separate_observation_labels: true

## [sources]
- mode: seeded
- registry: backend/config/llm_sources.json
- search_enabled: true
- require_source_for_external_claims: true
- min_source_tier: major_media
- allow_secondary_for_causal_claims: false
- max_items_per_domain: 2
- reject_undated: true
- require_verbatim_quote_check: true
- lookback_days: 3
- max_evidence_items: 8
- max_articles_per_source: 4

## [macro]
- include_global_context: true
- include_domestic_context: true
- avoid_unsupported_causality: true
- causality_requires_explicit_source: true
- allowed_safe_connectives: [seiring, di tengah, bertepatan dengan]

## [dashboard]
- max_sentences: 10
- max_words: 250
- must_cover: [domestic, global, catalyst, risk]
- forbidden_sections: []

## [equity_snapshot]
- max_sentences: 8
- max_words: 250
- sections:
  - market
  - macro
  - foreign
  - sector
- must_cover:
  - index
  - index_daily_change
  - market_breadth
  - macro_context
  - foreign_flow
  - leading_sectors
  - lagging_sectors
  - market_implication

## [validation]
- number_validation: required
- source_validation: required
- date_validation: required
- style_validation: required
- claim_validation: required
- max_repair_attempts: 1
- min_narrative_words: 25

## [fallback]
- on_llm_failure: deterministic_seed
- on_search_failure: dashboard_only
- on_no_evidence: neutral_phrasing
- on_validation_failure: deterministic_seed
- cache_negative_minutes: 30

## [cost]
- max_calls_per_refresh: 2
- max_calls_per_day: 12
- max_output_tokens: 700
- max_input_tokens: 6000
- daily_budget_usd: 1.00
- price_input_per_mtok: 0
- price_output_per_mtok: 0

## [thresholds]
- query_material_pct: 0.5
- index_material_pct: 0.35
- fx_material_pct: 0.25
- commodity_material_pct: 0.5
- yield_material_bp: 3
- coal_material_pct: 1
- foreign_flow_material_idr_bn: 250
- capital_flow_material_usd_mn: 100
- max_query_count: 6
- queries_per_signal: 2

## Macros (frasa aman yang wajib dipakai narator)
- neutral_phrasing_no_catalyst: Belum terdapat katalis yang cukup kuat dari sumber yang tersedia.
- neutral_phrasing_stale: Data terbaru untuk indikator ini belum tersedia pada tanggal laporan.
- neutral_phrasing_missing: Angka untuk indikator ini belum tersedia pada data laporan.

## Catatan untuk manusia (tidak dibaca mesin)

- `mode` pada `[sources]`: `seeded` memakai registry sumber yang sudah ditetapkan
  pengguna; `provider` memakai API pencarian pihak ketiga; `none` tidak mengambil
  konteks eksternal sama sekali.
- `min_source_tier` mengikuti urutan: `official_primary` > `supranational_official`
  > `company_primary` > `data_portal` > `id_market_media` > `global_market_media`
  > `major_media` > `secondary`.
- `price_input_per_mtok`/`price_output_per_mtok` diisi dengan harga model yang dipakai
  (per juta token) agar kolom `cost_usd` pada audit berisi angka. Nilai 0 berarti biaya
  tidak dihitung, bukan gratis.
- `must_cover` adalah daftar periksa untuk prompt, bukan izin menambah klaim tanpa bukti.
- `allow_display_rounding` (default true): validator menerima angka yang dibulatkan
  tepat seperti tampilan halaman (mis. IHSG 5.988,706 ditulis 5.988,71). Ini hanya
  toleransi tampilan: arah/tanda, satuan, dan tanggal tetap wajib sama, dan
  `never_round` tetap berlaku untuk pembulatan yang tidak ada di halaman.
- Narasi yang lulus validasi dibekukan ke laporan terbit dan dipakai PDF. Perubahan
  file ini tidak mengubah laporan yang sudah diterbitkan.
- Angka pada contoh/referensi proyek tidak boleh dianggap sebagai feed pasar nyata.

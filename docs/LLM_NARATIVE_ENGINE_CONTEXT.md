# Konteks Lanjutan: LLM Narrative Engine

Dokumen ini merangkum **status implementasi, kontrak, dan pekerjaan tersisa** untuk fitur narasi LLM pada proyek Daily Market Report. Abaikan topik di luar narasi (probe cleanup, schema `natl`/`glob`, timeseries catalog, dsb.).

**Tanggal konteks:** 16 Oktober 2026  
**Blueprint acuan:** `docs/LLM_NARRATIVE_ENGINE_BLUEPRINT.md`  
**Bahasa proyek:** backend Python (FastAPI), frontend Next.js (App Router)

---

## 1. Tujuan fitur

Menghasilkan **narasi pasar berbahasa Indonesia** untuk dua halaman:

| Halaman | Page key | Isi utama |
|---|---|---|
| Dashboard Utama | `dashboard` | Ringkasan pasar (FX, IHSG, yield, komoditas, implikasi treasury) |
| Equity Market Daily Snapshot | `equity_snapshot` | Headline + section narasi saham / aliran modal |

Prinsip non-negotiable (dari blueprint §1):

1. Angka hanya boleh berasal dari laporan/snapshot yang sudah divalidasi — **bukan** dari LLM atau scraping HTML bebas.
2. Narasi yang sudah **dibekukan** ke versi laporan terbit **tidak boleh berubah** saat regenerate/edit kemudian (immutability versi).
3. Fallback deterministik selalu tersedia; publikasi laporan tidak boleh gagal karena LLM/search down.
4. Kredensial & prompt penuh tidak pernah disimpan di audit trail.

---

## 2. Arsitektur ringkas

```
[Refresh pipeline / Operator] 
        │
        ▼
 NarrativeEngine.generate(request, report?, snapshot?, force?)
        │
        ├─ Rule engine (llm_rules.md)
        ├─ Number registry (dari report/snapshot)
        ├─ Search provider (seeded | webz | exa | none)
        ├─ LLM provider (openai-compatible | anthropic-compatible | none)
        ├─ Validator (angka, sumber, tanggal, klaim, gaya)
        └─ Cache + audit (Postgres + file mirror)
        │
        ▼
 attach_narratives(report)  ← dipanggil di jalur publish
        │
        ▼
 report["narrative"] = { dashboard: {...}, equity_snapshot: {...} }
        │
        ├─ PDF (report_pdf.summary_text → frozen_narrative)
        ├─ API /reports/latest (summary diganti frozen bila ada)
        └─ API /equity/latest (narratives diganti frozen sections bila ada)
```

### Modul backend utama

| Path | Peran |
|---|---|
| `backend/src/market_report/domain/narration_contract.py` | `NarrativePage`, `NarrativeStatus`, `NarrativeRequest`, `NarrativeResult` |
| `backend/src/market_report/domain/narrative_rules.py` | Parsing rules + default |
| `backend/src/market_report/services/narration/engine.py` | Orkestrasi generate |
| `backend/src/market_report/services/narration/freeze.py` | Pembekuan ke payload laporan |
| `backend/src/market_report/services/narration/providers/` | LLM + search abstraction |
| `backend/src/market_report/api/routers/narratives.py` | Endpoint HTTP |
| `backend/migrations/017_narratives.sql` | Tabel audit: `narrative_runs`, `narrative_outputs`, `narrative_evidence`, `narrative_claims` |

---

## 3. Kontrak API backend

Prefix: `/api/v1` (sesuai pola proyek). Akses: Bearer token (`API_READ_TOKEN` / `API_OPERATOR_TOKEN`).

| Metode | Rute | Akses | Perilaku |
|---|---|---|---|
| `GET` | `/narratives/latest?page=dashboard\|equity_snapshot&report_id=` | read | Baca cache/hasil terbit; **tidak** memanggil LLM |
| `GET` | `/narratives/runs?page=&limit=` | read | Riwayat audit ringkas |
| `GET` | `/narratives/runs/{run_id}` | read | Detail satu run |
| `POST` | `/narratives/regenerate?page=&allow_search=` | **operator** + rate limit | Satu run sinkron; response `200` + payload |

### Bentuk respons (skema §25.2)

```jsonc
{
  "page": "dashboard",
  "status": "published",           // published | fallback | stale | unavailable
  "report_id": "…",
  "report_date": "2026-10-16",
  "narrative": "…",
  "sections": [],                  // dipakai equity_snapshot
  "sources": [{ "url": "…", "source": "bi.go.id", "published_at": "…" }],
  "generated_at": "2026-10-16T08:05:12+07:00",
  "run_id": "…",
  "notes": ["…"],
  "validation": { "passed": true, "errors": [], "warnings": [], "numbers_used": 12 },
  "frozen": false
}
```

`NarrativeResult.to_payload()` harus konsisten dengan skema di atas.

---

## 4. Pembekuan narasi (§15.1) — sudah diimplementasi di backend

File: `services/narration/freeze.py`

- `FREEZE_KEY = "narrative"`
- `FREEZE_PAGES = (DASHBOARD, EQUITY_SNAPSHOT)`
- Status yang boleh dibekukan: `published`, `fallback`
- `freeze_enabled()` mengikuti `NARRATIVE_FREEZE` env atau status fitur LLM
- `attach_narratives(report)` dipanggil di `report_service` **sebelum** `publish`
- Helper baca:
  - `frozen_narrative(report, page) → str`
  - `frozen_sections(report, page) → list[dict]`
  - `frozen_entry(report, page) → dict | None`

### Integrasi yang sudah ada

| Lokasi | Perilaku |
|---|---|
| `report_service` (publish path) | `attach_narratives(report)` sebelum simpan |
| `report_pdf.summary_text` | Pakai `frozen_narrative(..., "dashboard")` bila ada |
| `api/routers/reports.py` | `summary` diganti teks frozen; flag `narrative_frozen` |
| `api/routers/equity.py` | `apply_frozen_narrative(...)` mengganti `narratives` dengan sections beku + `narrative_status`/`narrative_frozen` |
| `frontend/src/app/api/narratives/[page]/route.ts` | Proxy GET (baca, pakai read token) + POST (operator, pakai operator token) |
| `frontend/src/features/dashboard/narrative-panel.tsx` | Panel narasi dashboard dari `report.summary` + status/sumber; tombol Buat ulang bila sesi operator aktif |
| `frontend/src/app/equity-snapshot/page.tsx` | Chip status narasi + tombol Buat ulang (operator) di baris aksi |

`apply_frozen_narrative(payload, report=None, *, page=EQUITY_SNAPSHOT)`:
prioritas sumber `payload["narrative_frozen"]` → blok `report["narrative"][page]`,
hanya menerapkan bila ada `sections`; narasi deterministik dipertahankan bila tidak.

### Yang masih perlu dilengkapi (lihat §7)

- Uji end-to-end manual dengan kredensial LLM/search nyata (kualitas prompt & evidence).

---

## 5. Status & fallback

| Status | Arti | UI |
|---|---|---|
| `published` | LLM lulus validasi | Normal |
| `fallback` | Deterministik / degradasi aman | Penanda halus (bukan error merah) |
| `stale` | Cache lama / rules berubah | Penanda + opsi regenerate |
| `unavailable` | Belum pernah ada run | Sembunyikan panel atau tampilkan placeholder netral |

Fallback deterministik:

- Dashboard → `build_summary` / `build_insights` / `build_impacts`
- Equity → `compose_equity_narratives` (atau setara yang sudah ada)

---

## 6. Konfigurasi (env)

Default **aman**: fitur mati tanpa kredensial.

```env
LLM_NARRATIVE_ENABLED=false
LLM_PROVIDER=openai-compatible     # openai-compatible | anthropic-compatible | none
LLM_BASE_URL=https://opus.abhibots.com
LLM_MODEL=
LLM_API_KEY=
LLM_TIMEOUT_SECONDS=45
LLM_MAX_OUTPUT_TOKENS=700
LLM_MAX_INPUT_TOKENS=6000
LLM_TEMPERATURE=0.2
LLM_MAX_CALLS_PER_REFRESH=2
LLM_MAX_CALLS_PER_DAY=12
LLM_DAILY_BUDGET_USD=1.00

SEARCH_PROVIDER=seeded             # seeded | webz | exa | none
SEARCH_API_KEY=
SEARCH_SEED_MAX_ARTICLES_PER_SOURCE=4
SEARCH_TIMEOUT_SECONDS=20
SEARCH_MAX_QUERIES=6
SEARCH_MAX_RESULTS=8
SEARCH_LOOKBACK_DAYS=3
LLM_EVIDENCE_MAX_ITEMS=8

LLM_RULES_FILE=                    # kosong → backend/config/llm_rules.md lalu docs/llm_rules.md
NARRATIVE_CACHE_TTL_MINUTES=180
NARRATIVE_FREEZE=                  # always | never | (kosong = ikuti LLM_NARRATIVE_ENABLED)
PROMPT_VERSION=v1
```

---

## 7. Pekerjaan tersisa (prioritas untuk dilanjutkan)

> **Status 16 Oktober 2026:** 7.1–7.5 sudah diimplementasi; sisa pekerjaan adalah
> uji end-to-end manual dengan kredensial provider nyata (§7.6).

Urutan disarankan:

### 7.1 Backend — equity freeze (selesai)

Helper `apply_frozen_narrative` ditambahkan di `freeze.py` dan dipakai di
`api/routers/equity.py` setelah `enrich_equity_indicators`. Perilaku:

1. Sumber prioritas: `snapshot["narrative_frozen"]` → `report["narrative"]["equity_snapshot"]`.
2. Bila status freezable dan ada `sections`, `snapshot["narratives"]` diganti sections.
3. Metadata: `narrative_status` (status entri) dan `narrative_frozen` (bool diterapkan).
4. Angka/headline deterministik tidak diubah. Payload asal tidak dimutasi.

### 7.2 Backend — jahit ke refresh pipeline (selesai — terverifikasi)

Blueprint §4.2: tiga pemicu generate:

1. **Publish laporan** — `attach_narratives` dipanggil di `publish_snapshot()`.
2. **Regenerate operator** — `POST /narratives/regenerate`.
3. **Refresh pipeline** — kedua jalur refresh (`run_live_pipeline`, `rebuild_from_saved_snapshot`)
   memanggil `publish_snapshot()`, sehingga ikut membekukan narasi. Tidak ada jalur
   terbit lain yang melewatinya (dijaga test `test_publish_snapshot_invokes_attach_narratives`).

### 7.3 Frontend — proxy (selesai)

`frontend/src/app/api/narratives/[page]/route.ts`:

- **GET** → backend `GET /narratives/latest?page={page}&report_id=` (read token server-side).
- **POST** → cek same-origin + sesi operator → `POST /narratives/regenerate?page={page}&allow_search=`.
- Validasi `page ∈ {dashboard, equity_snapshot}`; `Retry-After` pada 429 diteruskan.
- `maxDuration = 120` karena regenerate sinkron memanggil LLM.

### 7.4 Frontend — panel Dashboard (selesai)

- Komponen client: `frontend/src/features/dashboard/narrative-panel.tsx`.
- Teks: **`report.summary`** (sumber kebenaran versi terbit). Metadata status/sumber:
  `GET /api/narratives/dashboard`.
- Tombol **Buat ulang** hanya muncul bila `useOperatorSession()` mengembalikan
  `authenticated`; jika belum, tampil arahan ke menu Pengelolaan (tanpa duplikasi form login).
- Dipasang setelah `<ReportInsights />`, sebelum `HistoryCharts`; disembunyikan untuk data demo.
- Status ≠ `published` diberi badge halus (bukan error merah); CSS di `globals.css`.

### 7.5 Frontend — kontrol Equity (selesai)

- Chip status + tombol **Buat ulang narasi** (compact) di baris `actions` Equity Snapshot.
- Tombol hanya tampil bila sesi operator aktif; setelah regenerate, snapshot dimuat ulang
  via `GET /api/equity/snapshot` sehingga `narratives` terisi sections beku dari backend.
- Isi narasi di dalam dokumen tetap dari `snapshot.narratives` (backend §7.1).

### 7.6 Verifikasi

Backend (hijau pada sesi ini — 100 test):

```bash
PYTHONPATH=backend/src python -m pytest \
  backend/tests/test_narrative_repository.py \
  backend/tests/test_narratives_api.py \
  backend/tests/test_narration_engine.py \
  backend/tests/test_narration_freeze.py \
  backend/tests/test_narration_rules.py \
  backend/tests/test_number_registry.py \
  backend/tests/test_search_seeded.py -q
```

`test_narration_freeze.py` menambahkan cakupan:

- Publish → `report["narrative"]["dashboard"]` & `equity_snapshot` terisi status freezable
- `attach_narratives` tidak menaikkan error saat engine gagal
- `apply_frozen_narrative` (prioritas sumber, tanpa sections, status non-freezable)
- Equity router mengembalikan `narratives` dari frozen sections
- Semua jalur `publish_snapshot` melewati `attach_narratives`
- `require_operator_access` menolak permintaan tanpa kredensial (401)

Frontend (bersih):

```bash
cd frontend && npm run lint && npx tsc --noEmit
```

Sisa manual: jalankan refresh/regenerate dengan `LLM_NARRATIVE_ENABLED=false` lalu `true`
dan kredensial nyata; pastikan PDF tidak kosong dan narasi beku tidak berubah saat regenerate.

---

## 8. Bentuk data frozen di payload laporan

```jsonc
{
  "report_id": "…",
  "summary": "teks narasi beku dashboard (juga di-set di API layer)",
  "narrative": {
    "dashboard": {
      "status": "published",
      "narrative": "…",
      "sections": [],
      "sources": […],
      "notes": […],
      "run_id": "…",
      "frozen": true,
      "frozen_at": "2026-10-16T…"
    },
    "equity_snapshot": {
      "status": "fallback",
      "narrative": "…",
      "sections": [
        { "id": "flow", "title": "Aliran modal", "text": "…" }
      ],
      "sources": [],
      "notes": ["Konteks eksternal tidak tersedia."],
      "run_id": "…",
      "frozen": true,
      "frozen_at": "…"
    }
  },
  "equity_snapshot": {
    "status": "available",
    "narratives": [ /* diganti dari frozen sections di router */ ],
    "narrative_frozen": { /* salinan entry, opsional */ }
  }
}
```

Kunci yang diawali `_` disaring di API publik laporan; kunci `narrative` **tidak** diawali `_` sehingga ikut terkirim (disengaja untuk audit/UI).

Catatan: pada payload laporan, `equity_snapshot.narrative_frozen` adalah **salinan entri** (objek)
yang ditulis `attach_narratives`. Pada respons `GET /equity/latest`, router menggantinya menjadi
**boolean** `true` plus `narrative_status`, karena `narratives` sudah diisi sections beku.

---

## 9. Aturan validasi yang dipaksakan kode

Validator menolak (memicu repair atau fallback):

- Angka di narasi yang tidak ada di number registry laporan
- Tanda arah terbalik vs data
- Satuan salah
- Tanggal observasi di masa depan
- Klaim kausal tanpa bukti (bila search aktif)
- Kutipan non-verbatim dari evidence

Rules file: prose + blok terstruktur (`[global]`, `[numbers]`, `[sources]`, `[dashboard]`, `[equity_snapshot]`, `[validation]`, `[fallback]`). Parser di `narrative_rules.py`.

---

## 10. Batasan yang harus dihormati saat lanjut

1. **Jangan** mengubah kontrak angka (`InstrumentReading`, skema laporan) demi narasi.
2. **Jangan** membuat publikasi gagal jika LLM/search error — selalu fallback.
3. **Jangan** expose `API_OPERATOR_TOKEN` / `LLM_API_KEY` ke browser.
4. **Jangan** rewrite besar UI dashboard/equity; sisipkan komponen kecil.
5. PDF harus reproducible dari payload beku versi itu, bukan dari cache terbaru.
6. Rate limit regenerate: ~2 per 5 menit (header `Retry-After` pada 429).

---

## 11. Checklist “selesai” untuk sesi berikutnya

- [x] `apply_frozen_narrative` (atau setara) dipakai di router equity
- [x] Semua jalur publish memanggil `attach_narratives` (terverifikasi via test)
- [x] `frontend/src/app/api/narratives/[page]/route.ts` GET + POST operator
- [x] Panel narasi di Dashboard menampilkan `report.summary` + status/sources
- [x] Kontrol compact (status + regenerate) di baris aksi Equity Snapshot
- [x] Test backend narasi tetap hijau; test baru untuk freeze + equity (`test_narration_freeze.py`)
- [x] Lint frontend bersih (`npm run lint`, `npx tsc --noEmit`)
- [ ] Manual: dengan `NARRATIVE_FREEZE=always` dan provider tidak tersedia, publish tetap menghasilkan fallback frozen; PDF tidak kosong
- [ ] Manual: end-to-end dengan kredensial LLM/search nyata

---

*Dokumen ini standalone. Untuk detail arsitektur 22 bagian, baca `docs/LLM_NARRATIVE_ENGINE_BLUEPRINT.md`. Untuk implementasi kode, mulai dari `services/narration/freeze.py` dan `api/routers/narratives.py`.*

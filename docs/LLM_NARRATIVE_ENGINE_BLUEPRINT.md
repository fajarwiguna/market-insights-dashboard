# Blueprint: LLM Narrative Engine (Dashboard Utama & Equity Market Daily Snapshot)

> **Status dokumen: DESAIN / BLUEPRINT — belum ada implementasi kode.**
> **Keputusan pengguna 16 Okt 2026 sudah dimasukkan:** LLM memakai endpoint
> OpenAI-compatible (`LLM_BASE_URL=https://opus.abhibots.com`) dengan API key & model
> opsional selama pengembangan; sumber bukti memakai registry sumber yang ditetapkan
> pengguna (§31); narasi dipakai di Dashboard, Equity Snapshot, **dan PDF laporan terbit**
> dan dibekukan (freeze) saat laporan diterbitkan (§15.1).
> Dokumen ini menggantikan `docs/LLM_NARRATOR_DESIGN.md` (kini ditandai superseded)
> sebagai acuan arsitektur.
> Perilaku LLM yang wajib dipatuhi tetap ditulis terpisah di file policy
> `docs/llm_rules.md` (lihat §9).
>
> Ruang lingkup: satu mesin narasi yang menjadi "otak" bahasa untuk dua halaman —
> Dashboard Utama (`/`) dan Equity Market Daily Snapshot (`/equity-snapshot`) —
> dengan angka yang **selalu** berasal dari payload aplikasi, bukan dari LLM.

---

## 0. Peta 22 bagian yang diminta

| # | Bagian yang diminta | § di dokumen ini |
|---|---|---|
| 1 | High-level architecture | §2 |
| 2 | Component architecture | §3 |
| 3 | Data flow | §4 |
| 4 | Dashboard → LLM data contract | §5 (dan §6 untuk equity) |
| 5 | Web search pipeline | §7 |
| 6 | Evidence pipeline | §8 |
| 7 | Rule engine | §9 |
| 8 | Prompt architecture | §10 |
| 9 | Number validation | §11 |
| 10 | Source validation | §12 |
| 11 | Hallucination protection | §13 |
| 12 | Error handling | §14 |
| 13 | Caching | §15 |
| 14 | Logging | §16 |
| 15 | Audit trail | §17 |
| 16 | Model/provider abstraction | §18 |
| 17 | Security | §19 |
| 18 | Cost control | §20 |
| 19 | Rate limiting | §21 |
| 20 | Fallback ketika LLM gagal | §22 |
| 21 | Fallback ketika web search gagal | §23 |
| 22 | Fallback ketika tidak ada berita relevan | §24 |

Tambahan: kontrak API & UI (§25), konfigurasi (§26), pengujian (§27), roadmap bertahap (§28), keputusan terbuka (§29).

---

## 1. Prinsip non-negotiable

1. **Angka dashboard adalah single source of truth.** Setiap angka yang muncul di narasi harus ada di payload yang sedang ditampilkan halaman tersebut.
2. **LLM tidak pernah menjadi sumber angka.** Web search hanya memasok *penyebab, katalis, sentimen, konteks*.
3. **LLM tidak pernah dipanggil dari browser.** Narasi dibentuk di backend; frontend hanya membaca hasil yang sudah tersimpan.
4. **Halaman tidak memicu inference.** Pembuatan narasi terjadi saat refresh pipeline/worker atau saat operator meminta regenerate — bukan pada setiap GET.
5. **Setiap klaim eksternal punya bukti.** Tanpa bukti, klaim dihapus atau diganti frasa "belum ada katalis".
6. **Output divalidasi sebelum ditampilkan.** Gagal validasi → regenerate terbatas → fallback deterministik.
7. **Perilaku dikendalikan file policy.** `docs/llm_rules.md` adalah *policy layer* yang dibaca sebelum generasi; kode tidak boleh mengunci nilai yang seharusnya configurable.
8. **Provider tidak hard-coded.** `LLM_PROVIDER`/`LLM_MODEL`/`SEARCH_PROVIDER` menentukan implementasi; business logic hanya melihat interface.
9. **Kegagalan narasi tidak boleh merusak apa pun.** Laporan, snapshot, riwayat, PDF, dan pipeline tetap berjalan tanpa narasi LLM.
10. **Semua teks eksternal diperlakukan sebagai data tak terpercaya** (anti prompt-injection, §19.5).

---

## 2. High-level architecture

```
                         ┌────────────────────────────────────────────┐
                         │   PIPELINE / WORKER (refresh_service,      │
                         │   equity_snapshot_service, scheduler)      │
                         └───────────────┬────────────────────────────┘
                                         │ laporan & snapshot diterbitkan
                                         ▼
   ┌──────────────────────────────────────────────────────────────────────┐
   │  BACKEND (FastAPI, market_report)                                    │
   │                                                                      │
   │  ┌───────────────────┐   ┌──────────────────────┐                    │
   │  │ Context Builder   │   │ Policy / Rule Engine │◀── docs/llm_rules.md│
   │  │ (§5, §6)          │   │ (§9)                 │                    │
   │  └─────────┬─────────┘   └──────────┬───────────┘                    │
   │            │  NarrativeContext      │ RuleSet + digest prompt        │
   │            ▼                        ▼                                │
   │  ┌────────────────────────────────────────────────────┐              │
   │  │  NarrativeEngine.generateNarrative(context)        │              │
   │  │  ┌────────────┐ ┌─────────────┐ ┌───────────────┐  │              │
   │  │  │ Research   │ │ Evidence    │ │ Prompt Builder│  │              │
   │  │  │ (§7)       │→│ (§8)        │→│ (§10)         │  │              │
   │  │  └─────┬──────┘ └─────────────┘ └───────┬───────┘  │              │
   │  │        │ SearchProvider                 │ messages │              │
   │  │        ▼                                ▼          │              │
   │  │  ┌──────────────┐            ┌──────────────────┐  │              │
   │  │  │ Provider     │            │ LLM Provider     │  │              │
   │  │  │ Registry §18 │───────────▶│ (interface)      │  │              │
   │  │  └──────────────┘            └────────┬─────────┘  │              │
   │  │                                       │ raw output  │              │
   │  │  ┌────────────────────────────────────▼──────────┐ │              │
   │  │  │ Validation Layer (§11, §12, §13)              │ │              │
   │  │  │ number → source → date → style → claims       │ │              │
   │  │  └───────────────┬───────────────────────────────┘ │              │
   │  └──────────────────┼─────────────────────────────────┘              │
   │                     │ accepted / rejected → retry → fallback         │
   │        ┌────────────▼─────────────┐   ┌─────────────────────────┐    │
   │        │ Narrative Cache (§15)    │   │ Audit Trail (§17)       │    │
   │        │ runtime/ + Postgres      │   │ narrative_runs, sources │    │
   │        └────────────┬─────────────┘   └─────────────────────────┘    │
   └─────────────────────┼───────────────────────────────────────────────-┘
                         │ GET /api/v1/narratives/{page}  (API_READ_TOKEN)
                         ▼
              ┌──────────────────────────┐        ┌─────────────────────────┐
              │ Next.js route handler    │───────▶│ Dashboard / Equity UI   │
              │ (token tetap di server)  │        │ (narasi read-only +     │
              └──────────────────────────┘        │  regenerate khusus      │
                                                  │  operator)              │
                                                  └─────────────────────────┘
```

**Batas tanggung jawab**

| Lapisan | Boleh | Tidak boleh |
|---|---|---|
| Pipeline/worker | memicu generasi setelah laporan terbit | memblokir publikasi laporan bila narasi gagal |
| NarrativeEngine | orkestrasi: policy → research → prompt → validate → simpan | menghitung/menebak angka pasar |
| Provider LLM | menghasilkan bahasa dari konteks | mengubah angka, tanggal, satuan |
| Validator | menolak/memperbaiki output | meloloskan angka di luar registry |
| API baca | menyajikan narasi tersimpan | memanggil LLM pada setiap request halaman |
| Frontend | menampilkan + meminta regenerate (operator) | menyimpan API key LLM/search |

---

## 3. Component architecture

Komponen diletakkan mengikuti struktur yang sudah ada (`domain/`, `services/`, `infrastructure/repositories/`, `api/routers/`, `migrations/`).

```
backend/src/market_report/
├── domain/
│   ├── narration_contract.py       # dataclass murni: NarrativeRequest, NarrativeContext,
│   │                               #   NumberRegistry, EvidenceItem, NarrativeResult
│   ├── number_registry.py          # ekstraksi token angka + pencocokan (tanpa I/O, mudah diuji)
│   └── narrative_rules.py          # parser docs/llm_rules.md → RuleSet (tanpa dependensi baru)
├── services/narration/
│   ├── __init__.py
│   ├── engine.py                   # NarrativeEngine.generate_narrative(context) — orkestrator (§2)
│   ├── context_builder.py          # payload laporan/equity → NarrativeContext (hanya angka tampil)
│   ├── research_service.py         # orkestrasi web search + dedup + freshness (§7)
│   ├── evidence.py                 # rank, ekstraksi klaim, penautan klaim→sumber (§8)
│   ├── prompt_builder.py           # system/context/evidence/task block + skema output (§10)
│   ├── validators.py               # number/source/date/style/claim validator (§11–§13)
│   ├── cache.py                    # narrative cache: key, TTL, invalidasi (§15)
│   ├── audit.py                    # penulis audit trail + redaksi log (§16, §17)
│   └── providers/
│       ├── base.py                 # Protocol LLMProvider & SearchProvider (§18)
│       ├── registry.py             # pemilihan provider dari env + circuit breaker
│       ├── openai_compatible.py    # REST via `requests` (OpenAI-compatible gateway/self-host)
│       ├── anthropic_compatible.py # opsional
│       ├── search_webz.py          # news search provider (§7)
│       ├── search_exa.py           # alternatif semantic search (§7)
│       └── search_none.py          # mode tanpa search (degradasi terencana)
├── infrastructure/repositories/
│   └── narrative_repository.py     # Postgres: runs, sources, claims, outputs (§17)
└── api/routers/
    └── narratives.py               # GET /narratives/{page}, POST /narratives/{page}/regenerate

backend/migrations/017_narratives.sql     # tabel audit + cache (§15, §17)
backend/config/llm_rules.md               # salinan policy untuk deployment (opsional; lihat §9.6)
frontend/src/app/api/narratives/[page]/route.ts   # proxy server → API internal
frontend/src/features/dashboard/llm-narrative-panel.tsx
frontend/src/features/equity-snapshot/llm-narrative-panel.tsx
```

**Kontrak interface inti (bentuk, bukan implementasi)**

```python
# domain/narration_contract.py
class NarrativePage(StrEnum):  DASHBOARD = "dashboard"; EQUITY_SNAPSHOT = "equity_snapshot"

@dataclass(frozen=True)
class NarrativeContext:
    page: NarrativePage
    report_id: str
    report_date: str                     # tanggal sesi/laporan, sudah tervalidasi
    as_of: dict[str, str]                # instrumen → tanggal observasi
    numbers: dict[str, float | None]     # hanya angka yang tampil di halaman
    units: dict[str, str]
    registry: NumberRegistry             # turunan `numbers` (§11)
    equity: dict | None = None           # blok khusus equity snapshots (§6)
    headlines: list[str] = ()            # narasi deterministik lama sebagai referensi aman

# services/narration/providers/base.py
class LLMProvider(Protocol):
    name: str
    model: str
    def generate(self, *, system: str, user: str, schema: dict,
                 max_tokens: int, temperature: float) -> "LLMResponse": ...

class SearchProvider(Protocol):
    name: str
    def search(self, *, query: str, since: str, limit: int) -> list["RawSearchResult"]: ...

# services/narration/engine.py
class NarrativeEngine:
    def generate_narrative(self, request: NarrativeRequest) -> NarrativeResult: ...
```

`generate_narrative(...)` adalah satu-satunya pintu masuk — setara `generateNarrative(context)` yang diminta — sehingga mengganti provider, model, atau strategi search tidak menyentuh pemanggil (worker, API, maupun PDF).

---

## 4. Data flow

### 4.1 Alur utama (sesuai permintaan, dengan penegasan titik kendali)

```
Application (pipeline/worker/operator)
   ↓
Dashboard Data  (laporan aktif + snapshot equity + riwayat yang sudah tersimpan)
   ↓
Context Builder → Structured JSON Payload (NarrativeContext)     ← HANYA angka yang tampil
   ↓
Narrative Engine
   ↓
Load llm_rules.md (RuleSet + rules_hash)                         ← policy layer
   ↓
Validate dashboard data (blocking: report_id, tanggal, unit, konsistensi)
   ↓
Web Search (query dibentuk dari anomali data — §7.3)
   ↓
Collect + Clean + Dedup + Rank sources (§7, §8)
   ↓
Evidence filtering (freshness ↔ tanggal laporan, kualitas sumber, relevansi)
   ↓
LLM reasoning + Generate narrative (JSON, skema tetap)
   ↓
Rule validation → Number validation → Source/date validation → Claim check
   ↓
   ├── lulus   → simpan cache + audit → status `published`
   └── gagal   → repair (maks N) → fallback deterministik → status `fallback`
   ↓
Dashboard UI / Equity UI (GET, read-only dari cache)
```

### 4.2 Tiga pemicu generasi (eksplisit)

| Pemicu | Kapan | Batas |
|---|---|---|
| Refresh pipeline (harian) | setelah `publish_snapshot()` sukses (§ `services/report_service.py`) | 1× per halaman per laporan |
| Intraday (opsional) | sesi berjalan, hanya bila diaktifkan di rules | dibatasi `LLM_MAX_CALLS_PER_DAY` |
| Regenerate manual | operator menekan tombol di UI | `require_operator_access`, rate limit ketat (§21) |
| **Pembekuan ke laporan terbit** | setelah narasi lulus validasi pada laporan aktif | ditulis sekali per `report_id`; PDF membaca salinan beku (§15.1) |

Pembacaan halaman (`GET /reports/latest`, `/equity/latest`) **tidak pernah** memicu LLM. Bila cache kosong atau kedaluwarsa, halaman menampilkan narasi deterministik lama (`build_summary` / `build_insights` / `compose_equity_narratives`) dan penanda "narasi otomatis sedang tidak tersedia".

### 4.3 Urutan yang penting dijaga

- Generasi dijalankan **setelah** laporan/snapshot tersimpan, sehingga angka yang dibaca identik dengan yang dilihat pengguna.
- Kegagalan generasi dibungkus `try/except` seperti pola yang sudah ada pada `record_sbn_history` dan `sync_timeseries_*` — publikasi laporan tidak boleh gagal karena narasi.

---

## 5. Dashboard → LLM data contract

### 5.1 Sumber angka (tanpa scraping HTML)

`Context Builder` memakai fungsi yang sudah ada:

- `report_service.load_report()` / `load_report_version(report_id)`
- `domain.market_analysis.market_facts(report)`
- `services.instrument_history_service.instrument_history(...)` bila tren diperlukan
- `presentation.formatting` untuk aturan format angka (tidak boleh diganti LLM)

Frontend **tidak pernah** mengirim HTML atau data mentah ke LLM; tidak ada komponen OCR/parsing DOM.

### 5.2 Bentuk payload yang diberikan ke LLM

Hanya angka yang benar-benar tampil pada Dashboard Utama, dengan tanggal observasi dan satuan:

```jsonc
{
  "page": "dashboard",
  "report_id": "2026-10-16T08:00:00Z-abc123",
  "report_date": "2026-10-16",
  "as_of": { "ihsg": "2026-10-16", "usd_idr": "2026-10-16", "sbn10": "2026-10-15" },
  "market": {
    "ihsg":   { "last": 6147, "change_pct": -0.75, "date": "2026-10-16" },
    "dji":    { "last": 46120.5, "change_pct": 0.32, "date": "2026-10-15" },
    "dxy":    { "last": 101.08, "change_pct": 0.11, "date": "2026-10-16" }
  },
  "fx": {
    "usd_idr": { "last": 17903, "prev": 17916, "change_pct": 0.07, "date": "2026-10-16" }
  },
  "foreign_flow": { "value": -1613.46, "unit": "IDR_bn", "date": "2026-10-16", "source": "BEI" },
  "rates": {
    "bi_rate": { "value": 4.75, "date": "2026-10-15" },
    "indonia": { "value": 4.51, "date": "2026-10-15" },
    "sbn10":   { "yield_pct": 6.31, "change_bp": -2.4, "date": "2026-10-15" },
    "ust10":   { "yield_pct": 4.06, "change_bp": 1.1, "date": "2026-10-15" },
    "spread_sbn10_ust10_bp": 225
  },
  "commodities": {
    "gold":  { "last": 4210.4, "change_pct": 0.48, "unit": "USD/oz", "date": "2026-10-16" },
    "brent": { "last": 63.12, "change_pct": -1.04, "unit": "USD/bbl", "date": "2026-10-16" },
    "antam": { "last": 2450000, "change_pct": 0.3, "unit": "IDR/gr", "date": "2026-10-16" }
  },
  "index_sectors": [
    { "id": "IDXENERGY", "label": "Energi", "mtd_pct": 2.39, "dtd_pct": 0.84, "date": "2026-10-16" }
  ],
  "macro": {
    "inflasi_yoy": { "value": 2.86, "period": "2026-09" }
  },
  "capital_flow": { "saham_usd_mn": -98.4, "date": "2026-10-16", "periods": { "1D": -98.4, "MtD": -410.2 } },
  "narrative_seed": {                  // narasi deterministik yang sudah ada hari ini
    "summary": "…string dari build_summary()…",
    "insights": [{ "title": "…", "text": "…", "dampak": "…" }]
  }
}
```

Aturan payload:

- Semua angka memakai **nilai mentah dari payload laporan**, bukan string hasil `formatting`, agar validasi angka bisa membandingkan nilai numerik (format tampilan diterapkan kembali setelahnya bila perlu).
- Kunci `null`/`"—"` tetap dikirim apa adanya dengan penanda `unavailable: true`; LLM wajib menghilangkan, bukan mengisi.
- Payload dibatasi pada instrumen yang relevan (`LLM_CONTEXT_MAX_INSTRUMENTS`, default 20) — bukan seluruh laporan.

### 5.3 Skema `NarrativeContext` sebagai sumber registry

Setiap entri `numbers` menghasilkan satu baris registry (§11.2) yang dipakai validator: nilai, satuan, tanggal, dan arah. Registry **tidak** diberikan ke LLM (agar tidak bisa dijadikan bahan mengarang); yang diberikan ke LLM adalah angka + konteksnya.

---

## 6. Data contract Equity Snapshot

Berasal dari `equity_snapshot_service.load_equity_snapshot()` + `domain.equity_snapshot.enrich_equity_indicators()` (jalur yang sudah dipakai `GET /api/v1/equity/latest`).

```jsonc
{
  "page": "equity_snapshot",
  "report_id": "…",
  "report_date": "2026-10-16",
  "ihsg": { "last": 6147, "change_pct": -0.75, "prev_date": "2026-10-15" },
  "coverage": { "valid_count": 842, "universe_count": 910, "ratio": 0.93, "residual_points": -12.4 },
  "market_performance": [
    { "id": "IDXENERGY", "label": "IDXENERGY", "level": 2183.4, "change_pct": 0.84, "date": "2026-10-16" },
    { "id": "SPX", "label": "S&P 500 (US)", "level": 6721.1, "change_pct": 0.28, "date": "2026-10-15" }
  ],
  "market_leaders": [{ "ticker": "BBCA", "change_pct": 1.42, "contribution_points": 12.8, "sector": "Financial Services" }],
  "market_laggards": [{ "ticker": "GOTO", "change_pct": -3.10, "contribution_points": -6.4, "sector": "Technology" }],
  "sector_contributions": [{ "sector": "Financial Services", "contribution_points": 18.2 }],
  "foreign_flow": { "net_usd_mn": -98.4, "net_idr": -1762000000000, "date": "2026-10-16", "source": "BEI", "stale": false },
  "foreign_flow_rows": [{ "country": "Indonesia", "date": "2026-10-16", "daily": -98.4, "mtd": -410.2, "ytd": -1220.0 }],
  "coal": { "mtd_pct": 3.12, "date": "2026-10-16", "price": 118.4, "source": "…", "stale": false },
  "narrative_seed": { "narratives": [{ "id": "market", "title": "Pergerakan IHSG dan sikap Investor", "text": "…" }] }
}
```

**Perbedaan konteks antarhalaman (context separation)**

| Aspek | Dashboard Utama | Equity Snapshot |
|---|---|---|
| Fokus | pasar & makro: FX, DXY, yield, komoditas, indeks global, suku bunga | saham: IHSG, sektor, movers, breadth, foreign flow, katalis saham/sektoral |
| Cakupan makro | wajib (domestik + global) | ringkas, hanya bila menjelaskan pergerakan equity |
| Data yang tidak dipakai | detail ratusan saham | kalender/tema makro panjang |
| Struktur keluaran | 1 blok narasi (2–4 kalimat) | blok per poin: pasar, makro ringkas, arus asing, sektoral |
| Batas panjang | dari rules `[dashboard]` | dari rules `[equity_snapshot]` |
| Query search | makro, FX, bank sentral, komoditas, geopolitik | berita emiten/sektor, aksi korporasi, arus asing, indeks |

Keduanya memakai komponen, validator, dan file policy yang sama; yang berbeda hanya `ContextBuilder`, blok prompt, dan set rule yang aktif. Tidak ada dua implementasi narasi terpisah.

---

## 7. Web search pipeline

### 7.1 Mode pengumpulan bukti

Ada tiga mode, dipilih lewat `SEARCH_PROVIDER` — semuanya menghasilkan bentuk `web_evidence` yang sama (§7.5), sehingga sisa pipeline tidak berubah:

| Mode | Cara kerja | Kebutuhan kredensial |
|---|---|---|
| `seeded` (aktif lebih dulu) | mengambil halaman/kanal dari **registry sumber** yang ditetapkan pengguna (§31) — kanal berita pasar, halaman kalender/stream data, siaran resmi lembaga | tidak perlu |
| `provider` | memanggil API pencarian berita/web untuk menemukan katalis di luar registry | perlu API key pihak ketiga |
| `none` | tidak ada konteks eksternal; narasi hanya dari angka + frasa netral (§24) | tidak perlu |

Mode `seeded` menjawab sebagian besar kebutuhan awal: registry sudah memuat Bank Indonesia, OJK, BPS, IDX, Fed, US Treasury, ECB, IMF, World Bank, TradingEconomics, Investing.com, Yahoo Finance, Bloomberg Technoz, Reuters, Bloomberg, FT, dan CNBC. Mode `provider` tetap disiapkan sebagai perluasan (mis. mencari berita emiten di luar kanal yang terdaftar).

Opsi implementasi `SearchProvider` (untuk mode `provider`):

| Opsi | Peran | Catatan |
|---|---|---|
| News/search API terstruktur (mis. Webz.io News Search) | pencarian berita dengan tanggal terbit, domain sumber, kutipan | paling cocok untuk evidence timestamp |
| Semantic search API (mis. Exa) | menemukan halaman/berita relevan + isi teks | baik untuk grounding, tetap perlu filter tanggal |
| Provider internal/self-host | bila ingin tanpa pihak ketiga | memerlukan pemeliharaan crawler |

Blueprint **tidak** mengikat satu vendor: `SEARCH_PROVIDER` memilih implementasi `SearchProvider`. Tahap awal memakai mode `seeded` sehingga tidak ada kredensial pihak ketiga yang dibutuhkan; bila mode `provider` dipakai, kredensial wajib disetujui lebih dulu (§29).

Catatan teknis mode `seeded`: halaman kanal sering memuat banyak tautan. Karena itu `research_service` mengambil **daftar tautan artikel** dari halaman kanal, lalu hanya membuka artikel yang lolos filter tanggal, dibatasi `SEARCH_SEED_MAX_ARTICLES_PER_SOURCE` (default 4) per sumber per run.

### 7.2 Tahapan

```
Trigger → Query planner → Search (provider) → Fetch/Extract → Clean → Dedup
        → Freshness filter → Quality filter → (Evidence pipeline §8)
```

1. **Query planner** menyusun ≤ `SEARCH_MAX_QUERIES` (default 6) query dari *anomali* data, bukan dari daftar statis.
2. **Ambil kandidat**: mode `seeded` menelusuri registry (§31) dengan batas `since = report_date − SEARCH_LOOKBACK_DAYS` (default 3); mode `provider` memanggil `SearchProvider` dengan `since` dan `limit` kecil (default 8/query). Keduanya menghasilkan daftar kandidat dengan struktur identik.
3. **Fetch/Extract** mengambil teks bersih; hanya untuk kandidat yang lolos ranking awal, maksimal `LLM_EVIDENCE_MAX_ITEMS` (default 8) dokumen.
4. **Clean**: buang boilerplate, iklan, navigasi, komentar pembaca, dan blok yang berisi instruksi (§19.5).
5. **Dedup**: kunci `sha1(canonical_url)` + `sha1(judul-ternormalisasi)`; bila ada sindikasi, simpan sumber primer dan tandai yang lain sebagai duplikat.
6. **Freshness filter**: `published_at` wajib ada. Item tanpa tanggal → diturunkan ke `low_confidence` atau dibuang. Item dengan tanggal > `report_date` → dibuang (tidak boleh memakai berita "masa depan" relatif laporan).
7. **Quality filter**: domain dinilai memakai registry sumber (§31) yang dipetakan ke tier.

### 7.3 Pembentukan query dari market data

Query dibentuk dari data yang benar-benar ada, hanya untuk instrumen yang bergerak bermakna (mis. `|change_pct| ≥ rules.thresholds.query_material_pct`, default 0.5%):

| Pemicu di payload | Contoh query |
|---|---|
| Rupiah bergerak | `"rupiah USD IDR pergerakan 16 Oktober 2026"`, `"Bank Indonesia intervensi pasar valas"` |
| IHSG bergerak / net foreign negatif | `"IHSG asing net sell alasan"`, `"sunset/aksi korporasi IHSG"` |
| Gainer/laggard terbesar | `"<TICKER> <nama emiten> berita <bulan tahun>"` (maks 3 ticker) |
| Brent/WTI bergerak | `"harga minyak dunia OPEC berita"` |
| Batubara MTD bergerak | `"harga batubara Newcastle permintaan China"` |
| SBN/UST bergerak | `"yield UST pergerakan data inflasi AS"` |
| Sektor memimpin/tertinggal | `"sektor <nama> IHSG katalis"` |

Batasan: query **tidak boleh** menyertakan pertanyaan yang meminta angka ("berapa level IHSG") — sistem sudah punya angkanya. Query selalu berupa pencarian peristiwa/katalis.

### 7.4 Cara menghindari duplikasi informasi

- Dedup URL/kanonik dan judul (SimHash atau normalisasi kata kunci bila tersedia).
- Satu kejadian boleh muncul dari beberapa outlet: simpan satu `event_key` (mis. `bi-rate-decision-2026-10-15`) dan jaga hanya sumber dengan kualitas tertinggi sebagai bukti utama.
- Batasi `n` item per domain (default 2) dan per `event_key` (default 1) pada bukti final.

### 7.5 Penyimpanan dan bentuk bukti

```jsonc
{
  "dashboard_data": { /* §5 */ },
  "web_evidence": [
    {
      "evidence_id": "E1",
      "title": "Bank Indonesia Jaga Stabilitas Rupiah",
      "url": "https://www.bi.go.id/…",
      "source": "bi.go.id",
      "source_tier": "primary_official",
      "published_at": "2026-10-15T17:20:00+07:00",
      "fetched_at": "2026-10-16T08:04:12+07:00",
      "language": "id",
      "event_key": "bi-stability-statement-2026-10-15",
      "summary": "Ringkasan netral ≤ 40 kata, tanpa angka pasar.",
      "relevance": 0.94,
      "used_for": ["fx_context"]
    }
  ]
}
```

Kontrak tegas: **`web_evidence` tidak pernah digabung ke `dashboard_data`.** Evidence masuk ke prompt pada blok terpisah (`<evidence>`), sedangkan angka masuk pada blok `<authoritative_numbers>` (§10).

---

## 8. Evidence pipeline

Permintaan Anda: `Search → Retrieve → Clean → Rank → Extract facts → Validate → Generate`. Pemetaan implementasinya:

| Tahap | Komponen | Aturan yang mengikat |
|---|---|---|
| Search | `research_service` + `SearchProvider` | hanya jika `search.enabled` di rules & provider tersedia |
| Retrieve | `research_service.fetch_full_text` | timeout, maksimum N dokumen, tolak `content-type` non-teks |
| Clean | `evidence.clean_text` | buang boilerplate & instruksi tak terpercaya |
| Rank | `evidence.rank` | skor = `w_s·tier + w_f·freshness + w_r·relevance`; skor < `min_relevance` (default 0.45) dibuang |
| Extract facts | `evidence.extract_claims` | satu klaim = kalimat atomik + `event_key` + `evidence_id` |
| Validate | `validators.validate_claims` | setiap klaim wajib punya minimal satu `evidence_id` bertipe `primary`/`major_media` |
| Generate | `engine` + `LLMProvider` | hanya klaim tervalidasi yang boleh menjadi klaim kausal |

**Struktur klaim (output antara, sebelum generasi)**

```jsonc
{
  "claims": [
    { "claim_id": "C1", "text": "Bank Indonesia menyatakan komitmen menjaga stabilitas nilai tukar.",
      "type": "statement", "evidence_ids": ["E1"], "event_key": "bi-stability-statement-2026-10-15",
      "supports": ["fx_context"] }
  ]
}
```

Aturan penautan: klaim `causal` hanya boleh dipakai bila ada ≥1 bukti yang **secara eksplisit** menyatakan hubungan sebab-akibat (`supports_causality: true`). Jika tidak, gaya output diturunkan ke "seiring"/"di tengah" sesuai §9.5.

Bila `claims` kosong → bukan error; generasi lanjut tanpa blok eksternal dan wajib memakai frasa netral (§24).

---

## 9. Rule engine

### 9.1 Posisi

`docs/llm_rules.md` adalah **policy layer** (aturan main), `docs/LLM_NARRATIVE_ENGINE_BLUEPRINT.md` adalah desain teknis. Bila aturan policy bertentangan dengan kode, policy menang; kode hanya boleh *lebih ketat*, tidak lebih longgar.

### 9.2 Format file: prosa + blok terstruktur

Agar bisa diedit manusia **dan** diparse mesin tanpa dependensi baru (project belum memakai PyYAML/TOML parser), formatnya adalah markdown dengan heading sebagai bagian, bullet `key: value` sebagai konfigurasi, dan kalimat bebas sebagai aturan manusia:

```markdown
# LLM Narrative Rules — Daily Market Report

> policy_version: 1
> Perubahan file ini otomatis mengubah rules_hash dan membatalkan cache narasi lama.

## [global]
- language: id
- tone: objective
- style: professional
- max_paragraphs: 1
- deductive: true

## [numbers]
- authoritative_source: application_payload
- never_invent: true
- never_estimate: true
- never_round: true
- preserve_units: true
- preserve_sign: true
- preserve_dates: true
- allow_derived_arithmetic: false
- reject_on_mismatch: true

## [sources]
- mode: seeded                     # seeded | provider | none (keputusan: seeded lebih dulu)
- registry: appendix_31            # registry domain & tier, lihat §31
- require_source_for_external_claims: true
- min_source_tier: major_media
- max_items_per_domain: 2
- reject_undated: true
- lookback_days: 3

## [dashboard]
- max_sentences: 4
- max_words: 100
- must_cover: [domestic, global, catalyst, risk]

## [equity_snapshot]
- max_sentences: 3
- max_words: 80
- sections: [market, macro, foreign_flow, sector]

## [macro]
- include_global_context: true
- include_domestic_context: true
- avoid_unsupported_causality: true
- causality_requires_explicit_source: true
- allowed_safe_connectives: [seiring, di tengah, bertepatan dengan]

## [validation]
- number_validation: required
- source_validation: required
- date_validation: required
- style_validation: required
- max_repair_attempts: 1

## [fallback]
- on_llm_failure: deterministic_seed
- on_search_failure: dashboard_only
- on_no_evidence: neutral_phrasing

## Macros (dipakai sebagai frasa aman oleh narator)
- neutral_phrasing_no_catalyst: "Belum terdapat katalis yang cukup kuat dari sumber yang tersedia."
- neutral_phrasing_stale: "Data terbaru untuk indikator ini belum tersedia pada tanggal laporan."

## Priority source list (tier menurun — versi lengkap & domain aktual ada di §31)
1. Bank Indonesia — primary_official
2. OJK — primary_official
3. BPS — primary_official
4. Kementerian/Lembaga — primary_official
5. IDX — primary_official
6. Federal Reserve / ECB / IMF / World Bank — supranational_official
7. Reuters / Bloomberg / FT — major_media
8. CNBC dan media keuangan besar — major_media
9. Sumber kredibel lain — secondary
```

### 9.3 Aturan angka yang dipaksakan kode (tidak cukup ditulis)

`never_invent`, `preserve_units`, `preserve_sign`, `preserve_dates` **bukan** sekadar instruksi prompt: §11 menegakkannya setelah generasi. Rules hanya boleh melonggarkan hal seperti `max_words`, `max_sentences`, `tone`, `must_cover`.

Value yang **tidak boleh** dilonggarkan lewat rules (hard-coded di validator): larangan menciptakan angka, larangan memakai angka web sebagai angka utama, larangan tanggal masa depan, kewajiban sumber untuk klaim eksternal.

### 9.4 Parser

`domain/narrative_rules.py`:
- membaca file teks (UTF-8) → `RuleSet` immutable + `rules_hash` (sha256 isi file),
- `key: value` diketikkan otomatis (`true/false`, int, float, `[a, b, c]`, string),
- baris tak dikenal → dicatat sebagai `unknown_keys` (warning log, **tidak** mematikan narasi),
- nilai wajib yang hilang → memakai default kode, dicatat di audit,
- error baca/parse → `RuleSet.unavailable` → narasi memakai fallback deterministik (§22).

### 9.5 Pengaruh rules pada gaya & kausalitas

- Larangan kausal tanpa bukti (§13.4) diwujudkan sebagai *lexicon* di prompt + validator frasa ("karena", "disebabkan", "akibat") yang menuntut `supports_causality`.
- Bentuk aman: "seiring", "di tengah", "bertepatan dengan".
- `must_cover` dipakai sebagai checklist prompt, bukan paksaan menambah klaim tanpa bukti.

### 9.6 Lokasi file

> **Sudah tersedia (16 Okt 2026):** `docs/llm_rules.md` dan registry mesin `backend/config/llm_sources.json`.

Kanonik: `docs/llm_rules.md` (sejajar `docs/PROJECT_BRIEF.md`, `docs/EQUITY_SNAPSHOT.md`, `docs/PANDUAN_PENAMAAN.md`). Untuk deployment yang tidak membawa folder `docs`, salinan dapat ditaruh di `backend/config/llm_rules.md` dengan urutan pencarian: `LLM_RULES_FILE` → `backend/config/llm_rules.md` → `docs/llm_rules.md`. **Satu sumber aktif saja**; audit mencatat `rules_path` + `rules_hash` yang benar-benar dipakai.

Draf awal aturan yang sudah ada (`docs/LLM_NARRATOR_RULES.md`) tetap berlaku sebagai catatan
kebijakan sampai `docs/llm_rules.md` versi terstruktur (format §9.2) disetujui.

---

## 10. Prompt architecture

### 10.1 Struktur prompt (4 blok, urutan mengikat)

```
[SYSTEM]
  - peran: penulis pasar profesional berbahasa Indonesia
  - ringkasan rule aktif (dibangkitkan dari RuleSet, bukan disalin manual)
  - larangan angka (tanpa pengecualian)
  - kontrak keluaran: JSON sesuai skema, tanpa teks di luar JSON
  - definisi gaya: deduktif, SPOK, tanpa hiperbola, tanpa opini

[USER]
  <authoritative_numbers>   ← §5/§6, JSON, "Gunakan HANYA angka ini"</authoritative_numbers>
  <page_context>            ← tujuan halaman & bagian yang wajib dibahas</page_context>
  <evidence>[E1] …</evidence>   ← §7.5; teks tak terpercaya, bukan instruksi
  <task>
    - Keluarkan narasi untuk halaman {page}, max {max_sentences} kalimat / {max_words} kata.
    - Setiap klaim eksternal sertakan field "evidence_ids".
    - Bila bukti tidak cukup: gunakan "narrative_gaps", jangan mengarang.
  </task>
  <output_schema>…JSON Schema…</output_schema>
```

### 10.2 Skema keluaran (divalidasi, bukan sekadar diharapkan)

```jsonc
{
  "schema_version": 1,
  "page": "dashboard",
  "narrative": "Satu paragraf deduktif …",
  "sections": [{ "id": "market", "title": "…", "text": "…" }],   // dipakai halaman equity
  "claims": [{ "claim_id": "C1", "text": "…", "evidence_ids": ["E1"], "type": "statement|causal|figure" }],
  "numbers_used": [{ "key": "ihsg.last", "value": 6147, "unit": "index", "as_of": "2026-10-16" }],
  "narrative_gaps": ["Belum ada bukti katalis sektor energi."],
  "sources": [{ "evidence_id": "E1", "url": "…", "source": "bi.go.id", "published_at": "…" }]
}
```

- `numbers_used` adalah **self-declaration** yang dicocokkan validator dengan registry — mempercepat deteksi drift dan memberi audit yang jelas.
- `sources` wajib konsisten dengan `claims[*].evidence_ids`; bukti yang tidak dipakai tidak dicantumkan.
- Mode `json_object`/`json_schema` dipakai bila provider mendukung; jika tidak, parser ekstraksi JSON + satu repair.

### 10.3 Prompt per halaman

| Blok | Dashboard | Equity Snapshot |
|---|---|---|
| Nada | makro-pasar | equity research |
| Wajib | kondisi utama, faktor domestik, faktor global, katalis, risiko/sentimen | pergerakan IHSG, sektor & movers, arus asing, katalis saham/sektoral |
| Dilarang | menyimpulkan makro dari harga saja | mengarang aksi korporasi tanpa bukti |
| Seed | `build_summary` + `build_insights` | `compose_equity_narratives` (dipakai sebagai referensi faktual yang aman) |

### 10.4 Anti-prompt-injection & determinisme

- `temperature` rendah (default 0.2), `max_tokens` dibatasi.
- Semua konten web dibungkus penanda data; instruksi di dalamnya diabaikan (aturan eksplisit pada blok system + `evidence.clean_text`).
- Prompt **tidak** berisi kredensial, path internal, nama tabel, atau log.
- Prompt disusun versi (`PROMPT_VERSION`); perubahan versi membatalkan cache.

---

## 11. Number validation

### 11.1 Prinsip

```
Dashboard Numbers (payload)  →  Number Registry  →  LLM  →  Generated Narrative
                                                                      ↓
                                                             Number Validator  →  lulus / tolak
```

Number Validator **tidak** mempercayai LLM maupun prompt. Ia membandingkan narasi dengan registry yang dibangun dari payload, dan hanya keluarannya yang lulus yang boleh ditampilkan atau dibekukan ke laporan terbit.

### 11.2 Number Registry

`domain/number_registry.py` membangun:

```python
registry.entries = {
  "ihsg.last":        Entry(value=6147,     unit="index",   as_of="2026-10-16", sign=+1),
  "ihsg.change_pct":  Entry(value=-0.75,    unit="percent", as_of="2026-10-16", sign=-1),
  "usd_idr.last":     Entry(value=17903,    unit="IDR/USD", as_of="2026-10-16", sign=+1),
  "foreign_flow.value": Entry(value=-1613.46, unit="IDR_bn", as_of="2026-10-16", sign=-1),
}
registry.allowed_numbers = {…him­punan nilai dengan varian format…}
registry.allowed_dates   = {"2026-10-16", "2026-10-15", …}
registry.allowed_years   = {2026, 2025}
```

### 11.3 Ekstraksi token dari narasi

1. Deteksi token numerik dengan dukungan format Indonesia (`6.147`, `1.613,46`) **dan** Inggris (`6,147`, `1613.46`).
2. Normalisasi ke `Decimal` (bukan float) untuk menghindari mismatch pembulatan.
3. Klasifikasikan token: angka pasar, persen, satuan mata uang, tahun, tanggal, angka ordinal dalam kalimat ("dua sektor") → daftar kata bilangan Indonesia ikut dianggap aman.

### 11.4 Pemeriksaan (semua wajib lulus)

| # | Pemeriksaan | Kegagalan → |
|---|---|---|
| N1 | Setiap angka numerik ada di `allowed_numbers` (toleransi relatif `1e-9`, atau varian pembulatan yang diizinkan rules) | reject |
| N2 | Tanda +/− tidak berubah dari payload | reject |
| N3 | Satuan pendamping cocok (`%`, `bp`, `Rp`, `IDR Tn/Bn/Mn`, `USD/bbl`, …) | reject |
| N4 | Tanggal & periode yang disebut ada di `allowed_dates`; tidak ada tanggal masa depan | reject |
| N5 | Angka dan tanggal berasal dari observasi yang sama (tidak mencampur IHSG 16 Okt dengan SBN 12 Okt tanpa label tanggal) | reject/repair |
| N6 | `numbers_used` di keluaran LLM konsisten dengan registry (toleransi pembulatan tampilan berlaku, angka berbeda tetap ditolak) | reject bila berbeda |
| N7 | Tidak ada angka web (URL/evidence) yang muncul sebagai angka pasar | reject |

### 11.5 Toleransi yang boleh dikonfigurasi

- `allow_rounding` (default `false`): bila `true`, hanya pembulatan ke jumlah desimal yang **sudah** dipakai halaman (mis. IHSG 0 desimal) yang diizinkan pada angka yang **sama**, bukan angka baru.
- Angka hasil turunan (mis. selisih dua level) **tidak** diizinkan kecuali `allow_derived_arithmetic: true` **dan** nilainya dapat dihitung ulang oleh validator dari registry.

### 11.6 Kegagalan

`ValidatorOutcome.rejected_numbers = [("1.610", "tidak ada di registry")]` → repair prompt menyebut token bermasalah → 1 kali retry → fallback deterministik. Tidak ada jalur yang menampilkan narasi gagal validasi.

---

## 12. Source validation

1. **Kelengkapan**: setiap klaim `type in {"statement","causal"}` wajib punya ≥1 `evidence_id` valid.
2. **Eksistensi**: `evidence_id` harus ada di `web_evidence` run tersebut (bukan dikarang).
3. **Tier minimum**: `source_tier ≥ rules.sources.min_source_tier` (default `major_media`); tier ditentukan registry sumber (§31), dan domain yang tidak terdaftar otomatis `secondary`.
4. **Waktu**: `published_at ≤ report_date` dan `≥ report_date − rules.sources.lookback_days`.
5. **Primer diprioritaskan**: bila dua bukti membahas `event_key` sama, hanya yang tertinggi dipakai; jika pernyataan berkaitan dengan kebijakan resmi, tier `primary_official` wajib.
6. **Kredibilitas domain**: registry §31 memetakan domain ke tier (`official_primary`, `id_market_media`, `global_market_media`, `data_portal`, `secondary`) dan dipakai sebagai skor, bukan penolakan absolut; domain `secondary` hanya boleh mendukung klaim non-kausal.
7. **Kutipan**: kutipan langsung (!) hanya bila teks kutipan ditemukan verbatim di bukti (pencocokan substring setelah normalisasi); kalau tidak, ubah menjadi parafrase atau hapus.
8. **Anti-sindikasi**: dua URL dengan isi identik dihitung satu sumber.

Kegagalan sumber → klaim dibuang (`drop_claim`), bukan narasi ditolak seluruhnya; bila seluruh klaim hilang → frasa netral (§24).

---

## 13. Hallucination protection

| Risiko yang disebut | Mekanisme |
|---|---|
| Berita karangan | klaim wajib punya `evidence_id`; validator memeriksa keberadaan dan kecocokan `event_key` (§12) |
| Statistik karangan | §11 penuh (registry + toleransi + tanggal) |
| Kutipan karangan | verifikasi substring verbatim (§12.7) |
| Hubungan kausal karangan | whitelist kata kausal hanya bila `supports_causality: true`; jika tidak → lexicon aman (§9.5) |
| Pergerakan pasar karangan | angka & arah dari payload; `numbers_used` dicocokkan (§11.2, N6) |
| Sumber karangan | `web_evidence` hanya dari provider; URL non-allowlist tidak dapat masuk `sources` |
| Peristiwa korporasi karangan (dividen, rights issue, suspend, rebalancing) | daftar "event sensitif": hanya boleh disebut bila bukti tier `primary_official`/`major_media` ada dan menyebut emiten/tanggal; bila tidak → hapus |
| Prediksi sebagai fakta | validator memblokir bentuk "akan", "diprediksi", "diperkirakan" kecuali berstatus kalimat bersyarat di `narrative_gaps` |

**Preferensi eksplisit yang diminta**: bila bukti kurang, LLM wajib memakai
"Belum terdapat katalis yang cukup kuat dari sumber yang tersedia."
Frasa ini diambil dari rules (`neutral_phrasing_no_catalyst`) sehingga bisa diedit tanpa mengubah kode.

Lapisan tambahan: **self-consistency check** — bila dua run paralel (opsional, hanya untuk halaman dashboard) menghasilkan klaim yang bertentangan pada `event_key` sama, klaim tersebut dibuang. Fitur ini opsional karena menambah biaya (§20).

---

## 14. Error handling

### 14.1 Taksonomi

```python
class NarrativeError(Exception): ...
class RulesUnavailableError(NarrativeError): ...      # file policy tidak terbaca
class ContextUnavailableError(NarrativeError): ...    # laporan/snapshot belum ada / tidak valid
class ProviderUnavailableError(NarrativeError): ...   # key hilang, provider mati, jaringan
class ProviderTimeoutError(ProviderUnavailableError): ...
class InvalidOutputError(NarrativeError): ...         # bukan JSON / skema tidak cocok
class ValidationRejectedError(NarrativeError): ...    # §11–§13
class BudgetExhaustedError(NarrativeError): ...       # §20
```

### 14.2 Kebijakan

- **Retry**: maksimum 2 percobaan pada error jaringan/timeout dengan backoff 1s → 3s; `InvalidOutputError` & `ValidationRejectedError` mendapat **1 repair attempt** (bukan retry buta).
- **Circuit breaker**: 3 kegagalan provider berturut-turut → breaker terbuka 15 menit (`runtime/narrative/breaker.json`), narasi memakai fallback tanpa memanggil provider. Ini mencegah pemborosan biaya saat provider down.
- **Fail-soft total**: seluruh jalur generasi dibungkus `try/except Exception` di pemanggil (worker/API), memakai pola yang sudah ada di `report_service` untuk `record_sbn_history`.
- **Idempotensi**: satu `run_key = (page, report_id, rules_hash, prompt_version, model)` hanya menghasilkan satu run sukses; kegagalan tidak menulis cache parsial.
- **Respons API**: `published` (narasi LLM), `fallback` (deterministik), `stale` (cache lama dari laporan sebelumnya, ditandai tanggalnya), `unavailable` (tidak ada apa pun). UI selalu tahu statusnya.

---

## 15. Caching

- **Kunci**: `sha256(page | report_id | context_hash | rules_hash | prompt_version | provider | model)`.
- **Lokasi**: Postgres (`narrative_runs` + `narrative_outputs`, §17) sebagai sumber utama; file `runtime/narrative/<key>.json` sebagai cermin agar tahan saat DB tidak tersedia — mengikuti pola `runtime/data/equity_snapshot.json` + `equity_versions/`.
- **TTL**: `NARRATIVE_CACHE_TTL_MINUTES` (default 180) untuk laporan aktif; tiap `report_id` baru membuat entri baru.
- **Invalidasi otomatis** bila: `rules_hash` berubah, `PROMPT_VERSION` berubah, model berubah, atau report baru terbit.
- **Cache negatif** dicatat (status `fallback` dengan alasan) selama 30 menit agar UI tidak memicu percobaan berulang.
- **Riwayat**: satu entri per `report_id` dipertahankan sehingga narasi versi lama tetap dapat ditampilkan bersama versi laporan lama (`/reports/{report_id}`) — konsisten dengan perilaku versi laporan yang sudah immutable.
- **Cache tidak memengaruhi angka**: halaman selalu membaca angka dari laporan/snapshot, hanya bahasa yang di-cache.

### 15.1 Pembekuan narasi ke laporan terbit (ditetapkan pengguna)

- Narasi final yang lulus validasi **ditulis ke artefak laporan versi itu** (field terpisah, mis. `narrative.dashboard` / `narrative.equity_snapshot`, plus `narrative_run_id`).
- Setelah beku, memperbarui narasi (regenerate atau edit analis) **tidak mengubah** laporan/PDF yang sudah terbit — perilaku ini konsisten dengan versi laporan yang sudah immutable di `report_service.load_report_version()`.
- PDF dibangun dari salinan beku, bukan dari cache terbaru, sehingga isi dokumen terbit selalu dapat direproduksi.
- Regenerasi menghasilkan **versi laporan/artefak baru** bila diinginkan, bukan menimpa yang lama.
- Bila narasi LLM tidak tersedia saat publikasi, yang dibekukan adalah **narasi deterministik** (`build_summary`, `build_insights`, `compose_equity_narratives`) dengan `narrative_status: fallback` — PDF tidak pernah kosong dan tidak pernah gagal terbit.

---

## 16. Logging

- Format existing (modul `logging` standar), satu logger per modul: `market_report.services.narration.*`.
- **Level**: `INFO` untuk 1 baris ringkasan per run; `WARNING` untuk degradasi (search gagal, repair dipakai, klaim dibuang); `ERROR` untuk kegagalan genap setelah fallback.
- **Contoh baris**:
  `narration run page=dashboard report_id=… rules_hash=ab12 prompt=v3 provider=openai-compatible model=… status=published ms=4210 tokens_in=3120 tokens_out=310 evidence=5 rejected=0`
- **Redaksi wajib**: API key, `Authorization`, isi cookie, URL dengan query token. Prompt lengkap **tidak** ditulis ke log (hanya hash). Konten web disimpan di audit, bukan di log.
- **Korelasi**: `run_id` (uuid) muncul di log, audit trail, dan respons API sehingga operator dapat melacak satu narasi dari UI sampai sumber.
- Logging mengikuti kebiasaan proyek: pesan dalam Bahasa Indonesia, tanpa detail sensitif.

---

## 17. Audit trail

### 17.1 Skema tabel (`backend/migrations/017_narratives.sql`)

```sql
CREATE TABLE IF NOT EXISTS narrative_runs (
    run_id           TEXT PRIMARY KEY,
    page             TEXT NOT NULL,              -- dashboard | equity_snapshot
    report_id        TEXT NOT NULL,
    report_date      DATE NOT NULL,
    rules_path       TEXT NOT NULL,
    rules_hash       TEXT NOT NULL,
    prompt_version   TEXT NOT NULL,
    provider         TEXT NOT NULL,
    model            TEXT NOT NULL,
    status           TEXT NOT NULL,              -- published | fallback | rejected | unavailable
    reason           TEXT,                        -- alasan fallback/penolakan
    context_hash     TEXT NOT NULL,
    cache_key        TEXT NOT NULL UNIQUE,
    latency_ms       INTEGER,
    tokens_in        INTEGER,
    tokens_out       INTEGER,
    cost_estimate_usd NUMERIC(10, 6),
    repair_count     INTEGER NOT NULL DEFAULT 0,
    evidence_count   INTEGER NOT NULL DEFAULT 0,
    validation       JSONB,                       -- ringkasan hasil validator (§11–§13)
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS narrative_outputs (
    run_id           TEXT PRIMARY KEY REFERENCES narrative_runs(run_id) ON DELETE CASCADE,
    narrative_json   JSONB NOT NULL,              -- §10.2
    rendered_text    TEXT NOT NULL,               -- teks final yang ditampilkan
    published        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS narrative_evidence (
    run_id           TEXT NOT NULL REFERENCES narrative_runs(run_id) ON DELETE CASCADE,
    evidence_id      TEXT NOT NULL,
    url              TEXT NOT NULL,
    source           TEXT NOT NULL,
    source_tier      TEXT NOT NULL,
    published_at     TIMESTAMPTZ,
    relevance        NUMERIC(4, 3),
    used_in_claims   BOOLEAN NOT NULL DEFAULT FALSE,
    snippet          TEXT,
    PRIMARY KEY (run_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS narrative_claims (
    run_id           TEXT NOT NULL REFERENCES narrative_runs(run_id) ON DELETE CASCADE,
    claim_id         TEXT NOT NULL,
    text             TEXT NOT NULL,
    claim_type       TEXT NOT NULL,
    evidence_ids     TEXT[] NOT NULL,
    accepted         BOOLEAN NOT NULL,
    rejected_reason  TEXT,
    PRIMARY KEY (run_id, claim_id)
);
```

Migrasi mengikuti pola yang ada: id berurutan (`011`…`016` sudah dipakai), `IF NOT EXISTS`, dijalankan `apply_schema_migrations`.

### 17.2 Yang harus dapat dijawab audit

1. Angka apa yang diberikan ke LLM, dan dari `report_id` mana.
2. Rule versi mana yang aktif (`rules_hash`) dan prompt versi mana.
3. Bukti mana yang dipakai per klaim, dan mana yang ditolak beserta alasannya.
4. Angka/klaim mana yang ditolak validator.
5. Berapa biaya & latensi run, serta mengapa fallback dipakai.

### 17.3 Retensi

- `narrative_runs`/`narrative_outputs`: simpan selama versi laporan disimpan (kebijakan yang sudah ada).
- `narrative_evidence`: simpan 90 hari (boleh dipangkas bila tabel membesar); `snippet` dibatasi ~500 karakter.
- Pembersihan dijalankan berkala oleh worker (bukan pada request API), dengan log ringkas.

---

## 18. Model/provider abstraction

### 18.1 Kontrak

Business logic hanya bergantung pada `LLMProvider`/`SearchProvider` (§3). Tidak ada `import openai` di service — panggilan HTTP memakai `requests` yang sudah menjadi dependensi, sehingga **tidak ada SDK baru** yang perlu diadopsi tanpa keputusan Anda.

```python
class LLMResponse(NamedTuple):
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int
```

Yang perlu disesuaikan per provider: membentuk request, memakai mode JSON, memetakan error HTTP ke taksonomi §14.1, dan menghitung token.

### 18.2 Pemilihan via environment

```env
LLM_PROVIDER=openai-compatible        # openai-compatible | anthropic-compatible | none
LLM_BASE_URL=https://opus.abhibots.com
LLM_MODEL=                            # boleh kosong saat pengembangan
LLM_API_KEY=                          # boleh kosong saat pengembangan
SEARCH_PROVIDER=seeded                # seeded | webz | exa | none
SEARCH_API_KEY=                       # hanya untuk mode provider pihak ketiga
```

**Perilaku saat kredensial belum ada (keputusan pengguna, wajib dipatuhi kode):**

1. Aplikasi **selalu start normal** — worker, API, dan halaman tidak gagal karena `LLM_API_KEY`/`LLM_MODEL` kosong.
2. `LLM_PROVIDER` diisi tetapi `LLM_MODEL`/`LLM_API_KEY` kosong → setara provider tidak tersedia: **tidak ada panggilan HTTP**, status `fallback`, narasi deterministik dipakai.
3. Endpoint yang diisi hanya dipakai bila ketiga hal tersedia: provider, model, key.
4. Pengisian kredensial **tidak memerlukan perubahan kode**: hanya environment variable, dan cache otomatis dibatalkan karena `model` termasuk dalam `cache_key`.

`LLM_PROVIDER=none`, atau `LLM_MODEL`/`LLM_API_KEY` masih kosong (kondisi normal saat pengembangan) → fitur narasi LLM mati rapi dan Dashboard, Equity Snapshot, serta PDF memakai narasi deterministik. Build, test, dan publish laporan tetap hijau tanpa kredensial.

### 18.3 Keputusan provider (16 Okt 2026)

**Ditetapkan pengguna:** LLM memakai endpoint **OpenAI-compatible** di `LLM_BASE_URL=https://opus.abhibots.com` dengan `LLM_PROVIDER=openai-compatible`. Nama model dan API key diisi belakangan lewat environment variable; kode tidak berubah dan aplikasi tidak boleh gagal berjalan sebelum keduanya tersedia (§18.2).

Karena endpoint bersifat OpenAI-compatible, adapter `providers/openai_compatible.py` (memakai `requests`, bukan SDK baru) melayani provider ini dan provider OpenAI-compatible lain di masa depan.

Sumber bukti tahap awal memakai **registry sumber** (§31) melalui mode `seeded`, sehingga tidak membutuhkan kredensial pihak ketiga. Opsi berikut tetap dicatat sebagai perluasan bila registry dirasa kurang luas:

| Kebutuhan | Opsi | Catatan desain |
|---|---|---|
| LLM dengan pengalihan provider/multi-model dari satu endpoint | Gateway OpenAI-compatible (mis. OpenLLM) | selaras dengan `LLM_BASE_URL` + `LLM_MODEL`; memudahkan ganti model tanpa ubah kode |
| LLM langsung dari vendor | OpenAI/Anthropic/Gemini (mode OpenAI-compatible atau REST sendiri) | hanya perlu menambah satu adapter di `providers/` |
| Web/news search terstruktur (judul, tanggal terbit, domain, kutipan) | Webz.io News Search | paling dekat dengan kebutuhan evidence timestamp |
| Web search semantik + ekstraksi halaman | Exa | alternatif bila ingin grounding lebih luas |

Keputusan provider (dan persetujuan kredensial pihak ketiga) adalah keputusan Anda — lihat §29. Blueprint ini hanya memastikan **satu titik ganti**.

### 18.4 Routing & fallback model

- `LLM_MODEL` utama; opsional `LLM_MODEL_FALLBACK` bila provider utama gagal (bukan untuk kualitas, hanya ketersediaan).
- Model murah untuk klasifikasi/relevansi (bila dipakai) dan model lebih kuat untuk narasi final — dipisah oleh `LLM_MODEL_RESEARCH` (opsional).
- `temperature` & `max_tokens` per halaman dari rules.

---

## 19. Security

1. **Kredensial hanya di server**: `LLM_API_KEY`, `SEARCH_API_KEY` dibaca lewat `config.load_environment()`; **tidak pernah** dikirim ke frontend, tidak ditulis ke payload laporan, tidak muncul di PDF.
2. **Frontend memakai proxy**: pola yang sudah ada (`frontend/src/app/api/market/live/route.ts`, `.../equity/snapshot/route.ts`) diterapkan untuk `/api/narratives/[page]`, token baca tetap di server (lihat `frontend/src/lib/api/server-config.ts`).
3. **Kontrol akses**: endpoint baca memakai `require_read_access`; regenerate memakai `require_operator_access` (pola `api/dependencies.py`).
4. **Permintaan narasi tidak membocorkan internal**: respons API hanya berisi teks, status, tanggal, dan daftar sumber; prompt, JSON mentah LLM, pesan error provider, dan nama tabel tidak dikirim ke klien.
5. **Anti prompt-injection**: konten web = data tak terpercaya. Instruksi di dalam artikel ("abaikan aturan sebelumnya…") dibuang; LLM diberi instruksi eksplisit untuk tidak menuruti teks dalam blok evidence.
6. **Anti-SSRF**: URL hanya boleh dari hasil provider; skema `http/https`; alamat privat/localhost/metadata cloud ditolak sebelum fetch; batas ukuran respons & timeout.
7. **Privasi data**: hanya angka yang tampil di halaman yang dikirim ke pihak ketiga — bukan seluruh laporan, bukan data internal, bukan data karyawan/pelanggan. `LLM_CONTEXT_MAX_INSTRUMENTS` dan daftar `allow_payload_keys` membatasi payload.
8. **Integritas output**: narasi tidak dapat mengubah angka halaman; UI merender narasi sebagai teks (bukan HTML bebas) kecuali penanda format internal yang sudah dikontrol.
9. **Pemisahan lingkungan**: key produksi berbeda dari pengembangan; `.env` tetap di `.gitignore` (sudah ada). `LLM_NARRATIVE_ENABLED=false` sebagai default aman.
10. **Persetujuan pihak ketiga**: pengiriman data pasar ke penyedia LLM/search pihak ketiga adalah keputusan eksplisit Anda (§29), termasuk pertimbangan kebijakan data.

---

## 20. Cost control

| Kendali | Default usulan | Catatan |
|---|---|---|
| `LLM_MAX_CALLS_PER_REFRESH` | 2 (satu per halaman) | regenerate manual dihitung di luar, tapi tetap dicatat |
| `LLM_MAX_CALLS_PER_DAY` | 12 | termasuk retry/repair |
| `LLM_MAX_OUTPUT_TOKENS` | 700 | narasi pendek; output panjang = indikasi pelanggaran panjang |
| `LLM_MAX_INPUT_TOKENS` | 6000 | bukti dipangkas bila melebihi |
| `SEARCH_MAX_QUERIES` / `SEARCH_MAX_RESULTS` | 6 / 8 per query | bukti final ≤ 8 |
| `LLM_DAILY_BUDGET_USD` | mis. 1.00 | dihitung dari `cost_estimate_usd` di audit (§17) |
| Pembatasan bukti | ≤ 8 dokumen, ≤ 2 per domain | mengurangi token input sekaligus duplikasi |

Prinsip: **tidak ada panggilan LLM pada jalur request pengguna.** Ini sendirian memotong biaya tak terduga (buka halaman berulang, refresh browser, crawler).

Bila anggaran habis: `BudgetExhaustedError` → status `fallback` dengan alasan `budget_exhausted`; dihitung ulang pada hari berikutnya (waktu lokal `Asia/Jakarta`, konsisten dengan `REFRESH_TIMEZONE`).

---

## 21. Rate limiting

- **Regenerate manual**: memakai `SlidingWindowLimiter` yang sudah ada di `api/rate_limits.py` dengan instance baru, mis. `narrative_regenerate = SlidingWindowLimiter(limit=2, window_seconds=300)`; respons `429` + `Retry-After`, mengikuti pola `export_requests`.
- **Endpoint baca**: tidak dibatasi khusus (read-only, cache lokal), tetap di belakang `require_read_access`.
- **Worker**: satu narasi per laporan per halaman; lock berbasis `run_key` mencegah duplikasi saat refresh bersamaan (pola lease/`refresh_job_leases` sudah ada sebagai referensi).
- **Provider**: bila provider mengembalikan `429`, breaker menghormati `Retry-After` dan langsung memakai fallback (tanpa loop).
- **Pemblokiran berulang**: dua kegagalan berturut-turut untuk `report_id` yang sama → status `fallback` dicache 30 menit agar tidak ada badai percobaan.

---

## 22. Fallback ketika LLM gagal

| Kondisi | Perilaku | Yang dilihat pengguna |
|---|---|---|
| `LLM_API_KEY` atau `LLM_MODEL` belum diisi / provider `none` | narasi deterministik | **kondisi normal saat pengembangan**: aplikasi tetap start, halaman tetap tampil, PDF tetap terbit, tanpa penanda error |
| Timeout / 5xx | retry 2× → fallback + breaker | narasi deterministik + "komentar LLM tidak tersedia" |
| Output bukan JSON / skema salah | 1 repair → fallback | idem |
| Validasi angka gagal | 1 repair → fallback | idem, alasan tercatat di audit |
| Anggaran habis | langsung fallback | idem |
| Rules tidak terbaca | fallback + log `ERROR` | idem |

Prioritas fallback: **(1)** narasi dari run sebelumnya (ditandai tanggalnya) → **(2)** narasi deterministik halaman → **(3)** teks penanda "narasi otomatis belum tersedia; data laporan tetap lengkap".

Yang **tidak boleh** terjadi: halaman error, tabel kosong, laporan gagal terbit, atau PDF rusak karena narasi gagal.

---

## 23. Fallback ketika web search gagal

1. `search_error` dicatat (provider, query, status) di log & audit; **bukan** error fatal.
2. Generasi lanjut dengan mode `dashboard_only`: prompt tetap menyertakan `<authoritative_numbers>` dan menghapus blok `<evidence>`.
3. Rules menambahkan batasan mode ini: tanpa bukti → tidak boleh ada klaim eksternal dan tidak boleh ada frasa kausal; hanya deskripsi angka + konteks umum yang dapat diverifikasi dari data.
4. Status narasi ditandai `partial` pada metadata; UI opsional menampilkan catatan kecil "konteks eksternal tidak tersedia untuk sesi ini".
5. Bila search gagal berulang, breaker search terpisah (default 30 menit) mencegah percobaan tiap refresh; narasi tetap tampil tanpa konteks eksternal.

---

## 24. Fallback ketika tidak ada berita relevan

1. Bukti lolos filter < `rules.sources.min_evidence_items` (default 1 untuk klaim kausal, 2 untuk klaim multi-sumber) → seluruh blok klaim eksternal dihapus.
2. LLM menghasilkan narasi yang **hanya** mendeskripsikan angka yang tersedia + menyatakan ketiadaan katalis memakai frasa dari rules:
   "Belum terdapat katalis yang cukup kuat dari sumber yang tersedia."
3. Struktur tetap dipenuhi: halaman equity tetap mengisi bagian pasar/sektoral dari angka; bagian makro memakai frasa ketiadaan data.
4. `narrative_gaps` diisi sehingga UI/analis tahu apa yang belum terjawab (mempermudah penambahan manual melalui editor yang sudah ada).
5. Frasa netral **bukan** pengganti angka: kekosongan angka tetap memakai konvensi proyek (`—` / datum hilang), tidak diisi teks.
6. Audit mencatat `no_evidence` sebagai alasan sehingga tim dapat menilai kualitas query planner dari waktu ke waktu.

---

## 25. Kontrak API & UI

### 25.1 Endpoint backend (rute baru di `api/routers/narratives.py`)

| Metode | Rute | Akses | Perilaku |
|---|---|---|---|
| `GET` | `/api/v1/narratives/latest?page=dashboard\|equity_snapshot` | `require_read_access` | membaca cache/hasil terbit; **tidak** memanggil LLM |
| `GET` | `/api/v1/narratives/runs?page=&limit=` | `require_read_access` | riwayat audit ringkas untuk operator |
| `GET` | `/api/v1/narratives/{report_id}?page=…` | `require_read_access` | narasi untuk versi laporan tertentu |
| `POST` | `/api/v1/narratives/regenerate?page=…&allow_search=…` | `require_operator_access` + rate limit 2/5 menit (`429` + `Retry-After`) | memicu **satu run sinkron** dan mengembalikan hasilnya (`200`) — satu run biasanya hanya beberapa detik, jadi antrean job belum diperlukan |

> Catatan implementasi: rencana awal `202 + run_id` diubah menjadi `200 + payload` karena run selesai dalam satu request. Bila nanti perlu antrean (mis. regenerate banyak halaman sekaligus), pola `refresh_jobs` yang sudah ada dapat dipakai.

### 25.2 Bentuk respons

```jsonc
{
  "page": "dashboard",
  "status": "published",           // published | fallback | stale | unavailable
  "report_id": "…",
  "report_date": "2026-10-16",
  "as_of": { "ihsg": "2026-10-16", "sbn10": "2026-10-15" },
  "narrative": "…",
  "sections": [],
  "sources": [{ "url": "…", "source": "bi.go.id", "published_at": "…" }],
  "generated_at": "2026-10-16T08:05:12+07:00",
  "run_id": "…",
  "notes": ["Konteks eksternal tidak tersedia untuk sesi ini."],
  "validation": { "passed": true, "errors": [], "warnings": [], "numbers_used": 12 },
  "frozen": false
}
```

### 25.3 Frontend

- `/api/narratives/[page]/route.ts` memakai pola `server-config.ts` (token server-side).
- Panel narasi ditambahkan di Dashboard Utama dan halaman Equity, **dan bagian narasi ikut ke area ekspor PDF** karena narasi adalah bagian dokumen terbit (§15.1, §29.1).
- Sumber ditampilkan ringkas (domain + tanggal terbit) agar dapat diperiksa; tautan keluar tidak wajib.
- Tombol **Regenerate** hanya tampil untuk operator (pola `operator-menu.tsx`), dengan konfirmasi dan indikator status; hasilnya dapat diedit analis melalui editor yang sudah ada di halaman equity, dan editan analis diperlakukan sebagai revisi atas narasi beku (§15.1).
- Bila `status != published`, UI menampilkan penanda halus (bukan error merah) dan tetap menampilkan angka seperti biasa.
- **Untuk laporan terbit**: UI (dan PDF) membaca narasi **beku** pada versi laporan tersebut (§15.1), bukan cache terbaru. Halaman aktif boleh menampilkan narasi terbaru dengan penanda tanggalnya.
- Panel narasi boleh berada di dalam area ekspor PDF karena narasi kini bagian dari dokumen terbit; kontrol, saran, dan catatan tetap di luar area ekspor seperti konvensi yang sudah ada.

---

## 26. Konfigurasi

Tambahan pada `.env.example` (belum ditulis ke repo sampai implementasi disetujui):

```env
# ── LLM Narrative Engine ────────────────────────────────────────────
LLM_NARRATIVE_ENABLED=false        # default aman; aktifkan bila narasi LLM diinginkan
LLM_PROVIDER=openai-compatible     # openai-compatible | anthropic-compatible | none
LLM_BASE_URL=https://opus.abhibots.com
LLM_MODEL=                         # opsional saat pengembangan
LLM_API_KEY=                       # opsional saat pengembangan
LLM_TIMEOUT_SECONDS=45
LLM_MAX_OUTPUT_TOKENS=700
LLM_MAX_INPUT_TOKENS=6000
LLM_TEMPERATURE=0.2
LLM_MAX_CALLS_PER_REFRESH=2
LLM_MAX_CALLS_PER_DAY=12
LLM_DAILY_BUDGET_USD=1.00

SEARCH_PROVIDER=seeded             # seeded | webz | exa | none
SEARCH_API_KEY=                    # hanya bila memakai provider pihak ketiga
SEARCH_SEED_MAX_ARTICLES_PER_SOURCE=4
SEARCH_TIMEOUT_SECONDS=20
SEARCH_MAX_QUERIES=6
SEARCH_MAX_RESULTS=8
SEARCH_LOOKBACK_DAYS=3
LLM_EVIDENCE_MAX_ITEMS=8

LLM_RULES_FILE=                    # kosong = cari backend/config/llm_rules.md lalu docs/llm_rules.md
NARRATIVE_CACHE_TTL_MINUTES=180
PROMPT_VERSION=v1
```

Prinsip: **semua** opsi tersebut punya default aman sehingga aplikasi tetap jalan tanpa satu pun kredensial.

---

## 27. Pengujian & verifikasi (rencana)

| Jenis | Isi | Tanpa kredensial? |
|---|---|---|
| Unit | parser rules (nilai, default, file rusak), number registry (varian format Indonesia/Inggris, tanda, satuan), dedup & freshness evidence | ya |
| Unit | validator: 8 kasus angka palsu, tanda terbalik, satuan salah, tanggal masa depan, klaim tanpa bukti, kutipan tidak verbatim | ya |
| Kontrak | `FakeLLMProvider`/`FakeSearchProvider` — memastikan engine bekerja, fallback bekerja, cache key stabil, breaker membuka | ya |
| Integrasi | `GET /narratives/latest` tanpa run → `unavailable`; dengan run → payload sesuai skema; `POST regenerate` menolak tanpa token operator | ya |
| Integrasi DB | migrasi `017_narratives.sql` idempoten, `cache_key` unik, cascade delete berjalan | butuh Postgres |
| Manual smoke | jalankan provider nyata pada satu laporan, bandingkan angka narasi vs payload | butuh kredensial |

Ambang lulus yang penting: **nol angka di narasi yang tidak ada di payload**, dan **kegagalan provider tidak pernah menaikkan status error halaman**.

---

## 28. Roadmap bertahap (setelah blueprint disetujui)

| Tahap | Keluaran | Bergantung pada |
|---|---|---|
| 1 | `docs/llm_rules.md` final (§9) | keputusan Anda atas format & nilai default |
| 2 | `domain/narrative_rules.py` + `domain/number_registry.py` + unit test | tahap 1 |
| 3 | `domain/narration_contract.py` + `context_builder` untuk dua halaman | tahap 2 |
| 4 | `providers/base.py` + `openai_compatible` + `FakeLLMProvider` (tanpa search) | tahap 3 |
| 5 | `prompt_builder` + `engine` + validator + fallback deterministik | tahap 4 |
| 6 | `search_*` + `research_service` + `evidence` | tahap 5 |
| 7 | migrasi `017_narratives.sql` + `narrative_repository` + cache + audit | tahap 5 |
| 8 | `api/routers/narratives.py` + proxy Next.js | tahap 7 |
| 9 | Panel narasi di Dashboard Utama | tahap 8 |
| 10 | Panel narasi di Equity Snapshot + tombol regenerate/edit operator | tahap 9 |

Setiap tahap dapat diuji tanpa kredensial nyata kecuali tahap 6 (search) dan smoke manual.

### 28.1 Status implementasi (16 Okt 2026)

| Tahap | Status | Bukti |
|---|---|---|
| 1 `docs/llm_rules.md` | **selesai** | file policy + registry `backend/config/llm_sources.json` |
| 2 rules parser + number registry | **selesai** | `domain/narrative_rules.py`, `domain/number_registry.py`, 29 test |
| 3 kontrak + context builder | **selesai** | `domain/narration_contract.py`, `services/narration/context_builder.py`, diuji pada laporan & snapshot nyata |
| 4 provider layer | **selesai** | `providers/{base,registry,openai_compatible,fake,none}.py` |
| 5 prompt + validator + engine + fallback | **selesai** | `prompt_builder.py`, `validators.py`, `engine.py` |
| 6 search `seeded` + evidence | **selesai** | `providers/search_seeded.py`, `evidence.py` (diuji dengan fetcher palsu; belum diuji ke internet) |
| 7 cache + audit + breaker | **sebagian** | cache/audit/usage/breaker berbasis berkas di `runtime/narrative/`; **tabel Postgres `017_narratives.sql` belum dibuat** |
| 8 API `/narratives` | **selesai** | `api/routers/narratives.py` terdaftar di `api/main.py` (3 rute terlihat di OpenAPI) |
| 8b Job refresh narasi | **selesai, belum dijahit ke scheduler** | `services/narration/jobs.py` dapat dipanggil worker atau dijalankan sebagai modul |
| 9 panel narasi Dashboard | **belum** | frontend belum disentuh |
| 10 panel narasi Equity + tombol regenerate | **belum** | frontend belum disentuh |

Pembekuan narasi ke laporan terbit (§15.1) juga **belum** dikerjakan: itu menyentuh `publish_snapshot()` dan `report_pdf.py`, sehingga perlu satu tahap tersendiri bersama tabel Postgres. Karena itu `refresh_service`/scheduler **belum** memanggil narasi secara otomatis; saat ini pemicunya adalah tombol regenerate operator atau `python -m market_report.services.narration.jobs`.

---

## 29. Keputusan: sudah ditetapkan vs masih terbuka

### 29.1 Sudah ditetapkan pengguna (16 Okt 2026)

| # | Keputusan | Dampak ke desain |
|---|---|---|
| 1 | **LLM OpenAI-compatible**, `LLM_BASE_URL=https://opus.abhibots.com`; API key & model opsional saat pengembangan | §18.2, §18.3, §22 — aplikasi wajib tetap jalan dan jatuh ke narasi deterministik bila key/model kosong |
| 2 | **Narasi dipakai di Dashboard, Equity Snapshot, dan PDF laporan terbit** | §15.1 (freeze), §4.2 (pemicu pembekuan), §25.3 |
| 3 | **Snapshot narasi dibekukan saat laporan diterbitkan** agar PDF tidak berubah ketika narasi diperbarui | §15.1, §17 |
| 4 | **Fallback narasi deterministik** yang sudah ada bila LLM/search tidak tersedia atau validasi gagal | §22, §23, §24 |
| 5 | **Registry sumber** Indonesia + global beserta domain resmi dan kanal berita | §7.1 (mode `seeded`), §12, §31 |

### 29.2 Masih terbuka (tidak menghambat tahap berikutnya)

1. **Nama model** yang dipakai di `https://opus.abhibots.com` (diisi lewat `LLM_MODEL`).
2. **API key** endpoint tersebut (diisi lewat `LLM_API_KEY`).
3. **Apakah mode `provider`** (API pencarian pihak ketiga) diperlukan di luar registry §31, dan provider mana.
4. **Nilai default rules** (§9.2) dan batas biaya (§20) — usulan default sudah ada di dokumen, tinggal disetujui.
5. **Lokasi file policy aktif**: `docs/llm_rules.md` atau salinan deployment `backend/config/llm_rules.md` (§9.6).
6. **Nasib draf lama** `docs/LLM_NARRATOR_RULES.md`: dipertahankan sebagai catatan kebijakan atau digantikan `docs/llm_rules.md` versi terstruktur.
7. **Apakah regenerate manual boleh diakses non-operator** (mis. analis) — memengaruhi §20 dan §21.
8. **Dua tautan registry yang perlu dikonfirmasi** (§31.5): `tradingeconomics.com/indu:ind` dan daftar halaman Yahoo Finance/detail kanal yang mungkin berubah bentuk.

---

## 30. Ringkasan alur (versi satu layar)

```
laporan/snapshot terbit  →  Context Builder (angka yang tampil)
       →  RuleSet dari docs/llm_rules.md
       →  Query planner (dari anomali data)
       →  Search → Clean → Dedup → Freshness/Tier filter
       →  Evidence + claims (klaim ↔ bukti)
       →  Prompt (numbers | evidence | task | schema)
       →  LLM
       →  Validasi angka → sumber → tanggal → gaya → klaim
       →  lulus: cache + audit → UI   |   gagal: repair → fallback deterministik → UI
```

**Satu kalimat penutup:** LLM menyusun bahasanya, aplikasi pemilik angkanya, dan file policy yang menentukan batas keduanya.

---

## 31. Registry sumber bukti (ditetapkan pengguna, 16 Okt 2026)

Registry ini adalah bahan baku mode `seeded` (§7.1) sekaligus pemetaan **domain → tier** untuk §12.

> **Sudah diimplementasikan (16 Okt 2026):** berkas mesinnya ada di
> `backend/config/llm_sources.json` dan dibaca `providers/search_seeded.py`.
> Dua entri ditandai pada `unverified_urls` (lihat §31.5).

Aturan pemakaian:

1. Registry menentukan **tier**, bukan kebenaran isi; klaim tetap wajib punya bukti (§12).
2. Domain di luar registry → `secondary`; hanya boleh mendukung klaim non-kausal.
3. Angka dari halaman registry **tetap tidak boleh** menjadi angka pasar — hanya angka payload (§11).
4. Halaman kanal berita dipakai untuk menemukan artikel; yang masuk bukti adalah artikelnya, bukan halaman indeks.
5. Setiap perubahan registry mengubah `rules_hash` dan membatalkan cache narasi.

### 31.1 Indonesia — resmi/primer

| Domain | Tier | Keterangan |
|---|---|---|
| `idx.co.id` | `official_primary` | IDX: daftar emiten, pengumuman, laporan keuangan, aksi korporasi, statistik |
| `bi.go.id` | `official_primary` | Bank Indonesia: suku bunga, JISDOR, cadangan devisa, siaran pers |
| `bps.go.id` | `official_primary` | BPS: inflasi, ekspor-impor, neraca perdagangan, PDB |
| `ojk.co.id` | `official_primary` | OJK: kebijakan pasar modal & lembaga keuangan |

### 31.2 Global — resmi/primer

| Domain | Tier |
|---|---|
| `federalreserve.gov` | `official_primary` |
| `home.treasury.gov` | `official_primary` |
| `ecb.europa.eu` | `official_primary` |
| `imf.org` | `official_primary` |
| `worldbank.org` | `official_primary` |

### 31.3 Portal data & kalender ekonomi

| Sumber | Halaman yang terdaftar | Tier |
|---|---|---|
| TradingEconomics | `/stream`, `/calendar`, `/united-states/currency`, `/commodity/gold`, `/united-states/government-bond-yield` | `data_portal` |
| Investing.com | `/news/commodities-news/`, `/news/economy-news/`, `/news/forex-news/`, `/indices/us-30-news/` | `data_portal` |
| Yahoo Finance | `/economy/policy/article/`, `/topic/stock-market-news/`, `/topic/latest-news/`, `/markets/live/`, `/quote/^DJI/news/`, `/quote/^FTSE/news/`, `/quote/^FCHI/news/`, `/quote/^GDAXI/news/`, `/videos/series/market-domination-overtime/` | `global_market_media` |

Catatan: portal data dipakai untuk **konteks/kalender**, bukan untuk mengganti angka payload (§11). Halaman kalender berguna untuk menjelaskan kekosongan katalis (mis. hari tanpa rilis data).

### 31.4 Berita pasar & media keuangan

| Sumber | Halaman yang terdaftar | Tier |
|---|---|---|
| Bloomberg Technoz | kanal `/market/ekonomi`, `/market/investasi`, `/market/pasar-modal`, `/market/komoditi`, `/market/valuta-asing`, tag `/tag/ihsg` | `id_market_media` |
| Reuters | `reuters.com` | `global_market_media` |
| Bloomberg | `bloomberg.com` | `global_market_media` |
| Financial Times | `ft.com` | `global_market_media` |
| CNBC | `cnbc.com` | `global_market_media` |

### 31.5 Sumber lain yang perlu diaktifkan dengan pengecekan

- **Situs investor relations emiten** (laporan keuangan, rilis laba, presentasi) → tier `company_primary`; diaktifkan per emiten setelah domain resminya diverifikasi (registry per ticker, pola mirip `runtime/data/equity_registry.json`).
- **Halaman resmi bursa/regulator/lembaga statistik/komoditas lain** → `official_primary`, ditambahkan saat diverifikasi.
- `https://tradingeconomics.com/indu:ind` **tidak valid apa adanya** (terlihat terpotong). Mohon konfirmasi apakah maksudnya halaman Indonesia (mis. `/indonesia/indicators`); tautan ini tidak akan diaktifkan sebelum diperbaiki.

### 31.6 Cakupan topik yang harus bisa dijawab narasi

Registry di atas dipakai untuk memastikan narasi dapat menjelaskan topik berikut (checklist query planner §7.3):

- **Indeks global**: S&P 500, Nasdaq Composite/100, Dow Jones, Russell 2000, VIX, Euro Stoxx 50, DAX, CAC 40, FTSE 100, Nikkei 225, TOPIX, Hang Seng, Shanghai Composite, CSI 300, KOSPI, ASX 200.
- **Pendapatan tetap**: US 2Y/5Y/10Y/30Y, Indonesia 2Y/5Y/10Y, Jerman 10Y, Jepang 10Y.
- **Komoditas**: emas, minyak mentah, batubara, nikel, tembaga, CPO, gas alam.
- **FX**: USD/IDR, DXY, EUR/USD, USD/JPY, USD/CNY, GBP/USD, USD/SGD, AUD/USD.
- **Makro Indonesia**: inflasi, PDB, neraca perdagangan, ekspor, impor, transaksi berjalan, cadangan devisa, suku bunga, pertumbuhan kredit.
- **Makro global**: inflasi/PDB/ketenagakerjaan/CPI/PPI/suku bunga AS, inflasi & suku bunga zona euro, PDB/CPI/PMI/perdagangan Tiongkok, PDB/CPI/suku bunga Jepang.
- **Equity Indonesia**: IHSG, LQ45, IDX30, IDX80, IDX High Dividend 20, IDX ESG Leaders, indeks sektoral; pengumuman & aksi korporasi emiten.
- **Aksi korporasi**: dividen, rights issue, stock split/reverse, buyback, tender offer, akuisisi, merger, divestasi, private placement, IPO, secondary offering, penerbitan obligasi, restrukturisasi utang, perubahan manajemen/kepemilikan.
- **Fundamental emiten**: pendapatan, laba kotor, EBITDA/EBIT, laba bersih, EPS, margin, ROE, ROA, utang/net debt, arus kas, capex, dividen, guidance, volume produksi/penjualan, utilisasi, realisasi komoditas.
- **Sektor**: Financials, Energy, Basic Materials, Industrials, Consumer Cyclicals, Consumer Non-Cyclicals, Healthcare, Technology, Infrastructure, Property, Transportation, Utilities.
- **Indikator risiko global**: VIX, MOVE Index, US 10Y/2Y, DXY, emas, minyak mentah, tembaga, batubara, CPO.

Checklist ini **bukan izin** membahas semua topik setiap hari: yang masuk narasi tetap hanya topik yang punya angka payload atau bukti registry pada tanggal laporan.

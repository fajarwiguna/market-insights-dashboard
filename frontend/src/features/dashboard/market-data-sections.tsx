import type { InstrumentReading, MarketReport } from "@/lib/api/types";

type CategoryId = "fx" | "gold" | "capital-flow" | "yields" | "macro" | "monetary-operations" | "indices" | "commodities";
type Column = { key: string; label: string; kind: "value" | "percent" | "basis-points" | "date" | "unit" | "month"; title?: string };
type MarketGroup = { id: CategoryId; label: string; title: string; description: string; kind: "close" | "gold" | "flow" | "yield" | "macro" | "operation" | "index" | "commodity" };

export const MARKET_GROUPS: MarketGroup[] = [
  { id: "fx", label: "01 / VALUTA", title: "Kurs", description: "Nilai penutupan tiap instrumen; tanggal pembanding mengikuti kalender sumber.", kind: "close" },
  { id: "gold", label: "02 / EMAS", title: "Harga Emas", description: "Gold Spot, futures sebagai seri terpisah, dan harga dasar Antam 1 gram.", kind: "gold" },
  { id: "capital-flow", label: "03 / ARUS MODAL", title: "Capital Flow", description: "Arus bersih saham dan obligasi dalam USD juta.", kind: "flow" },
  { id: "yields", label: "04 / FIXED INCOME", title: "Bond Yield", description: "Perubahan yield ditampilkan dalam basis point; 1 bp = 0,01 poin persentase.", kind: "yield" },
  { id: "macro", label: "05 / MAKRO", title: "Indicators", description: "Nilai indikator berdasarkan bulan publikasi, bukan perubahan bulanan.", kind: "macro" },
  { id: "monetary-operations", label: "06 / LIKUIDITAS", title: "Operasi Moneter", description: "Posisi akhir periode dari SEKI BI; frekuensi bulanan dan tanggal mengikuti observasi terbaru.", kind: "operation" },
  { id: "indices", label: "07 / EQUITIES", title: "Index", description: "IHSG, indeks global, dan sektor IDX-IC.", kind: "index" },
  { id: "commodities", label: "08 / KOMODITAS", title: "Commodity", description: "Harga, unit kontrak, dan perubahan lintas periode.", kind: "commodity" },
];

const SECTORS = [
  "Energi", "Bahan Baku", "Industri", "Konsumen Siklikal", "Konsumen Non-Siklikal",
  "Kesehatan", "Keuangan", "Properti", "Teknologi", "Infrastruktur", "Transportasi dan Logistik",
];
const MACRO_NAMES = [
  "FED Fund Rate (%)", "BI Rate (%)", "Inflasi Indonesia YoY (%)", "M2 (% YoY)",
  "Kredit/Pembiayaan (% YoY) - BI", "DPK (% YoY) - BI",
];
const FLOW_NAMES = ["Saham", "Obligasi"];
const FX_NAMES = ["DXY", "USD/IDR", "CNY/IDR", "SAR/IDR", "EUR/IDR", "JPY/IDR"];
const YIELD_NAMES = [
  "US Treasury 5 Tahun", "US Treasury 10 Tahun", "ID SBN 5 Tahun", "ID SBN 10 Tahun",
  "ID SBSN PBS030", "ID SBSN PBS004",
];
const INDEX_NAMES = ["IHSG (ID)", "DJI (US)"];
const MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const FX_UNITS: Record<string, string> = {
  DXY: "indeks",
  "USD/IDR": "IDR/USD",
  "CNY/IDR": "IDR/CNY",
  "SAR/IDR": "IDR/SAR",
  "EUR/IDR": "IDR/EUR",
  "JPY/IDR": "IDR/JPY",
};
const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const decimalFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function emptyReading(unit?: string): InstrumentReading {
  return { unit, periods: {}, observations: {}, availability: "unavailable" };
}

function isReading(value: unknown): value is InstrumentReading {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function entries(value: unknown): [string, InstrumentReading][] {
  if (!value || typeof value !== "object" || Array.isArray(value)) return [];
  return Object.entries(value).filter((row): row is [string, InstrumentReading] => isReading(row[1]));
}

function sectionRows(group: MarketGroup, report: MarketReport): [string, InstrumentReading][] {
  switch (group.kind) {
    case "close": {
      const values = entries(report.fx);
      return FX_NAMES.map((name) => [
        name,
        values.find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? emptyReading(FX_UNITS[name]),
      ] as [string, InstrumentReading]);
    }
    case "gold": {
      const explicit = entries(report.gold);
      const legacy = explicit.length ? explicit : entries(report.commodities).filter(([name]) => /gold|emas antam/i.test(name))
        .map(([name, reading]) => [
          /emas antam/i.test(name) ? "Emas Antam (Rp/gram)" : "Gold Futures COMEX (GC=F, USD/troy oz)",
          { ...reading, unit: reading.unit || (/emas antam/i.test(name) ? "Rp/gram" : "USD/troy oz") },
        ] as [string, InstrumentReading]);
      const ensure = (name: string, unit: string, note: string) => {
        if (!legacy.some(([key]) => key.toLowerCase().startsWith(name.toLowerCase()))) {
          legacy.push([name, { ...emptyReading(unit), availability_note: note }]);
        }
      };
      ensure("Gold Spot (USD/troy oz)", "USD/troy oz", "Feed spot belum tersedia; GC=F adalah futures.");
      ensure("Gold Futures COMEX", "USD/troy oz", "Feed futures belum tersedia.");
      ensure("Emas Antam", "Rp/gram", "Feed harga Antam belum tersedia.");
      return [
        ...legacy.filter(([name]) => /gold spot/i.test(name)),
        ...legacy.filter(([name]) => /gold futures|gold \(usd/i.test(name)),
        ...legacy.filter(([name]) => /emas antam/i.test(name)),
      ];
    }
    case "flow":
      return FLOW_NAMES.map((name) => [name, entries(report.capital_flow).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? emptyReading("USD juta")] as [string, InstrumentReading]);
    case "yield": {
      const values = entries(report.yields);
      const expected = YIELD_NAMES.map((name) => {
        const matched = values.find(([key]) => key.toLowerCase() === name.toLowerCase())
          ?? values.find(([key]) => name.startsWith("ID SBSN") && key.toLowerCase().startsWith(name.toLowerCase()));
        return [matched?.[0] ?? name, matched?.[1] ?? emptyReading("% yield")] as [string, InstrumentReading];
      });
      const remaining = values.filter(([key]) => !expected.some(([name]) => key.toLowerCase() === name.toLowerCase() || (name.startsWith("ID SBSN") && key.toLowerCase().startsWith(name.toLowerCase()))));
      return [...expected, ...remaining];
    }
    case "macro":
      return MACRO_NAMES.map((name) => [
        name,
        entries(report.macro_indicators).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? emptyReading("%"),
      ] as [string, InstrumentReading]);
    case "operation":
      return entries(report.monetary_operations).length
        ? entries(report.monetary_operations)
        : [["Posisi OM BI (Rp T)", emptyReading("Rp triliun")] as [string, InstrumentReading]];
    case "index": {
      const indices = entries(report.indices);
      const headline = INDEX_NAMES.map((name) => [
        name,
        indices.find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? emptyReading("poin"),
      ] as [string, InstrumentReading]);
      const otherIndices = indices.filter(([key]) => !INDEX_NAMES.some((name) => name.toLowerCase() === key.toLowerCase()));
      return [...headline, ...otherIndices, ...SECTORS.map((name) => [name, entries(report.index_sectors).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? emptyReading("poin")] as [string, InstrumentReading])];
    }
    case "commodity": {
      const rows = entries(report.commodities).filter(([name]) => !/gold|emas antam/i.test(name))
        .map(([name, reading]) => [name, { ...reading, unit: reading.unit || (/brent|wti/i.test(name) ? "USD/barrel" : reading.unit) }] as [string, InstrumentReading]);
      if (!rows.some(([name]) => /brent/i.test(name))) rows.unshift(["Brent Crude", emptyReading("USD/barrel")]);
      if (!rows.some(([name]) => /newcastle/i.test(name))) rows.push(["Coal (Newcastle)", emptyReading("USD/ton")]);
      if (!rows.some(([name]) => /cpo|palm oil/i.test(name))) rows.push(["CPO (Bursa Malaysia)", emptyReading("MYR/ton")]);
      return [
        ...rows.filter(([name]) => /brent/i.test(name)),
        ...rows.filter(([name]) => /newcastle/i.test(name)),
        ...rows.filter(([name]) => /cpo|palm oil/i.test(name)),
        ...rows.filter(([name]) => !/brent|newcastle|cpo|palm oil/i.test(name)),
      ];
    }
  }
}

function recentMonths(report: MarketReport): { key: string; label: string }[] {
  const day = report.report_date_iso ? new Date(`${report.report_date_iso}T00:00:00Z`) : null;
  if (!day || Number.isNaN(day.getTime())) {
    return [1, 2, 3].map((index) => ({ key: `no-month-${index}`, label: "—" }));
  }
  return [2, 1, 0].map((offset) => {
    const monthDate = new Date(Date.UTC(day.getUTCFullYear(), day.getUTCMonth() - offset, 1));
    const monthIndex = monthDate.getUTCMonth();
    return {
      key: monthDate.toISOString().slice(0, 7),
      label: `${MONTH_NAMES[monthIndex]} ${monthDate.getUTCFullYear()}`,
    };
  });
}

function columnsFor(group: MarketGroup, months: { key: string; label: string }[]): Column[] {
  if (group.kind === "flow") return [
    { key: "1D", label: "1D", kind: "value", title: "Net flow pada satu sesi perdagangan." },
    { key: "1W", label: "1W", kind: "value", title: "Akumulasi lima sesi perdagangan terakhir." },
    { key: "MtD", label: "MtD", kind: "value", title: "Akumulasi sejak sesi terakhir sebelum bulan berjalan." },
    { key: "QtD", label: "QtD", kind: "value", title: "Akumulasi sejak sesi terakhir sebelum kuartal berjalan." },
    { key: "YtD", label: "YtD", kind: "value", title: "Akumulasi sejak sesi terakhir sebelum tahun berjalan." },
  ];
  if (group.kind === "yield") return [
    { key: "prev", label: "Sebelumnya (%)", kind: "value" },
    { key: "today", label: "Terakhir (%)", kind: "value" },
    { key: "dtd_bp", label: "DtD (bp)", kind: "basis-points", title: "Perubahan yield dari observasi sebelumnya; 1 bp = 0,01 poin persentase." },
    { key: "ytd_bp", label: "YtD (bp)", kind: "basis-points", title: "Perubahan yield sejak akhir tahun sebelumnya." },
    { key: "date", label: "Tanggal data", kind: "date" },
  ];
  if (group.kind === "macro") return months.map((month): Column => ({ key: month.key, label: month.label, kind: "month", title: `Observasi bulan ${month.label}.` }));
  if (group.kind === "operation") return [
    { key: "today", label: "Terakhir (Rp T)", kind: "value" },
    { key: "mtd_pct", label: "MtD (%)", kind: "percent", title: "Perubahan dari penutupan/posisi terakhir sebelum bulan berjalan." },
    { key: "ytd_pct", label: "YtD (%)", kind: "percent", title: "Perubahan dari penutupan/posisi terakhir sebelum tahun berjalan." },
    { key: "date", label: "Tanggal data", kind: "date" },
  ];
  if (group.kind === "commodity") return [
    { key: "unit", label: "Unit", kind: "unit" },
    { key: "today", label: "Terakhir", kind: "value" },
    { key: "dtd_pct", label: "DtD (%)", kind: "percent", title: "Perubahan dibanding penutupan sesi sebelumnya." },
    { key: "wtd_pct", label: "WtD (%)", kind: "percent", title: "Perubahan dibanding penutupan terakhir sebelum minggu berjalan." },
    { key: "mtd_pct", label: "MtD (%)", kind: "percent", title: "Perubahan dibanding penutupan terakhir sebelum bulan berjalan." },
    { key: "ytd_pct", label: "YtD (%)", kind: "percent", title: "Perubahan dibanding penutupan terakhir sebelum tahun berjalan." },
    { key: "date", label: "Tanggal data", kind: "date" },
  ];
  return [
    { key: "prev", label: "Sebelumnya", kind: "value" },
    { key: "today", label: "Terakhir", kind: "value" },
    { key: "dtd_pct", label: "DtD (%)", kind: "percent", title: "Perubahan dibanding penutupan sesi sebelumnya." },
    { key: "ytd_pct", label: "YtD (%)", kind: "percent", title: "Perubahan dibanding penutupan terakhir sebelum tahun berjalan." },
    { key: "date", label: "Tanggal data", kind: "date" },
  ];
}

function signed(value: number, format: Intl.NumberFormat): string {
  return `${value > 0 ? "+" : ""}${format.format(value)}`;
}

function cellValue(reading: InstrumentReading, column: Column, group: MarketGroup): string {
  if (column.kind === "unit") return typeof reading.unit === "string" ? reading.unit : "—";
  if (column.kind === "date") {
    const date = reading.date || "—";
    return reading.prev_date && reading.prev_date !== date ? `${reading.prev_date} → ${date}` : date;
  }
  if (column.kind === "month") {
    const value = reading.observations?.[column.key];
    return typeof value === "number" && Number.isFinite(value) ? decimalFormat.format(value) : "—";
  }
  const raw = column.key === "dtd_pct" ? (reading.dtd_pct ?? reading.change_pct)
    : column.key === "dtd_bp" ? (reading.dtd_bp ?? reading.change_bp)
      : column.key in (reading.periods ?? {}) ? reading.periods?.[column.key]
        : reading[column.key];
  if (typeof raw !== "number" || !Number.isFinite(raw)) return "—";
  if (column.kind === "percent") return `${signed(raw, decimalFormat)}%`;
  if (column.kind === "basis-points") return `${signed(raw, decimalFormat)} bp`;
  const hasFraction = group.kind === "yield" || group.kind === "macro" || group.kind === "operation";
  const format = hasFraction ? decimalFormat : numberFormat;
  const formatted = format.format(raw);
  return group.kind === "yield" ? `${formatted}%` : formatted;
}

function rowHasData(reading: InstrumentReading): boolean {
  const direct = [reading.today, reading.prev, reading.change_pct, reading.change_bp, reading.dtd_pct, reading.dtd_bp,
    reading.wtd_pct, reading.mtd_pct, reading.qtd_pct, reading.ytd_pct, reading.ytd_bp];
  const periods = Object.values(reading.periods ?? {});
  const months = Object.values(reading.observations ?? {});
  return [...direct, ...periods, ...months].some((value) => typeof value === "number" && Number.isFinite(value));
}

export function MarketDataSections({ report }: { report: MarketReport }) {
  const months = recentMonths(report);
  return <div className="market-sections">
    {MARKET_GROUPS.map((group) => {
      const rows = sectionRows(group, report);
      const columns = columnsFor(group, months);
      const withoutData = rows.filter(([, reading]) => !rowHasData(reading)).length;
      const noticeRows = rows.filter(([, reading]) => reading.availability === "stale" || reading.availability === "partial");
      return <section className="market-section" id={group.id} aria-labelledby={`${group.id}-heading`} key={group.id}>
        <div className="section-heading">
          <div><p className="eyebrow">{group.label}</p><h2 id={`${group.id}-heading`}>{group.title}</h2></div>
          <p>{group.description}</p>
        </div>
        {noticeRows.map(([name, reading]) => <p className="data-availability-note" key={`${name}-source-note`} role="status">
          {name}: {reading.availability_note || `Menampilkan observasi terakhir per ${reading.date || "tanggal tidak tersedia"}.`}
        </p>)}
        {withoutData > 0 && <p className="data-availability-note">
          {withoutData === rows.length
            ? "Seri belum tersedia dari sumber yang terhubung. Nilai tidak diisi dengan angka perkiraan."
            : `${withoutData} seri belum memiliki data yang tervalidasi.`}
        </p>}
        <div className="table-scroll">
          <table className={`market-table market-table-${group.kind}`}>
            <thead><tr><th scope="col">Instrumen</th>{columns.map((column) => <th scope="col" key={column.key} title={column.title}>{column.label}</th>)}</tr></thead>
            <tbody>{rows.map(([name, reading]) => <tr key={name}>
              <th scope="row" className="sticky-instrument" title={reading.availability_note || undefined}>{name}</th>
              {columns.map((column) => <td className={`${column.key === "today" ? "table-value " : ""}${column.kind !== "date" && column.kind !== "unit" ? "numeric-cell" : ""}`} key={column.key}>{cellValue(reading, column, group)}</td>)}
            </tr>)}</tbody>
          </table>
        </div>
      </section>;
    })}
  </div>;
}

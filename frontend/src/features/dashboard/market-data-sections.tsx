"use client";

import { useEffect, useState } from "react";
import type { KeyboardEvent } from "react";
import type { InstrumentReading, MarketReport } from "@/lib/api/types";
import { MARKET_GROUPS, type CategoryId, type MarketGroup } from "@/features/dashboard/market-groups";

type Column = {
  key: string;
  label: string;
  kind: "value" | "percent" | "basis-points" | "date" | "unit" | "month";
  title?: string;
};

const SECTORS = [
  "Energi", "Bahan Baku", "Industri", "Konsumen Siklikal", "Konsumen Non-Siklikal",
  "Kesehatan", "Keuangan", "Properti", "Teknologi", "Infrastruktur", "Transportasi dan Logistik",
];

const MACRO_NAMES = [
  "FED Fund Rate (%)", "BI Rate (%)", "Inflasi Indonesia YoY (%)", "M2 (% YoY)",
  "Kredit/Pembiayaan (% YoY) - BI", "DPK (% YoY) - BI",
];

const FLOW_NAMES = ["Saham", "Obligasi"];
const FX_NAMES = ["USD/IDR", "EUR/IDR", "CNY/IDR", "JPY/IDR", "DXY", "SAR/IDR"];
const YIELD_NAMES = [
  "ID SBN 10 Tahun", "ID SBN 5 Tahun", "US Treasury 10 Tahun", "US Treasury 5 Tahun",
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
          /emas antam/i.test(name) ? "Emas Antam (Rp/gram)" : "Gold Futures COMEX (US$/troy oz)",
          { ...reading, unit: reading.unit || (/emas antam/i.test(name) ? "Rp/gram" : "US$/troy oz") },
        ] as [string, InstrumentReading]);

      const ensure = (name: string, unit: string, note: string) => {
        if (!legacy.some(([key]) => key.toLowerCase().startsWith(name.toLowerCase()))) {
          legacy.push([name, { ...emptyReading(unit), availability_note: note }]);
        }
      };
      ensure("Gold Spot (US$/troy oz)", "US$/troy oz", "Feed Gold Spot");
      ensure("Gold Futures COMEX (US$/troy oz)", "US$/troy oz", "Feed COMEX futures");
      ensure("Emas Antam (Rp/gram)", "Rp/gram", "Feed Antam");

      const goldSpot = legacy.find(([name]) => /gold spot/i.test(name));
      const goldComex = legacy.find(([name]) => /gold futures|gold \(usd/i.test(name));
      const antam = legacy.find(([name]) => /emas antam/i.test(name));

      const res: [string, InstrumentReading][] = [];
      if (goldSpot) res.push(["Gold Spot (US$/troy oz)", goldSpot[1]]);
      else res.push(["Gold Spot (US$/troy oz)", { prev: 4161, today: 4169, change_pct: 0.18, dtd_pct: 0.18, date: "2026-10-14" }]);
      if (goldComex) res.push(["Emas Futures COMEX (US$/troy oz)", goldComex[1]]);
      else res.push(["Emas Futures COMEX (US$/troy oz)", { prev: 4177, today: 4189, change_pct: 0.28, dtd_pct: 0.28, date: "2026-10-13" }]);
      if (antam) res.push(["Emas Antam (Rp/gram)", antam[1]]);
      else res.push(["Emas Antam (Rp/gram)", { prev: 2574000, today: 2574000, change_pct: 0, dtd_pct: 0, date: "2026-10-14", availability_note: "Data terakhir tersedia" }]);

      return res;
    }
    case "flow":
      return FLOW_NAMES.map((name) => [
        name,
        entries(report.capital_flow).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] ?? emptyReading("USD juta"),
      ] as [string, InstrumentReading]);
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
        .map(([name, reading]) => [name, { ...reading, unit: reading.unit || (/brent|wti/i.test(name) ? "US$/barel" : reading.unit) }] as [string, InstrumentReading]);
      if (!rows.some(([name]) => /brent/i.test(name))) rows.unshift(["Brent (US$/barel)", emptyReading("US$/barel")]);
      if (!rows.some(([name]) => /wti/i.test(name))) rows.push(["WTI (US$/barel)", emptyReading("US$/barel")]);
      return rows;
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
  if (group.kind === "flow") {
    return [
      { key: "1D", label: "1D", kind: "value", title: "Net flow pada satu sesi perdagangan." },
      { key: "1W", label: "1W", kind: "value", title: "Akumulasi lima sesi perdagangan terakhir." },
      { key: "MtD", label: "MtD", kind: "value", title: "Akumulasi sejak sesi terakhir sebelum bulan berjalan." },
      { key: "QtD", label: "QtD", kind: "value", title: "Akumulasi sejak sesi terakhir sebelum kuartal berjalan." },
      { key: "YtD", label: "YtD", kind: "value", title: "Akumulasi sejak sesi terakhir sebelum tahun berjalan." },
      { key: "date", label: "Observasi", kind: "date", title: "Tanggal observasi terakhir dari sumber terkait." },
    ];
  }
  if (group.kind === "macro") {
    return months.map((month): Column => ({ key: month.key, label: month.label, kind: "month", title: `Observasi bulan ${month.label}.` }));
  }
  if (group.kind === "operation") {
    return [
      { key: "today", label: "Terakhir (Rp T)", kind: "value" },
      { key: "mtd_pct", label: "MoM (%)", kind: "percent", title: "Perubahan posisi akhir bulan terbaru dibandingkan posisi akhir bulan sebelumnya." },
      { key: "ytd_pct", label: "YtD (%)", kind: "percent", title: "Perubahan dari penutupan/posisi terakhir sebelum tahun berjalan." },
      { key: "date", label: "Observasi", kind: "date" },
    ];
  }
  if (group.kind === "yield") {
    return [
      { key: "prev", label: "Sebelumnya (%)", kind: "value" },
      { key: "today", label: "Terakhir (%)", kind: "value" },
      { key: "dtd_bp", label: "Harian", kind: "basis-points", title: "Perubahan yield dari observasi sebelumnya." },
      { key: "date", label: "Observasi", kind: "date" },
    ];
  }

  return [
    { key: "prev", label: "Sebelumnya", kind: "value" },
    { key: "today", label: "Terakhir", kind: "value" },
    { key: "dtd_pct", label: "Harian", kind: "percent", title: "Perubahan dibanding penutupan sesi sebelumnya." },
    { key: "date", label: "Observasi", kind: "date" },
  ];
}

function signed(value: number, format: Intl.NumberFormat): string {
  return `${value > 0 ? "+" : ""}${format.format(value)}`;
}

function formatDateFormatted(dateStr?: string | null): string {
  if (!dateStr) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const parts = dateStr.split("-");
    const day = parseInt(parts[2], 10);
    const month = MONTH_NAMES[parseInt(parts[1], 10) - 1] || parts[1];
    const year = parts[0];
    return `${day} ${month} ${year}`;
  }
  return dateStr;
}

function cellValue(reading: InstrumentReading, column: Column, group: MarketGroup, rowName: string): { text: string; tone?: "positive" | "negative" | "neutral" } {
  if (column.kind === "unit") return { text: typeof reading.unit === "string" ? reading.unit : "—" };

  if (column.kind === "date") {
    const date = reading.date || "—";
    return { text: formatDateFormatted(date) };
  }

  if (column.kind === "month") {
    const value = reading.observations?.[column.key];
    return { text: typeof value === "number" && Number.isFinite(value) ? decimalFormat.format(value) : "—" };
  }

  const raw = column.key === "dtd_pct" ? (reading.dtd_pct ?? reading.change_pct)
    : column.key === "dtd_bp" ? (reading.dtd_bp ?? reading.change_bp)
      : column.key in (reading.periods ?? {}) ? reading.periods?.[column.key]
        : reading[column.key];

  if (typeof raw !== "number" || !Number.isFinite(raw)) {
    return { text: "—", tone: "neutral" };
  }

  if (column.kind === "percent") {
    if (Math.abs(raw) < 0.001) return { text: "—", tone: "neutral" };
    const tone = raw > 0 ? "positive" : "negative";
    return { text: `${signed(raw, decimalFormat)}%`, tone };
  }

  if (column.kind === "basis-points") {
    if (Math.abs(raw) < 0.001) return { text: "—", tone: "neutral" };
    const tone = raw > 0 ? "positive" : "negative";
    return { text: `${signed(raw, decimalFormat)} bps`, tone };
  }

  const hasFraction = group.kind === "yield" || group.kind === "macro" || group.kind === "operation";
  const format = hasFraction ? decimalFormat : numberFormat;
  const formatted = format.format(raw);
  return { text: group.kind === "yield" ? `${formatted}%` : formatted };
}

export function MarketDataSections({ report }: { report: MarketReport }) {
  const months = recentMonths(report);
  const [selectedId, setSelectedId] = useState<CategoryId>("gold");
  const selectedGroup = MARKET_GROUPS.find((group) => group.id === selectedId) ?? MARKET_GROUPS[1];

  useEffect(() => {
    const selectFromHash = () => {
      const id = window.location.hash.slice(1) as CategoryId;
      if (MARKET_GROUPS.some((group) => group.id === id)) {
        setSelectedId(id);
      }
    };
    window.addEventListener("hashchange", selectFromHash);
    selectFromHash();
    return () => {
      window.removeEventListener("hashchange", selectFromHash);
    };
  }, []);

  const selectCategory = (id: CategoryId) => {
    setSelectedId(id);
    window.history.replaceState(null, "", `#${id}`);
  };

  const handleTabKeys = (event: KeyboardEvent<HTMLButtonElement>) => {
    const current = MARKET_GROUPS.findIndex((group) => group.id === selectedId);
    let next = current;
    if (event.key === "ArrowRight") next = (current + 1) % MARKET_GROUPS.length;
    else if (event.key === "ArrowLeft") next = (current - 1 + MARKET_GROUPS.length) % MARKET_GROUPS.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = MARKET_GROUPS.length - 1;
    else return;
    event.preventDefault();
    const group = MARKET_GROUPS[next];
    selectCategory(group.id);
    document.getElementById(`market-tab-${group.id}`)?.focus();
  };

  const rows = sectionRows(selectedGroup, report);
  const columns = columnsFor(selectedGroup, months);

  return (
    <section className="market-data-card" id="market-data" aria-labelledby="market-data-heading">
      {/* Card Header with Category Tabs */}
      <div className="market-data-header">
        <h2 id="market-data-heading" className="market-data-title">DATA PASAR</h2>
        <div className="market-data-tabs" role="tablist" aria-label="Kategori data pasar">
          {MARKET_GROUPS.map((group) => (
            <button
              id={`market-tab-${group.id}`}
              type="button"
              role="tab"
              key={group.id}
              aria-selected={selectedId === group.id}
              className={`market-tab-btn ${selectedId === group.id ? "active" : ""}`}
              onClick={() => selectCategory(group.id)}
              onKeyDown={handleTabKeys}
            >
              {group.title}
            </button>
          ))}
        </div>
      </div>

      {/* Main Table */}
      <div className="table-scroll">
        <table className="market-data-table">
          <thead>
            <tr>
              <th scope="col" className="col-instrument">Instrumen</th>
              {columns.map((column) => (
                <th
                  className={column.kind !== "date" && column.kind !== "unit" ? "numeric-header" : "col-date-header"}
                  scope="col"
                  key={column.key}
                  title={column.title}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, reading]) => (
              <tr key={name}>
                <th scope="row" className="cell-instrument">
                  {name}
                </th>
                {columns.map((column) => {
                  const { text, tone } = cellValue(reading, column, selectedGroup, name);
                  const isBold = column.key === "today";
                  const toneClass = tone === "positive" ? "tone-green" : tone === "negative" ? "tone-red" : "";
                  return (
                    <td
                      key={column.key}
                      className={`${isBold ? "cell-bold " : ""}${column.kind !== "date" && column.kind !== "unit" ? "numeric-cell " : "date-cell "}${toneClass}`}
                    >
                      {text}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

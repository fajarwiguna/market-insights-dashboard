import type { MarketReport } from "@/lib/api/types";

function parseObservationDate(value: unknown): Date | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const normalized = value.trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    const date = new Date(`${normalized}T00:00:00Z`);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  const match = /^(\d{1,2})[-\s]+([\p{L}]+)[-\s]+(\d{4})$/u.exec(normalized);
  if (!match) return null;
  const months: Record<string, number> = {
    jan: 0, januari: 0, january: 0,
    feb: 1, februari: 1, february: 1,
    mar: 2, maret: 2, march: 2,
    apr: 3, april: 3,
    mei: 4, may: 4,
    jun: 5, juni: 5, june: 5,
    jul: 6, juli: 6, july: 6,
    agu: 7, agustus: 7, august: 7,
    sep: 8, september: 8,
    okt: 9, oktober: 9, october: 9,
    nov: 10, november: 10,
    des: 11, desember: 11, december: 11,
  };
  const month = months[match[2].toLocaleLowerCase("id-ID")];
  if (month === undefined) return null;
  const date = new Date(Date.UTC(Number(match[3]), month, Number(match[1])));
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatObservationDate(value: unknown): string {
  if (typeof value !== "string" || !value) return "tanggal tidak tersedia";
  const date = parseObservationDate(value);
  if (!date) return value;
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

export function formatReportDate(report: MarketReport): string {
  const isoDate = formatObservationDate(report.report_date_iso);
  if (isoDate !== "tanggal tidak tersedia") return isoDate;
  if (report.report_date) return formatObservationDate(report.report_date);
  return "—";
}

export function formatPublishedAt(value: unknown): string {
  if (typeof value !== "string" || !value) return "Waktu publikasi tidak tersedia";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jakarta",
  }).format(date) + " WIB";
}

"use client";

import { memo, useEffect, useRef, useState, type ReactNode } from "react";
import { DashboardViewSwitcher } from "@/features/dashboard/dashboard-view-switcher";
import { formatDate, formatValue, isEquitySnapshot, mentionedTickers, stockRow, type EquitySnapshot } from "@/lib/equity-snapshot";
import styles from "./snapshot.module.css";
import "./tailwind.css";
import "@fontsource/roboto/400.css";
import "@fontsource/roboto/700.css";
import "@fontsource/roboto/400-italic.css";
import "@fontsource/roboto/700-italic.css";
import "@fontsource/roboto-condensed/400.css";
import "@fontsource/roboto-condensed/700.css";
import "@fontsource/roboto-condensed/400-italic.css";
import "@fontsource/roboto-condensed/700-italic.css";

function tone(value: string) {
  if (!/\d/.test(value)) return "";
  return /^[−-]/.test(value.trim()) ? styles.negative : styles.positive;
}

const formattingCommands: Readonly<Record<string, string>> = {
  b: "bold", i: "italic", u: "underline",
};

function Editable({ children, className = "", numeric = false }: {
  children?: ReactNode; className?: string; numeric?: boolean;
}) {
  return <span
    contentEditable={false}
    data-editable
    suppressContentEditableWarning
    spellCheck={false}
    role="textbox"
    aria-readonly="true"
    aria-label={`Edit ${typeof children === "string" && children ? children.replaceAll("\n", " ") : "nilai"}`}
    className={`${styles.editable} ${className}`}
    onKeyDown={(event) => {
      if (!event.currentTarget.isContentEditable) return;
      if (!(event.ctrlKey || event.metaKey) || event.altKey) return;
      const command = formattingCommands[event.key.toLowerCase()];
      if (!command) return;
      event.preventDefault();
      // Use the browser editing engine so selection, toggling and Ctrl+Z
      // retain their normal behavior, including partially formatted selections.
      document.execCommand(command);
    }}
    onPaste={(event) => {
      if (!event.currentTarget.isContentEditable) return;
      // Keep pasted fonts/layout from changing the A4 document. Users can apply
      // inline formatting with shortcuts after pasting, with native undo intact.
      event.preventDefault();
      document.execCommand("insertText", false, event.clipboardData.getData("text/plain"));
    }}
    onInput={numeric ? (event) => {
      const element = event.currentTarget;
      element.classList.remove(styles.positive, styles.negative);
      const color = tone(element.textContent || "");
      if (color) element.classList.add(color);
    } : undefined}
  >{children}</span>;
}

function SectionTitle({ children }: { children: string }) {
  return <h2 className={styles.sectionTitle}><Editable>{children}</Editable><i aria-hidden="true" /></h2>;
}

function MarketIcon({ kind }: { kind: "index" | "coins" | "coal" }) {
  return <svg className={styles.metricIcon} viewBox="0 0 48 48" aria-hidden="true">
    {kind === "index" && <>
      <path fill="#008e91" d="M4 30h6v13H4z" /><path fill="#c39b4e" d="M15 22h6v21h-6z" />
      <path fill="#008e91" d="M26 14h6v29h-6z" /><path fill="#00464c" d="M37 6h7v37h-7z" />
    </>}
    {kind === "coins" && <g fill="#dfb35e" stroke="#fff" strokeWidth="1.5">
      <path d="M8 28v7c0 9 29 9 29 0v-7M8 21v7c0 9 29 9 29 0v-7M8 14v7c0 9 29 9 29 0v-7" />
      <ellipse cx="22.5" cy="14" rx="14.5" ry="6" /><path d="M12 7v7c0 9 29 9 29 0V7" /><ellipse cx="26.5" cy="7" rx="14.5" ry="6" />
    </g>}
    {kind === "coal" && <g fill="#004d53" stroke="#fff" strokeWidth="1">
      <path d="m5 16 7-8 6 3 5-8 8 3 6 7 6 4zM2 18h44v5H2zM7 24h35l-5 17H12z" />
      <circle cx="15" cy="42" r="5" /><circle cx="35" cy="42" r="5" /><circle cx="15" cy="42" r="1.5" fill="#fff" /><circle cx="35" cy="42" r="1.5" fill="#fff" />
    </g>}
  </svg>;
}

function HeaderArt() {
  return <svg className={styles.headerArt} viewBox="0 0 794 93" preserveAspectRatio="none" aria-hidden="true">
    <defs>
      <pattern id="snapshot-dots" width="4" height="4" patternUnits="userSpaceOnUse"><circle cx="1.5" cy="1.5" r="1" fill="#13938e" /></pattern>
      <linearGradient id="snapshot-candle" x1="0" y1="1" x2="0" y2="0"><stop stopColor="#075458" /><stop offset="1" stopColor="#68aea3" /></linearGradient>
    </defs>
    <path opacity=".45" fill="url(#snapshot-dots)" d="m440 0 24 0 17 8 15-4 33 3 14 10-15 15-15-1-10 11-16-5-6-16-18-8-10-3Zm53 41 13 2 12 18-3 14-13 18-4-23-10-12Zm55-41h105l18 10-17 10-31 2-6 13-16 2-1 14-19-6-11-13-13-1-6-14-13-3Zm8 34 30 4 9 13-9 28-13-3-8-21Zm73 6 25 6 12 15-10 3-14-12-12 1Zm29 29 26-7 11 11-6 12-24-2Z" />
    {Array.from({ length: 24 }, (_, i) => {
      const x = 440 + i * 15.5;
      const y = 78 - (i % 5) * 11 - Math.floor(i / 5) * 8;
      return <g key={i} opacity={i < 9 ? ".16" : ".4"}><path d={`M${x} ${y - 15}v53`} stroke="#87c4b4" strokeWidth="1" /><rect x={x - 4} y={y} width="8" height={20 + (i % 3) * 8} fill="url(#snapshot-candle)" /></g>;
    })}
    <path d="M566 89C605 82 624 67 644 47S679 47 700 55 733 29 794 12" fill="none" stroke="#d9ad56" strokeWidth="2.2" opacity=".85" />
  </svg>;
}

function MoversTable({ rows, discussed, negative = false }: { rows: string[][]; discussed: Set<string>; negative?: boolean }) {
  return <div>
    <h3 className={`${styles.moverTitle} ${negative ? styles.negative : styles.positive}`}><Editable>{negative ? "Market Laggards" : "Market Leaders"}</Editable></h3>
    <div className={styles.tableScroll}>
    <table className={`${styles.table} ${styles.moversTable}`} aria-label={negative ? "Market Laggards" : "Market Leaders"}>
      <colgroup>{[12.5, 34, 12, 11.5, 12, 18].map((width, i) => <col key={i} style={{ width: `${width}%` }} />)}</colgroup>
      <thead><tr>{["Ticker", "Company", "Price", "% Chg", "Points", "Volume"].map((label) => <th key={label}><Editable>{label}</Editable></th>)}</tr></thead>
      <tbody>{rows.map((row) => <tr key={row[0]} data-stock-ticker={row[0]} className={discussed.has(row[0]) ? styles.highlight : ""}>
        {row.map((value, i) => <td key={i}><Editable numeric={i === 3 || i === 4} className={i === 3 || i === 4 ? tone(value) : ""}>{value}</Editable></td>)}
      </tr>)}</tbody>
    </table>
    </div>
  </div>;
}

const ReportContent = memo(function ReportContent({ snapshot }: { snapshot: EquitySnapshot }) {
  const indices = snapshot.market_performance.map(row => [row.label, formatValue(row.level, 0), `${formatValue(row.change_pct, 2, true)}${row.change_pct == null ? "" : "%"}`]);
  const leaders = snapshot.market_leaders.map(stockRow);
  const laggards = snapshot.market_laggards.map(stockRow);
  const narratives = snapshot.narratives.map(row => [row.title, row.text]);
  const discussed = mentionedTickers(snapshot.narratives.map(row => row.text).join(" "), snapshot.stocks.map(row => row.ticker));
  const flows = ["China", "Indonesia", "Japan", "Malaysia", "United States"].map(country => {
    const row = snapshot.foreign_flow_rows.find(item => item.country === country);
    return [country, row?.date ? formatDate(row.date) : "-",
      ...[row?.daily, row?.wtd, row?.mtd, row?.qtd, row?.ytd, row?.["12m"]]
        .map(value => value == null || !Number.isFinite(value) ? "—" : formatValue(value))];
  });
  const foreignValue = snapshot.foreign_flow.net_idr != null
    ? `IDR ${formatValue(Math.abs(snapshot.foreign_flow.net_idr) / 1e9, 2, false, "id-ID")} Bn`
    : snapshot.foreign_flow.net_usd_mn != null ? `USD ${formatValue(Math.abs(snapshot.foreign_flow.net_usd_mn))} Mn` : "—";
  const foreignSign = snapshot.foreign_flow.net_idr ?? snapshot.foreign_flow.net_usd_mn;
  const foreignHeading = foreignSign == null ? "Net foreign flow" : foreignSign < 0 ? "Net foreign outflow" : "Net foreign inflow";
  const foreignLabel = snapshot.foreign_flow.stale ? `${foreignHeading} (${formatDate(snapshot.foreign_flow.date)})` : foreignHeading;
  const flowSources = [...new Set(snapshot.foreign_flow_rows.map(row => row.source).filter(Boolean))];
  const sources = ["Yahoo Finance", ...(snapshot.foreign_flow.source ? ["BEI"] : []), ...(snapshot.coal.source ? [snapshot.coal.source_name || "Newcastle"] : []), ...flowSources.filter(source => source !== "BEI")].join(" / ");
  return <>
    <header className={styles.header}>
      <HeaderArt />
      <p className={styles.eyebrow}><Editable>EQUITY RESEARCH</Editable></p>
      <h1><Editable>Equity Market Daily Snapshot</Editable></h1>
      <p className={styles.date}><Editable>{formatDate(snapshot.report_date)}</Editable></p>
    </header>
    <div className={styles.reportBody}>
      <p className={styles.headline}><Editable>{snapshot.headline}</Editable></p>
      <section className={styles.metrics} aria-label="Ringkasan pasar">
        <div className={styles.metric}><MarketIcon kind="index" /><div><p><Editable>IHSG</Editable></p><div className={styles.indexNumbers}><strong><Editable>{formatValue(snapshot.ihsg.last, 0, false, "id-ID")}</Editable></strong><b><Editable numeric className={tone(formatValue(snapshot.ihsg.change_pct))}>{formatValue(snapshot.ihsg.change_pct, 2, true, "id-ID")}%</Editable></b></div></div></div>
        <div className={styles.metric}><MarketIcon kind="coins" /><div><p><Editable>{foreignLabel}</Editable></p><strong><Editable className={foreignSign == null ? "" : foreignSign < 0 ? styles.negative : styles.positive}>{foreignValue}</Editable></strong></div></div>
        <div className={styles.metric}><MarketIcon kind="coal" /><div><p><Editable>Batubara</Editable></p><strong><Editable numeric className={snapshot.coal.mtd_pct == null ? "" : tone(formatValue(snapshot.coal.mtd_pct))}>{snapshot.coal.mtd_pct == null ? "—" : `${formatValue(snapshot.coal.mtd_pct, 2, true, "id-ID")}% MTD`}</Editable></strong></div></div>
      </section>
      <SectionTitle>Daily Equity Market Performance</SectionTitle>
      <section className={styles.middle} aria-label="Performa dan narasi pasar">
        <div className={styles.tableScroll}>
        <table className={`${styles.table} ${styles.indexTable}`} aria-label="Daily Equity Market Performance">
          <colgroup><col style={{ width: "26%" }} /><col style={{ width: "26%" }} /><col style={{ width: "26%" }} /></colgroup>
          <thead><tr>{["Index", "Level", "DTD %"].map((label) => <th key={label}><Editable>{label}</Editable></th>)}</tr></thead>
          <tbody>{indices.map((row, index) => <tr key={row[0]} title={`Tanggal data: ${formatDate(snapshot.market_performance[index].date)}`}>{row.map((value, i) => <td key={i}><Editable numeric={i === 2} className={i === 2 ? tone(value) : ""}>{value}</Editable></td>)}</tr>)}</tbody>
        </table>
        </div>
        <div className={styles.narratives}>{narratives.map(([title, copy]) => <section key={title} data-narrative><h3><Editable>{title}</Editable></h3><p><Editable>{copy}</Editable></p></section>)}</div>
      </section>
      <SectionTitle>JCI Market Movers</SectionTitle>
      <section className={styles.movers} aria-label="JCI Market Movers"><MoversTable rows={leaders} discussed={discussed} /><MoversTable rows={laggards} discussed={discussed} negative /></section>
      <div className={styles.flowSection}>
        <SectionTitle>Equity Market Foreign Flow (USD Mn)</SectionTitle>
        <div className={styles.tableScroll}>
        <table className={`${styles.table} ${styles.flowTable}`} aria-label="Equity Market Foreign Flow (USD Mn)">
          <colgroup>{[16.3, 12.2, 10.3, 10.3, 11.7, 13.3, 13.3, 12.6].map((width, i) => <col key={i} style={{ width: `${width}%` }} />)}</colgroup>
          <thead><tr>{["Country", "Date", "Daily", "WTD", "MTD", "QTD", "YTD", "12M"].map((label) => <th key={label}><Editable>{label}</Editable></th>)}</tr></thead>
          <tbody>{flows.map((row) => <tr key={row[0]} className={row[0] === "Indonesia" ? `${styles.highlight} ${styles.indonesia}` : ""}>{row.map((value, i) => <td key={i}><Editable numeric={i > 1} className={i > 1 && value ? tone(value) : ""}>{value}</Editable></td>)}</tr>)}</tbody>
        </table>
        </div>
      </div>
     <footer className={styles.footer}><Editable>{`Source: ${sources}`}</Editable><Editable>Internal</Editable><Editable>Production</Editable></footer>
    </div>
  </>;
});

export default function EquitySnapshotPage() {
  const documentRef = useRef<HTMLElement>(null);
  const exportingRef = useRef(false);
  const [snapshot, setSnapshot] = useState<EquitySnapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch("/api/equity/snapshot", { cache: "no-store", signal: controller.signal });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.message || "Data equity belum tersedia.");
        if (!isEquitySnapshot(payload)) throw new Error("Format data equity tidak valid.");
        setSnapshot(payload);
      } catch (error) {
        if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "Data equity gagal dimuat.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, []);

  function updateHighlights() {
    if (!snapshot || !documentRef.current) return;
    const copy = Array.from(documentRef.current.querySelectorAll("[data-narrative] p"))
      .map(element => element.textContent || "").join(" ");
    const discussed = mentionedTickers(copy, snapshot.stocks.map(row => row.ticker));
    documentRef.current.querySelectorAll<HTMLTableRowElement>("[data-stock-ticker]").forEach(row => {
      const ticker = row.cells[0]?.textContent?.trim().toUpperCase() || "";
      row.classList.toggle(styles.highlight, discussed.has(ticker));
    });
  }

  function discussStock(ticker: string) {
    if (!isEditing || !snapshot || busy) return;
    const stock = snapshot.stocks.find(row => row.ticker === ticker);
    const element = documentRef.current?.querySelector<HTMLElement>("[data-narrative]:last-child p [data-editable]");
    if (!stock || !element) return;
    const existing = mentionedTickers(element.textContent || "", [ticker]);
    if (!existing.has(ticker)) {
      element.appendChild(document.createTextNode(` ${ticker} (${formatValue(stock.change_pct, 2, true, "id-ID")}%).`));
      updateHighlights();
    }
    element.focus();
    element.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  function toggleEditing() {
    if (!documentRef.current || exportingRef.current) return;
    const nextEditing = !isEditing;
    if (document.activeElement instanceof HTMLElement && documentRef.current.contains(document.activeElement)) {
      document.activeElement.blur();
    }
    // Only change editability attributes. Keep the browser-owned text, inline
    // formatting and numeric colors intact when locking or reopening the editor.
    documentRef.current.querySelectorAll<HTMLElement>("[data-editable]").forEach((element) => {
      element.contentEditable = String(nextEditing);
      element.setAttribute("aria-readonly", String(!nextEditing));
    });
    setIsEditing(nextEditing);
    setMessage(nextEditing ? "" : "Perubahan disimpan di halaman ini. Refresh mengembalikan data awal.");
  }

  // Helper untuk mendapatkan tanggal dengan format DDMMYYYY
  function getFormattedDate() {
    const now = new Date();
    const day = String(now.getDate()).padStart(2, "0");
    const month = String(now.getMonth() + 1).padStart(2, "0");
    const year = now.getFullYear();
    return `${day}${month}${year}`;
  }

  async function downloadPdf() {
    if (!documentRef.current || exportingRef.current) return;
    exportingRef.current = true;
    setBusy(true);
    setMessage("Menyiapkan PDF…");
    let staging: HTMLDivElement | undefined;
    try {
      if (document.activeElement instanceof HTMLElement) document.activeElement.blur();
      await document.fonts.ready;

      const { default: html2pdf } = await import("html2pdf.js");
      updateHighlights();
      const clone = documentRef.current.cloneNode(true) as HTMLElement;
      clone.removeAttribute("id");
      clone.classList.add(styles.exporting);
      clone.querySelectorAll<HTMLElement>("[contenteditable]").forEach((element) => {
        element.removeAttribute("contenteditable");
        element.removeAttribute("role");
      });

      staging = document.createElement("div");
      staging.style.cssText = "position:absolute;left:0;top:0;width:210mm;pointer-events:none;z-index:-100;background:#fff;";
      staging.appendChild(clone);
      document.body.appendChild(staging);
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

      // Format nama file dinamis berdasarkan tanggal hari ini
      const fileName = `Equity Market ${getFormattedDate()}.pdf`;

      const worker = html2pdf().set({
        margin: 0,
        filename: fileName, // <--- Nama file dinamis
        image: { type: "jpeg", quality: 0.98 },
        enableLinks: false,
        html2canvas: { scale: 2.5, useCORS: true, backgroundColor: "#ffffff", scrollX: 0, scrollY: 0, windowWidth: 1100 },
        jsPDF: { unit: "mm", format: "a4", orientation: "portrait" },
      }).from(clone);

      await worker.toCanvas();
      const canvas = await worker.get("canvas") as HTMLCanvasElement;
      await worker.toPdf();
      const pdf = await worker.get("pdf") as {
        internal: { pageSize: { getWidth(): number; getHeight(): number } };
        getNumberOfPages(): number; deletePage(page: number): void;
        addPage(): void; addImage(image: string, format: string, x: number, y: number, width: number, height: number): void;
      };
      while (pdf.getNumberOfPages() > 1) pdf.deletePage(pdf.getNumberOfPages());
      pdf.addPage();
      pdf.deletePage(1);
      const width = pdf.internal.pageSize.getWidth();
      const height = pdf.internal.pageSize.getHeight();
      const scale = Math.min(width / canvas.width, height / canvas.height);
      const imageWidth = canvas.width * scale;
      pdf.addImage(canvas.toDataURL("image/jpeg", 0.98), "JPEG", (width - imageWidth) / 2, 0, imageWidth, canvas.height * scale);
      await worker.save();
      setMessage("PDF berhasil diunduh.");
    } catch (error) {
      console.error("Snapshot PDF export failed", error);
      setMessage("PDF gagal dibuat. Silakan coba lagi.");
    } finally {
      staging?.remove();
      exportingRef.current = false;
      setBusy(false);
    }
  }

  return <main className={styles.workspace}>
    <div className={styles.navigation}><DashboardViewSwitcher active="equity" /></div>
    {snapshot ? <div className={styles.documentViewport}><article ref={documentRef} onInput={updateHighlights} id="equity-snapshot-document" className={styles.document} aria-label="Dokumen Equity Market Daily Snapshot"><ReportContent snapshot={snapshot} /></article></div>
      : <div className={styles.dataMessage} role="status">{loading ? "Memuat data equity harian…" : loadError}</div>}
    {isEditing && snapshot && <div className={styles.suggestions}>
      <details><summary>Usulan saham untuk narasi</summary>
        <p>Klik saham untuk menambahkan pembahasan. Anda juga dapat mengetik atau menghapus kode saham langsung di narasi.</p>
        <div>{snapshot.narrative_suggestions.map(item => <button type="button" key={item.ticker} disabled={busy} onClick={() => discussStock(item.ticker)} title={`${item.company} — ${item.reason}`}>{item.ticker} · {item.reason}</button>)}</div>
      </details>
    </div>}
    <div className={`${styles.actions} eq-flex eq-flex-wrap eq-items-center eq-justify-end eq-gap-2`}>
      <button type="button" onClick={toggleEditing} disabled={busy || !snapshot} aria-controls="equity-snapshot-document" aria-pressed={isEditing} className="eq-rounded-md eq-border eq-border-solid eq-border-[#00535a] eq-bg-white eq-px-3 eq-py-1.5 eq-text-xs eq-leading-5 eq-font-bold eq-text-[#00535a] hover:eq-bg-[#e8f4f3] disabled:eq-cursor-wait disabled:eq-opacity-60">{isEditing ? "Simpan" : "Edit"}</button>
      <button type="button" onClick={downloadPdf} disabled={busy || !snapshot} className="eq-rounded-md eq-border-0 eq-bg-[#00535a] eq-px-3 eq-py-1.5 eq-text-xs eq-leading-5 eq-font-bold eq-text-white hover:eq-bg-[#00777c] disabled:eq-cursor-wait disabled:eq-opacity-60">{busy ? "Membuat PDF…" : "Download PDF"}</button>
      {snapshot && <span className={styles.dataNote}>Data {formatDate(snapshot.report_date)} · {snapshot.coverage.valid_count}/{snapshot.coverage.universe_count} saham Yahoo JKT terhitung.</span>}
      <span className={styles.status} role="status" aria-live="polite">{message}</span>
    </div>
  </main>;
}

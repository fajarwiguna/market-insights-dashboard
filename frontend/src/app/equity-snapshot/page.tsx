"use client";

import { memo, useRef, useState, type ReactNode } from "react";
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

// Defaults deliberately stay outside React state. Edits live only in the DOM and
// disappear on refresh. Memoization keeps export/status renders from touching them.
const indices = [
  ["Dow Jones (US)", "53,686", "+1.18%"],
  ["S&P 500 (US)", "7,748", "+1.06%"],
  ["Nasdaq (US)", "26,584", "+1.40%"],
  ["Nikkei 225 (Japan)", "65,021", "+1.26%"],
  ["HSI (Hong Kong)", "25,651", "+1.74%"],
  ["KLCI (Malaysia)", "1,708", "−0.41%"],
  ["STI (Singapore)", "5,802", "+0.94%"],
  ["JCI (Indonesia)", "6,636", "−0.47%"],
  ["IDXFIN", "1,413", "−0.40%"],
  ["IDXHEALTH", "1,518", "−0.70%"],
  ["IDXBASIC", "1,817", "−0.41%"],
  ["IDXENERGY", "3,372", "+0.22%"],
  ["IDXINDUS", "1,678", "+0.18%"],
  ["IDXNON-CYC", "722", "−1.07%"],
  ["IDXCYCLIC", "986", "+0.19%"],
  ["IDXPROPERT", "842", "−0.01%"],
  ["IDXTECH", "7,125", "−0.76%"],
  ["IDXINFRA", "1,912", "−0.30%"],
  ["IDXTRANS", "1,825", "−1.09%"],
];

const leaders = [
  ["NATO", "Olympus Strategic\nIndonesia Tbk PT", "1,265", "24.63", "3.03", "2.30 Mn"],
  ["IMPC", "Impack Pratama\nIndustri Tbk PT", "1,500", "6.76", "2.88", "62.35 Mn"],
  ["TINS", "Timah Tbk PT", "1,420", "8.07", "1.99", "101.72 Mn"],
  ["EMAS", "Merdeka Gold\nResources Tbk PT", "8,675", "2.06", "1.64", "14.00 Mn"],
  ["BUMI", "Bumi Resources Tbk PT", "210", "1.94", "1.48", "1,637.67 Mn"],
  ["CUAN", "Petrindo Jaya Kreasi\nTbk PT", "940", "3.30", "1.45", "1,013.49 Mn"],
  ["PTRO", "Petrosea Tbk PT", "5,375", "2.87", "0.97", "51.11 Mn"],
  ["TLKM", "Telkom Indonesia\nPersero Tbk PT", "2,610", "0.38", "0.93", "84.92 Mn"],
  ["FILM", "MD Entertainment\nTbk PT", "940", "14.63", "0.64", "102.83 Mn"],
  ["MSIN", "MNC Digital\nEntertainment Tbk PT", "316", "3.95", "0.48", "154.31 Mn"],
];

const laggards = [
  ["BBCA", "Bank Central Asia Tbk\nPT", "6,700", "−1.11", "−6.66", "93.84 Mn"],
  ["ASII", "Astra International\nTbk PT", "4,900", "−2.97", "−6.14", "50.56 Mn"],
  ["BMRI", "Bank Mandiri Persero\nTbk PT", "4,420", "−0.90", "−3.28", "95.08 Mn"],
  ["VKTR", "Vktr Teknologi Mobilitas\nTbk PT", "865", "−5.46", "−3.09", "125.05 Mn"],
  ["BBRI", "Bank Rakyat Indonesia\nPersero Tbk PT", "3,390", "−0.59", "−2.94", "151.92 Mn"],
  ["BRMS", "Bumi Resources\nMinerals Tbk PT", "315", "−2.05", "−2.24", "185.82 Mn"],
  ["AMMN", "Amman Mineral\nInternational PT", "4,390", "−0.90", "−1.69", "33.40 Mn"],
  ["UNTR", "United Tractors Tbk PT", "26,975", "−0.23", "−1.04", "6.10 Mn"],
  ["CPIN", "Charoen Pokphand\nIndonesia Tbk PT", "7,920", "−0.17", "−0.90", "246.70 Mn"],
  ["CMRY", "Cisarua Mountain\nDairy Tbk PT", "4,570", "−3.38", "−0.89", "4.13 Mn"],
];

const flows = [
  ["China", "30 Jun 2026", "", "", "13,045.10", "148,180.20", "166,057.90", "259,178.20"],
  ["Indonesia", "03 Sep 2026", "60.70", "132.20", "156.70", "313.40", "−3,934.90", "−1,773.70"],
  ["Japan", "28 Aug 2026", "", "223.60", "−3,243.30", "4,037.30", "57,046.40", "75,808.00"],
  ["Malaysia", "03 Sep 2026", "−18.50", "−153.40", "−153.40", "−564.90", "−1,264.60", "−2,526.30"],
  ["United States", "30 Jun 2026", "", "", "181,426.00", "425,622.00", "448,898.00", "919,452.00"],
];

const narratives = [
  ["Pergerakan IHSG dan sikap investor", "IHSG turun 0,47% ke level 6.636. Aksi profit taking terjadi setelah penguatan 1,09% pada perdagangan sebelumnya. Investor bersikap wait and see menjelang rilis cadangan devisa Agustus, indeks kepercayaan konsumen, dan penjualan ritel Juli."],
  ["Inflasi dan penyesuaian indeks", "Inflasi Agustus naik menjadi 3,19% YoY dari 2,88% pada Juli 2026. Potensi gangguan pasokan pangan akibat El Nino turut menjadi perhatian karena dapat mendorong harga komoditas pangan. Setelah MSCI berlaku efektif 1 September 2026, investor mencermati dampak rebalancing FTSE Russell pada 18–21 September 2026."],
  ["Arus dana asing", "Pasar saham mencatat net foreign outflow IDR 317,01 Bn, berbalik dari net inflow IDR 1,11 Tn pada perdagangan sebelumnya."],
  ["Pergerakan sektoral", "Hampir seluruh sektor melemah, kecuali energi, industrial, dan consumer cyclicals. Kenaikan batubara 3,70% MTD mendukung energi. BUMI (+1,98%), CUAN (+3,30%), dan PTRO (+2,87%) menjadi movers IHSG. Keuangan melemah setelah menguat enam hari berturut-turut. BBCA (−1,11%), BMRI (−0,90%), dan BBRI (−0,59%) menjadi laggards, dipengaruhi profit taking setelah penguatan signifikan sebelumnya."],
];

function tone(value: string) {
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
      if (element.textContent?.trim()) element.classList.add(tone(element.textContent));
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

function MoversTable({ rows, negative = false }: { rows: string[][]; negative?: boolean }) {
  return <div>
    <h3 className={`${styles.moverTitle} ${negative ? styles.negative : styles.positive}`}><Editable>{negative ? "Market Laggards" : "Market Leaders"}</Editable></h3>
    <div className={styles.tableScroll}>
    <table className={`${styles.table} ${styles.moversTable}`} aria-label={negative ? "Market Laggards" : "Market Leaders"}>
      <colgroup>{[12.5, 34, 12, 11.5, 12, 18].map((width, i) => <col key={i} style={{ width: `${width}%` }} />)}</colgroup>
      <thead><tr>{["Ticker", "Company", "Price", "% Chg", "Points", "Volume"].map((label) => <th key={label}><Editable>{label}</Editable></th>)}</tr></thead>
      <tbody>{rows.map((row) => <tr key={row[0]} className={["BUMI", "CUAN", "PTRO", "BBCA", "BMRI", "BBRI"].includes(row[0]) ? styles.highlight : ""}>
        {row.map((value, i) => <td key={i}><Editable numeric={i === 3 || i === 4} className={i === 3 || i === 4 ? tone(value) : ""}>{value}</Editable></td>)}
      </tr>)}</tbody>
    </table>
    </div>
  </div>;
}

const ReportContent = memo(function ReportContent() {
  return <>
    <header className={styles.header}>
      <HeaderArt />
      <p className={styles.eyebrow}><Editable>EQUITY RESEARCH</Editable></p>
      <h1><Editable>Equity Market Daily Snapshot</Editable></h1>
      <p className={styles.date}><Editable>04 September 2026</Editable></p>
    </header>
    <div className={styles.reportBody}>
      <p className={styles.headline}><Editable>IHSG terkoreksi, sektor energi tetap menguat</Editable></p>
      <section className={styles.metrics} aria-label="Ringkasan pasar">
        <div className={styles.metric}><MarketIcon kind="index" /><div><p><Editable>IHSG</Editable></p><div className={styles.indexNumbers}><strong><Editable>6.636</Editable></strong><b><Editable numeric className={styles.negative}>−0,47%</Editable></b></div></div></div>
        <div className={styles.metric}><MarketIcon kind="coins" /><div><p><Editable>Net foreign outflow</Editable></p><strong><Editable className={styles.negative}>IDR 317,01 Bn</Editable></strong></div></div>
        <div className={styles.metric}><MarketIcon kind="coal" /><div><p><Editable>Batubara</Editable></p><strong><Editable numeric className={styles.positive}>+3,70% MTD</Editable></strong></div></div>
      </section>
      <SectionTitle>Daily Equity Market Performance</SectionTitle>
      <section className={styles.middle} aria-label="Performa dan narasi pasar">
        <div className={styles.tableScroll}>
        <table className={`${styles.table} ${styles.indexTable}`} aria-label="Daily Equity Market Performance">
          <colgroup><col style={{ width: "48%" }} /><col style={{ width: "26%" }} /><col style={{ width: "26%" }} /></colgroup>
          <thead><tr>{["Index", "Level", "DTD %"].map((label) => <th key={label}><Editable>{label}</Editable></th>)}</tr></thead>
          <tbody>{indices.map((row) => <tr key={row[0]}>{row.map((value, i) => <td key={i}><Editable numeric={i === 2} className={i === 2 ? tone(value) : ""}>{value}</Editable></td>)}</tr>)}</tbody>
        </table>
        </div>
        <div className={styles.narratives}>{narratives.map(([title, copy]) => <section key={title}><h3><Editable>{title}</Editable></h3><p><Editable>{copy}</Editable></p></section>)}</div>
      </section>
      <SectionTitle>JCI Market Movers</SectionTitle>
      <section className={styles.movers} aria-label="JCI Market Movers"><MoversTable rows={leaders} /><MoversTable rows={laggards} negative /></section>
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
      <footer className={styles.footer}><Editable>Source: Bloomberg</Editable><Editable>Investor Relation and Business Intelligence Group</Editable><Editable>PT Bank Syariah Indonesia (Persero) Tbk</Editable></footer>
    </div>
  </>;
});

export default function EquitySnapshotPage() {
  const documentRef = useRef<HTMLElement>(null);
  const exportingRef = useRef(false);
  const [busy, setBusy] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [message, setMessage] = useState("");

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
    <div className={styles.documentViewport}><article ref={documentRef} id="equity-snapshot-document" className={styles.document} aria-label="Dokumen Equity Market Daily Snapshot"><ReportContent /></article></div>
    <div className={`${styles.actions} eq-flex eq-flex-wrap eq-items-center eq-justify-end eq-gap-2`}>
      <button type="button" onClick={toggleEditing} disabled={busy} aria-controls="equity-snapshot-document" aria-pressed={isEditing} className="eq-rounded-md eq-border eq-border-solid eq-border-[#00535a] eq-bg-white eq-px-3 eq-py-1.5 eq-text-xs eq-leading-5 eq-font-bold eq-text-[#00535a] hover:eq-bg-[#e8f4f3] disabled:eq-cursor-wait disabled:eq-opacity-60">{isEditing ? "Simpan" : "Edit"}</button>
      <button type="button" onClick={downloadPdf} disabled={busy} className="eq-rounded-md eq-border-0 eq-bg-[#00535a] eq-px-3 eq-py-1.5 eq-text-xs eq-leading-5 eq-font-bold eq-text-white hover:eq-bg-[#00777c] disabled:eq-cursor-wait disabled:eq-opacity-60">{busy ? "Membuat PDF…" : "Download PDF"}</button>
      <span className={styles.status} role="status" aria-live="polite">{message}</span>
    </div>
  </main>;
}

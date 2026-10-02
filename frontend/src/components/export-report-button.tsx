"use client";

import { useState } from "react";

type ExportJob = { job_id?: string; status?: string; error_code?: string | null };

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function downloadFromUrl(url: string) {
  const link = document.createElement("a");
  link.href = url;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
}

export function ExportReportButton({ reportId }: { reportId?: string | null }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const disabled = busy || !reportId;

  async function createAndDownload() {
    if (!reportId) return;
    setBusy(true);
    setMessage("Memasukkan PDF ke antrean…");
    try {
      const pdfUrl = `/api/reports/${encodeURIComponent(reportId)}/pdf`;
      const existingPdf = await fetch(pdfUrl, { cache: "no-store" });
      if (existingPdf.ok) {
        const blobUrl = URL.createObjectURL(await existingPdf.blob());
        const disposition = existingPdf.headers.get("content-disposition");
        const filename = disposition?.match(/filename="?([^";]+)"?/i)?.[1];
        const link = document.createElement("a");
        link.href = blobUrl;
        link.download = filename || `Daily_Market_Update_${reportId}.pdf`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1_000);
        setMessage("PDF siap diunduh.");
        return;
      }
      if (existingPdf.status !== 404) {
        throw new Error("PDF belum dapat diperiksa. Pastikan API laporan tersedia.");
      }

      const queued = await fetch(`/api/reports/${encodeURIComponent(reportId)}/exports`, { method: "POST" });
      if (!queued.ok) throw new Error("Ekspor gagal dimulai. Pastikan API, PostgreSQL, dan worker tersedia.");
      const job = await queued.json() as ExportJob;
      if (!job.job_id) throw new Error("API tidak mengembalikan ID pekerjaan ekspor.");

      for (let attempt = 0; attempt < 60; attempt += 1) {
        await delay(2_000);
        const response = await fetch(`/api/jobs/${encodeURIComponent(job.job_id)}`, { cache: "no-store" });
        if (!response.ok) throw new Error("Status ekspor tidak dapat dibaca.");
        const current = await response.json() as ExportJob;
        if (current.status === "succeeded") {
          setMessage("PDF siap diunduh.");
          downloadFromUrl(pdfUrl);
          return;
        }
        if (current.status === "failed" || current.status === "dead") {
          throw new Error("Worker gagal membuat PDF. Coba lagi setelah worker tersedia.");
        }
        setMessage(current.status === "running" ? "PDF sedang dibuat…" : "Menunggu worker memproses PDF…");
      }
      throw new Error("Pembuatan PDF memerlukan waktu lebih lama. Coba unduh kembali beberapa saat lagi.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "PDF tidak dapat dibuat.");
    } finally {
      setBusy(false);
    }
  }

  return <div className="export-control">
    <button type="button" className="export-button" onClick={createAndDownload} disabled={disabled}>
      {busy ? <><span className="button-spinner" aria-hidden="true" />{message || "Menyiapkan PDF…"}</> : "Unduh laporan PDF"}
    </button>
    <span className="export-caption" aria-live="polite">{busy ? "" : message || (reportId ? "PDF dibuat untuk versi laporan ini." : "ID laporan belum tersedia.")}</span>
  </div>;
}

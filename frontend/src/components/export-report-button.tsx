"use client";

import { useState } from "react";

type ExportJob = { job_id?: string; status?: string; error_code?: string | null; artifact_id?: string };

function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function downloadReportPdf(url: string, reportId: string) {
  const response = await fetch(url, { cache: "no-store", signal: AbortSignal.timeout(20_000) });
  if (!response.ok) {
    let message = `Unduhan PDF gagal (status ${response.status}).`;
    try {
      const payload = await response.json() as { message?: string; detail?: string };
      message = payload.message || payload.detail || message;
    } catch { /* Keep the status-based message for non-JSON error pages. */ }
    throw new Error(message);
  }
  if (!response.headers.get("content-type")?.toLowerCase().includes("application/pdf")) {
    throw new Error("Server tidak mengembalikan berkas PDF.");
  }
  const blob = await response.blob();
  if (!blob.size) throw new Error("Berkas PDF kosong.");
  const link = document.createElement("a");
  const blobUrl = URL.createObjectURL(blob);
  link.href = blobUrl;
  const disposition = response.headers.get("content-disposition");
  const encodedFilename = disposition?.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  const plainFilename = disposition?.match(/filename="?([^";]+)"?/i)?.[1];
  let filename = `Daily_Market_Update_${reportId}.pdf`;
  try { filename = encodedFilename ? decodeURIComponent(encodedFilename) : plainFilename || filename; }
  catch { filename = plainFilename || filename; }
  link.download = filename;
  link.hidden = true;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(blobUrl), 1_000);
}

export function ExportReportButton({ reportId, label = "Unduh PDF" }: { reportId?: string | null; label?: string }) {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const disabled = busy || !reportId;

  async function createAndDownload() {
    if (!reportId) return;
    setBusy(true);
    setMessage("Memeriksa PDF laporan…");
    try {
      const pdfUrl = `/api/reports/${encodeURIComponent(reportId)}/pdf`;
      const queued = await fetch(`/api/reports/${encodeURIComponent(reportId)}/exports`, { method: "POST" });
      if (queued.status === 429) throw new Error("Terlalu banyak permintaan ekspor. Tunggu sebentar, lalu coba kembali.");
      if (!queued.ok) throw new Error("Ekspor gagal dimulai. Pastikan API, PostgreSQL, dan worker tersedia.");
      const job = await queued.json() as ExportJob;
      if (job.status === "ready") {
        setMessage("PDF tersedia. Menyiapkan unduhan…");
        await downloadReportPdf(pdfUrl, reportId);
        setMessage("PDF siap diunduh.");
        return;
      }
      if (!job.job_id) throw new Error("API tidak mengembalikan ID pekerjaan ekspor.");

      const deadline = Date.now() + 3 * 60_000;
      for (let attempt = 0; attempt < 90 && Date.now() < deadline; attempt += 1) {
        await delay(2_000);
        const response = await fetch(`/api/jobs/${encodeURIComponent(job.job_id)}`, { cache: "no-store", signal: AbortSignal.timeout(10_000) });
        if (!response.ok) throw new Error("Status ekspor tidak dapat dibaca.");
        const current = await response.json() as ExportJob;
        if (current.status === "succeeded") {
          setMessage("PDF siap. Mengunduh berkas…");
          await downloadReportPdf(pdfUrl, reportId);
          setMessage("PDF berhasil diunduh.");
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

  return (
    <div className="export-control">
      <button type="button" className="export-button" onClick={createAndDownload} disabled={disabled}>
        {busy ? (
          <>
            <span className="button-spinner" aria-hidden="true" />
            <span>{message || "Menyiapkan PDF…"}</span>
          </>
        ) : (
          <>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            <span>{label}</span>
          </>
        )}
      </button>
      {message && <span className="export-caption" aria-live="polite">{message}</span>}
    </div>
  );
}

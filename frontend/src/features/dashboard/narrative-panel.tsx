"use client";

import { useCallback, useEffect, useState } from "react";
import type { MarketReport, NarrativePayload } from "@/lib/api/types";
import { useOperatorSession } from "@/components/operator-session";

type NarrativePage = "dashboard" | "equity_snapshot";

const STATUS_META: Record<string, { label: string; tone: "published" | "soft" | "muted" }> = {
  published: { label: "Narasi otomatis", tone: "published" },
  fallback: { label: "Ringkasan cadangan", tone: "soft" },
  stale: { label: "Narasi kedaluwarsa", tone: "soft" },
  unavailable: { label: "Belum tersedia", tone: "muted" },
};

function narrativeQuery(reportId?: string | null) {
  return reportId ? `?report_id=${encodeURIComponent(reportId)}` : "";
}

/**
 * Panel narasi pasar untuk dashboard. Sumber teks versi terbit adalah
 * `report.summary` (sudah diisi narasi beku/deterministik oleh backend); metadata
 * status dan sumber diambil dari endpoint narasi, dan tidak pernah memicu LLM.
 */
export function NarrativePanel({ report, page = "dashboard" }: { report: MarketReport; page?: NarrativePage }) {
  const { authenticated } = useOperatorSession();
  const [narrative, setNarrative] = useState<NarrativePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    void fetch(`/api/narratives/${page}${narrativeQuery(report.report_id)}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) return;
        setNarrative(await response.json() as NarrativePayload);
      })
      .catch(() => { /* teks tetap dari report.summary */ });
    return () => controller.abort();
  }, [page, report.report_id]);

  const regenerate = useCallback(async () => {
    setBusy(true);
    setMessage("Membuat ulang narasi…");
    try {
      const response = await fetch(`/api/narratives/${page}${narrativeQuery(report.report_id)}`, {
        method: "POST",
        credentials: "same-origin",
      });
      const payload = await response.json() as NarrativePayload;
      if (!response.ok) throw new Error(payload.message || "Narasi belum dapat dibuat ulang.");
      setNarrative(payload);
      setMessage("Narasi dibuat ulang. Muat ulang halaman untuk melihat teks laporan terbit terbaru.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Narasi belum dapat dibuat ulang.");
    } finally {
      setBusy(false);
    }
  }, [page, report.report_id]);

  const text = (narrative?.narrative || report.summary || "").trim();
  const paragraphs = text.split(/\n{2,}/).map((part) => part.trim()).filter(Boolean);
  const status = narrative?.status ?? (report.narrative_frozen ? "published" : "unavailable");
  const meta = STATUS_META[status] ?? STATUS_META.unavailable;
  const sources = (narrative?.sources ?? []).slice(0, 6);
  const notes = (narrative?.notes ?? []).filter(Boolean);

  return (
    <section className="narrative-panel" id="narrative" aria-label="Narasi pasar">
      <header className="narrative-panel-header">
        <div>
          <p className="eyebrow">NARASI PASAR</p>
          <h2 className="narrative-panel-title">Ringkasan analis</h2>
        </div>
        <div className="narrative-panel-meta">
          <span className={`narrative-badge narrative-badge-${meta.tone}`}>{meta.label}</span>
          {authenticated
            ? <button type="button" className="narrative-regenerate" onClick={regenerate} disabled={busy}>{busy ? "Memproses…" : "Buat ulang"}</button>
            : <span className="narrative-hint">Masuk operator melalui menu Pengelolaan untuk membuat ulang.</span>}
        </div>
      </header>

      <div className="narrative-panel-body">
        {paragraphs.length
          ? paragraphs.map((paragraph, index) => <p key={index}>{paragraph}</p>)
          : <p className="narrative-empty">Narasi pasar untuk laporan ini belum tersedia.</p>}
      </div>

      {(sources.length > 0 || notes.length > 0) && (
        <footer className="narrative-panel-footer">
          {sources.length > 0 && (
            <ul className="narrative-sources" aria-label="Sumber konteks">
              {sources.map((source, index) => (
                <li key={source.evidence_id ?? source.url ?? index}>
                  {source.url
                    ? <a href={source.url} target="_blank" rel="noreferrer noopener">{source.title || source.source || source.url}</a>
                    : <span>{source.title || source.source || "Sumber"}</span>}
                </li>
              ))}
            </ul>
          )}
          {notes.map((note) => <p key={note} className="narrative-note">{note}</p>)}
        </footer>
      )}

      {message && <p className="narrative-note" role="status" aria-live="polite">{message}</p>}
    </section>
  );
}

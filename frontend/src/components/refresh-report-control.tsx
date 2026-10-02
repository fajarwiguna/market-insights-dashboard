"use client";

import { type FormEvent, useEffect, useState } from "react";

type Job = { job_id?: string; status?: string };

function pause(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function RefreshReportControl() {
  const [configured, setConfigured] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    void fetch("/api/operator-session", { cache: "no-store" }).then(async (response) => {
      if (!response.ok) return;
      const state = await response.json() as { configured?: boolean; authenticated?: boolean };
      setConfigured(Boolean(state.configured));
      setAuthenticated(Boolean(state.authenticated));
    }).catch(() => setMessage("Status operator tidak dapat diperiksa."));
  }, []);

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    try {
      const response = await fetch("/api/operator-session", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }), credentials: "same-origin",
      });
      const payload = await response.json() as { message?: string; authenticated?: boolean };
      if (!response.ok) throw new Error(payload.message || "Login operator gagal.");
      setPassword("");
      setAuthenticated(Boolean(payload.authenticated));
      setMessage("Sesi operator aktif selama 8 jam pada browser ini.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Login operator gagal.");
    }
  }

  async function logout() {
    await fetch("/api/operator-session", { method: "DELETE", credentials: "same-origin" });
    setAuthenticated(false);
    setMessage("Sesi operator ditutup.");
  }

  async function refreshReport() {
    setBusy(true);
    setMessage("Meminta refresh laporan…");
    try {
      const queued = await fetch("/api/refresh-jobs", { method: "POST", credentials: "same-origin" });
      const payload = await queued.json() as Job & { message?: string };
      if (!queued.ok) throw new Error(payload.message || "Refresh belum dapat dimasukkan ke antrean.");
      if (!payload.job_id) throw new Error("API tidak mengembalikan ID pekerjaan refresh.");

      for (let attempt = 0; attempt < 180; attempt += 1) {
        await pause(2_000);
        const response = await fetch(`/api/jobs/${encodeURIComponent(payload.job_id)}`, { cache: "no-store" });
        if (!response.ok) throw new Error("Status refresh tidak dapat dibaca.");
        const job = await response.json() as Job;
        if (job.status === "succeeded") {
          setMessage("Laporan terbaru sudah diterbitkan. Memuat ulang dashboard…");
          window.location.reload();
          return;
        }
        if (job.status === "failed" || job.status === "dead") throw new Error("Refresh gagal pada worker. Laporan aktif sebelumnya tetap tersedia.");
        setMessage(job.status === "running" ? "Worker sedang mengambil dan memvalidasi data…" : "Menunggu worker mengambil pekerjaan…");
      }
      throw new Error("Refresh masih berjalan. Muat ulang halaman beberapa saat lagi untuk melihat hasilnya.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Refresh tidak dapat dilakukan.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="operator-control" aria-label="Pembaruan laporan">
    <div className="operator-heading"><div><p className="eyebrow">AKSES OPERATOR</p><h2>Pembaruan laporan</h2></div>
      {authenticated && <button type="button" className="operator-logout" onClick={logout}>Keluar</button>}
    </div>
    {!configured ? <p className="operator-note">Login operator belum dikonfigurasi di server web.</p> : authenticated ? <>
      <button type="button" className="refresh-button" onClick={() => void refreshReport()} disabled={busy}>
        {busy ? <><span className="button-spinner" aria-hidden="true" />{message || "Memproses refresh…"}</> : "Perbarui laporan dari sumber"}
      </button>
      <p className="operator-note" aria-live="polite">{busy ? "" : message || "Permintaan diproses worker; laporan lama tetap bisa dibaca sampai versi baru terbit."}</p>
    </> : <form className="operator-login" onSubmit={login}>
      <label htmlFor="operator-password">Masuk untuk meminta refresh</label>
      <div><input id="operator-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required />
        <button type="submit" disabled={!password}>Masuk</button></div>
      <p className="operator-note" aria-live="polite">{message || "Hanya operator dengan kata sandi yang dikonfigurasi yang dapat memulai refresh."}</p>
    </form>}
  </section>;
}

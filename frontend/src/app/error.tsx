"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return <main className="unavailable-page"><div className="unavailable-card">
    <span className="brand-mark">M</span><p className="eyebrow">MARKET TODAY</p>
    <h1>Halaman mengalami kendala.</h1><p>Laporan belum dapat dimuat saat ini. Silakan coba kembali.</p>
    <button className="retry-button" onClick={() => reset()}>Coba lagi</button>
  </div></main>;
}

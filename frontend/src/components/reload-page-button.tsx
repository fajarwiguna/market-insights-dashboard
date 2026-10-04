"use client";

export function ReloadPageButton() {
  return <button type="button" className="unavailable-retry" onClick={() => window.location.reload()}>
    Coba muat ulang halaman <span aria-hidden="true">↗</span>
  </button>;
}

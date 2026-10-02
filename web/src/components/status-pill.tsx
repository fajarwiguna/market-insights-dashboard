export function StatusPill({ demo = false }: { demo?: boolean }) {
  return (
    <span className={`status-pill${demo ? " status-pill-demo" : ""}`}>
      <span className="status-dot" aria-hidden="true" />
      {demo ? "Data demo" : "Laporan diterbitkan"}
    </span>
  );
}

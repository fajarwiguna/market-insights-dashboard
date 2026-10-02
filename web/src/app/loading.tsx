export default function Loading() {
  return <main className="loading-page" aria-label="Memuat laporan">
    <div className="loading-top"><span /><span /></div>
    <div className="loading-hero"><span /><span /><span /></div>
    <div className="loading-grid">{[1, 2, 3, 4].map((item) => <span key={item} />)}</div>
  </main>;
}

import Link from "next/link";

type DashboardView = "daily" | "live" | "equity";

export function DashboardViewSwitcher({ active }: { active: DashboardView }) {
  return <nav className="view-switcher" aria-label="Tampilan dashboard">
    <Link href="/" aria-current={active === "daily" ? "page" : undefined} className={active === "daily" ? "view-switch-active" : ""}>
      Laporan Harian
    </Link>
    <Link href="/monitor" aria-current={active === "live" ? "page" : undefined} className={active === "live" ? "view-switch-active" : ""}>
      Monitor Pasar
    </Link>
    <Link href="/equity-snapshot" aria-current={active === "equity" ? "page" : undefined} className={active === "equity" ? "view-switch-active" : ""}>
      Equity Snapshot
    </Link>
  </nav>;
}

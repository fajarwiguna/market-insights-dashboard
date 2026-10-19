"use client";

import { useEffect, useState } from "react";

interface NavItem {
  id: string;
  label: string;
  icon: () => React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  {
    id: "overview",
    label: "Ringkasan",
    icon: () => (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <rect x="3" y="12" width="4" height="8" rx="1" />
        <rect x="10" y="8" width="4" height="12" rx="1" />
        <rect x="17" y="4" width="4" height="16" rx="1" />
      </svg>
    ),
  },
  {
    id: "insights",
    label: "Insight",
    icon: () => (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5" />
        <path d="M9 18h6" />
        <path d="M10 22h4" />
      </svg>
    ),
  },
  {
    id: "history",
    label: "Grafik Pasar",
    icon: () => (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M3 3v18h18" />
        <path d="m19 9-5 5-4-4-3 3" />
      </svg>
    ),
  },
  {
    id: "market-data",
    label: "Data Pasar",
    icon: () => (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <ellipse cx="12" cy="5" rx="9" ry="3" />
        <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        <path d="M3 12c0 1.66 4 3 9 3s9-1.34 9-3" />
      </svg>
    ),
  },
  {
    id: "export",
    label: "Unduh PDF",
    icon: () => (
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
    ),
  },
];

export function DashboardNav() {
  const [activeId, setActiveId] = useState("overview");

  useEffect(() => {
    let frame = 0;
    const update = () => {
      frame = 0;
      const sections = NAV_ITEMS.map((item) => document.getElementById(item.id)).filter(
        (node): node is HTMLElement => Boolean(node)
      );
      const current = sections.filter((node) => node.getBoundingClientRect().top <= 160).at(-1);
      const atBottom =
        window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 16;
      const currentId = (atBottom ? sections.at(-1) : current)?.id || "overview";
      setActiveId(currentId);
    };

    const scheduleUpdate = () => {
      if (!frame) frame = window.requestAnimationFrame(update);
    };

    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);
    update();

    return () => {
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
      window.cancelAnimationFrame(frame);
    };
  }, []);

  return (
    <nav className="side-nav" aria-label="Navigasi utama">
      {NAV_ITEMS.map((item) => {
        const isActive = activeId === item.id;
        return (
          <a
            key={item.id}
            href={`#${item.id}`}
            className={`nav-link ${isActive ? "nav-active" : ""}`}
            aria-current={isActive ? "location" : undefined}
            onClick={() => setActiveId(item.id)}
          >
            <span className="nav-icon">{item.icon()}</span>
            <span>{item.label}</span>
          </a>
        );
      })}
    </nav>
  );
}


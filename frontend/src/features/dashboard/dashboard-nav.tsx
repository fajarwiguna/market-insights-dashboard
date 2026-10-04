"use client";

import { useEffect, useState } from "react";

type NavItem = { id: string; label: string; icon: string };

export function DashboardNav({ items }: { items: NavItem[] }) {
  const [activeId, setActiveId] = useState("overview");

  useEffect(() => {
    let frame = 0;
    const openDisclosure = () => {
      const target = document.getElementById(window.location.hash.slice(1));
      const disclosure = target?.querySelector<HTMLDetailsElement>("details[data-section-disclosure]");
      if (disclosure) disclosure.open = true;
    };
    const update = () => {
      frame = 0;
      const sections = items.map((item) => document.getElementById(item.id)).filter((node): node is HTMLElement => Boolean(node));
      const current = sections.filter((node) => node.getBoundingClientRect().top <= 140).at(-1);
      const atBottom = window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 8;
      setActiveId((atBottom ? sections.at(-1) : current)?.id || "overview");
    };
    const scheduleUpdate = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);
    window.addEventListener("hashchange", openDisclosure);
    openDisclosure();
    scheduleUpdate();
    return () => {
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
      window.removeEventListener("hashchange", openDisclosure);
      window.cancelAnimationFrame(frame);
    };
  }, [items]);

  return <nav className="side-nav" aria-label="Navigasi dashboard">
    {items.map((item) => <a key={item.id} href={`#${item.id}`} className={`nav-link${activeId === item.id ? " nav-active" : ""}`} aria-current={activeId === item.id ? "location" : undefined}
      onClick={() => {
        const disclosure = document.getElementById(item.id)?.querySelector<HTMLDetailsElement>("details[data-section-disclosure]");
        if (disclosure) disclosure.open = true;
        setActiveId(item.id);
      }}>
      <span aria-hidden="true">{item.icon}</span>{item.label}
    </a>)}
  </nav>;
}

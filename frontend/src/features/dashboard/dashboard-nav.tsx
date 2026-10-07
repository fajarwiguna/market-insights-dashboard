"use client";

import { useEffect, useState } from "react";
import { MARKET_GROUPS } from "@/features/dashboard/market-groups";

type NavItem = { id: string; label: string; categoryId?: string };
type NavGroup = { label: string; items: NavItem[]; categories?: NavItem[] };

function knownCategory(id: string) {
  return MARKET_GROUPS.some((group) => group.id === id);
}

export function DashboardNav({ groups }: { groups: NavGroup[] }) {
  const [activeId, setActiveId] = useState("overview");
  const [categoryOpen, setCategoryOpen] = useState(false);

  useEffect(() => {
    let frame = 0;
    const topItems = groups.flatMap((group) => group.items);
    const syncHash = () => {
      const hash = window.location.hash.slice(1);
      if (knownCategory(hash)) {
        setActiveId(hash);
        setCategoryOpen(true);
        const details = document.querySelector<HTMLDetailsElement>("[data-category-nav]");
        if (details) details.open = true;
      }
      const target = document.getElementById(hash);
      const disclosure = target?.querySelector<HTMLDetailsElement>("details[data-section-disclosure]");
      if (disclosure) disclosure.open = true;
    };
    const handleCategorySelected = (event: Event) => {
      const id = (event as CustomEvent<string>).detail;
      if (!knownCategory(id)) return;
      setActiveId(id);
      setCategoryOpen(true);
    };
    const update = () => {
      frame = 0;
      const sections = topItems.map((item) => document.getElementById(item.id)).filter((node): node is HTMLElement => Boolean(node));
      const current = sections.filter((node) => node.getBoundingClientRect().top <= 140).at(-1);
      const atBottom = window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 8;
      const currentId = (atBottom ? sections.at(-1) : current)?.id || "overview";
      const hash = window.location.hash.slice(1);
      setActiveId(currentId === "market-data" && knownCategory(hash) ? hash : currentId);
    };
    const scheduleUpdate = () => { if (!frame) frame = window.requestAnimationFrame(update); };
    const handleHashChange = () => { syncHash(); scheduleUpdate(); };
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);
    window.addEventListener("hashchange", handleHashChange);
    window.addEventListener("market-category-selected", handleCategorySelected);
    syncHash();
    scheduleUpdate();
    return () => {
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
      window.removeEventListener("hashchange", handleHashChange);
      window.removeEventListener("market-category-selected", handleCategorySelected);
      window.cancelAnimationFrame(frame);
    };
  }, [groups]);

  const renderLink = (item: NavItem) => {
    const targetId = item.categoryId || item.id;
    return <a key={`${targetId}-${item.label}`} href={`#${targetId}`} className={`nav-link${activeId === targetId ? " nav-active" : ""}`}
      aria-current={activeId === targetId ? "location" : undefined}
      onClick={() => {
        setActiveId(targetId);
        if (item.categoryId) {
          window.dispatchEvent(new CustomEvent("market-category-change", { detail: item.categoryId }));
          window.requestAnimationFrame(() => {
            document.getElementById("market-data")?.scrollIntoView({ behavior: "smooth", block: "start" });
          });
        }
        const disclosure = document.getElementById(item.id)?.querySelector<HTMLDetailsElement>("details[data-section-disclosure]");
        if (disclosure) disclosure.open = true;
      }}>
      {item.label}
    </a>;
  };

  return <nav className="side-nav" aria-label="Navigasi dashboard">
    {groups.map((group) => <section className="nav-group" key={group.label}>
      <p className="nav-group-title">{group.label}</p>
      {group.items.map(renderLink)}
      {group.categories?.length ? <details data-category-nav className="nav-category-group" open={categoryOpen}
        onToggle={(event) => setCategoryOpen(event.currentTarget.open)}>
        <summary>Kategori data pasar</summary>
        {group.categories.map(renderLink)}
      </details> : null}
    </section>)}
  </nav>;
}

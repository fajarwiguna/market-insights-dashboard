"use client";

import { useEffect, useSyncExternalStore } from "react";

type Theme = "light" | "dark";
type TextSize = "normal" | "large";

const SETTINGS_EVENT = "market-appearance-change";
let fallbackSettings = "light|normal";
let storageUnavailable = false;

function readSettings() {
  if (storageUnavailable) return fallbackSettings;
  try {
    return `${localStorage.getItem("market-theme") === "dark" ? "dark" : "light"}|${localStorage.getItem("market-text-size") === "large" ? "large" : "normal"}`;
  } catch { storageUnavailable = true; return fallbackSettings; }
}

function subscribeSettings(notify: () => void) {
  window.addEventListener("storage", notify);
  window.addEventListener(SETTINGS_EVENT, notify);
  return () => {
    window.removeEventListener("storage", notify);
    window.removeEventListener(SETTINGS_EVENT, notify);
  };
}

function writeSettings(theme: Theme, textSize: TextSize) {
  fallbackSettings = `${theme}|${textSize}`;
  try {
    localStorage.setItem("market-theme", theme);
    localStorage.setItem("market-text-size", textSize);
  } catch { storageUnavailable = true; }
  window.dispatchEvent(new Event(SETTINGS_EVENT));
}

export function AppearanceControls() {
  const settings = useSyncExternalStore(subscribeSettings, readSettings, () => "light|normal");
  const [theme, textSize] = settings.split("|") as [Theme, TextSize];

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.textSize = textSize;
  }, [theme, textSize]);

  return (
    <div className="appearance-controls" role="group" aria-label="Pengaturan tampilan">
      <button type="button" className="appearance-button" onClick={() => writeSettings(theme === "dark" ? "light" : "dark", textSize)} aria-label={theme === "dark" ? "Gunakan tema terang" : "Gunakan tema gelap"}>
        {theme === "dark" ? "☀ Terang" : "◐ Gelap"}
      </button>
      <button type="button" className="appearance-button text-size-button" onClick={() => writeSettings(theme, textSize === "large" ? "normal" : "large")} aria-pressed={textSize === "large"}>
        A{ textSize === "large" ? "+" : "" } <span>{textSize === "large" ? "Teks besar" : "Ukuran teks"}</span>
      </button>
    </div>
  );
}

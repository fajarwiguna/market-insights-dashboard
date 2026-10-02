"use client";

import { useEffect, useState } from "react";

type Theme = "light" | "dark";
type TextSize = "normal" | "large";

export function AppearanceControls() {
  const [theme, setTheme] = useState<Theme>("light");
  const [textSize, setTextSize] = useState<TextSize>("normal");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const savedTheme = localStorage.getItem("market-theme");
    const savedSize = localStorage.getItem("market-text-size");
    if (savedTheme === "dark" || savedTheme === "light") setTheme(savedTheme);
    if (savedSize === "large" || savedSize === "normal") setTextSize(savedSize);
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.textSize = textSize;
    localStorage.setItem("market-theme", theme);
    localStorage.setItem("market-text-size", textSize);
  }, [ready, theme, textSize]);

  return (
    <div className="appearance-controls" aria-label="Pengaturan tampilan">
      <button type="button" className="appearance-button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label={theme === "dark" ? "Gunakan tema terang" : "Gunakan tema gelap"}>
        {theme === "dark" ? "☀ Terang" : "◐ Gelap"}
      </button>
      <button type="button" className="appearance-button text-size-button" onClick={() => setTextSize(textSize === "large" ? "normal" : "large")} aria-pressed={textSize === "large"}>
        A{ textSize === "large" ? "+" : "" } <span>{textSize === "large" ? "Teks besar" : "Ukuran teks"}</span>
      </button>
    </div>
  );
}

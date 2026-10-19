"use client";

import { useEffect, useState } from "react";

/**
 * Cek sesi operator dari server web. Dipakai panel/kontrol yang hanya boleh
 * muncul atau aktif untuk operator; token tetap server-side.
 */
export function useOperatorSession() {
  const [authenticated, setAuthenticated] = useState(false);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    void fetch("/api/operator-session", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) return;
        const state = await response.json() as { authenticated?: boolean };
        if (!controller.signal.aborted) setAuthenticated(Boolean(state.authenticated));
      })
      .catch(() => { /* panel tetap tampil tanpa kontrol operator */ })
      .finally(() => { if (!controller.signal.aborted) setChecked(true); });
    return () => controller.abort();
  }, []);

  return { authenticated, checked, setAuthenticated };
}

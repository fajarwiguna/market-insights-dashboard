"use client";

import { useRef, useState } from "react";
import { RefreshReportControl } from "@/components/refresh-report-control";

export function OperatorMenu() {
  const dialog = useRef<HTMLDialogElement>(null);
  const [sessionCheck, setSessionCheck] = useState(0);

  return <>
    <button type="button" className="appearance-button operator-menu-button" aria-haspopup="dialog" onClick={() => { dialog.current?.showModal(); setSessionCheck((value) => value + 1); }}>
      Pengelolaan
    </button>
    <dialog ref={dialog} className="operator-dialog" aria-labelledby="operator-dialog-heading">
      <div className="operator-dialog-header">
        <h2 id="operator-dialog-heading">Pengelolaan laporan</h2>
        <button type="button" className="appearance-button" onClick={() => dialog.current?.close()} aria-label="Tutup pengelolaan laporan">Tutup ×</button>
      </div>
      <RefreshReportControl key={sessionCheck} />
    </dialog>
  </>;
}

#!/usr/bin/env python3
"""
Daily Market Report Automation Pipeline
=======================================
Market Data → Calculate → Charts → PDF Report

Usage:
    python run_pipeline.py              # full pipeline (fetch + report)
    python run_pipeline.py --no-fetch   # use existing snapshot
    python run_pipeline.py --demo       # generate with sample numbers matching the image
"""

from __future__ import annotations
import argparse
import sys
from pathlib import Path
from datetime import datetime

# allow running from src/
sys.path.insert(0, str(Path(__file__).resolve().parent))

from charts import generate_rate_differential_chart, generate_fx_bar_chart, seri_dari_snapshot
from report_pdf import build_pdf
from services import report_service


def demo_report_data() -> dict:
    """Hard-coded numbers that match the screenshot (28 Agustus 2026)."""
    return {
        "report_date": "28 Agustus 2026",
        "report_date_iso": "2026-08-28",
        "fx": {
            "DXY": {"today": 99.21, "prev": 99.17, "change_pct": 0.04},
            "USD/IDR": {"today": 17744, "prev": 17725, "change_pct": 0.11},
            "CNY/IDR": {"today": 2.698, "prev": 2.696, "change_pct": 0.08},
            "SAR/IDR": {"today": 4.727, "prev": 4.724, "change_pct": 0.06},
            "EUR/IDR": {"today": 20679, "prev": 20690, "change_pct": -0.05},
            "JPY/IDR": {"today": 111.36, "prev": 111.47, "change_pct": -0.10},
        },
        "indices": {
            "IHSG (ID)": {"today": 6522, "prev": 6406, "change_pct": 1.81},
            "DJI (US)": {"today": 51569, "prev": 51464, "change_pct": 0.20},
        },
        "yields": {
            "US Treasury 5 Tahun": {"today": 4.38, "prev": 4.36, "change_bp": 2.0},
            "US Treasury 10 Tahun": {"today": 4.66, "prev": 4.65, "change_bp": 1.0},
            "ID SBN 5 Tahun": {"today": 6.84, "prev": 6.87, "change_bp": -3.0},
            "ID SBN 10 Tahun": {"today": 7.02, "prev": 6.99, "change_bp": 3.0},
            "ID SBSN 4 Tahun Benchmark (PBS040)": {"today": 6.83, "prev": 6.82, "change_bp": 1.0},
            "ID SBSN 13 Tahun Benchmark (PBS034)": {"today": 7.12, "prev": 7.10, "change_bp": 2.0},
        },
        "spread_sbn10_ust10_bp": 236,
        "bi": {
            "BI Rate": 5.75,
            "INDONIA": 6.16,
            "JISDOR": 17762,
        },
        "commodities": {},
        "source_snapshot": datetime.now().isoformat(),
        "schema_version": 1,
        "is_demo": True,
    }


def main():
    parser = argparse.ArgumentParser(description="Daily Market Report Pipeline")
    parser.add_argument("--no-fetch", action="store_true", help="Skip live data fetch")
    parser.add_argument("--demo", action="store_true", help="Use demo numbers from the sample image")
    args = parser.parse_args()

    print("=" * 60)
    print("  Daily Market Report Automation")
    print("=" * 60)

    if args.demo:
        print("\n[DEMO MODE] Using sample numbers matching the screenshot …")
        report = demo_report_data()
        demo_path = report_service.save_demo_report(report)
        print(f"Demo data saved separately -> {demo_path}")
    else:
        if args.no_fetch:
            print("\n[1/4] Skipping fetch (using existing snapshot)")
            report = report_service.rebuild_from_saved_snapshot()
        else:
            print("\n[1/4] Fetching market data …")
            report = report_service.run_live_pipeline()
        print("\n[2/4] Calculated and published validated report")

    print("\n[3/4] Generating charts …")
    # Grafik memakai data nyata dari snapshot laporan (bukan angka hard-coded)
    dates, sbn, ust = seri_dari_snapshot(report=report)
    chart = generate_rate_differential_chart(
        sbn, ust, dates, title="Rate Differential — SBN 10Y vs UST 10Y",
        catatan=f"Data per {report.get('report_date', '—')} · sumber: PHEI & Yahoo Finance. 1 bp = 0,01%.",
    )
    fx_chart = generate_fx_bar_chart(report.get("fx", {}))

    print("\n[4/4] Building PDF report …")
    pdf_path = build_pdf(report, chart, fx_chart_path=fx_chart)

    print("\n" + "=" * 60)
    print(f"  DONE  ->  {pdf_path}")
    print("=" * 60)

    # Quick console summary (like the example output)
    print("\nDaily Market Update —", report.get("report_date"))
    print("-" * 40)
    fx = report.get("fx", {})
    if "USD/IDR" in fx:
        v = fx["USD/IDR"]
        print(f"USD/IDR       {_fmt(v['today']):>8}    {_fmt_pct(v['change_pct'])}")
    if "DXY" in fx:
        v = fx["DXY"]
        print(f"DXY           {_fmt(v['today']):>8}    {_fmt_pct(v['change_pct'])}")
    yld = report.get("yields", {})
    for k in ["US Treasury 10 Tahun", "US Treasury 10Y", "ID SBN 10 Tahun", "ID SBN 10Y"]:
        if k in yld:
            v = yld[k]
            print(f"UST / SBN 10Y {_fmt(v.get('today')):>6}%   {_fmt_bp(v.get('change_bp'))}")
            break
    bi = report.get("bi", {})
    print(f"BI Rate       {_fmt(bi.get('BI Rate')):>6}%")
    print(f"INDONIA       {_fmt(bi.get('INDONIA')):>6}%")
    print(f"Spread        {report.get('spread_sbn10_ust10_bp')} bps")
    print()


def _fmt(v):
    if v is None:
        return "–"
    return f"{float(v):,.2f}"


def _fmt_pct(v):
    if v is None:
        return "–"
    return f"{v:+.2f}%"


def _fmt_bp(v):
    if v is None:
        return "–"
    return f"{v:+.1f} bp"


if __name__ == "__main__":
    main()

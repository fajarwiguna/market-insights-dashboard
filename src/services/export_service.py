"""Penyusunan berkas PDF dari data yang sedang ditampilkan dashboard."""

import io
import json
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt

from presentation.charts import make_fx_chart, make_rate_diff_chart
from report_pdf import build_pdf


def build_report_pdf(report_json: str, sbn_json: str) -> tuple[bytes, str]:
    """Bangun PDF di memori beserta grafik dari snapshot dan riwayat yang diberikan."""
    report = json.loads(report_json)
    sbn_history = json.loads(sbn_json)
    with tempfile.TemporaryDirectory() as temporary_directory:
        chart_path = Path(temporary_directory) / "rate_differential.png"
        chart = make_rate_diff_chart(report, sbn_hist=sbn_history)
        chart.savefig(chart_path, dpi=150, bbox_inches="tight")
        plt.close(chart)

        fx_chart_path = Path(temporary_directory) / "fx_change.png"
        fx_chart = make_fx_chart(report.get("fx") or {})
        fx_chart.savefig(fx_chart_path, dpi=150, bbox_inches="tight")
        plt.close(fx_chart)

        return build_pdf(
            report,
            chart_path=chart_path,
            fx_chart_path=fx_chart_path,
            stream=io.BytesIO(),
        )

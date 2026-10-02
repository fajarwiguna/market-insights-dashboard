"""Konfigurasi lokal aplikasi, termasuk pemuatan .env dari root project."""

from functools import lru_cache
import os
from pathlib import Path


@lru_cache(maxsize=1)
def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as error:
        raise RuntimeError("Pemuatan .env memerlukan python-dotenv dari requirements.txt.") from error
    load_dotenv(project_root() / ".env", override=False)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def runtime_directory() -> Path:
    return project_root() / "runtime"


def market_data_directory() -> Path:
    return runtime_directory() / "data"


def chart_directory() -> Path:
    return runtime_directory() / "charts"


def report_artifact_directory() -> Path:
    """Lokasi bersama untuk berkas PDF yang ditulis worker dan dibaca API."""
    load_environment()
    root = project_root()
    configured = os.environ.get("REPORT_ARTIFACT_DIR", "runtime/reports").strip() or "runtime/reports"
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else root / path).resolve()

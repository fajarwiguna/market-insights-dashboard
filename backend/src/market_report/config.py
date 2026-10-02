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
    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)


def report_artifact_directory() -> Path:
    """Lokasi bersama untuk berkas PDF yang ditulis worker dan dibaca API."""
    load_environment()
    project_root = Path(__file__).resolve().parents[3]
    configured = os.environ.get("REPORT_ARTIFACT_DIR", "reports").strip() or "reports"
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else project_root / path).resolve()

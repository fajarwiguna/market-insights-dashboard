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
    configured = os.environ.get("DAILY_MARKET_PROJECT_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    package_dir = Path(__file__).resolve().parent
    # Editable checkout and installed wheels have different directory layouts.
    if package_dir.parent.name == "src" and package_dir.parent.parent.name == "backend":
        return package_dir.parents[2]
    return Path.cwd().resolve()


def runtime_directory() -> Path:
    load_environment()
    configured = os.environ.get("DAILY_MARKET_RUNTIME_DIR", "").strip()
    if not configured:
        return project_root() / "runtime"
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else project_root() / path).resolve()


def market_data_directory() -> Path:
    return runtime_directory() / "data"


def chart_directory() -> Path:
    return runtime_directory() / "charts"


def report_artifact_directory() -> Path:
    """Lokasi bersama untuk berkas PDF yang ditulis worker dan dibaca API."""
    load_environment()
    root = project_root()
    configured = os.environ.get("REPORT_ARTIFACT_DIR", "").strip()
    if not configured:
        return runtime_directory() / "reports"
    path = Path(configured).expanduser()
    return (path if path.is_absolute() else root / path).resolve()

"""Konfigurasi lokal aplikasi, termasuk pemuatan .env dari root project."""

from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_environment() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError as error:
        raise RuntimeError("Pemuatan .env memerlukan python-dotenv dari requirements.txt.") from error
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv(project_root / ".env", override=False)

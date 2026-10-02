"""Memuat stylesheet dashboard dari aset frontend."""

from pathlib import Path

_STYLESHEET = Path(__file__).resolve().parent / "assets" / "styles.css"

def load_css() -> str:
    """Kembalikan CSS dashboard sebagai teks UTF-8."""
    return _STYLESHEET.read_text(encoding="utf-8")

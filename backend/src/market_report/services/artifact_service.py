"""Resolve existing artifacts within the shared storage directory."""

from pathlib import Path

from market_report.config import report_artifact_directory

PDF_TEMPLATE_VERSION = "1"


def pdf_artifact_path(artifact: dict | None, directory: Path | None = None) -> Path | None:
    if not artifact:
        return None
    key = artifact.get("storage_key")
    if not isinstance(key, str) or not key or Path(key).name != key:
        return None
    root = (directory if directory is not None else report_artifact_directory()).resolve()
    path = (root / key).resolve()
    return path if path.parent == root and path.is_file() else None


def pdf_artifact_is_current(artifact: dict | None, directory: Path | None = None) -> bool:
    key = artifact.get("storage_key") if isinstance(artifact, dict) else None
    return bool(
        isinstance(key, str)
        and f"_pdfv{PDF_TEMPLATE_VERSION}_" in key
        and pdf_artifact_path(artifact, directory) is not None
    )

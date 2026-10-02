"""Dependency keamanan untuk endpoint baca internal."""

import hmac
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import load_environment


bearer = HTTPBearer(auto_error=False)


def _require_token(credentials: HTTPAuthorizationCredentials | None, setting: str, label: str) -> None:
    load_environment()
    expected = os.environ.get(setting, "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail=f"{setting} belum dikonfigurasi.")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not hmac.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail=f"Token {label} tidak valid.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def require_read_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    _require_token(credentials, "API_READ_TOKEN", "baca")


def require_operator_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    _require_token(credentials, "API_OPERATOR_TOKEN", "operator")

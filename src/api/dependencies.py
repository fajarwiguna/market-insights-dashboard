"""Dependency keamanan untuk endpoint baca internal."""

import hmac
import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import load_environment


bearer = HTTPBearer(auto_error=False)


def require_read_access(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> None:
    load_environment()
    expected = os.environ.get("API_READ_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="API_READ_TOKEN belum dikonfigurasi.")
    if (
        credentials is None
        or credentials.scheme.lower() != "bearer"
        or not hmac.compare_digest(credentials.credentials, expected)
    ):
        raise HTTPException(
            status_code=401,
            detail="Token baca tidak valid.",
            headers={"WWW-Authenticate": "Bearer"},
        )

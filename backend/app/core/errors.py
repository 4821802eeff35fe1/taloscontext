"""Machine-readable API errors.

Every error response has the shape
    {"code": "CONTENT_NOT_FOUND", "detail": "<English message>", "details": {...}}
Clients localize by `code` (+ `details` parameters); `detail` stays as an
English fallback and for backward compatibility. Codes are part of the API
contract: add new ones, never rename existing ones.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException

# Fallback code when a raise site doesn't name one.
DEFAULT_CODE_BY_STATUS = {
    400: "BAD_REQUEST",
    401: "AUTH_REQUIRED",
    402: "BUDGET_EXCEEDED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    410: "GONE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(HTTPException):
    """HTTPException with a stable code and structured parameters."""

    def __init__(self, status_code: int, code: str, message: str, **details: Any):
        super().__init__(status_code=status_code, detail=message)
        self.code = code
        self.details = {k: v for k, v in details.items() if v is not None}


def error_body(status_code: int, message: Any, code: str | None = None, details: dict | None = None) -> dict:
    return {
        "code": code or DEFAULT_CODE_BY_STATUS.get(status_code, "ERROR"),
        "detail": message,
        "details": details or {},
    }

from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import error_body
from app.core.logging import configure_logging, get_logger
from app.core.rbac import PermissionDeniedError
from app.core.security import EncryptionKeyMissingError
from app.services.content.service import InvalidTransitionError
from app.services.costs.service import BudgetExceededError
from app.services.security.rate_limit import RateLimitExceeded
from app.services.system.health import readiness

configure_logging(json_logs=get_settings().is_production)
log = get_logger(__name__)

app = FastAPI(title="ChannelOS API", version="0.3.0")

settings = get_settings()

CSRF_HEADER = "x-channelos-client"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """Cookie-authenticated API: every state-changing request must carry a
    custom header. Cross-site forms can't set one, and CORS only lets our own
    frontend origin send it."""
    if request.method in _UNSAFE_METHODS and request.url.path.startswith("/api/") and CSRF_HEADER not in request.headers:
        return JSONResponse(status_code=403, content=error_body(403, "Missing X-ChannelOS-Client header.", "CSRF_HEADER_MISSING"))
    return await call_next(request)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id[:64])
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-ID"] = request_id[:64]
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response


# Added last so it wraps everything (incl. error responses from the guards above).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-ChannelOS-Client", "X-Request-ID"],
    expose_headers=["Retry-After", "X-Request-ID"],
)

app.include_router(api_router)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    body = error_body(exc.status_code, exc.detail, getattr(exc, "code", None), getattr(exc, "details", None))
    return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=error_body(422, jsonable_encoder(exc.errors()), "VALIDATION_ERROR"))


@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
    return JSONResponse(status_code=403, content=error_body(403, str(exc), "PERMISSION_DENIED"))


@app.exception_handler(InvalidTransitionError)
async def invalid_transition_handler(request: Request, exc: InvalidTransitionError):
    return JSONResponse(status_code=409, content=error_body(409, str(exc), "INVALID_TRANSITION"))


@app.exception_handler(BudgetExceededError)
async def budget_exceeded_handler(request: Request, exc: BudgetExceededError):
    details = {"kind": exc.kind, "spent": exc.spent, "limit": exc.limit}
    body = error_body(402, str(exc), "BUDGET_EXCEEDED", {k: v for k, v in details.items() if v is not None})
    body["kind"] = exc.kind  # v0.2 clients read the top-level field
    return JSONResponse(status_code=402, content=body)


@app.exception_handler(EncryptionKeyMissingError)
async def encryption_key_missing_handler(request: Request, exc: EncryptionKeyMissingError):
    return JSONResponse(status_code=503, content=error_body(503, str(exc), "ENCRYPTION_NOT_CONFIGURED"))


@app.exception_handler(RateLimitExceeded)
async def rate_limited_handler(request: Request, exc: RateLimitExceeded):
    code = "AUTH_RATE_LIMITED" if request.url.path.startswith("/api/v1/auth/") or "/telegram/auth/" in request.url.path else "RATE_LIMITED"
    body = error_body(429, str(exc), code, {"retry_after": exc.retry_after})
    body["retry_after"] = exc.retry_after
    return JSONResponse(status_code=429, content=body, headers={"Retry-After": str(exc.retry_after)})


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/health/ready")
async def health_ready():
    checks = await readiness()
    ready = checks["postgres"]["ok"] and checks["redis"]["ok"]
    return JSONResponse(status_code=200 if ready else 503, content={"ready": ready, "checks": checks})

from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.rbac import PermissionDeniedError
from app.core.security import EncryptionKeyMissingError
from app.services.content.service import InvalidTransitionError
from app.services.costs.service import BudgetExceededError
from app.services.security.rate_limit import RateLimitExceeded
from app.services.system.health import readiness

configure_logging(json_logs=get_settings().is_production)
log = get_logger(__name__)

app = FastAPI(title="ChannelOS API", version="0.2.0")

settings = get_settings()

CSRF_HEADER = "x-channelos-client"
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_guard(request: Request, call_next):
    """Cookie-authenticated API: every state-changing request must carry a
    custom header. Cross-site forms can't set one, and CORS only lets our own
    frontend origin send it."""
    if request.method in _UNSAFE_METHODS and request.url.path.startswith("/api/") and CSRF_HEADER not in request.headers:
        return JSONResponse(status_code=403, content={"detail": "Missing X-ChannelOS-Client header."})
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


@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(InvalidTransitionError)
async def invalid_transition_handler(request: Request, exc: InvalidTransitionError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(BudgetExceededError)
async def budget_exceeded_handler(request: Request, exc: BudgetExceededError):
    return JSONResponse(status_code=402, content={"detail": str(exc), "kind": exc.kind})


@app.exception_handler(EncryptionKeyMissingError)
async def encryption_key_missing_handler(request: Request, exc: EncryptionKeyMissingError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(RateLimitExceeded)
async def rate_limited_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429, content={"detail": str(exc), "retry_after": exc.retry_after},
        headers={"Retry-After": str(exc.retry_after)},
    )


@app.get("/health")
async def health():
    return {"status": "ok", "version": app.version}


@app.get("/health/ready")
async def health_ready():
    checks = await readiness()
    ready = checks["postgres"]["ok"] and checks["redis"]["ok"]
    return JSONResponse(status_code=200 if ready else 503, content={"ready": ready, "checks": checks})

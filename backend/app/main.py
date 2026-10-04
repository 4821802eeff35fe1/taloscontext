from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.core.rbac import PermissionDeniedError
from app.services.content.service import InvalidTransitionError
from app.services.costs.service import BudgetExceededError

configure_logging(json_logs=get_settings().is_production)
log = get_logger(__name__)

app = FastAPI(title="ChannelOS API", version="0.1.0")

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    structlog.contextvars.clear_contextvars()
    return response


@app.exception_handler(PermissionDeniedError)
async def permission_denied_handler(request: Request, exc: PermissionDeniedError):
    return JSONResponse(status_code=403, content={"detail": str(exc)})


@app.exception_handler(InvalidTransitionError)
async def invalid_transition_handler(request: Request, exc: InvalidTransitionError):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(BudgetExceededError)
async def budget_exceeded_handler(request: Request, exc: BudgetExceededError):
    return JSONResponse(status_code=402, content={"detail": str(exc), "kind": exc.kind})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready():
    checks = {"postgres": False, "redis": False}
    try:
        from sqlalchemy import text

        from app.db.session import engine

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception as exc:  # noqa: BLE001
        log.warning("readiness_check_failed", dependency="postgres", error=type(exc).__name__)

    try:
        from app.jobs.queue import get_arq_pool

        pool = await get_arq_pool()
        await pool.ping()
        checks["redis"] = True
    except Exception as exc:  # noqa: BLE001
        log.warning("readiness_check_failed", dependency="redis", error=type(exc).__name__)

    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503, content={"ready": ready, "checks": checks})


class ConnectionManager:
    def __init__(self):
        self.connections: dict[str, list[WebSocket]] = {}

    async def connect(self, workspace_id: str, ws: WebSocket):
        await ws.accept()
        self.connections.setdefault(workspace_id, []).append(ws)

    def disconnect(self, workspace_id: str, ws: WebSocket):
        if workspace_id in self.connections and ws in self.connections[workspace_id]:
            self.connections[workspace_id].remove(ws)

    async def broadcast(self, workspace_id: str, message: dict):
        for ws in self.connections.get(workspace_id, []):
            await ws.send_json(message)


manager = ConnectionManager()


@app.websocket("/ws/{workspace_id}")
async def websocket_endpoint(websocket: WebSocket, workspace_id: str):
    await manager.connect(workspace_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(workspace_id, websocket)

"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessLoader
from agent_runtime.adapters.model_client import FakeModelAdapter
from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.errors import register_error_handlers
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.routes import academic_records, gateway, planning, reports, sessions
from agent_runtime.api.session_store import SessionStore
from agent_runtime.api.settings import Settings
from agent_runtime.application.runner import PlanningRunner

_MODULE_ROOT = Path(__file__).resolve().parents[3]


def create_app(
    settings: Settings | None = None,
    *,
    tool_client: ToolClient | None = None,
    runner: PlanningRunner | None = None,
) -> FastAPI:
    settings = settings or Settings()
    harness = HarnessLoader(_resolve_harness_dir(settings)).load()
    if tool_client is None:
        if settings.java_base_url:
            tool_client = ToolClient(settings.java_base_url, settings.service_key)
        elif settings.use_fake_tools:
            tool_client = TypedFakeToolClient()
        else:
            tool_client = ToolClient(None, settings.service_key)

    app = FastAPI(title="CoursePilot planning API", version="1.0.0")
    app.state.settings = settings
    app.state.session_store = SessionStore(settings.session_ttl_seconds)
    app.state.idempotency = IdempotencyStore()
    app.state.harness = harness
    app.state.tool_client = tool_client
    app.state.runner = runner or PlanningRunner(
        tool_client=tool_client,
        harness=harness,
        model_adapter=FakeModelAdapter(),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Idempotency-Key",
            "X-Request-Id",
            "X-Admin-Key",
        ],
    )
    register_error_handlers(app)
    app.include_router(sessions.router)
    app.include_router(planning.router)
    app.include_router(academic_records.router)
    app.include_router(gateway.router)
    app.include_router(reports.router)
    return app


def _resolve_harness_dir(settings: Settings) -> Path:
    path = Path(settings.harness_dir)
    if path.is_absolute():
        return path
    return (_MODULE_ROOT / path).resolve()

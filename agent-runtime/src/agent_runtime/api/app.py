"""FastAPI application factory."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_runtime.adapters.fake_tools import TypedFakeToolClient
from agent_runtime.adapters.harness_loader import HarnessLoader
from agent_runtime.adapters.model_client import build_model_adapter
from agent_runtime.adapters.result_repository import FileResultRepository
from agent_runtime.adapters.tool_client import ToolClient
from agent_runtime.api.errors import register_error_handlers
from agent_runtime.api.idempotency import IdempotencyStore
from agent_runtime.api.rate_limit import FixedWindowRateLimiter, RateLimit
from agent_runtime.api.routes import (
    academic_records,
    gateway,
    plan_replacement,
    planning,
    reports,
    school_progress,
    sessions,
)
from agent_runtime.api.session_store import SessionStore
from agent_runtime.api.settings import Settings, load_settings
from agent_runtime.application.budget import Budget, SessionSpendCap, SessionSpendLedger
from agent_runtime.application.plan_store import SessionPlanStore
from agent_runtime.application.run_manifest import RunIdentity
from agent_runtime.application.runner import PlanningRunner

_MODULE_ROOT = Path(__file__).resolve().parents[3]


def create_app(
    settings: Settings | None = None,
    *,
    tool_client: ToolClient | None = None,
    runner: PlanningRunner | None = None,
    result_repository: FileResultRepository | None = None,
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
    app.state.session_store = SessionStore(settings.session_ttl_seconds, settings.max_live_sessions)
    app.state.session_rate_limiter = FixedWindowRateLimiter(
        RateLimit(
            max_events=settings.session_rate_limit_max,
            window_seconds=settings.session_rate_limit_window_seconds,
            max_tracked_keys=settings.max_tracked_sessions,
        )
    )
    app.state.plan_store = SessionPlanStore()
    app.state.idempotency = IdempotencyStore()
    app.state.harness = harness
    app.state.tool_client = tool_client
    verifier_version = (
        "verifier:fake" if isinstance(tool_client, TypedFakeToolClient) else "verifier:local-unset"
    )
    budget = Budget(
        max_input_tokens=settings.max_input_tokens,
        max_output_tokens=settings.max_output_tokens,
        max_tool_calls=settings.max_tool_calls,
        max_model_calls=settings.max_model_calls,
        deadline_ms=settings.deadline_ms,
    )
    # 跨请求的那一层上限：Budget 只管一次运行，换 Idempotency-Key 重提就归零。
    app.state.spend_ledger = SessionSpendLedger(
        SessionSpendCap(
            max_input_tokens=settings.session_max_input_tokens,
            max_output_tokens=settings.session_max_output_tokens,
            max_tracked_sessions=settings.max_tracked_sessions,
        )
    )
    app.state.runner = runner or PlanningRunner(
        tool_client=tool_client,
        harness=harness,
        model_adapter=build_model_adapter(
            model_base_url=settings.model_base_url,
            model_api_key=settings.model_api_key,
            model_id=settings.model_id,
            temperature=settings.temperature,
            # 预算是部署设置，不是 harness 文件：演化器改不到这里（settings.py 的注释）
            max_output_tokens=settings.max_output_tokens,
        ),
        result_repository=result_repository,
        run_identity=RunIdentity(verifier_version=verifier_version),
        budget=budget,
        plan_store=app.state.plan_store,
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
    app.include_router(plan_replacement.router)
    app.include_router(academic_records.router)
    app.include_router(school_progress.router)
    app.include_router(gateway.router)
    app.include_router(reports.router)
    return app


def _resolve_harness_dir(settings: Settings) -> Path:
    path = Path(settings.harness_dir)
    if path.is_absolute():
        return path
    return (_MODULE_ROOT / path).resolve()


app = create_app(
    settings=load_settings(),
    result_repository=FileResultRepository(_MODULE_ROOT / "runs"),
)

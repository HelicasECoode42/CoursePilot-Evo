"""Environment-driven configuration (docs/16 section 2)."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent_runtime.adapters.model_client import PLACEHOLDER_MODEL_ID

_MODULE_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CP_",
        extra="ignore",
    )

    # Java tool API (module B). Empty -> tools report TOOL_UNAVAILABLE (503).
    java_base_url: str | None = None
    service_key: str = ""

    # Admin key for the restricted teacher report (docs/04 section 1).
    admin_key: str = ""

    # Controlled model endpoint. Empty -> FakeModelAdapter (W2 typed fake).
    model_base_url: str | None = None
    model_api_key: str = ""
    model_id: str = PLACEHOLDER_MODEL_ID
    temperature: float = 0.0

    # Local W2 demo only. True -> TypedFakeToolClient. Never a real verifier.
    use_fake_tools: bool = False

    # Sessions and CORS.
    session_ttl_seconds: int = 1800
    # 建会话的配额与内存上限。POST /sessions 不要认证，不限流的话一个循环就能把
    # 会话表、幂等表、方案库撑爆。这些和 Budget 一样是部署设置，不在 harness 白名单里。
    session_rate_limit_max: int = Field(default=10, ge=1)
    session_rate_limit_window_seconds: int = Field(default=300, ge=1)
    max_live_sessions: int = Field(default=10000, ge=1)
    cors_origins: str = "http://127.0.0.1:5173"
    # 请求体上限（字节）。2 MiB 够最大的合法请求（学校进度 PUT，Java 侧也是 2 MiB）。
    # 超过返回 413，信封里的 code 仍是 INVALID_INPUT（与 Java 侧一致）。
    max_body_bytes: int = Field(default=2 * 1024 * 1024, ge=1)
    # 只有直连对端是回环地址（同机的 cloudflared / Vite 代理）时，才信任 CF-Connecting-IP
    # 作为建会话限流的分桶键。不信任 X-Forwarded-For。默认关闭：直接暴露时头部可以伪造。
    trust_cf_connecting_ip: bool = False

    # Harness whitelist directory (relative to the agent-runtime module root).
    harness_dir: str = "harness"

    # Run budget. Defaults are docs/04 section 3. These are deployment settings,
    # not harness files: the evolver must not be able to change the budget.
    max_input_tokens: int = Field(default=8000, ge=1)
    max_output_tokens: int = Field(default=4000, ge=1)
    max_tool_calls: int = Field(default=6, ge=1)
    max_model_calls: int = Field(default=3, ge=1)
    deadline_ms: int = Field(default=45000, ge=1)

    # 每会话累计上限（SessionSpendCap）。上面那组是「一次运行」的预算，运行结束即归零；
    # 这组限制一个会话总共能花多少，防止换 Idempotency-Key 反复提交把账单跑上去。
    session_max_input_tokens: int = Field(default=40000, ge=1)
    session_max_output_tokens: int = Field(default=10000, ge=1)
    max_tracked_sessions: int = Field(default=10000, ge=1)
    # 进程级每日上限（input 与 output 合计，UTC 日切换）。所有会话共用，挡住多开会话绕过
    # 每会话上限。默认 1000000，约等于 80 次满额单次运行（每次最多 8000 + 4000）。
    model_daily_token_cap: int = Field(default=1000000, ge=1)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def load_settings(env_file: Path | None = None) -> Settings:
    """Load ``agent-runtime/.env`` for local runs. Tests should call ``Settings()``."""
    env_path = env_file if env_file is not None else _MODULE_ROOT / ".env"
    if env_path.is_file():
        return Settings(_env_file=env_path)
    return Settings()

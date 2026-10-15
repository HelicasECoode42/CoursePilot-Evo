"""Environment-driven configuration (docs/16 section 2)."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

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
    model_id: str = "DEPLOYMENT_MODEL_PLACEHOLDER"
    temperature: float = 0.0

    # Local W2 demo only. True -> TypedFakeToolClient. Never a real verifier.
    use_fake_tools: bool = False

    # Sessions and CORS.
    session_ttl_seconds: int = 1800
    cors_origins: str = "http://127.0.0.1:5173"

    # Harness whitelist directory (relative to the agent-runtime module root).
    harness_dir: str = "harness"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def load_settings(env_file: Path | None = None) -> Settings:
    """Load ``agent-runtime/.env`` for local runs. Tests should call ``Settings()``."""
    env_path = env_file if env_file is not None else _MODULE_ROOT / ".env"
    if env_path.is_file():
        return Settings(_env_file=env_path)
    return Settings()

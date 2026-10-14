"""Environment-driven configuration (docs/16 section 2)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CP_", env_file=".env", extra="ignore")

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

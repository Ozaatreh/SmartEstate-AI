"""Application settings, read from the repository-level .env file and the environment.

AI-related values are kept as raw strings on purpose: a wrong AI setting must never stop the
application from starting (see app/ai/status.py). Everything else is validated strictly.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
PLACEHOLDER_MARKERS = ("<", "change-me", "changeme")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    app_name: str = "SmartEstate AI"
    app_version: str = "0.1.0"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: str
    test_database_url: str | None = None
    db_echo: bool = False

    secret_key: SecretStr
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "smartestate-api"
    jwt_audience: str = "smartestate-web"
    session_ttl_minutes: int = Field(default=480, ge=5, le=24 * 60)
    cookie_name: str = "se_session"
    cookie_secure: bool | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    login_max_failures: int = Field(default=5, ge=1)
    login_lock_minutes: int = Field(default=15, ge=1)
    login_ip_max_failures: int = Field(default=30, ge=1)
    login_ip_window_minutes: int = Field(default=15, ge=1)
    password_min_length: int = Field(default=12, ge=8)

    seed_admin_email: str = "admin@smartestate.demo"
    seed_demo_password: SecretStr | None = None

    # --- AI: lenient on purpose (validated by app.ai.status, never at startup) ---
    ai_enabled: str = "false"
    anthropic_api_key: SecretStr | None = None
    ai_default_model: str = ""

    @field_validator("cookie_secure", mode="before")
    @classmethod
    def _blank_is_auto(cls, v: object) -> object:
        return None if isinstance(v, str) and v.strip() == "" else v

    @model_validator(mode="after")
    def _production_guards(self) -> Settings:
        if self.app_env in ("staging", "production"):
            secret = self.secret_key.get_secret_value()
            if len(secret) < 32 or any(m in secret.lower() for m in PLACEHOLDER_MARKERS):
                raise ValueError("SECRET_KEY must be a real secret of at least 32 characters")
            if self.cookie_secure is False:
                raise ValueError("COOKIE_SECURE cannot be false outside development/test")
        return self

    @property
    def is_dev_like(self) -> bool:
        return self.app_env in ("development", "test")

    @property
    def secure_cookies(self) -> bool:
        return self.cookie_secure if self.cookie_secure is not None else not self.is_dev_like

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

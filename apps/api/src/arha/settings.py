"""Application settings, read from environment variables only."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    arha_env: Literal["dev", "test", "staging", "prod"] = "dev"
    arha_base_domain: str = "arha.localhost"
    arha_app_url: str = "http://localhost:5173"
    arha_forms_url: str = "http://localhost:5174"
    arha_api_url: str = "http://localhost:8000"
    arha_files_url: str = "http://localhost:8000/files"
    arha_site_url: str = "http://localhost:4321"
    arha_admin_emails: list[str] = Field(default_factory=list)

    database_url: str = "postgresql+asyncpg://arha_app:arha_app@localhost:5432/arha"
    database_platform_url: str = "postgresql+asyncpg://arha_platform:arha_platform@localhost:5432/arha"
    database_migration_url: str = "postgresql+asyncpg://arha_owner:arha_owner@localhost:5432/arha"
    valkey_url: str = "redis://localhost:6379/0"

    s3_endpoint: str | None = None
    s3_bucket: str = "arha-files"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    local_files_dir: Path = Path("/tmp/arha-files")

    # 32 bytes, base64. Required outside dev and test.
    master_key: SecretStr = SecretStr("ZGV2LW9ubHktbWFzdGVyLWtleS0zMi1ieXRlcy0wMDA=")
    # Ed25519 seed, 32 bytes, base64. Required outside dev and test.
    ticket_signing_key: SecretStr = SecretStr("ZGV2LW9ubHktdGlja2V0LXNpZ25pbmcta2V5LTMyYmI=")

    payment_provider_override: str | None = None  # "fake" in dev and test
    notchpay_public_key: SecretStr | None = None
    notchpay_private_key: SecretStr | None = None
    notchpay_webhook_secret: SecretStr | None = None
    notchpay_base_url: str = "https://api.notchpay.co"
    campay_username: SecretStr | None = None
    campay_password: SecretStr | None = None
    campay_base_url: str = "https://demo.campay.net/api"

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    mail_from: str = "Arha <no-reply@arha.localhost>"

    google_oauth_client_id: str | None = None
    google_oauth_client_secret: SecretStr | None = None
    turnstile_secret: SecretStr | None = None
    glitchtip_dsn: str | None = None
    pwned_passwords_check: bool = True

    config_dir: Path = REPO_ROOT / "config"
    session_idle_days: int = 14
    cookie_secure: bool = True

    @property
    def is_dev(self) -> bool:
        return self.arha_env in ("dev", "test")

    def validate_production(self) -> None:
        if self.is_dev:
            return
        defaults = Settings.model_fields
        for name in ("master_key", "ticket_signing_key"):
            if getattr(self, name).get_secret_value() == defaults[name].default.get_secret_value():
                raise RuntimeError(f"{name} must be set outside dev and test")
        if self.payment_provider_override == "fake" and self.arha_env == "prod":
            raise RuntimeError("fake payment provider is forbidden in production")


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.validate_production()
    return s

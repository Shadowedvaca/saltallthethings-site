"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvironmentName = Literal["local", "development", "test", "production"]
_PRODUCTION_HOSTS = {"saltallthethings.com", "www.saltallthethings.com"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://localhost/sattdb"
    secret_key: str = "dev-secret-key-change-in-production"
    environment: EnvironmentName = "local"
    database_environment: EnvironmentName = "local"
    site_url: str = "http://localhost:8200"
    cors_origins: str = "http://localhost:8200,http://127.0.0.1:8200"
    commit_sha: str = "unknown"
    ai_request_timeout: int = 60
    google_oauth_client_id: str = ""
    google_oauth_client_secret: str = ""
    google_oauth_refresh_token: str = ""
    allow_nonproduction_external_services: bool = False

    # sv-tools server-to-server export key
    sv_export_key: str = ""

    # JWT settings
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    @model_validator(mode="after")
    def validate_environment_isolation(self) -> "Settings":
        """Fail closed when an environment is paired with another tier's data."""
        if self.database_environment != self.environment:
            raise ValueError(
                "DATABASE_ENVIRONMENT must match ENVIRONMENT; refusing cross-environment data access"
            )

        if self.environment == "production":
            return self

        configured_origins = [self.site_url]
        configured_origins.extend(self.cors_origins.split(","))
        for origin in configured_origins:
            hostname = urlparse(origin.strip()).hostname
            if hostname in _PRODUCTION_HOSTS:
                raise ValueError(
                    "non-production SITE_URL/CORS_ORIGINS must not target production"
                )

        google_credentials_configured = any(
            (
                self.google_oauth_client_id,
                self.google_oauth_client_secret,
                self.google_oauth_refresh_token,
            )
        )
        if (
            google_credentials_configured
            and not self.allow_nonproduction_external_services
        ):
            raise ValueError(
                "non-production Google credentials require explicit external-service opt-in"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()

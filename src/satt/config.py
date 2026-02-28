"""Application settings loaded from environment variables / .env file."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://localhost/sattdb"
    secret_key: str = "dev-secret-key-change-in-production"
    environment: str = "development"
    ai_request_timeout: int = 60

    # JWT settings
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480  # 8 hours

    # X-Auth bridge (Phase 2 only — removed in Phase 4)
    admin_password_hash: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()

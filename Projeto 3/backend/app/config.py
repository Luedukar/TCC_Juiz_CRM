from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://crm:crm@localhost:5432/crm"

    # Sem default de propósito: a aplicação não sobe sem um segredo explícito.
    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    # Janela em que reapresentar um refresh token recém-rotacionado é tratado como corrida (duas abas), não como roubo.
    refresh_reuse_grace_seconds: int = 10

    max_failed_logins: int = 5
    lockout_minutes: int = 15
    login_rate_limit_attempts: int = 5
    login_rate_limit_window_seconds: int = 60
    refresh_rate_limit_attempts: int = 30
    refresh_rate_limit_window_seconds: int = 60
    # Só habilite atrás de um proxy confiável que sobrescreva X-Forwarded-For.
    trust_proxy_headers: bool = False

    cors_origins: list[str] = ["http://localhost:5173"]
    environment: str = "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()

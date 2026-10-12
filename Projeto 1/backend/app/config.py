from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://crm:change-me@localhost:5432/crm"
    jwt_secret_key: str = "development-only-change-this-secret"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 15
    refresh_token_days: int = 14
    login_rate_limit: str = "5/minute"
    rate_limit_storage_uri: str = "memory://"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    environment: str = "development"
    bootstrap_email: str | None = None
    bootstrap_password: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

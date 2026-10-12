from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    database_url: str = "postgresql://crm:crm@localhost:5432/crm"
    jwt_secret: str = ""
    access_token_minutes: int = 15
    refresh_token_days: int = 30
    login_rate_limit: str = "5/minute"
    cors_origins: str = "http://localhost:5173"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
if len(settings.jwt_secret) < 32:
    raise RuntimeError("JWT_SECRET precisa ter pelo menos 32 caracteres; configure o ambiente antes de iniciar.")

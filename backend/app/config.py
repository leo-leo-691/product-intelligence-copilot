from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
STORAGE_DIR = ROOT / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = STORAGE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = STORAGE_DIR / "copilot.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    tavily_api_key: str | None = None
    serpapi_api_key: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    log_level: str = "INFO"
    max_upload_mb: int = 25
    app_env: str = "development"


settings = Settings()

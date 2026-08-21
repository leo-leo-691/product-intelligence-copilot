from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
STORAGE_DIR = ROOT / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR = STORAGE_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RASTER_DIR = STORAGE_DIR / "rasters"
RASTER_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = STORAGE_DIR / "copilot.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM provider: gemini (default) | anthropic
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.1-flash-lite"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"
    dual_llm_enabled: bool = False
    tavily_api_key: str | None = None
    serpapi_api_key: str | None = None

    # Deploy: set API_KEY to require X-API-Key on /api/* (health stays public)
    api_key: str | None = None
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://localhost:5174"
    log_level: str = "INFO"
    max_upload_mb: int = 25
    app_env: str = "development"

    # Pipeline knobs
    pdf_raster_max_pages: int = 3
    pdf_sparse_char_threshold: int = 120
    gap_fill_max_calls: int = 2
    crawl_max_pages: int = 3
    crawl_enabled: bool = True
    outlier_z_threshold: float = 2.5
    translate_enabled: bool = True
    kg_enabled: bool = True

    def cors_origin_list(self) -> list[str]:
        """Parsed CORS origins (trailing slashes stripped)."""
        origins = [o.strip().rstrip("/") for o in self.cors_origins.split(",") if o.strip()]
        return origins or ["*"]


settings = Settings()

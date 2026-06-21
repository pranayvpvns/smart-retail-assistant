from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# ─────────────────────────────────────────────
# Project Root Path
# ─────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# ─────────────────────────────────────────────
# Application Settings
# ─────────────────────────────────────────────

class Settings(BaseSettings):

    # ── MongoDB ─────────────────────────────
    mongodb_uri: str

    mongodb_db_name: str = "smart_retail"

    # ── Flask ───────────────────────────────
    flask_env: str = "development"

    flask_debug: bool = True

    secret_key: str

    # ── JWT Authentication ──────────────────
    jwt_secret: str

    jwt_expire_minutes: int = 90

    # ── Azure OpenAI ────────────────────────
    azure_openai_api_key: str = ""

    azure_openai_endpoint: str = ""

    azure_openai_deployment: str = "gpt-4o"

    azure_openai_embedding_deployment: str = "text-embedding-3-large"

    azure_openai_api_version: str = "2024-12-01-preview"

    # ── Azure Blob Storage ──────────────────
    azure_storage_connection_string: str = ""

    azure_storage_container_raw: str = "raw"

    azure_storage_container_staged: str = "staged"

    azure_storage_container_curated: str = "curated"

    # ── Vector Database ─────────────────────
    vector_db_path: str = "./vector_store"

    # ── Frontend / CORS ─────────────────────
    frontend_url: str = "http://localhost:3000"

    # ── Pydantic Settings Config ────────────
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


# ─────────────────────────────────────────────
# Cached Settings Instance
# ─────────────────────────────────────────────

@lru_cache()
def get_settings() -> Settings:

    return Settings()
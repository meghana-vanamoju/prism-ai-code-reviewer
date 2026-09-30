from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


def env_files() -> tuple[Path, ...]:
    """Environment files to load, ordered from lowest to highest precedence.

    The project keeps its ``.env`` at the repository root, so it is resolved
    from this file's location instead of the process working directory. That
    keeps the backend working whether uvicorn is started from the repository
    root or from ``backend/``. An optional ``backend/.env`` is loaded last so a
    developer can override a single value locally without editing the shared
    file.
    """
    return (REPO_ROOT / ".env", BACKEND_DIR / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hindsight_base_url: str = "http://localhost:8888"
    hindsight_bank_id: str = "prism-demo-team"
    hindsight_retain_extraction_mode: str = "chunks"

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    # Groq free tier enforces an org-wide tokens-per-minute budget; the client
    # paces requests so multi-file reviews don't burn the budget on 429s.
    groq_tpm_limit: int = 8000

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    review_max_files: int = 40
    review_max_file_bytes: int = 200_000
    review_max_total_bytes: int = 2_000_000
    review_concurrency: int = 3
    review_max_memories: int = 5
    git_clone_timeout: int = 90
    job_ttl_seconds: int = 3600

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
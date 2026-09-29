from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    hindsight_base_url: str = "http://localhost:8888"
    hindsight_bank_id: str = "prism-demo-team"

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"

    api_host: str = "0.0.0.0"
    api_port: int = 8000

    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
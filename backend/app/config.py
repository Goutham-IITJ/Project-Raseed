from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://raseed:raseed_local@localhost:5432/raseed"
    firebase_project_id: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        if make_url(value).drivername != "postgresql+psycopg":
            raise ValueError("V2 requires PostgreSQL with the psycopg driver")
        return value

    @field_validator("cors_origins")
    @classmethod
    def explicit_origins(cls, value: list[str]) -> list[str]:
        if any(origin == "*" or not origin.startswith(("http://", "https://")) for origin in value):
            raise ValueError("CORS origins must be explicit HTTP(S) origins")
        return value

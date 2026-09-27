from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = "postgresql+psycopg://raseed:raseed_local@localhost:5432/raseed"
    firebase_project_id: str = ""
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    storage_provider: Literal["local", "gcs"] = "local"
    local_storage_path: Path = ROOT / ".local" / "receipts"
    gcs_bucket: str = ""
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=20 * 1024 * 1024)
    max_pdf_pages: int = Field(default=20, ge=1, le=100)
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    extraction_timeout_seconds: float = Field(default=45, gt=0, le=120)
    receipt_lease_seconds: int = Field(default=300, ge=300, le=3600)
    receipt_max_attempts: int = Field(default=3, ge=1, le=10)
    receipt_retry_seconds: int = Field(default=5, ge=1, le=300)
    worker_poll_seconds: float = Field(default=2, gt=0, le=60)
    openai_api_key: SecretStr = SecretStr("")
    assistant_model: str = Field(default="", max_length=100)
    assistant_request_timeout_seconds: float = Field(default=20, gt=0, le=60)
    assistant_turn_timeout_seconds: float = Field(default=120, gt=0, le=180)
    assistant_max_rounds: int = Field(default=6, ge=1, le=10)
    assistant_max_tool_calls: int = Field(default=8, ge=1, le=8)
    assistant_max_attempts: int = Field(default=2, ge=1, le=3)
    assistant_max_output_tokens: int = Field(default=4096, ge=256, le=16384)
    wallet_issuer_id: str = Field(default="", pattern=r"^(?:[0-9]{1,40})?$")
    wallet_service_account_email: str = Field(
        default="", pattern=r"^(?:[a-zA-Z0-9._-]+@[a-zA-Z0-9.-]+\.iam\.gserviceaccount\.com)?$"
    )
    wallet_origins: list[str] = Field(default_factory=list)
    wallet_request_timeout_seconds: float = Field(default=15, gt=0, le=30)

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

    @field_validator("wallet_origins")
    @classmethod
    def wallet_web_origins(cls, value: list[str]) -> list[str]:
        from urllib.parse import urlsplit

        for origin in value:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
            ):
                raise ValueError("Wallet origins must be explicit HTTP(S) origins without paths")
        return value

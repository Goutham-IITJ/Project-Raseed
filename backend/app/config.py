import os
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


def configured(value: str) -> bool:
    """Empty example values are configuration gaps, not usable credentials."""
    return bool(value.strip()) and not value.strip().lower().startswith(
        ("your-", "replace-me", "example-project")
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["development", "test", "production"] = "production"
    local_demo: bool = False

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
    market_ebay_token: SecretStr = SecretStr("")
    market_ebay_marketplace: Literal["EBAY_US", "EBAY_GB", "EBAY_DE", "EBAY_AU"] = "EBAY_US"
    market_request_timeout_seconds: float = Field(default=10, gt=0, le=20)

    @model_validator(mode="after")
    def demo_is_local_only(self) -> "Settings":
        if self.app_env == "production":
            for origin in [*self.cors_origins, *self.wallet_origins]:
                parsed = urlsplit(origin)
                if parsed.scheme != "https" and parsed.hostname not in {
                    "localhost",
                    "127.0.0.1",
                    "::1",
                }:
                    raise ValueError("Production remote web origins require HTTPS")
        if self.local_demo:
            database = make_url(self.database_url)
            if (
                self.app_env != "development"
                or any(
                    os.getenv(key)
                    for key in ("K_SERVICE", "GAE_ENV", "VERCEL", "WEBSITE_INSTANCE_ID")
                )
                or database.host not in {"localhost", "127.0.0.1", "::1"}
                or not (database.database or "").endswith("_demo")
                or self.storage_provider != "local"
            ):
                raise ValueError(
                    "Local demo requires development, loopback PostgreSQL *_demo and local storage"
                )
            for origin in self.cors_origins:
                parsed = urlsplit(origin)
                if (
                    parsed.scheme != "http"
                    or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
                    or parsed.username
                    or parsed.password
                    or parsed.path
                    or parsed.query
                    or parsed.fragment
                ):
                    raise ValueError(
                        "Local demo CORS origins must be explicit loopback HTTP origins"
                    )
        return self

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: str) -> str:
        if make_url(value).drivername != "postgresql+psycopg":
            raise ValueError("V2 requires PostgreSQL with the psycopg driver")
        return value

    @field_validator("cors_origins", "wallet_origins")
    @classmethod
    def explicit_origins(cls, value: list[str]) -> list[str]:
        for origin in value:
            parsed = urlsplit(origin)
            # Accessing port also validates malformed/out-of-range ports.
            port = parsed.port
            if (
                parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
                or "*" in origin
                or "?" in origin
                or "#" in origin
                or "\\" in origin
                or any(char.isspace() or ord(char) < 32 for char in origin)
                or port == 0
                or parsed.netloc.endswith(":")
            ):
                raise ValueError("Web origins must be explicit HTTP(S) origins without paths")
        return value

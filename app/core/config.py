from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "extra": "ignore"}

    # Default to local Postgres. For dev, use backend/docker-compose.yml.
    database_url: str = (
        "postgresql+psycopg2://postgres:postgres@localhost:5432/document_hub"
    )
    secret_key: str = "your-secret-key-here"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Local file storage (dev default). In production prefer S3.
    storage_dir: str = "./storage"

    # AWS S3
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_default_region: str = "us-east-1"
    s3_bucket_name: str = "document-hub-files"

    # Redis
    redis_url: str = "redis://localhost:6379"

    # OCR
    ocr_engine: str = "easyocr"
    ocr_confidence_threshold: float = 0.7

    # External OCR (custom service)
    ocr_external_url: str = ""  # e.g. http://localhost:9000/ocr/trigger
    ocr_external_api_key: str = ""
    ocr_external_webhook_secret: str = (
        ""  # shared secret for webhook verification (optional)
    )

    # If external OCR needs to fetch the file from our API, this must be reachable.
    # Example: https://api.example.com
    public_base_url: str = ""

    # Development
    debug: bool = True
    # NOTE: keep this as string to avoid JSON decoding issues in pydantic-settings.
    # Set env as comma-separated string:
    #   CORS_ORIGINS=http://localhost:8080,http://localhost:3000
    cors_origins: str = "http://localhost:8080,http://localhost:3000"

    def cors_origins_list(self) -> list[str]:
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _normalize_cors_origins(cls, v: Any):
        if v is None:
            return ""
        if isinstance(v, list):
            return ",".join(str(x).strip() for x in v if str(x).strip())
        return str(v)


settings = Settings()

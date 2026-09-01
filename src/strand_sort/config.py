import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    bedrock_vision_model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_agent_model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    aws_profile: str
    aws_region: str = "us-east-1"

    gcp_project_id: str
    gcp_location: str = "us-central1"
    gemini_api_key: str = ""
    gemini_model_id: str = "gemini-3.5-flash"
    model_pro: str = "gemini-2.5-pro"

    vision_provider: Literal["bedrock", "gemini", "auto"] = "auto"

    # Database selection switch: "sqlite" or "dynamodb"
    db_engine: Literal["sqlite", "dynamodb"] = "sqlite"
    
    # Engine-specific configs
    sqlite_db_path: str = "data/inventory.db"
    dynamodb_table_name: str = "foodbank_inventory"

    # Deployed frontend origin (for CORS)
    frontend_origin: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()

# Auto-detect Cloud Run environment if storage_backend not explicitly overridden
if not os.environ.get("STORAGE_BACKEND") and os.environ.get("K_SERVICE"):
    settings.storage_backend = "gcs"

BEDROCK_FALLBACK_ERROR_CODES: tuple[str, ...] = (
    "AccessDeniedException",
    "ModelNotAllowedException",
    "UnauthorizedOperation",
    "ResourceNotFoundException",
    "ValidationException",
    "ThrottlingException",
)
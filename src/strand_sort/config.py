import os
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    aws_region: str = "us-east-1"
    bedrock_vision_model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    bedrock_agent_model_id: str = "anthropic.claude-sonnet-4-5-20250929-v1:0"
    # Not read by any boto3 call (every client/resource construction in this
    # codebase already omits profile_name and relies on default credential
    # resolution) — this only exists so AWS_PROFILE can be set locally for
    # the strand-sort-agent IAM user without boto3's default chain having to
    # be told explicitly. Must default to "" rather than being required: on
    # Lambda there's no named profile, credentials come from the execution
    # role, and AWS_PROFILE is never set — a required field with no default
    # would crash Settings() at cold start.
    aws_profile: str = ""
    aws_region: str = "us-east-1"

    gcp_project_id: str
    gcp_location: str = "us-central1"
    gemini_location: str
    gemini_api_key: str = ""
    gemini_model_id: str = "gemini-3.5-flash"
    model_pro: str = "gemini-2.5-pro"

    vision_provider: Literal["bedrock", "gemini", "auto"] = "auto"

    # Database selection switch: "sqlite" or "dynamodb"
    db_engine: Literal["sqlite", "dynamodb"] = "sqlite"
    
    # Engine-specific configs
    sqlite_db_path: str = "data/inventory.db"
    dynamodb_table_name: str = "foodbank_inventory"

    storage_backend: Literal["local", "s3"] = "local"
    image_storage_local_path: str = "data/raw"
    s3_bucket_name: str = ""

    # Secrets Manager secret holding the raw GCP service account JSON key,
    # used to authenticate Gemini/Vertex on Lambda (no ADC credentials file
    # there). Only read when running on Lambda — see vision/extract.py.
    gcp_secrets_manager_secret_id: str = "strand-sort/gcp-service-account"

    # Deployed frontend origin (for CORS)
    frontend_origin: str = "https://strand-sort.vercel.app"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


settings = Settings()

BEDROCK_FALLBACK_ERROR_CODES: tuple[str, ...] = (
    "AccessDeniedException",
    "ModelNotAllowedException",
    "UnauthorizedOperation",
    "ResourceNotFoundException",
    "ValidationException",
    "ThrottlingException",
)
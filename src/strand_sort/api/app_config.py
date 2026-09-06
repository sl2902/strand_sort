from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from strand_sort.config import settings

router = APIRouter()


class AppConfigResponse(BaseModel):
    upload_mode: Literal["local", "presigned"]


@router.get("/config")
def get_app_config() -> AppConfigResponse:
    """Single source of truth for which intake upload mode the frontend
    should use — derived directly from settings.storage_backend, rather
    than duplicated into a separate frontend env var (two independent
    sources of truth that can silently drift apart, exactly the kind of
    mismatch that caused the earlier /api/v1 path bug)."""
    upload_mode: Literal["local", "presigned"] = "presigned" if settings.storage_backend == "s3" else "local"
    return AppConfigResponse(upload_mode=upload_mode)

from pathlib import Path
from typing import List, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from strand_sort.storage.pending_uploads import presign_put_url

router = APIRouter()

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}


class PresignRequest(BaseModel):
    filenames: list[str]  # original filenames, used only to derive extension
    kind: Literal["image", "video"] = "image"


class PresignedUpload(BaseModel):
    s3_key: str
    upload_url: str


def _validate_extension(filename: str, allowed: set[str]) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext or '(none)'}")
    return ext


@router.post("/uploads/presign")
def presign_uploads(body: PresignRequest) -> List[PresignedUpload]:
    """Returns one presigned S3 PUT URL per requested filename. The browser
    uploads directly to S3 with these — bypassing this API (and Lambda's 6MB
    payload limit) for the actual file bytes entirely.

    Extension allowlist is a weaker guarantee than real content-type
    sniffing (a renamed file could still slip through), but closes the
    "any file at all" gap the old multipart endpoints' content_type check
    used to close — this is the presigned-upload equivalent."""
    allowed = ALLOWED_VIDEO_EXTENSIONS if body.kind == "video" else ALLOWED_IMAGE_EXTENSIONS

    # Validate the whole batch before presigning any of it — one bad
    # filename shouldn't leave the client holding presigned URLs for the
    # other, valid ones in the same request.
    for filename in body.filenames:
        _validate_extension(filename, allowed)

    results = []
    for filename in body.filenames:
        s3_key, upload_url = presign_put_url(filename)
        results.append(PresignedUpload(s3_key=s3_key, upload_url=upload_url))
    return results

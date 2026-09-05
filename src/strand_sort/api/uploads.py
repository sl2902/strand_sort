from typing import List

from fastapi import APIRouter
from pydantic import BaseModel

from strand_sort.storage.pending_uploads import presign_put_url

router = APIRouter()


class PresignRequest(BaseModel):
    filenames: list[str]  # original filenames, used only to derive extension


class PresignedUpload(BaseModel):
    s3_key: str
    upload_url: str


@router.post("/uploads/presign")
def presign_uploads(body: PresignRequest) -> List[PresignedUpload]:
    """Returns one presigned S3 PUT URL per requested filename. The browser
    uploads directly to S3 with these — bypassing this API (and Lambda's 6MB
    payload limit) for the actual file bytes entirely."""
    results = []
    for filename in body.filenames:
        s3_key, upload_url = presign_put_url(filename)
        results.append(PresignedUpload(s3_key=s3_key, upload_url=upload_url))
    return results

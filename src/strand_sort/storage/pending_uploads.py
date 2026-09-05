"""Staging area for browser-to-S3 direct uploads (presigned PUT flow).

Bypasses Lambda's 6MB synchronous payload limit: the browser uploads image/
video bytes straight to S3 under the `pending-uploads/` prefix, and only a
small JSON list of resulting keys ever passes through the API. Always S3,
regardless of `settings.storage_backend` — presigned PUT URLs have no
local-disk equivalent, so this module doesn't go through the ImageStorage
abstraction (that governs where an item's *final*, committed images live,
which is a separate concern from this staging step).

Objects left here when an upload is never processed (user navigates away
mid-scan) aren't cleaned up by this module — that's a follow-up S3
lifecycle rule on the `pending-uploads/` prefix, not handled in code.
"""

import uuid
from pathlib import Path

import boto3

from strand_sort.config import settings

PENDING_UPLOADS_PREFIX = "pending-uploads"


def _client():
    return boto3.client("s3", region_name=settings.aws_region)


def presign_put_url(filename: str, expires_in: int = 300) -> tuple[str, str]:
    """Returns (s3_key, upload_url) for a new pending-upload object. The
    5-minute default is plenty for a direct browser upload while staying
    short-lived."""
    ext = Path(filename).suffix or ".jpg"
    key = f"{PENDING_UPLOADS_PREFIX}/{uuid.uuid4()}{ext}"
    url = _client().generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.s3_bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )
    return key, url


def get_bytes(s3_key: str) -> bytes:
    obj = _client().get_object(Bucket=settings.s3_bucket_name, Key=s3_key)
    return obj["Body"].read()


def download_to_file(s3_key: str, dest_path: str) -> None:
    _client().download_file(settings.s3_bucket_name, s3_key, dest_path)


def put_bytes(data: bytes, ext: str = ".jpg", content_type: str = "image/jpeg") -> str:
    """Uploads raw bytes as a new pending-upload object (e.g. a video frame
    sampled server-side), returns its key."""
    key = f"{PENDING_UPLOADS_PREFIX}/{uuid.uuid4()}{ext}"
    _client().put_object(Bucket=settings.s3_bucket_name, Key=key, Body=data, ContentType=content_type)
    return key

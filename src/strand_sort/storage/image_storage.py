import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import boto3
from strand_sort.config import settings


class ImageStorage(ABC):
    @abstractmethod
    def save_images(self, item_id: str, source_paths: list[str]) -> list[str]:
        """Persists images for an item. Returns durable references — final,
        servable URLs for local storage; object keys for S3 (see resolve_urls)"""
        pass

    @abstractmethod
    def resolve_urls(self, refs: list[str]) -> list[str]:
        """Turns stored references into URLs that are valid right now. Must be
        called fresh on every read: for S3 this regenerates a presigned URL
        rather than reusing one that may have expired. Never persist the
        result of this call — only the reference passed into it"""
        pass


class LocalImageStorage(ImageStorage):
    def __init__(self, base_path: str | None = None):
        # Read settings lazily rather than as a default-arg (evaluated once at
        # import time) so tests can override settings.image_storage_local_path.
        self.base_path = Path(base_path or settings.image_storage_local_path)

    def save_images(self, item_id: str, source_paths: list[str]) -> list[str]:
        item_dir = self.base_path / item_id
        item_dir.mkdir(parents=True, exist_ok=True)

        saved_urls = []
        for i, src in enumerate(source_paths):
            ext = Path(src).suffix or ".jpg"
            dest = item_dir / f"{i}{ext}"
            shutil.copy(src, dest)
            # Served via StaticFiles mount at /images — see main.py
            saved_urls.append(f"/images/{item_id}/{dest.name}")
        return saved_urls

    def resolve_urls(self, refs: list[str]) -> list[str]:
        # Local URLs are already final and don't expire — nothing to refresh.
        return list(refs)


class S3ImageStorage(ImageStorage):
    def __init__(
        self,
        bucket_name: str | None = None,
        region: str | None = None,
        url_expiry_seconds: int = 3600,
    ):
        self.bucket_name = bucket_name or settings.s3_bucket_name
        self.url_expiry_seconds = url_expiry_seconds
        self.s3 = boto3.client("s3", region_name=region or settings.aws_region)

    def save_images(self, item_id: str, source_paths: list[str]) -> list[str]:
        """Uploads each image and returns durable object keys — NOT presigned
        URLs, which expire and must never be what's stored in the database."""
        keys = []
        for i, src in enumerate(source_paths):
            ext = Path(src).suffix or ".jpg"
            key = f"{item_id}/{i}{ext}"
            self.s3.upload_file(src, self.bucket_name, key)
            keys.append(key)
        return keys

    def resolve_urls(self, refs: list[str]) -> list[str]:
        return [
            self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=self.url_expiry_seconds,
            )
            for key in refs
        ]


def get_image_storage() -> ImageStorage:
    if settings.storage_backend == "s3":
        return S3ImageStorage()
    return LocalImageStorage()


def resolve_image_urls(refs: list[str]) -> list[str]:
    """Converts an item's stored image references into URLs valid right now.
    Call this on every read path (list/detail/review) — never cache the result"""
    if not refs:
        return []
    return get_image_storage().resolve_urls(refs)

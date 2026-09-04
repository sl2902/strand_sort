import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import boto3
from strand_sort.config import settings

# image_storage.py -> storage/ -> strand_sort/ -> src/ -> repo root. Anchored
# to where this file lives on disk, not the process's cwd — a plain relative
# path (e.g. "data/raw") would resolve differently depending on what
# directory uvicorn happens to be launched from, silently orphaning every
# image saved under a previous cwd once the server is restarted from a
# different one.
_PACKAGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def resolve_local_storage_path(configured_path: str | None = None) -> Path:
    """Resolves the local image storage directory to an absolute path that's
    stable regardless of the current working directory. Used for both the
    save path (here) and the StaticFiles serve mount (main.py) so they can
    never diverge."""
    raw = configured_path or settings.image_storage_local_path
    path = Path(raw)
    return path if path.is_absolute() else (_PACKAGE_ROOT / path)


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
        self.base_path = resolve_local_storage_path(base_path)

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


def check_local_image_integrity(local_root: Path, items: list[dict]) -> list[str]:
    """Checks that every locally-stored image reference in `items` still
    points at a file that actually exists under `local_root`. Meant to be
    called on every app startup/reload — exactly the moment a relative
    storage path resolving against a different cwd would silently orphan
    previously-saved images. Returns the list of missing "item_id: url"
    references (empty if everything's fine)."""
    missing: list[str] = []
    for item in items:
        for url in item.get("image_urls") or []:
            if not url.startswith("/images/"):
                continue  # not a local reference (e.g. an S3 key from a different backend)
            rel_path = url[len("/images/"):]
            if not (local_root / rel_path).exists():
                missing.append(f"{item.get('item_id')}: {url}")
    return missing


def resolve_image_urls(refs: list[str]) -> list[str]:
    """Converts an item's stored image references into URLs valid right now.
    Call this on every read path (list/detail/review) — never cache the result"""
    if not refs:
        return []
    return get_image_storage().resolve_urls(refs)

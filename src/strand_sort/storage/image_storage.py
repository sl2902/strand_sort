import shutil
from abc import ABC, abstractmethod
from pathlib import Path
from typing import NamedTuple

import boto3
from loguru import logger
from strand_sort.config import settings
from strand_sort.storage.pending_uploads import get_bytes as get_pending_upload_bytes
from strand_sort.vision.thumbnail import generate_thumbnail

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


class SavedImages(NamedTuple):
    """Originals and thumbnails are always saved together, one thumbnail per
    original, same order — callers can zip them by index."""

    image_urls: list[str]
    thumbnail_urls: list[str]


def _thumbnail_bytes_or_original(image_bytes: bytes) -> bytes:
    """Generating a thumbnail is a nice-to-have on top of saving the
    original, not something the whole scan should fail over — an unusual
    image format/corrupt bytes falls back to reusing the original bytes for
    that slot (no size savings for that one image, but image_urls and
    thumbnail_urls stay the same length and aligned by index)."""
    try:
        return generate_thumbnail(image_bytes)
    except Exception as e:
        logger.warning(f"Thumbnail generation failed, using original image instead: {e}")
        return image_bytes


class ImageStorage(ABC):
    @abstractmethod
    def save_images(self, item_id: str, source_paths: list[str]) -> SavedImages:
        """Persists images (and a thumbnail per image) for an item. Returns
        durable references — final, servable URLs for local storage; object
        keys for S3 (see resolve_urls)"""
        pass

    @abstractmethod
    def resolve_urls(self, refs: list[str]) -> list[str]:
        """Turns stored references into URLs that are valid right now. Must be
        called fresh on every read: for S3 this regenerates a presigned URL
        rather than reusing one that may have expired. Never persist the
        result of this call — only the reference passed into it"""
        pass

    @abstractmethod
    def save_images_from_s3(self, item_id: str, pending_keys: list[str]) -> SavedImages:
        """Same contract as save_images, but the source images already live
        in S3 under pending-uploads/ (the presigned browser-upload flow) —
        used when scan_package_batch's image_sources are S3 keys rather than
        local file paths."""
        pass


class LocalImageStorage(ImageStorage):
    def __init__(self, base_path: str | None = None):
        # Read settings lazily rather than as a default-arg (evaluated once at
        # import time) so tests can override settings.image_storage_local_path.
        self.base_path = resolve_local_storage_path(base_path)

    def save_images(self, item_id: str, source_paths: list[str]) -> SavedImages:
        item_dir = self.base_path / item_id
        item_dir.mkdir(parents=True, exist_ok=True)

        image_urls = []
        thumbnail_urls = []
        for i, src in enumerate(source_paths):
            ext = Path(src).suffix or ".jpg"
            dest = item_dir / f"{i}{ext}"
            shutil.copy(src, dest)
            # Served via StaticFiles mount at /images — see main.py
            image_urls.append(f"/images/{item_id}/{dest.name}")

            thumb_bytes = _thumbnail_bytes_or_original(Path(src).read_bytes())
            thumb_dest = item_dir / f"thumb_{i}.jpg"
            thumb_dest.write_bytes(thumb_bytes)
            thumbnail_urls.append(f"/images/{item_id}/{thumb_dest.name}")

        return SavedImages(image_urls=image_urls, thumbnail_urls=thumbnail_urls)

    def resolve_urls(self, refs: list[str]) -> list[str]:
        # Local URLs are already final and don't expire — nothing to refresh.
        return list(refs)

    def save_images_from_s3(self, item_id: str, pending_keys: list[str]) -> SavedImages:
        """Downloads each pending-uploads/ object and stores it locally — a
        valid combination when the presigned-upload bucket is real S3 but
        final image storage stays on local disk for dev convenience."""
        item_dir = self.base_path / item_id
        item_dir.mkdir(parents=True, exist_ok=True)

        image_urls = []
        thumbnail_urls = []
        for i, pending_key in enumerate(pending_keys):
            ext = Path(pending_key).suffix or ".jpg"
            dest = item_dir / f"{i}{ext}"
            original_bytes = get_pending_upload_bytes(pending_key)
            dest.write_bytes(original_bytes)
            image_urls.append(f"/images/{item_id}/{dest.name}")

            thumb_bytes = _thumbnail_bytes_or_original(original_bytes)
            thumb_dest = item_dir / f"thumb_{i}.jpg"
            thumb_dest.write_bytes(thumb_bytes)
            thumbnail_urls.append(f"/images/{item_id}/{thumb_dest.name}")

        return SavedImages(image_urls=image_urls, thumbnail_urls=thumbnail_urls)


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

    def save_images(self, item_id: str, source_paths: list[str]) -> SavedImages:
        """Uploads each image (and a thumbnail) and returns durable object
        keys — NOT presigned URLs, which expire and must never be what's
        stored in the database."""
        keys = []
        thumbnail_keys = []
        for i, src in enumerate(source_paths):
            ext = Path(src).suffix or ".jpg"
            key = f"{item_id}/{i}{ext}"
            self.s3.upload_file(src, self.bucket_name, key)
            keys.append(key)

            thumb_bytes = _thumbnail_bytes_or_original(Path(src).read_bytes())
            thumb_key = f"{item_id}/thumb_{i}.jpg"
            self.s3.put_object(Bucket=self.bucket_name, Key=thumb_key, Body=thumb_bytes, ContentType="image/jpeg")
            thumbnail_keys.append(thumb_key)

        return SavedImages(image_urls=keys, thumbnail_urls=thumbnail_keys)

    def resolve_urls(self, refs: list[str]) -> list[str]:
        return [
            self.s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": key},
                ExpiresIn=self.url_expiry_seconds,
            )
            for key in refs
        ]

    def save_images_from_s3(self, item_id: str, pending_keys: list[str]) -> SavedImages:
        """Server-side copy from pending-uploads/ to this item's real image
        location for the original — no bytes flow through this process for
        that part. The thumbnail needs actual bytes to generate, though, so
        this does fetch the object once just for that; cleanup of the
        pending source is a follow-up S3 lifecycle rule, not handled here
        (see storage/pending_uploads.py's module docstring)."""
        keys = []
        thumbnail_keys = []
        for i, pending_key in enumerate(pending_keys):
            ext = Path(pending_key).suffix or ".jpg"
            dest_key = f"{item_id}/{i}{ext}"
            self.s3.copy_object(
                Bucket=self.bucket_name,
                CopySource={"Bucket": self.bucket_name, "Key": pending_key},
                Key=dest_key,
            )
            keys.append(dest_key)

            # Not get_pending_upload_bytes() — that hardcodes
            # settings.s3_bucket_name, which would silently diverge from
            # self.bucket_name if this instance was ever constructed with
            # an explicit override (as tests do). Fetch via this instance's
            # own client/bucket instead, consistent with copy_object above.
            original_bytes = self.s3.get_object(Bucket=self.bucket_name, Key=pending_key)["Body"].read()
            thumb_bytes = _thumbnail_bytes_or_original(original_bytes)
            thumb_key = f"{item_id}/thumb_{i}.jpg"
            self.s3.put_object(Bucket=self.bucket_name, Key=thumb_key, Body=thumb_bytes, ContentType="image/jpeg")
            thumbnail_keys.append(thumb_key)

        return SavedImages(image_urls=keys, thumbnail_urls=thumbnail_keys)


def get_image_storage() -> ImageStorage:
    if settings.storage_backend == "s3":
        return S3ImageStorage()
    return LocalImageStorage()


def check_local_image_integrity(local_root: Path, items: list[dict]) -> list[str]:
    """Checks that every locally-stored image reference in `items` (both
    originals and thumbnails) still points at a file that actually exists
    under `local_root`. Meant to be called on every app startup/reload —
    exactly the moment a relative storage path resolving against a
    different cwd would silently orphan previously-saved images. Returns
    the list of missing "item_id: url" references (empty if everything's
    fine)."""
    missing: list[str] = []
    for item in items:
        urls = (item.get("image_urls") or []) + (item.get("thumbnail_urls") or [])
        for url in urls:
            if not url.startswith("/images/"):
                continue  # not a local reference (e.g. an S3 key from a different backend)
            rel_path = url[len("/images/"):]
            if not (local_root / rel_path).exists():
                missing.append(f"{item.get('item_id')}: {url}")
    return missing


def resolve_image_urls(refs: list[str]) -> list[str]:
    """Converts an item's stored image references into URLs valid right now.
    Call this on every read path (list/detail/review) — never cache the
    result. Works for both image_urls and thumbnail_urls — call it for
    each."""
    if not refs:
        return []
    return get_image_storage().resolve_urls(refs)

from io import BytesIO
from pathlib import Path

import boto3
import pytest
from moto import mock_aws
from PIL import Image

from strand_sort.storage.image_storage import (
    LocalImageStorage,
    S3ImageStorage,
    check_local_image_integrity,
    get_image_storage,
    resolve_image_urls,
    resolve_local_storage_path,
)


def _real_jpeg_bytes(size: tuple[int, int] = (800, 600)) -> bytes:
    """A genuine JPEG, not fake placeholder bytes — needed to exercise the
    real thumbnail-generation path rather than always hitting its
    corrupt-image fallback."""
    buf = BytesIO()
    Image.new("RGB", size, color=(200, 50, 50)).save(buf, format="JPEG")
    return buf.getvalue()


class TestLocalImageStorage:
    def test_save_images_copies_files_and_returns_urls(self, tmp_path):
        src = tmp_path / "photo.jpg"
        src.write_bytes(_real_jpeg_bytes())

        storage = LocalImageStorage(base_path=str(tmp_path / "store"))
        saved = storage.save_images("item-123", [str(src)])

        assert saved.image_urls == ["/images/item-123/0.jpg"]
        assert (tmp_path / "store" / "item-123" / "0.jpg").read_bytes() == src.read_bytes()

    def test_save_images_also_generates_a_smaller_thumbnail(self, tmp_path):
        src = tmp_path / "photo.jpg"
        original_bytes = _real_jpeg_bytes((1600, 1200))
        src.write_bytes(original_bytes)

        storage = LocalImageStorage(base_path=str(tmp_path / "store"))
        saved = storage.save_images("item-123", [str(src)])

        assert saved.thumbnail_urls == ["/images/item-123/thumb_0.jpg"]
        thumb_path = tmp_path / "store" / "item-123" / "thumb_0.jpg"
        assert thumb_path.exists()
        # The whole point: dramatically smaller than the original, not just
        # a renamed copy of it.
        assert len(thumb_path.read_bytes()) < len(original_bytes) / 2
        with Image.open(thumb_path) as thumb_img:
            assert max(thumb_img.size) <= 400

    def test_save_images_preserves_order_and_extension(self, tmp_path):
        src1 = tmp_path / "a.png"
        src2 = tmp_path / "b.jpg"
        src1.write_bytes(_real_jpeg_bytes())
        src2.write_bytes(_real_jpeg_bytes())

        storage = LocalImageStorage(base_path=str(tmp_path / "store"))
        saved = storage.save_images("item-xyz", [str(src1), str(src2)])

        assert saved.image_urls == ["/images/item-xyz/0.png", "/images/item-xyz/1.jpg"]
        # Thumbnails are always re-encoded as JPEG regardless of source format.
        assert saved.thumbnail_urls == ["/images/item-xyz/thumb_0.jpg", "/images/item-xyz/thumb_1.jpg"]

    def test_resolve_urls_is_passthrough(self, tmp_path):
        storage = LocalImageStorage(base_path=str(tmp_path))
        refs = ["/images/item-1/0.jpg", "/images/item-1/1.jpg"]
        assert storage.resolve_urls(refs) == refs

    def test_resolve_urls_empty_list(self, tmp_path):
        storage = LocalImageStorage(base_path=str(tmp_path))
        assert storage.resolve_urls([]) == []

    @mock_aws
    def test_save_images_from_s3_downloads_pending_uploads(self, tmp_path, monkeypatch):
        """Valid combination: presigned uploads always land in S3 (see
        storage/pending_uploads.py), but this dev setup keeps final image
        storage on local disk — save_images_from_s3 has to bridge the two."""
        from strand_sort.config import settings

        bucket = "test-foodbank-pending"
        monkeypatch.setattr(settings, "s3_bucket_name", bucket)
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)
        original_bytes = _real_jpeg_bytes()
        s3.put_object(Bucket=bucket, Key="pending-uploads/abc.jpg", Body=original_bytes)

        storage = LocalImageStorage(base_path=str(tmp_path / "store"))
        saved = storage.save_images_from_s3("item-123", ["pending-uploads/abc.jpg"])

        assert saved.image_urls == ["/images/item-123/0.jpg"]
        assert (tmp_path / "store" / "item-123" / "0.jpg").read_bytes() == original_bytes
        assert saved.thumbnail_urls == ["/images/item-123/thumb_0.jpg"]
        assert (tmp_path / "store" / "item-123" / "thumb_0.jpg").exists()


class TestResolveLocalStoragePath:
    """A relative configured path (the default, "data/raw") must always
    resolve to the same absolute directory regardless of the process's cwd —
    otherwise starting the dev server from a different directory across
    restarts silently orphans every image saved under the old cwd."""

    def test_absolute_configured_path_passed_through(self):
        assert resolve_local_storage_path("/tmp/somewhere/raw") == Path("/tmp/somewhere/raw")

    def test_relative_path_anchored_to_package_root_not_cwd(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)  # simulate the server being launched from elsewhere
        resolved = resolve_local_storage_path("data/raw")
        assert resolved.is_absolute()
        assert resolved != tmp_path / "data/raw"
        assert resolved.name == "raw" and resolved.parent.name == "data"
        # Must land at the actual repo root (this test file lives at
        # <repo>/tests/storage/, two levels down from it) — not some
        # intermediate directory like src/.
        repo_root = Path(__file__).resolve().parent.parent.parent
        assert resolved == repo_root / "data" / "raw"

    def test_resolution_is_identical_across_different_cwds(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        first = resolve_local_storage_path("data/raw")
        (tmp_path / "nested").mkdir()
        monkeypatch.chdir(tmp_path / "nested")
        second = resolve_local_storage_path("data/raw")
        assert first == second


class TestCheckLocalImageIntegrity:
    """This is what runs on every app startup/reload (see main.py) to catch
    the storage-path/cwd bug immediately instead of waiting for a blank
    thumbnail to be noticed in the UI."""

    def test_no_items_no_missing(self, tmp_path):
        assert check_local_image_integrity(tmp_path, []) == []

    def test_existing_file_not_reported(self, tmp_path):
        (tmp_path / "item-1").mkdir()
        (tmp_path / "item-1" / "0.jpg").write_bytes(b"x")
        items = [{"item_id": "item-1", "image_urls": ["/images/item-1/0.jpg"]}]
        assert check_local_image_integrity(tmp_path, items) == []

    def test_missing_file_is_reported(self, tmp_path):
        """Exactly the failure mode from the storage-path bug: the DB row
        references a file that isn't where the resolved root says it should
        be."""
        items = [{"item_id": "item-1", "image_urls": ["/images/item-1/0.jpg"]}]
        missing = check_local_image_integrity(tmp_path, items)
        assert missing == ["item-1: /images/item-1/0.jpg"]

    def test_non_local_refs_are_skipped(self, tmp_path):
        """An S3 key from a different backend shouldn't be checked against
        the local filesystem."""
        items = [{"item_id": "item-1", "image_urls": ["item-1/0.jpg"]}]
        assert check_local_image_integrity(tmp_path, items) == []

    def test_items_without_image_urls_are_skipped(self, tmp_path):
        assert check_local_image_integrity(tmp_path, [{"item_id": "no-images"}]) == []

    def test_missing_thumbnail_is_reported_same_as_missing_original(self, tmp_path):
        (tmp_path / "item-1").mkdir()
        (tmp_path / "item-1" / "0.jpg").write_bytes(b"x")  # original exists
        items = [{
            "item_id": "item-1",
            "image_urls": ["/images/item-1/0.jpg"],
            "thumbnail_urls": ["/images/item-1/thumb_0.jpg"],  # thumbnail doesn't
        }]
        missing = check_local_image_integrity(tmp_path, items)
        assert missing == ["item-1: /images/item-1/thumb_0.jpg"]


class TestS3ImageStorage:
    @mock_aws
    def test_save_images_uploads_and_returns_keys_not_urls(self, tmp_path):
        bucket = "test-foodbank-images"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)

        src = tmp_path / "photo.jpg"
        original_bytes = _real_jpeg_bytes()
        src.write_bytes(original_bytes)

        storage = S3ImageStorage(bucket_name=bucket, region="us-east-1")
        saved = storage.save_images("item-123", [str(src)])

        assert saved.image_urls == ["item-123/0.jpg"]
        # A bare key, not a presigned URL — presigned URLs must never be persisted.
        assert not saved.image_urls[0].startswith("http")

        obj = s3.get_object(Bucket=bucket, Key="item-123/0.jpg")
        assert obj["Body"].read() == original_bytes

    @mock_aws
    def test_save_images_also_uploads_a_smaller_thumbnail(self, tmp_path):
        bucket = "test-foodbank-images"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)

        src = tmp_path / "photo.jpg"
        original_bytes = _real_jpeg_bytes((1600, 1200))
        src.write_bytes(original_bytes)

        storage = S3ImageStorage(bucket_name=bucket, region="us-east-1")
        saved = storage.save_images("item-123", [str(src)])

        assert saved.thumbnail_urls == ["item-123/thumb_0.jpg"]
        thumb_bytes = s3.get_object(Bucket=bucket, Key="item-123/thumb_0.jpg")["Body"].read()
        assert len(thumb_bytes) < len(original_bytes) / 2
        with Image.open(BytesIO(thumb_bytes)) as thumb_img:
            assert max(thumb_img.size) <= 400

    @mock_aws
    def test_save_images_from_s3_copies_within_the_bucket(self):
        """Server-side copy_object — no bytes should flow through this
        process for the S3-to-S3 case (for the original — the thumbnail
        does need bytes fetched to generate from)."""
        bucket = "test-foodbank-images"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)
        original_bytes = _real_jpeg_bytes()
        s3.put_object(Bucket=bucket, Key="pending-uploads/abc.jpg", Body=original_bytes)

        storage = S3ImageStorage(bucket_name=bucket, region="us-east-1")
        saved = storage.save_images_from_s3("item-123", ["pending-uploads/abc.jpg"])

        assert saved.image_urls == ["item-123/0.jpg"]
        obj = s3.get_object(Bucket=bucket, Key="item-123/0.jpg")
        assert obj["Body"].read() == original_bytes
        # The pending source is left in place — cleanup is a follow-up
        # lifecycle rule, not this method's job.
        assert s3.get_object(Bucket=bucket, Key="pending-uploads/abc.jpg")["Body"].read() == original_bytes

        assert saved.thumbnail_urls == ["item-123/thumb_0.jpg"]
        thumb_bytes = s3.get_object(Bucket=bucket, Key="item-123/thumb_0.jpg")["Body"].read()
        assert len(thumb_bytes) < len(original_bytes)

    @mock_aws
    def test_save_images_from_s3_uses_this_instances_own_bucket_not_global_settings(self, monkeypatch):
        """Regression: originally fetched pending-upload bytes for the
        thumbnail via a helper that reads settings.s3_bucket_name globally,
        ignoring this instance's own explicit bucket_name override — broke
        the moment the two diverged (exactly what this test sets up)."""
        from strand_sort.config import settings

        monkeypatch.setattr(settings, "s3_bucket_name", "some-other-bucket-entirely")

        bucket = "test-foodbank-images"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)
        s3.put_object(Bucket=bucket, Key="pending-uploads/abc.jpg", Body=_real_jpeg_bytes())

        storage = S3ImageStorage(bucket_name=bucket, region="us-east-1")
        saved = storage.save_images_from_s3("item-123", ["pending-uploads/abc.jpg"])  # must not raise

        assert saved.thumbnail_urls == ["item-123/thumb_0.jpg"]

    @mock_aws
    def test_resolve_urls_generates_fresh_presigned_urls(self):
        bucket = "test-foodbank-images"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)
        s3.put_object(Bucket=bucket, Key="item-1/0.jpg", Body=b"data")

        storage = S3ImageStorage(bucket_name=bucket, region="us-east-1")
        urls = storage.resolve_urls(["item-1/0.jpg"])

        assert len(urls) == 1
        assert urls[0].startswith("http")
        assert "item-1/0.jpg" in urls[0]

    @mock_aws
    def test_resolve_urls_empty_list(self):
        storage = S3ImageStorage(bucket_name="whatever", region="us-east-1")
        assert storage.resolve_urls([]) == []


class TestGetImageStorage:
    def test_defaults_to_local(self, monkeypatch):
        from strand_sort.config import settings

        monkeypatch.setattr(settings, "storage_backend", "local")
        assert isinstance(get_image_storage(), LocalImageStorage)

    def test_s3_backend_selected(self, monkeypatch):
        from strand_sort.config import settings

        monkeypatch.setattr(settings, "storage_backend", "s3")
        assert isinstance(get_image_storage(), S3ImageStorage)


class TestResolveImageUrls:
    def test_empty_refs_short_circuits(self, monkeypatch):
        # Should return [] without even constructing a storage backend.
        assert resolve_image_urls([]) == []

    def test_delegates_to_active_backend(self, monkeypatch):
        from strand_sort.config import settings

        monkeypatch.setattr(settings, "storage_backend", "local")
        refs = ["/images/item-1/0.jpg"]
        assert resolve_image_urls(refs) == refs

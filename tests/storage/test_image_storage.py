import boto3
import pytest
from moto import mock_aws

from strand_sort.storage.image_storage import (
    LocalImageStorage,
    S3ImageStorage,
    get_image_storage,
    resolve_image_urls,
)


class TestLocalImageStorage:
    def test_save_images_copies_files_and_returns_urls(self, tmp_path):
        src = tmp_path / "photo.jpg"
        src.write_bytes(b"fake-jpeg-bytes")

        storage = LocalImageStorage(base_path=str(tmp_path / "store"))
        urls = storage.save_images("item-123", [str(src)])

        assert urls == ["/images/item-123/0.jpg"]
        assert (tmp_path / "store" / "item-123" / "0.jpg").read_bytes() == b"fake-jpeg-bytes"

    def test_save_images_preserves_order_and_extension(self, tmp_path):
        src1 = tmp_path / "a.png"
        src2 = tmp_path / "b.jpg"
        src1.write_bytes(b"one")
        src2.write_bytes(b"two")

        storage = LocalImageStorage(base_path=str(tmp_path / "store"))
        urls = storage.save_images("item-xyz", [str(src1), str(src2)])

        assert urls == ["/images/item-xyz/0.png", "/images/item-xyz/1.jpg"]

    def test_resolve_urls_is_passthrough(self, tmp_path):
        storage = LocalImageStorage(base_path=str(tmp_path))
        refs = ["/images/item-1/0.jpg", "/images/item-1/1.jpg"]
        assert storage.resolve_urls(refs) == refs

    def test_resolve_urls_empty_list(self, tmp_path):
        storage = LocalImageStorage(base_path=str(tmp_path))
        assert storage.resolve_urls([]) == []


class TestS3ImageStorage:
    @mock_aws
    def test_save_images_uploads_and_returns_keys_not_urls(self, tmp_path):
        bucket = "test-foodbank-images"
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=bucket)

        src = tmp_path / "photo.jpg"
        src.write_bytes(b"fake-jpeg-bytes")

        storage = S3ImageStorage(bucket_name=bucket, region="us-east-1")
        keys = storage.save_images("item-123", [str(src)])

        assert keys == ["item-123/0.jpg"]
        # A bare key, not a presigned URL — presigned URLs must never be persisted.
        assert not keys[0].startswith("http")

        obj = s3.get_object(Bucket=bucket, Key="item-123/0.jpg")
        assert obj["Body"].read() == b"fake-jpeg-bytes"

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

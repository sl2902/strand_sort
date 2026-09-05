from unittest.mock import MagicMock, patch

from strand_sort.storage.pending_uploads import (
    PENDING_UPLOADS_PREFIX,
    download_to_file,
    get_bytes,
    presign_put_url,
    put_bytes,
)


class TestPresignPutUrl:
    @patch("strand_sort.storage.pending_uploads._client")
    def test_generates_a_pending_uploads_key_with_source_extension(self, mock_client_factory):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://example.com/signed"
        mock_client_factory.return_value = mock_s3

        s3_key, upload_url = presign_put_url("photo.PNG")

        assert s3_key.startswith(f"{PENDING_UPLOADS_PREFIX}/")
        assert s3_key.endswith(".PNG")
        assert upload_url == "https://example.com/signed"

    @patch("strand_sort.storage.pending_uploads._client")
    def test_defaults_to_jpg_extension_when_filename_has_none(self, mock_client_factory):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://example.com/signed"
        mock_client_factory.return_value = mock_s3

        s3_key, _ = presign_put_url("no_extension")
        assert s3_key.endswith(".jpg")

    @patch("strand_sort.storage.pending_uploads._client")
    def test_each_call_gets_a_unique_key(self, mock_client_factory):
        mock_s3 = MagicMock()
        mock_s3.generate_presigned_url.return_value = "https://example.com/signed"
        mock_client_factory.return_value = mock_s3

        key1, _ = presign_put_url("a.jpg")
        key2, _ = presign_put_url("a.jpg")
        assert key1 != key2


class TestGetBytes:
    @patch("strand_sort.storage.pending_uploads._client")
    def test_reads_the_object_body(self, mock_client_factory):
        mock_s3 = MagicMock()
        mock_body = MagicMock()
        mock_body.read.return_value = b"raw-image-bytes"
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_client_factory.return_value = mock_s3

        result = get_bytes("pending-uploads/abc.jpg")
        assert result == b"raw-image-bytes"


class TestDownloadToFile:
    @patch("strand_sort.storage.pending_uploads._client")
    def test_delegates_to_boto3_download_file(self, mock_client_factory, tmp_path):
        mock_s3 = MagicMock()
        mock_client_factory.return_value = mock_s3
        dest = str(tmp_path / "video.mp4")

        download_to_file("pending-uploads/clip.mp4", dest)

        mock_s3.download_file.assert_called_once()
        args = mock_s3.download_file.call_args[0]
        assert args[1] == "pending-uploads/clip.mp4"
        assert args[2] == dest


class TestPutBytes:
    @patch("strand_sort.storage.pending_uploads._client")
    def test_uploads_and_returns_a_pending_uploads_key(self, mock_client_factory):
        mock_s3 = MagicMock()
        mock_client_factory.return_value = mock_s3

        key = put_bytes(b"jpeg-bytes")

        assert key.startswith(f"{PENDING_UPLOADS_PREFIX}/")
        assert key.endswith(".jpg")
        mock_s3.put_object.assert_called_once()
        _, kwargs = mock_s3.put_object.call_args
        assert kwargs["Body"] == b"jpeg-bytes"
        assert kwargs["Key"] == key

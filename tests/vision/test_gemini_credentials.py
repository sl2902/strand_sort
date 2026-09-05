import json
from unittest.mock import MagicMock, patch

import pytest

from strand_sort.vision import extract as extract_module
from strand_sort.vision.extract import (
    GeminiExtractor,
    _get_gcp_credentials,
    _get_gcp_credentials_dict,
    _running_on_lambda,
)


@pytest.fixture(autouse=True)
def clear_credential_caches():
    """lru_cache-backed module-level singletons — don't leak state across
    tests, same reasoning as clearing the review_queue used to need."""
    _get_gcp_credentials_dict.cache_clear()
    _get_gcp_credentials.cache_clear()
    yield
    _get_gcp_credentials_dict.cache_clear()
    _get_gcp_credentials.cache_clear()


class TestRunningOnLambda:
    def test_true_when_lambda_env_var_present(self, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "strand-sort-api")
        assert _running_on_lambda() is True

    def test_false_locally(self, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        assert _running_on_lambda() is False


class TestGetGcpCredentialsDict:
    @patch("strand_sort.vision.extract.boto3.client")
    def test_fetches_and_parses_the_secret(self, mock_boto_client):
        mock_secretsmanager = MagicMock()
        mock_secretsmanager.get_secret_value.return_value = {
            "SecretString": json.dumps({"type": "service_account", "project_id": "fake"})
        }
        mock_boto_client.return_value = mock_secretsmanager

        result = _get_gcp_credentials_dict()

        assert result == {"type": "service_account", "project_id": "fake"}
        mock_boto_client.assert_called_once_with("secretsmanager", region_name=extract_module.settings.aws_region)

    @patch("strand_sort.vision.extract.boto3.client")
    def test_second_call_does_not_refetch(self, mock_boto_client):
        """The whole point of lru_cache here: Secrets Manager calls have
        real latency/cost and must not run on every invocation."""
        mock_secretsmanager = MagicMock()
        mock_secretsmanager.get_secret_value.return_value = {
            "SecretString": json.dumps({"type": "service_account"})
        }
        mock_boto_client.return_value = mock_secretsmanager

        _get_gcp_credentials_dict()
        _get_gcp_credentials_dict()
        _get_gcp_credentials_dict()

        mock_secretsmanager.get_secret_value.assert_called_once()


class TestGeminiExtractorCredentialWiring:
    """These confirm the branch is wired correctly (mocked, not a real AWS
    or GCP call). End-to-end behavior against a real deployed Lambda still
    needs to be exercised for real once this ships — that can't be verified
    from a local dev machine."""

    @patch("strand_sort.vision.extract.genai.Client")
    @patch("strand_sort.vision.extract._get_gcp_credentials")
    def test_on_lambda_passes_secrets_manager_credentials(self, mock_get_creds, mock_client, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "strand-sort-api")
        fake_credentials = object()
        mock_get_creds.return_value = fake_credentials

        GeminiExtractor()

        mock_get_creds.assert_called_once()
        _, kwargs = mock_client.call_args
        assert kwargs["credentials"] is fake_credentials

    @patch("strand_sort.vision.extract.genai.Client")
    @patch("strand_sort.vision.extract._get_gcp_credentials")
    def test_locally_does_not_touch_secrets_manager(self, mock_get_creds, mock_client, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

        GeminiExtractor()

        mock_get_creds.assert_not_called()
        _, kwargs = mock_client.call_args
        assert "credentials" not in kwargs

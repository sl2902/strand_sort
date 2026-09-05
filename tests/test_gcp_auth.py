import json
from unittest.mock import MagicMock, patch

import pytest

from strand_sort import gcp_auth
from strand_sort.gcp_auth import (
    get_gcp_credentials,
    get_gcp_credentials_dict,
    running_on_lambda,
)


@pytest.fixture(autouse=True)
def clear_credential_caches():
    """lru_cache-backed module-level singletons — don't leak state across
    tests, same reasoning as clearing the review_queue used to need."""
    get_gcp_credentials_dict.cache_clear()
    get_gcp_credentials.cache_clear()
    yield
    get_gcp_credentials_dict.cache_clear()
    get_gcp_credentials.cache_clear()


class TestRunningOnLambda:
    def test_true_when_lambda_env_var_present(self, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "strand-sort-api")
        assert running_on_lambda() is True

    def test_false_locally(self, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
        assert running_on_lambda() is False


class TestGetGcpCredentialsDict:
    @patch("strand_sort.gcp_auth.boto3.client")
    def test_fetches_and_parses_the_secret(self, mock_boto_client):
        mock_secretsmanager = MagicMock()
        mock_secretsmanager.get_secret_value.return_value = {
            "SecretString": json.dumps({"type": "service_account", "project_id": "fake"})
        }
        mock_boto_client.return_value = mock_secretsmanager

        result = get_gcp_credentials_dict()

        assert result == {"type": "service_account", "project_id": "fake"}
        mock_boto_client.assert_called_once_with("secretsmanager", region_name=gcp_auth.settings.aws_region)

    @patch("strand_sort.gcp_auth.boto3.client")
    def test_second_call_does_not_refetch(self, mock_boto_client):
        """The whole point of lru_cache here: Secrets Manager calls have
        real latency/cost and must not run on every invocation."""
        mock_secretsmanager = MagicMock()
        mock_secretsmanager.get_secret_value.return_value = {
            "SecretString": json.dumps({"type": "service_account"})
        }
        mock_boto_client.return_value = mock_secretsmanager

        get_gcp_credentials_dict()
        get_gcp_credentials_dict()
        get_gcp_credentials_dict()

        mock_secretsmanager.get_secret_value.assert_called_once()


class TestGetGcpCredentials:
    @patch("strand_sort.gcp_auth.service_account.Credentials.from_service_account_info")
    @patch("strand_sort.gcp_auth.boto3.client")
    def test_builds_credentials_with_cloud_platform_scope(self, mock_boto_client, mock_from_info):
        mock_secretsmanager = MagicMock()
        mock_secretsmanager.get_secret_value.return_value = {
            "SecretString": json.dumps({"type": "service_account"})
        }
        mock_boto_client.return_value = mock_secretsmanager
        fake_credentials = object()
        mock_from_info.return_value = fake_credentials

        result = get_gcp_credentials()

        assert result is fake_credentials
        _, kwargs = mock_from_info.call_args
        assert kwargs["scopes"] == ["https://www.googleapis.com/auth/cloud-platform"]

    @patch("strand_sort.gcp_auth.service_account.Credentials.from_service_account_info")
    @patch("strand_sort.gcp_auth.boto3.client")
    def test_second_call_does_not_rebuild(self, mock_boto_client, mock_from_info):
        mock_secretsmanager = MagicMock()
        mock_secretsmanager.get_secret_value.return_value = {
            "SecretString": json.dumps({"type": "service_account"})
        }
        mock_boto_client.return_value = mock_secretsmanager

        get_gcp_credentials()
        get_gcp_credentials()

        mock_from_info.assert_called_once()

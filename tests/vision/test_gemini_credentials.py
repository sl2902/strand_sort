from unittest.mock import patch

import pytest

from strand_sort.gcp_auth import get_gcp_credentials, get_gcp_credentials_dict
from strand_sort.vision.extract import GeminiExtractor


@pytest.fixture(autouse=True)
def clear_credential_caches():
    """lru_cache-backed module-level singletons — don't leak state across
    tests, same reasoning as clearing the review_queue used to need."""
    get_gcp_credentials_dict.cache_clear()
    get_gcp_credentials.cache_clear()
    yield
    get_gcp_credentials_dict.cache_clear()
    get_gcp_credentials.cache_clear()


class TestGeminiExtractorCredentialWiring:
    """These confirm the branch is wired correctly (mocked, not a real AWS
    or GCP call). End-to-end behavior against a real deployed Lambda still
    needs to be exercised for real once this ships — that can't be verified
    from a local dev machine. running_on_lambda/get_gcp_credentials live in
    strand_sort.gcp_auth (shared with agent/intake_agent.py's own Gemini
    fallback — see tests/agent/test_intake_agent.py) but are patched here at
    vision.extract's import site, matching this codebase's existing
    mock-where-it's-used convention."""

    @patch("strand_sort.vision.extract.genai.Client")
    @patch("strand_sort.vision.extract.get_gcp_credentials")
    def test_on_lambda_passes_secrets_manager_credentials(self, mock_get_creds, mock_client, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "strand-sort-api")
        fake_credentials = object()
        mock_get_creds.return_value = fake_credentials

        GeminiExtractor()

        mock_get_creds.assert_called_once()
        _, kwargs = mock_client.call_args
        assert kwargs["credentials"] is fake_credentials

    @patch("strand_sort.vision.extract.genai.Client")
    @patch("strand_sort.vision.extract.get_gcp_credentials")
    def test_locally_does_not_touch_secrets_manager(self, mock_get_creds, mock_client, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

        GeminiExtractor()

        mock_get_creds.assert_not_called()
        _, kwargs = mock_client.call_args
        assert "credentials" not in kwargs

    @patch("strand_sort.vision.extract.logger")
    @patch("strand_sort.vision.extract.genai.Client")
    @patch("strand_sort.vision.extract.get_gcp_credentials")
    def test_on_lambda_logs_which_credentials_path_was_taken(
        self, mock_get_creds, mock_client, mock_logger, monkeypatch
    ):
        """The diagnostic this ticket is actually about: logs must say
        definitively which branch executed, not just that a failure
        eventually happened somewhere downstream."""
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "strand-sort-api")

        GeminiExtractor()

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("Secrets-Manager" in msg and "Lambda" in msg for msg in logged)

    @patch("strand_sort.vision.extract.logger")
    @patch("strand_sort.vision.extract.genai.Client")
    @patch("strand_sort.vision.extract.get_gcp_credentials")
    def test_locally_logs_adc_credentials_path(self, mock_get_creds, mock_client, mock_logger, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

        GeminiExtractor()

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("ADC" in msg for msg in logged)

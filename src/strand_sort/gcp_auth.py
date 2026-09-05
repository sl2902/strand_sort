"""Shared GCP/Vertex AI authentication for every Gemini client construction
in this codebase. There are exactly two: vision/extract.py's
GeminiExtractor (image extraction) and agent/intake_agent.py's
_gemini_model() (the agent's own reasoning fallback when Bedrock fails at
the agent level — a distinct fallback from the one inside GeminiExtractor).
Both need the same credentials resolution; don't duplicate this logic at a
new call site — import from here.
"""

import json
import os
from functools import lru_cache

import boto3
from google.oauth2 import service_account

from strand_sort.config import settings


def running_on_lambda() -> bool:
    """AWS sets this in every Lambda execution environment automatically;
    it's never present locally. Decides whether Gemini/Vertex auth comes
    from Secrets Manager (Lambda has no `gcloud auth application-default
    login` credentials file) or ADC (local dev, unchanged)."""
    return bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


@lru_cache(maxsize=1)
def get_gcp_credentials_dict() -> dict:
    """Fetched once per Lambda execution environment — lru_cache persists
    for the container's lifetime (reused across invocations), not just a
    single request. Secrets Manager calls have real latency/cost that
    shouldn't be paid on every invocation."""
    client = boto3.client("secretsmanager", region_name=settings.aws_region)
    response = client.get_secret_value(SecretId=settings.gcp_secrets_manager_secret_id)
    return json.loads(response["SecretString"])


@lru_cache(maxsize=1)
def get_gcp_credentials() -> service_account.Credentials:
    """Also cached: a Credentials object holds a signer built from the
    private key and manages its own token refresh — worth reusing rather
    than reconstructing on every Gemini call within the same container."""
    return service_account.Credentials.from_service_account_info(
        get_gcp_credentials_dict(),
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
    )

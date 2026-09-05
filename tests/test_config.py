import importlib

import strand_sort.config as config_module
from strand_sort.config import Settings


def test_settings_loads_from_plain_env_vars_without_dotenv(monkeypatch):
    """Lambda ships no .env file — env vars must be sufficient on their own
    (this already works, pydantic-settings reads both; this just confirms
    it rather than assuming)."""
    monkeypatch.setenv("GCP_PROJECT_ID", "fake-project")
    monkeypatch.setenv("GEMINI_LOCATION", "us-central1")
    monkeypatch.setenv("DB_ENGINE", "dynamodb")
    monkeypatch.setenv("STORAGE_BACKEND", "s3")

    settings = Settings(_env_file=None)

    assert settings.gcp_project_id == "fake-project"
    assert settings.db_engine == "dynamodb"
    assert settings.storage_backend == "s3"


def test_aws_profile_is_not_required(monkeypatch):
    """aws_profile isn't read by any boto3 call in this codebase (every
    client/resource construction relies on default credential resolution) —
    it must have a default, or Settings() crashes at import/cold-start
    whenever AWS_PROFILE isn't set, which is exactly the case on Lambda
    (credentials come from the execution role, not a named profile)."""
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "fake-project")
    monkeypatch.setenv("GEMINI_LOCATION", "us-central1")

    settings = Settings(_env_file=None)  # must not raise

    assert settings.aws_profile == ""


def test_config_module_imports_without_aws_profile_env_var(monkeypatch, tmp_path):
    """Reproduces the actual cold-start failure mode: strand_sort.config
    builds its module-level `settings` singleton at import time, so a
    missing required field crashes the whole app, not just a bare Settings()
    call. Re-imports the module fresh to catch that — chdir'd to an empty
    tmp_path so pydantic-settings can't fall back to this repo's real .env
    file and mask the very thing being tested (confirmed: without that
    chdir, this test passes even with the old required-field config, since
    .env supplies AWS_PROFILE regardless of what's monkeypatched into
    os.environ)."""
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    monkeypatch.setenv("GCP_PROJECT_ID", "fake-project")
    monkeypatch.setenv("GEMINI_LOCATION", "us-central1")
    monkeypatch.chdir(tmp_path)

    importlib.reload(config_module)  # must not raise

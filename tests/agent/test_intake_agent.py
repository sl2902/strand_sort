from unittest.mock import MagicMock, patch

import pytest

from strand_sort.agent.intake_agent import _gemini_model, format_intake_summary, run_intake_workflow
from strand_sort.gcp_auth import get_gcp_credentials, get_gcp_credentials_dict


@pytest.fixture(autouse=True)
def clear_credential_caches():
    get_gcp_credentials_dict.cache_clear()
    get_gcp_credentials.cache_clear()
    yield
    get_gcp_credentials_dict.cache_clear()
    get_gcp_credentials.cache_clear()


class TestGeminiModelCredentialWiring:
    """Same fix as GeminiExtractor's (vision/extract.py) applied to this
    SEPARATE genai.Client construction — the agent's own reasoning
    fallback when Bedrock fails at the agent level, not the extractor's
    fallback inside get_extractor. Confirmed via traceback that this one
    was missed by the earlier fix and still hit DefaultCredentialsError on
    Lambda."""

    @patch("strand_sort.agent.intake_agent.GeminiModel")
    @patch("strand_sort.agent.intake_agent.get_gcp_credentials")
    def test_on_lambda_passes_secrets_manager_credentials(self, mock_get_creds, mock_gemini_model, monkeypatch):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "strand-sort-api")
        fake_credentials = object()
        mock_get_creds.return_value = fake_credentials

        _gemini_model()

        mock_get_creds.assert_called_once()
        _, kwargs = mock_gemini_model.call_args
        assert kwargs["client_args"]["credentials"] is fake_credentials

    @patch("strand_sort.agent.intake_agent.GeminiModel")
    @patch("strand_sort.agent.intake_agent.get_gcp_credentials")
    def test_locally_does_not_touch_secrets_manager(self, mock_get_creds, mock_gemini_model, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

        _gemini_model()

        mock_get_creds.assert_not_called()
        _, kwargs = mock_gemini_model.call_args
        assert "credentials" not in kwargs["client_args"]

    @patch("strand_sort.agent.intake_agent.logger")
    @patch("strand_sort.agent.intake_agent.GeminiModel")
    @patch("strand_sort.agent.intake_agent.get_gcp_credentials")
    def test_on_lambda_logs_which_credentials_path_was_taken(
        self, mock_get_creds, mock_gemini_model, mock_logger, monkeypatch
    ):
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "strand-sort-api")

        _gemini_model()

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("Secrets-Manager" in msg and "Lambda" in msg for msg in logged)

    @patch("strand_sort.agent.intake_agent.logger")
    @patch("strand_sort.agent.intake_agent.GeminiModel")
    @patch("strand_sort.agent.intake_agent.get_gcp_credentials")
    def test_locally_logs_adc_credentials_path(self, mock_get_creds, mock_gemini_model, mock_logger, monkeypatch):
        monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)

        _gemini_model()

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("ADC" in msg for msg in logged)


def _base_item(**overrides):
    item = {
        "item_id": "abc",
        "product_name": "10on10 Whole Wheat Atta",
        "category": "grains_pulses",
        "quantity": 2,
        "expiration_date": "2026-11-20",
        "date_confidence": "high",
        "requires_human_review": False,
        "review_reason": None,
        "dietary_flags": {},
    }
    item.update(overrides)
    return item


def test_committed_item_summary_mentions_quantity_product_category_and_expiry():
    summary = format_intake_summary(_base_item())
    assert "2 x 10on10 Whole Wheat Atta" in summary
    assert "grains pulses" in summary
    assert "2026-11-20" in summary
    assert "flagged" not in summary.lower()


def test_low_date_confidence_adds_a_note():
    summary = format_intake_summary(_base_item(date_confidence="low"))
    assert "low" in summary.lower()


def test_high_date_confidence_has_no_confidence_note():
    summary = format_intake_summary(_base_item(date_confidence="high"))
    assert "confidence" not in summary.lower()


def test_dietary_highlights_are_listed_when_present():
    summary = format_intake_summary(
        _base_item(dietary_flags={"is_vegan": True, "is_gluten_free": True, "is_low_sodium": True})
    )
    assert "vegan" in summary
    assert "gluten-free" in summary
    assert "low sodium" in summary


def test_no_dietary_clause_when_nothing_is_flagged():
    summary = format_intake_summary(_base_item(dietary_flags={"is_vegan": False}))
    assert "Dietary flags" not in summary


def test_vegetarian_false_is_not_treated_as_a_highlight():
    """is_vegetarian is tri-state (True/False/None) — only an explicit True counts."""
    summary = format_intake_summary(_base_item(dietary_flags={"is_vegetarian": False}))
    assert "vegetarian" not in summary.lower()


def test_flagged_item_summary_mentions_review_and_reason():
    summary = format_intake_summary(
        _base_item(requires_human_review=True, review_reason="low-confidence date read")
    )
    assert "flagged for human review" in summary
    assert "low-confidence date read" in summary
    assert "committed to inventory" not in summary


def test_flagged_item_without_reason_still_produces_a_sentence():
    summary = format_intake_summary(_base_item(requires_human_review=True, review_reason=None))
    assert "flagged for human review" in summary


def test_missing_product_name_falls_back_gracefully():
    item = _base_item()
    del item["product_name"]
    summary = format_intake_summary(item)
    assert "This item" in summary


class TestRunIntakeWorkflowBranchLogging:
    """Closes a gap where a request completed with no exception anywhere but
    returned an empty summary and null item, with no indication of which
    branch run_intake_workflow actually took — i.e. whether the hook ever
    captured an item at all."""

    def _mock_agent_that(self, mock_create_agent, mutate_hook=None, response_text=""):
        """run_intake_workflow constructs its own ItemResultHook internally
        and passes it to create_intake_agent(model, hooks=[...]) — it isn't
        injectable directly, so grab it back out of the hooks kwarg to
        simulate the real agent's tool-call hook firing during agent(prompt)."""
        mock_agent = MagicMock()

        def fake_call(prompt):
            if mutate_hook is not None:
                _, kwargs = mock_create_agent.call_args
                item_hook = kwargs["hooks"][-1]
                mutate_hook(item_hook)
            return MagicMock(message={"content": [{"text": response_text}]})

        mock_agent.side_effect = fake_call
        mock_create_agent.return_value = mock_agent

    @patch("strand_sort.agent.intake_agent.logger")
    @patch("strand_sort.agent.intake_agent.create_intake_agent")
    @patch("strand_sort.agent.intake_agent._bedrock_model")
    def test_logs_templated_summary_branch_when_item_captured(self, mock_bedrock_model, mock_create_agent, mock_logger):
        captured_item = {"item_id": "abc", "product_name": "Milk", "quantity": 1, "requires_human_review": False}
        self._mock_agent_that(mock_create_agent, mutate_hook=lambda hook: setattr(hook, "item", captured_item))

        run_intake_workflow(image_sources=["pending-uploads/a.jpg"])

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("Using templated summary from captured item" in msg for msg in logged)

    @patch("strand_sort.agent.intake_agent.logger")
    @patch("strand_sort.agent.intake_agent.create_intake_agent")
    @patch("strand_sort.agent.intake_agent._bedrock_model")
    def test_logs_fallback_branch_when_no_item_captured(self, mock_bedrock_model, mock_create_agent, mock_logger):
        self._mock_agent_that(mock_create_agent, mutate_hook=None, response_text="something went wrong")

        run_intake_workflow(image_sources=["pending-uploads/a.jpg"])

        warned = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert any("No item captured by hook" in msg for msg in warned)


class TestRunIntakeWorkflowSurfacesToolException:
    """The actual bug this was built for: a tool call (e.g.
    commit_to_inventory hitting a stale DynamoDB index name) raises, the
    agent framework treats that as a tool observation rather than a raised
    Python exception, so this completes with no exception AND no item
    captured — previously an opaque empty summary, visible only by pulling
    CloudWatch logs. Now the actual error surfaces directly in the summary
    returned to whoever's waiting on the Scan page."""

    def _mock_agent_that(self, mock_create_agent, mutate_hook=None, response_text=""):
        mock_agent = MagicMock()

        def fake_call(prompt):
            if mutate_hook is not None:
                _, kwargs = mock_create_agent.call_args
                item_hook = kwargs["hooks"][-1]
                mutate_hook(item_hook)
            return MagicMock(message={"content": [{"text": response_text}]})

        mock_agent.side_effect = fake_call
        mock_create_agent.return_value = mock_agent

    @patch("strand_sort.agent.intake_agent.create_intake_agent")
    @patch("strand_sort.agent.intake_agent._bedrock_model")
    def test_tool_exception_becomes_the_summary_when_no_item_captured(self, mock_bedrock_model, mock_create_agent):
        tool_exc = Exception(
            "ValidationException: The table does not have the specified index: ProductNameIndex"
        )
        self._mock_agent_that(mock_create_agent, mutate_hook=lambda hook: setattr(hook, "tool_exception", tool_exc))

        summary, item = run_intake_workflow(image_sources=["pending-uploads/a.jpg"])

        assert item is None
        assert "Processing failed" in summary
        assert "ProductNameIndex" in summary

    @patch("strand_sort.agent.intake_agent.logger")
    @patch("strand_sort.agent.intake_agent.create_intake_agent")
    @patch("strand_sort.agent.intake_agent._bedrock_model")
    def test_logs_the_tool_exception_branch(self, mock_bedrock_model, mock_create_agent, mock_logger):
        tool_exc = RuntimeError("boom")
        self._mock_agent_that(mock_create_agent, mutate_hook=lambda hook: setattr(hook, "tool_exception", tool_exc))

        run_intake_workflow(image_sources=["pending-uploads/a.jpg"])

        warned = [call.args[0] for call in mock_logger.warning.call_args_list]
        assert any("Tool call raised, no item captured" in msg and "boom" in msg for msg in warned)

    @patch("strand_sort.agent.intake_agent.create_intake_agent")
    @patch("strand_sort.agent.intake_agent._bedrock_model")
    def test_captured_item_still_wins_over_a_stale_tool_exception(self, mock_bedrock_model, mock_create_agent):
        """An earlier tool call in the same run could have raised (e.g. a
        transient error on a retry) — if a LATER tool call in the same run
        still settles the item successfully, that must win over the
        earlier exception, not the other way around."""
        captured_item = {"item_id": "abc", "product_name": "Milk", "quantity": 1, "requires_human_review": False}

        def mutate(hook):
            hook.tool_exception = RuntimeError("earlier transient failure")
            hook.item = captured_item

        self._mock_agent_that(mock_create_agent, mutate_hook=mutate)

        summary, item = run_intake_workflow(image_sources=["pending-uploads/a.jpg"])

        assert item == captured_item
        assert "Processing failed" not in summary

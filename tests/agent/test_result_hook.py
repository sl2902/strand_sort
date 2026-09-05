import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from strand_sort.agent.result_hook import ItemResultHook


def _event(tool_name: str, result_data: dict, exception: Exception | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        tool_use={"name": tool_name},
        result={"content": [{"text": json.dumps(result_data)}]},
        exception=exception,
        agent=MagicMock(),
    )


def test_ignores_unrelated_tool_calls():
    hook = ItemResultHook()
    event = _event("search_inventory", {"item": {"item_id": "x"}})
    hook._capture(event)
    assert hook.item is None
    event.agent.cancel.assert_not_called()


def test_calls_with_exceptions_do_not_capture_an_item_but_record_the_exception():
    """No item ever gets captured here (correct — the tool call failed, so
    there's no result to trust), but the exception itself is recorded now,
    not silently discarded: run_intake_workflow uses it to surface an
    actual error message instead of an empty summary with no indication
    anything went wrong."""
    hook = ItemResultHook()
    exc = RuntimeError("boom")
    event = _event("commit_to_inventory", {"item": {"item_id": "x"}}, exception=exc)
    hook._capture(event)
    assert hook.item is None
    assert hook.tool_exception is exc
    event.agent.cancel.assert_not_called()


def test_exception_on_unrelated_tool_call_is_not_recorded():
    hook = ItemResultHook()
    event = _event("search_inventory", {"item": {"item_id": "x"}}, exception=RuntimeError("boom"))
    hook._capture(event)
    assert hook.tool_exception is None


def test_captures_flagged_scan_package_batch_result_and_cancels():
    hook = ItemResultHook()
    flagged_item = {"item_id": "abc", "requires_human_review": True, "review_reason": "low-confidence date"}
    event = _event("scan_package_batch", {"needs_review": True, "item": flagged_item})
    hook._capture(event)
    assert hook.item == flagged_item
    # Fate is fully settled here — no further model call is needed, so the
    # agent should be cancelled right at this checkpoint rather than being
    # allowed to make one purely to narrate what's already known.
    event.agent.cancel.assert_called_once()


def test_ready_for_commit_scan_package_batch_result_does_not_cancel():
    """scan_package_batch's committed-path result is a pre-commit snapshot —
    the agent still needs one more turn to actually call commit_to_inventory,
    so this checkpoint must NOT cancel it."""
    hook = ItemResultHook()
    event = _event("scan_package_batch", {"needs_review": False, "item": {"item_id": "abc"}})
    hook._capture(event)
    assert hook.item is None
    event.agent.cancel.assert_not_called()


def test_commit_to_inventory_overwrites_scan_package_batch_capture_and_cancels():
    hook = ItemResultHook()
    scan_event = _event("scan_package_batch", {"needs_review": True, "item": {"item_id": "stale"}})
    hook._capture(scan_event)

    committed_item = {"item_id": "abc", "requires_human_review": False, "quantity": 1}
    commit_event = _event("commit_to_inventory", {"status": "committed", "item": committed_item})
    hook._capture(commit_event)

    assert hook.item == committed_item
    commit_event.agent.cancel.assert_called_once()


def test_missing_item_key_does_not_clear_previous_capture_or_cancel():
    hook = ItemResultHook()
    committed_item = {"item_id": "abc"}
    hook._capture(_event("commit_to_inventory", {"status": "committed", "item": committed_item}))

    event = _event("commit_to_inventory", {"status": "quantity_updated"})  # no "item" key
    hook._capture(event)

    assert hook.item == committed_item
    event.agent.cancel.assert_not_called()


def test_unparseable_result_is_ignored():
    hook = ItemResultHook()
    bad_event = SimpleNamespace(
        tool_use={"name": "commit_to_inventory"},
        result={"content": [{"text": "not json"}]},
        exception=None,
        agent=MagicMock(),
    )
    hook._capture(bad_event)
    assert hook.item is None
    bad_event.agent.cancel.assert_not_called()


class TestVisibilityLogging:
    """Added to close a silent-failure gap: a request completed with no
    exception anywhere and no indication of whether this hook fired, or
    whether it fired but failed to parse a result — event.exception is not
    None returns completely silently otherwise, with zero trace."""

    @patch("strand_sort.agent.result_hook.logger")
    def test_logs_triggered_for_every_tool_call_including_unrelated_ones(self, mock_logger):
        hook = ItemResultHook()
        hook._capture(_event("search_inventory", {"item": {"item_id": "x"}}))

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("triggered" in msg and "search_inventory" in msg for msg in logged)

    @patch("strand_sort.agent.result_hook.logger")
    def test_logs_triggered_even_when_the_tool_call_raised(self, mock_logger):
        hook = ItemResultHook()
        hook._capture(_event("commit_to_inventory", {"item": {"item_id": "x"}}, exception=RuntimeError("boom")))

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("triggered" in msg and "commit_to_inventory" in msg for msg in logged)

    @patch("strand_sort.agent.result_hook.logger")
    def test_logs_parsed_item_true_when_item_captured(self, mock_logger):
        hook = ItemResultHook()
        flagged_item = {"item_id": "abc", "requires_human_review": True}
        hook._capture(_event("scan_package_batch", {"needs_review": True, "item": flagged_item}))

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("parsed item: True" in msg for msg in logged)

    @patch("strand_sort.agent.result_hook.logger")
    def test_logs_parsed_item_false_when_item_key_missing(self, mock_logger):
        hook = ItemResultHook()
        hook._capture(_event("commit_to_inventory", {"status": "quantity_updated"}))  # no "item" key

        logged = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("parsed item: False" in msg for msg in logged)

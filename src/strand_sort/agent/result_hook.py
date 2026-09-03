import json
from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry
from loguru import logger


class ItemResultHook(HookProvider):
    """
    Captures the full DonationItem dict produced by this intake run, so the
    API layer can return structured data (requires_human_review, image_urls,
    ...) instead of only the agent's prose.

    Whichever tool call actually settles the item's fate wins:
    - scan_package_batch, when it flags the item for review (commit_to_inventory
      is never called in that path per the agent's system prompt).
    - commit_to_inventory, when the item is auto-committed — this fires after
      scan_package_batch and overwrites the captured item with the committed
      record, which is what we want.

    The moment the item's fate is settled, everything a summary needs
    (product_name, category, quantity, dietary_flags, requires_human_review,
    review_reason, ...) is already fully known — a further model call at that
    point would only be generating prose commentary on data that's already
    final, not deciding anything. So this hook also cancels the agent right
    there (`Agent.cancel()` stops "after tool execution, before the next
    model call" — exactly this checkpoint), and run_intake_workflow builds
    the summary from `self.item` via a plain template instead of waiting on
    that now-unnecessary extra turn. This is what actually closes the gap
    where Review/Inventory could show an item as done before the Scan page
    did — that lag was the wait for this decorative turn, not the write.
    """

    def __init__(self):
        self.item: dict | None = None

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterToolCallEvent, self._capture)

    def _capture(self, event: AfterToolCallEvent) -> None:
        tool_name = event.tool_use.get("name")
        if tool_name not in ("scan_package_batch", "commit_to_inventory"):
            return
        if event.exception is not None:
            return

        try:
            text_content = event.result["content"][0]["text"]
            result_data = json.loads(text_content)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.warning(f"Could not parse {tool_name} result for item capture: {e}")
            return

        if tool_name == "scan_package_batch" and not result_data.get("needs_review"):
            return  # committed path — wait for commit_to_inventory's authoritative record

        item = result_data.get("item")
        if item is not None:
            self.item = item
            event.agent.cancel()

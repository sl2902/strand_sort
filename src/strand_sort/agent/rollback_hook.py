import json
from strands.hooks import AfterToolCallEvent, HookProvider, HookRegistry
from loguru import logger


class InventoryRollbackHook(HookProvider):
    def __init__(self):
        self.committed_actions: list[dict] = []

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterToolCallEvent, self._track_commit)

    def _track_commit(self, event: AfterToolCallEvent) -> None:
        tool_name = event.tool_use.get("name")
        if tool_name != "commit_to_inventory":
            return
        if event.exception is not None:
            return

        try:
            text_content = event.result["content"][0]["text"]
            result_data = json.loads(text_content)
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            logger.warning(f"Could not parse commit_to_inventory result for rollback tracking: {e}")
            return

        action = result_data.get("action")
        if action == "incremented_existing_batch":
            self.committed_actions.append({
                "type": "increment",
                "item_id": result_data.get("item_id"),
                "qty": result_data.get("added_quantity"),
            })
        elif action == "created_new_batch":
            self.committed_actions.append({
                "type": "new_batch",
                "item_id": result_data.get("item_id"),
            })
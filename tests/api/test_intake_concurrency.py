import asyncio
import time
from unittest.mock import patch

import httpx
import pytest
from httpx import ASGITransport

from strand_sort.main import app


@pytest.mark.asyncio
async def test_slow_intake_does_not_block_other_requests():
    """
    Regression test for a bug where run_intake_workflow (synchronous, blocks on
    a live model call) was invoked directly inside an `async def` route, which
    stalls FastAPI's single event-loop thread for the whole request — starving
    every other in-flight request, including totally unrelated ones like
    GET /inventory. Asserts on completion ORDER rather than a wall-clock
    threshold: a fixed-duration sleep on the test side is unreliable here,
    since a truly blocking call freezes the single shared thread, silently
    eating into that sleep's own wait window and making a threshold-based
    assertion pass either way. Order is unambiguous: if the event loop is free,
    the fast GET finishes before the slow intake call does; if the loop is
    blocked, nothing can finish before the blocking call releases it.
    """
    completion_order: list[str] = []

    def _slow_workflow(*args, **kwargs):
        time.sleep(0.5)
        completion_order.append("intake")
        return "Item processed.", {
            "item_id": "abc",
            "requires_human_review": False,
            "review_reason": None,
            "image_urls": [],
        }

    with (
        patch("strand_sort.api.intake.run_intake_workflow", side_effect=_slow_workflow),
        patch("strand_sort.api.inventory.get_inventory_repository") as mock_repo_factory,
    ):
        mock_repo_factory.return_value.list_all.return_value = []

        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            intake_task = asyncio.create_task(
                client.post(
                    "/api/v1/intake",
                    json={"s3_keys": ["pending-uploads/egg.jpg"]},
                )
            )
            await asyncio.sleep(0.05)  # let the intake request start before racing it

            inventory_response = await client.get("/api/v1/inventory")
            completion_order.append("inventory")

            intake_response = await intake_task

            assert inventory_response.status_code == 200
            assert intake_response.status_code == 200
            assert completion_order == ["inventory", "intake"], (
                f"expected the fast GET to finish before the slow intake call, got {completion_order} — "
                "the event loop is being blocked by run_intake_workflow."
            )

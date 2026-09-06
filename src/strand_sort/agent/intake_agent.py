from typing import Any

from strands import Agent
from strands.models import BedrockModel
from strands.models.gemini import GeminiModel

import botocore.exceptions
from loguru import logger

from strand_sort.config import settings, BEDROCK_FALLBACK_ERROR_CODES
from strand_sort.gcp_auth import running_on_lambda, get_gcp_credentials
from strand_sort.agent.tools import (
    scan_package_batch,
    commit_to_inventory,
    search_inventory,
    checkout_from_inventory,
)
from strand_sort.agent.result_hook import ItemResultHook


INTAKE_SYSTEM_PROMPT = """
You are the Lead Intake Orchestration Agent for an automated food bank repository.
1. Call scan_package_batch on incoming package images.
2. If needs_review is True: DO NOT call commit_to_inventory.
3. If needs_review is False: call commit_to_inventory to register the item.

Do not write a closing summary message. The moment scan_package_batch (when
flagged) or commit_to_inventory returns, this invocation is cancelled — the
summary shown to the user is generated directly from that tool's result, not
from anything you say afterward, so there is nothing left for you to add.
"""

def _bedrock_model() -> BedrockModel:
    return BedrockModel(
        model_id=settings.bedrock_agent_model_id,
        region_name=settings.aws_region,
        temperature=0,
    )


def _gemini_model() -> GeminiModel:
    client_args = {
        "vertexai": True,
        "project": settings.gcp_project_id,
        "location": settings.gemini_location or settings.gcp_location,
    }
    if running_on_lambda():
        # No ADC credentials file on Lambda — same fix as GeminiExtractor
        # (vision/extract.py), needed here too since this is a SEPARATE
        # genai.Client construction (the agent's own reasoning fallback,
        # distinct from the one inside get_extractor).
        logger.info("Using Secrets-Manager-sourced GCP credentials (Lambda)")
        client_args["credentials"] = get_gcp_credentials()
    else:
        logger.info("Using local ADC for GCP credentials")

    return GeminiModel(
        client_args=client_args,
        model_id=settings.gemini_model_id,
        params={"temperature": 0},
    )

def create_intake_agent(model: BedrockModel | GeminiModel, hooks: list | None = None) -> Agent:
    return Agent(
        model=model,
        system_prompt=INTAKE_SYSTEM_PROMPT,
        tools=[scan_package_batch, commit_to_inventory],
        callback_handler=None,
        hooks=hooks,
    )


def _dietary_highlights(dietary_flags: dict[str, Any]) -> list[str]:
    highlights = []
    if dietary_flags.get("is_vegetarian") is True:
        highlights.append("vegetarian")
    if dietary_flags.get("is_vegan"):
        highlights.append("vegan")
    if dietary_flags.get("is_gluten_free"):
        highlights.append("gluten-free")
    if dietary_flags.get("is_low_sugar"):
        highlights.append("low sugar")
    if dietary_flags.get("is_low_sodium"):
        highlights.append("low sodium")
    return highlights


def format_intake_summary(item: dict[str, Any]) -> str:
    """
    Builds the intake result summary directly from the settled DonationItem
    dict, in place of the second LLM call the agent used to make purely to
    narrate this same data in prose. Every field used here (product_name,
    category, quantity, expiration_date, date_confidence, dietary_flags,
    requires_human_review, review_reason) is already known the instant
    scan_package_batch/commit_to_inventory returns — there's nothing this
    text needs to wait on.
    """
    product_name = item.get("product_name") or "This item"
    category = str(item.get("category") or "").replace("_", " ")
    quantity = item.get("quantity", 1)

    if item.get("requires_human_review"):
        sentence = f"{product_name} has been flagged for human review."
        reason = item.get("review_reason")
        if reason:
            sentence += f" Reason: {reason}."
    else:
        expiration_date = item.get("expiration_date")
        expiry_clause = f", expires {expiration_date}" if expiration_date else ""
        sentence = f"{quantity} x {product_name} ({category}) committed to inventory{expiry_clause}."
        if item.get("date_confidence") == "low":
            sentence += " Note: expiry date confidence was low."

    highlights = _dietary_highlights(item.get("dietary_flags") or {})
    if highlights:
        sentence += f" Dietary flags: {', '.join(highlights)}."

    return sentence


def run_intake_workflow(image_sources: list[str], hooks: list | None = None) -> tuple[str, dict | None]:
    """
    Runs the intake agent and returns (summary_text, item) — item is the full
    DonationItem dict for whichever outcome actually happened (flagged or
    committed), captured via ItemResultHook. As soon as that outcome is
    settled, ItemResultHook cancels the agent (see its docstring) instead of
    letting it make a further, purely decorative model call — so
    summary_text comes from format_intake_summary(item), not the agent's own
    words. That extra call was also the reason a scan could still show
    "pending" on the Scan page after the same item was already visible,
    correctly, on Inventory/Review — this closes that gap.

    Falls back to whatever text the agent did produce if nothing ever
    settled (e.g. a hard failure before either tool call completed), in
    which case item is None.
    """
    # "S3 keys" isn't accurate when storage_backend=local (image_sources are
    # local temp file paths in that mode) — the prompt should match whatever
    # scan_package_batch's own _get_image_bytes actually resolves.
    source_kind = "S3 keys" if settings.storage_backend == "s3" else "local file paths"
    prompt = (
        f"Process this incoming package's images for intake using these {source_kind}: "
        f"{image_sources}"
    )
    item_hook = ItemResultHook()
    agent_hooks = [*(hooks or []), item_hook]

    logger.info("Agent: trying Bedrock first")
    agent = create_intake_agent(_bedrock_model(), hooks=agent_hooks)

    try:
        response = agent(prompt)
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in BEDROCK_FALLBACK_ERROR_CODES:
            logger.warning(f"Agent Bedrock unusable ({error_code}); falling back to Gemini.")
        else:
            logger.error(f"Agent Bedrock call failed with unhandled error code: {error_code}")
            raise

        agent = create_intake_agent(_gemini_model(), hooks=agent_hooks)
        response = agent(prompt)

    if item_hook.item is not None:
        logger.info("Using templated summary from captured item")
        return format_intake_summary(item_hook.item), item_hook.item

    if item_hook.tool_exception is not None:
        # The tool call itself raised (e.g. a DynamoDB ValidationException) —
        # the agent framework treats that as a tool observation, not a
        # raised Python exception, so this path completes "normally" with no
        # item ever settled. Surfacing the actual error here is what makes
        # this class of infrastructure failure visible to whoever's staring
        # at the Scan page, instead of only in CloudWatch.
        logger.warning(f"Tool call raised, no item captured: {item_hook.tool_exception}")
        return f"Processing failed: {item_hook.tool_exception}", None

    logger.warning("No item captured by hook — falling back to raw agent response text")
    text_parts = [
        block["text"]
        for block in response.message.get("content", [])
        if "text" in block
    ]
    return "".join(text_parts), None

def create_fulfillment_agent(model: BedrockModel | GeminiModel) -> Agent:
    """Agent specialized in checking out items for food bank distribution"""
    return Agent(
        model=model,
        system_prompt="""
        You are the Distribution Agent for the food bank.
        1. Search inventory using search_inventory or fetch item details.
        2. Execute checkout_from_inventory when a distribution request is confirmed.
        3. If checkout returns an error (such as insufficient stock), report it clearly.
        """,
        tools=[search_inventory, checkout_from_inventory],
        callback_handler=None,
    )

from strands import Agent
from strands.models import BedrockModel
from strands.models.gemini import GeminiModel

import botocore.exceptions
from loguru import logger

from strand_sort.config import settings, BEDROCK_FALLBACK_ERROR_CODES
from strand_sort.agent.tools import scan_package_batch, commit_to_inventory

INTAKE_SYSTEM_PROMPT = """
You are the Lead Intake Orchestration Agent for an automated food bank repository.
1. Call scan_package_batch on incoming package images.
2. If needs_review is True: DO NOT call commit_to_inventory. Report the item
   as flagged for human review, including review_reason.
3. If needs_review is False: call commit_to_inventory to register the item.
4. Provide a concise summary of the intake result including dietary flags.
"""

def _bedrock_model() -> BedrockModel:
    return BedrockModel(
        model_id=settings.bedrock_agent_model_id,
        region_name=settings.aws_region,
        temperature=0,
    )


def _gemini_model() -> GeminiModel:
    return GeminiModel(
        client_args={
            "vertexai": True,
            "project": settings.gcp_project_id,
            "location": "global" or settings.gcp_location,
        },
        model_id=settings.gemini_model_id,
        params={"temperature": 0},
    )

def create_intake_agent(model: BedrockModel | GeminiModel) -> Agent:
    return Agent(
        model=model,
        system_prompt=INTAKE_SYSTEM_PROMPT,
        tools=[scan_package_batch, commit_to_inventory],
        callback_handler=None,
    )



def run_intake_workflow(image_paths: list[str]) -> str:
    prompt = (
        f"Process this incoming package's images for intake using these file paths: "
        f"{image_paths}"
    )

    logger.info("Agent: trying Bedrock first")
    agent = create_intake_agent(_bedrock_model())

    try:
        return agent(prompt)
    except botocore.exceptions.ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "")
        if error_code in BEDROCK_FALLBACK_ERROR_CODES:
            logger.warning(f"Agent Bedrock unusable ({error_code}); falling back to Gemini.")
        else:
            logger.error(f"Agent Bedrock call failed with unhandled error code: {error_code}")
            raise

    agent = create_intake_agent(_gemini_model())
    return agent(prompt)
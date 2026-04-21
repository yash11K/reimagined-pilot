"""QA Agent — assesses quality, uniqueness, and metadata completeness of extracted files."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent, tool
from strands.models import BedrockModel

from kb_manager.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for structured output
# ---------------------------------------------------------------------------

class QAOutput(BaseModel):
    """Structured output from the QA Agent."""
    quality_verdict: Literal["good", "acceptable", "poor"] = "acceptable"
    quality_reasoning: str = ""
    uniqueness_verdict: Literal["unique", "overlapping", "duplicate"] = "unique"
    uniqueness_reasoning: str = ""
    similar_file_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Dataclass used by the rest of the app
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field

@dataclass
class SimilarDoc:
    file_id: str
    title: str
    score: float

@dataclass
class QAResult:
    quality_verdict: str  # good | acceptable | poor
    quality_reasoning: str
    uniqueness_verdict: str  # unique | overlapping | duplicate
    uniqueness_reasoning: str
    similar_file_ids: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# KB query tool
# ---------------------------------------------------------------------------

@tool
def query_kb(content_snippet: str, limit: int = 3) -> list[dict]:
    """Query the Bedrock knowledge base for similar documents.

    Args:
        content_snippet: A representative snippet of the file content to search for.
        limit: Maximum number of similar documents to return.
    """
    settings = get_settings()
    if not settings.BEDROCK_KB_ID:
        logger.debug("🔍 KB query skipped — BEDROCK_KB_ID not configured")
        return []
    logger.info("🔍 Querying Bedrock KB (id=%s) for similar docs (limit=%d)",
                settings.BEDROCK_KB_ID, limit)
    # Stub: real implementation will call Bedrock KB retrieve API
    return []


SYSTEM_PROMPT = (
    "You are a quality assurance agent for knowledge base files extracted from AEM websites. "
    "You will receive the markdown content AND metadata as separate inputs.\n\n"
    "Assess the provided markdown file on two independent axes:\n\n"
    "1. QUALITY — assess based on content completeness and structure:\n"
    "   - good: 300+ words of substantive content, well-structured with headings, "
    "coherent and informative. Includes details like pricing, features, terms, or regional data.\n"
    "   - acceptable: useful content but thin (under 300 words) or poorly structured. "
    "Still contains real information a customer would find helpful.\n"
    "   - poor: near-empty, gibberish, pure navigation/breadcrumbs with no real content, "
    "or only boilerplate text with no product/service information.\n\n"
    "2. UNIQUENESS — use the query_kb tool to search for similar docs, then classify:\n"
    "   - unique: no meaningful overlap with existing KB content.\n"
    "   - overlapping: partial overlap but adds new information not in existing docs.\n"
    "   - duplicate: near-identical content already exists in the KB.\n\n"
    "IMPORTANT UNIQUENESS RULES:\n"
    "- A detail page is NOT a duplicate of a listing page that contains a teaser for it. "
    "The detail page is the canonical source; the listing page teaser is the summary.\n"
    "- If a file has a specific source_url pointing to a detail sub-page (e.g. /products/mobile-wifi), "
    "it should be considered unique even if a parent listing page mentions the same product briefly.\n"
    "- Only mark as 'duplicate' if another file covers the SAME topic with the SAME level of detail."
)


class QAAgent:
    """Assesses quality and uniqueness of extracted markdown files using Haiku."""

    def __init__(self) -> None:
        settings = get_settings()
        logger.info("🧪 Initialising QA Agent (model=%s)", settings.HAIKU_MODEL_ID)
        model = BedrockModel(
            model_id=settings.HAIKU_MODEL_ID,
            max_tokens=settings.HAIKU_MAX_TOKENS,
        )
        self._agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
            tools=[query_kb],
        )

    async def run(
        self,
        md_content: str,
        metadata: dict[str, str | None] | None = None,
    ) -> QAResult:
        """Assess quality and uniqueness of a markdown file.

        Args:
            md_content: Pure markdown content (no YAML frontmatter).
            metadata: Dict with title, source_url, region, brand for context.
        """
        content_len = len(md_content)
        logger.info("🧪 QA Agent running — content_length=%d chars", content_len)
        parts = ["Assess this markdown file.\n"]
        if metadata:
            parts.append("Metadata:\n" + "\n".join(
                f"  {k}: {v}" for k, v in metadata.items() if v
            ) + "\n")
        parts.append(f"```markdown\n{md_content}\n```")
        prompt = "\n".join(parts)
        result = await self._agent.invoke_async(
            prompt, structured_output_model=QAOutput,
        )

        output: QAOutput | None = getattr(result, "structured_output", None)
        if output is None:
            logger.warning("⚠️ QA Agent returned no structured output, using defaults")
            return QAResult(
                quality_verdict="acceptable",
                quality_reasoning="Failed to get structured output from agent",
                uniqueness_verdict="unique",
                uniqueness_reasoning="Failed to get structured output from agent",
                similar_file_ids=[],
            )

        qa = QAResult(
            quality_verdict=output.quality_verdict,
            quality_reasoning=output.quality_reasoning,
            uniqueness_verdict=output.uniqueness_verdict,
            uniqueness_reasoning=output.uniqueness_reasoning,
            similar_file_ids=output.similar_file_ids or [],
        )
        logger.info("🧪 QA Agent finished — quality=%s, uniqueness=%s",
                     qa.quality_verdict, qa.uniqueness_verdict)
        return qa

"""Link Triage Agent — classifies discovered links as expansion, sibling, navigation, or uncertain."""

from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel
from strands import Agent
from strands.models import BedrockModel

from kb_manager.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for structured output
# ---------------------------------------------------------------------------

class TriageOutput(BaseModel):
    """Structured output from the Link Triage Agent."""
    classification: Literal["expansion", "sibling", "navigation", "uncertain"] = "uncertain"
    reason: str = ""
    has_sub_links: bool = False
    sub_link_count: int = 0


# ---------------------------------------------------------------------------
# Dataclass used by the rest of the app
# ---------------------------------------------------------------------------

from dataclasses import dataclass

@dataclass
class TriageResult:
    classification: str  # expansion | sibling | navigation | uncertain
    reason: str
    has_sub_links: bool
    sub_link_count: int


SYSTEM_PROMPT = (
    "You are a link triage agent for AEM website content ingestion. Given the source "
    "context (the card/teaser text where the link was found) and the linked page's "
    "pruned AEM JSON structure, classify the link.\n\n"
    "CLASSIFICATIONS:\n"
    "- expansion: The linked page provides MORE DETAIL about a topic introduced on the "
    "source page. Typical pattern: a listing page has a teaser card with 'Learn More' "
    "linking to a full detail page. The detail page has its own hero banner, content "
    "modules, and possibly accordion sections with terms/conditions or regional data.\n"
    "- sibling: The linked page covers a DIFFERENT but related topic at the same level. "
    "Not a sub-page of the source, but a peer page in the same section.\n"
    "- navigation: The link is purely structural — breadcrumbs, header/footer nav, "
    "homepage links, section index pages with no unique content.\n"
    "- uncertain: Cannot determine the relationship from the available context.\n\n"
    "IMPORTANT:\n"
    "- A link back to the SAME page (self-link) should be classified as 'navigation'.\n"
    "- Links to the site homepage (/en/home or /) should be classified as 'navigation'.\n"
    "- 'Learn More' CTAs on content cards almost always point to expansion pages.\n\n"
    "Also report whether the linked page has sub-links (ctaLink fields pointing to "
    "further detail pages) and how many."
)


class LinkTriageAgent:
    """Classifies a discovered link using Haiku."""

    def __init__(self) -> None:
        settings = get_settings()
        logger.info("🏷️ Initialising Link Triage Agent (model=%s)", settings.HAIKU_MODEL_ID)
        model = BedrockModel(
            model_id=settings.HAIKU_MODEL_ID,
            max_tokens=settings.HAIKU_MAX_TOKENS,
        )
        self._agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
        )

    async def run(self, source_context: str, linked_structure: dict) -> TriageResult:
        """Classify a link based on source context and linked page structure."""
        logger.debug("🏷️ Classifying link — context_len=%d, structure_keys=%d",
                      len(source_context), len(linked_structure))
        prompt = (
            "Classify this link.\n\n"
            f"Source context:\n{source_context}\n\n"
            f"Linked page structure:\n```json\n{json.dumps(linked_structure, indent=2)}\n```"
        )
        result = await self._agent.invoke_async(
            prompt, structured_output_model=TriageOutput,
        )

        output: TriageOutput | None = getattr(result, "structured_output", None)
        if output is None:
            logger.warning("⚠️ Link Triage Agent returned no structured output, defaulting to uncertain")
            return TriageResult(
                classification="uncertain",
                reason="Failed to get structured output from agent",
                has_sub_links=False,
                sub_link_count=0,
            )

        triage = TriageResult(
            classification=output.classification,
            reason=output.reason,
            has_sub_links=output.has_sub_links,
            sub_link_count=output.sub_link_count,
        )
        logger.info("🏷️ Link classified as: %s — %s", triage.classification, triage.reason)
        return triage

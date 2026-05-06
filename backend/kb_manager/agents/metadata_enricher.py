"""Metadata Enricher Agent — uses Haiku to derive rich metadata from raw content.

Given raw FAQ/article content, produces a structured metadata envelope
(title, filename, brand, category, tags, visibility) that matches the
same schema the ExtractorAgent produces for AEM pages.

Uses Strands structured_output_model for type-safe extraction with
a JSON-parsing fallback for resilience.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from strands import Agent

from kb_manager.agents._models import get_bedrock_model
from kb_manager.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for structured output (Strands tool-based extraction)
# ---------------------------------------------------------------------------

class EnrichedMetadataOutput(BaseModel):
    """Structured metadata for a knowledge base article."""

    title: str = Field(
        description="Clean, concise title. For Q&A content strip 'Q:' prefix. Max ~80 chars.",
    )
    filename: str = Field(
        description="URL-safe slug for S3 key, e.g. 'refueling-policies-and-fees'. "
        "Lowercase, hyphens only, no extension. Max 60 chars.",
    )
    brand: Literal["avis", "budget", "avis_budget", "unknown"] = Field(
        description="Brand the content belongs to. Use 'avis_budget' when content "
        "applies to both brands.",
    )
    category: Literal[
        "faq", "policy", "product", "service", "promotion", "help", "general"
    ] = Field(
        description="Content category. Pick the single best fit.",
    )
    visibility: Literal["public", "internal"] = Field(
        default="public",
        description="'internal' if the content contains agent-only context/instructions "
        "that should not be shown to customers. Otherwise 'public'.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="3-6 lowercase hyphenated keyword tags describing the content, "
        "e.g. ['fuel', 'refueling', 'charges', 'gas-station'].",
    )


# ---------------------------------------------------------------------------
# Dataclass used by the rest of the app
# ---------------------------------------------------------------------------

@dataclass
class EnrichedMetadata:
    title: str
    filename: str
    brand: str
    category: str
    visibility: str = "public"
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = (
    "You are a metadata extraction API for a car-rental knowledge base.\n"
    "You receive raw FAQ or article content and return a single JSON object.\n\n"
    "OUTPUT FORMAT — you MUST respond with ONLY a JSON object, no text before or after:\n"
    "```\n"
    "{\n"
    '  "title": "string — concise topic, max 80 chars, strip Q:/Question: prefixes",\n'
    '  "filename": "string — URL-safe slug, lowercase, hyphens only, no extension, max 60 chars",\n'
    '  "brand": "avis | budget | avis_budget | unknown",\n'
    '  "category": "faq | policy | product | service | promotion | help | general",\n'
    '  "visibility": "public | internal",\n'
    '  "tags": ["3-6 lowercase hyphenated keywords"]\n'
    "}\n"
    "```\n\n"
    "FIELD RULES:\n"
    "- title: Extract the core question or topic. Remove Q:/Question:/A:/Answer: prefixes.\n"
    "- filename: Derive from title. Example: 'Refueling Policies and Fees' → 'refueling-policies-and-fees'.\n"
    "- brand: Infer from content — 'avis' for Avis Preferred®/Avis app mentions, "
    "'budget' for FastBreak®/Budget Bucks, 'avis_budget' if both apply, 'unknown' only if impossible.\n"
    "- category: 'faq' for Q&A, 'policy' for rules/terms, 'product' for features, "
    "'service' for offerings, 'promotion' for deals/rewards, 'help' for how-to, 'general' as last resort.\n"
    "- visibility: 'internal' if content has agent-facing instructions (Context: lines, coaching notes). "
    "'public' otherwise.\n"
    "- tags: Include brand name. Focus on topic-specific keywords, not generic words.\n\n"
    "EXAMPLE INPUT:\n"
    "Q: How do I earn Budget Bucks?\n"
    "A: Enroll with your Budget Fastbreak® number and complete two paid rentals...\n\n"
    "EXAMPLE OUTPUT:\n"
    '{"title": "How to Earn Budget Bucks", "filename": "how-to-earn-budget-bucks", '
    '"brand": "budget", "category": "promotion", "visibility": "public", '
    '"tags": ["budget", "budget-bucks", "loyalty-program", "rental-rewards"]}\n\n'
    "CRITICAL: Output the raw JSON object only. No markdown fences, no explanation, no preamble."
)


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class MetadataEnricher:
    """Derives rich metadata from raw content using Haiku.

    Creates a fresh Agent per call to avoid conversation history bleed
    across concurrent invocations (Strands agents are stateful).
    Uses structured_output_model at the Agent init level per Strands
    best practices, with a JSON-parsing fallback for resilience.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._model_id = settings.HAIKU_MODEL_ID
        self._max_tokens = settings.HAIKU_MAX_TOKENS
        logger.info(
            "🏷️  Initialising MetadataEnricher (model=%s)", self._model_id
        )

    def _make_agent(self) -> Agent:
        """Create a fresh, stateless agent for a single invocation."""
        return Agent(
            model=get_bedrock_model(self._model_id, self._max_tokens),
            system_prompt=SYSTEM_PROMPT,
        )

    async def run(
        self,
        content: str,
        *,
        tags_hint: str | None = None,
        display_name: str | None = None,
    ) -> EnrichedMetadata:
        """Enrich a single piece of content.

        Args:
            content: Raw FAQ / article text.
            tags_hint: Original tags string from the source (e.g. 'avis, deeplink').
            display_name: Optional display name / title hint from the source.

        Returns:
            EnrichedMetadata with LLM-derived fields.
        """
        parts = ["Extract metadata from this content."]
        if display_name:
            parts.append(f"Display name hint: {display_name}")
        if tags_hint:
            parts.append(f"Tags hint: {tags_hint}")
        parts.append(f"\n{content}")

        prompt = "\n".join(parts)
        agent = self._make_agent()

        try:
            result = await agent.invoke_async(prompt)
        except Exception as exc:
            logger.warning("⚠️ MetadataEnricher invoke failed: %s", exc)
            return self._fallback(display_name)

        # Strands structured_output (works on newer SDK versions)
        output = getattr(result, "structured_output", None)
        if output is not None:
            logger.debug("🏷️  Structured output parsed via Strands tool")
            return self._to_dataclass(output)

        # Parse JSON from the raw text response
        raw_text = str(result).strip() if result else ""
        output = self._parse_json_response(raw_text)
        if output is not None:
            logger.debug("🏷️  Parsed metadata from JSON text response")
            return self._to_dataclass(output)

        logger.warning(
            "⚠️ MetadataEnricher could not extract metadata — using fallbacks. "
            "Preview=%.200s", raw_text,
        )
        return self._fallback(display_name)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fallback(display_name: str | None) -> EnrichedMetadata:
        return EnrichedMetadata(
            title=display_name or "Untitled",
            filename="untitled",
            brand="unknown",
            category="general",
        )

    @staticmethod
    def _to_dataclass(output: EnrichedMetadataOutput) -> EnrichedMetadata:
        return EnrichedMetadata(
            title=output.title,
            filename=output.filename,
            brand=output.brand,
            category=output.category,
            visibility=output.visibility,
            tags=output.tags or [],
        )

    @staticmethod
    def _parse_json_response(text: str) -> EnrichedMetadataOutput | None:
        """Extract and validate JSON from the LLM's raw text response."""
        # 1. Direct parse
        try:
            return EnrichedMetadataOutput(**json.loads(text))
        except (json.JSONDecodeError, ValidationError):
            pass

        # 2. Markdown code block
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                return EnrichedMetadataOutput(**json.loads(m.group(1)))
            except (json.JSONDecodeError, ValidationError):
                pass

        # 3. First JSON object in text (handles nested arrays/objects)
        depth = 0
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start >= 0:
                    try:
                        return EnrichedMetadataOutput(**json.loads(text[start : i + 1]))
                    except (json.JSONDecodeError, ValidationError):
                        start = -1
                        continue

        return None

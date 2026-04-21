"""Extractor Agent — converts content components into markdown files with metadata."""

from __future__ import annotations

import json
import logging
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from strands import Agent
from strands.models import BedrockModel

from kb_manager.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic model for structured output
# ---------------------------------------------------------------------------

class ExtractedFileOutput(BaseModel):
    title: str = ""
    md_content: str = ""
    source_url: Optional[str] = None
    content_type: Optional[str] = None
    region: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    visibility: Optional[str] = None
    tags: list[str] = Field(default_factory=list)


class ExtractionOutput(BaseModel):
    """Structured output from the Extractor Agent."""
    files: list[ExtractedFileOutput] = Field(default_factory=list)

    @field_validator("files", mode="before")
    @classmethod
    def _coerce_files_to_list(cls, v):
        """LLMs sometimes return a single dict instead of a list — wrap it."""
        if isinstance(v, dict):
            return [v]
        return v


# ---------------------------------------------------------------------------
# Dataclass used by the rest of the app
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class ExtractedFile:
    title: str
    md_content: str
    source_url: str | None = None
    content_type: str | None = None
    region: str | None = None
    brand: str | None = None
    category: str | None = None
    visibility: str | None = None
    tags: list[str] = field(default_factory=list)


SYSTEM_PROMPT = (
    "You are a content extraction agent for AEM (Adobe Experience Manager) pages. "
    "Your job is to convert AEM JSON content into clean, complete markdown documents.\n\n"
    "CRITICAL RULES:\n"
    "1. PRESERVE ALL TEXT VERBATIM — do not rephrase, summarise, shorten, or omit any text. "
    "Every word from the source must appear in the output.\n"
    "2. PRESERVE ALL HYPERLINKS as [text](url) markdown.\n"
    "3. PRESERVE ALL HTML CONTENT — convert HTML tables to markdown tables, HTML lists to "
    "markdown lists, HTML bold/italic to markdown equivalents. Do not drop HTML content.\n"
    "4. ACCORDION CONTENT — AEM accordion modules (accordionmodule/accordionitem) contain "
    "critical content in their 'body' field, often as HTML. Extract ALL accordion items "
    "with their titles as subheadings and their full body content converted to markdown.\n"
    "5. CONTENT MODULES — extract headline + bodyText from every contentmodule component.\n"
    "6. HERO BANNERS — extract heroHeadline and heroDescription.\n"
    "7. BREADCRUMBS — extract as a breadcrumb trail.\n\n"
    "OUTPUT FORMAT:\n"
    "Output PURE MARKDOWN only. Do NOT include YAML frontmatter (no --- blocks).\n"
    "Start directly with the content heading. Metadata (title, source_url, region, brand, "
    "category, visibility, tags) is handled separately — populate the structured output "
    "fields instead.\n\n"
    "METADATA FIELDS — populate these based on the page content:\n"
    "- title: The main heading or page title\n"
    "- source_url: The page URL (without .model.json suffix)\n"
    "- region: Geographic region code (e.g. 'US', 'CA', 'AU', 'NZ', 'EU'). "
    "Infer from URL path or content.\n"
    "- brand: Brand name (e.g. 'Avis', 'Budget'). Infer from URL domain or content.\n"
    "- category: Content category — one of: 'faq', 'product', 'policy', 'service', "
    "'promotion', 'location', 'help', 'general'. Pick the best fit based on content.\n"
    "- visibility: Access level — 'public' for customer-facing content, 'internal' for "
    "employee/partner content. Default to 'public' if unclear.\n"
    "- tags: List of 3-5 descriptive keyword tags for the content (e.g. ['car-sales', "
    "'used-cars', 'purchase', 'faq']). Use lowercase, hyphenated terms.\n\n"
    "Each AEM page should produce exactly ONE markdown file containing ALL content from "
    "that page. Do not split a single page into multiple files.\n\n"
    "OUTPUT SHAPE — STRICT:\n"
    "The top-level output object has a single field `files` which MUST be a JSON "
    "array (list), even when there is only one file. Never return a bare object for "
    "`files`.\n"
    "CORRECT (one file):\n"
    '  { "files": [ { "title": "...", "md_content": "...", ... } ] }\n'
    "INCORRECT (do NOT do this):\n"
    '  { "files": { "title": "...", "md_content": "...", ... } }\n'
    "The array must contain exactly one element per AEM page processed. Wrap the "
    "single file in `[ ... ]`.\n\n"
    "If a steering prompt is provided, follow its guidance on what to focus on or skip."
)


class ExtractorAgent:
    """Extracts markdown files from content components using Sonnet."""

    def __init__(self) -> None:
        settings = get_settings()
        logger.info("📝 Initialising Extractor Agent (model=%s)", settings.BEDROCK_MODEL_ID)
        model = BedrockModel(
            model_id=settings.BEDROCK_MODEL_ID,
            max_tokens=settings.BEDROCK_MAX_TOKENS,
        )
        self._agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
        )

    async def run(
        self,
        components: list[dict],
        steering_prompt: str | None = None,
    ) -> list[ExtractedFile]:
        """Extract markdown files from content components."""
        logger.info("📝 Extractor Agent running — %d components, steering=%s",
                     len(components), bool(steering_prompt))
        parts = [
            "Extract markdown files from these components. Return the result as "
            "`{ \"files\": [ { ... } ] }` — `files` MUST be a JSON array even for "
            "a single file. Do not return a bare object.\n\n"
            f"Components:\n```json\n{json.dumps(components, indent=2)}\n```"
        ]
        if steering_prompt:
            parts.append(f"\nSteering prompt: {steering_prompt}")

        prompt = "\n".join(parts)
        result = await self._agent.invoke_async(
            prompt, structured_output_model=ExtractionOutput,
        )

        output: ExtractionOutput | None = getattr(result, "structured_output", None)
        if output is None:
            logger.warning("⚠️ Extractor Agent returned no structured output, returning empty list")
            return []

        files = [
            ExtractedFile(
                title=f.title,
                md_content=f.md_content,
                source_url=f.source_url,
                content_type=f.content_type,
                region=f.region,
                brand=f.brand,
                category=f.category,
                visibility=f.visibility,
                tags=f.tags or [],
            )
            for f in output.files
            if f.title or f.md_content
        ]

        logger.info("📝 Extractor Agent finished — %d files extracted", len(files))
        return files

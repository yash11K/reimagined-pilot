"""Discovery Agent — walks pruned AEM JSON to identify components and classify links."""

from __future__ import annotations

import json
import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator
from strands import Agent
from strands.models import BedrockModel

from kb_manager.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic models for structured output
# ---------------------------------------------------------------------------

class ComponentLink(BaseModel):
    url: str = ""
    anchor_text: Optional[str] = None


class ComponentOutput(BaseModel):
    id: str = ""
    component_type: str = ""
    title: Optional[str] = None
    text_snippet: Optional[str] = None
    links: list[ComponentLink] = Field(default_factory=list)


class ClassifiedLinkOutput(BaseModel):
    """A link with its classification decided by the Discovery Agent."""
    url: str = ""
    anchor_text: Optional[str] = None
    context: Optional[str] = None
    classification: Literal["certain", "uncertain", "navigation"] = "uncertain"
    reason: str = ""


class DiscoveryOutput(BaseModel):
    """Structured output from the Discovery Agent."""
    components: list[ComponentOutput] = Field(default_factory=list)
    classified_links: list[ClassifiedLinkOutput] = Field(default_factory=list)

    @field_validator("components", mode="before")
    @classmethod
    def _coerce_components_to_list(cls, v):
        """LLMs sometimes return a single dict instead of a list — wrap it."""
        if isinstance(v, dict):
            return [v]
        return v

    @field_validator("classified_links", mode="before")
    @classmethod
    def _coerce_links_to_list(cls, v):
        if isinstance(v, dict):
            return [v]
        return v


# ---------------------------------------------------------------------------
# Dataclasses used by the rest of the app
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field


@dataclass
class Component:
    id: str
    component_type: str
    title: str | None = None
    text_snippet: str | None = None
    links: list[str] = field(default_factory=list)


@dataclass
class RawLink:
    url: str
    anchor_text: str | None = None
    context: str | None = None


@dataclass
class ClassifiedLink:
    url: str
    anchor_text: str | None = None
    context: str | None = None
    classification: str = "uncertain"   # certain | uncertain | navigation
    reason: str = ""


@dataclass
class DiscoveryResult:
    components: list[Component] = field(default_factory=list)
    classified_links: list[ClassifiedLink] = field(default_factory=list)


SYSTEM_PROMPT = (
    "You are a content discovery and link classification agent specialising in AEM "
    "(Adobe Experience Manager) JSON structures.\n\n"
    "You receive TWO inputs:\n"
    "1. The pruned AEM JSON tree for a page\n"
    "2. A list of PRE-EXTRACTED LINKS found deterministically from that JSON\n\n"
    "Your job has TWO parts:\n\n"
    "═══ PART 1: COMPONENT EXTRACTION ═══\n"
    "Walk the pruned AEM JSON tree recursively through :items objects and extract "
    "content components.\n"
    "For each content node that has actual text, extract:\n"
    "- id: the node's 'id' field\n"
    "- component_type: from the ':type' field\n"
    "- title: from 'title', 'headline', 'heroHeadline', or 'header' fields\n"
    "- text_snippet: the first 200 chars of body text (from 'bodyText', 'description', "
    "'body', 'bodyContent', 'heroDescription'). Preserve verbatim.\n"
    "- links: all outbound URLs found in that node\n\n"
    "Skip purely structural containers (containers with no text, only children references).\n\n"
    "═══ PART 2: LINK CLASSIFICATION ═══\n"
    "For each link in the pre-extracted links list, classify it by examining the "
    "surrounding context in the AEM JSON.\n\n"
    "CLASSIFICATIONS (only three options):\n"
    "- certain: The link points to a CONTENT PAGE that is worth ingesting. It has "
    "meaningful content — FAQ detail pages, product detail pages, service descriptions, "
    "policy pages, help articles, etc. Typical signals:\n"
    "  • 'Learn More' CTAs on content cards pointing to detail sub-pages\n"
    "  • Links to FAQ category pages or individual FAQ topics\n"
    "  • Links to informational pages about services, policies, or features\n"
    "  • Any link where the target page likely has substantive text content\n"
    "- navigation: The link is purely structural or transactional — NOT content worth "
    "ingesting. Signals:\n"
    "  • Breadcrumbs, header/footer nav, homepage links\n"
    "  • Links to /reservation, /login, /account, /search, /booking, /checkout\n"
    "  • Links to external domains (non-AEM content)\n"
    "  • Section index pages with no unique content of their own\n"
    "  • Promotional/deal links that are time-sensitive offers\n"
    "- uncertain: Cannot confidently determine if the link has content worth ingesting. "
    "Use this when the context is ambiguous.\n\n"
    "CRITICAL RULES FOR THE `classified_links` OUTPUT:\n"
    "1. You MUST return one entry for EVERY link in the PRE-EXTRACTED LINKS list. "
    "Do not skip any.\n"
    "2. You MUST NOT invent, synthesise, paraphrase, or add any URL that is not "
    "verbatim present in the PRE-EXTRACTED LINKS list. No cross-domain guesses. "
    "No related pages. No anchor text in the url field.\n"
    "3. The `url` field must be copied byte-for-byte from the PRE-EXTRACTED LINKS "
    "entry you are classifying. If you cannot copy it verbatim, do not include it.\n"
    "4. The number of items in `classified_links` must equal the number of "
    "PRE-EXTRACTED LINKS exactly — no more, no fewer.\n\n"
    "Return your output as:\n"
    "- components: list of extracted components\n"
    "- classified_links: list of links with classification and reason"
)


class DiscoveryAgent:
    """Discovers content components and classifies links from pruned AEM JSON."""

    def __init__(self) -> None:
        settings = get_settings()
        logger.info("🔎 Initialising Discovery Agent (model=%s)", settings.HAIKU_MODEL_ID)
        model = BedrockModel(
            model_id=settings.HAIKU_MODEL_ID,
            max_tokens=settings.HAIKU_MAX_TOKENS,
        )
        self._agent = Agent(
            model=model,
            system_prompt=SYSTEM_PROMPT,
        )

    async def run(
        self,
        pruned_json: dict,
        pre_extracted_links: list[dict] | None = None,
    ) -> DiscoveryResult:
        """Analyse pruned AEM JSON with pre-extracted links.

        Args:
            pruned_json: The pruned AEM JSON tree.
            pre_extracted_links: List of dicts with keys: url, anchor_text, context.
        """
        json_size = len(json.dumps(pruned_json))
        link_count = len(pre_extracted_links) if pre_extracted_links else 0
        logger.info(
            "🔎 Discovery Agent running on %d bytes of pruned JSON with %d pre-extracted links",
            json_size, link_count,
        )

        links_section = ""
        if pre_extracted_links:
            links_block = json.dumps(pre_extracted_links, indent=2)
            links_section = (
                f"\n\n═══ PRE-EXTRACTED LINKS ({link_count} found) ═══\n"
                "These links were extracted deterministically from the JSON. "
                "Classify EACH one as 'certain', 'uncertain', or 'navigation'.\n\n"
                f"```json\n{links_block}\n```"
            )

        prompt = (
            "Analyse the following pruned AEM JSON. Extract all content components "
            "and classify each pre-extracted link.\n\n"
            f"═══ PRUNED AEM JSON ═══\n```json\n{json.dumps(pruned_json, indent=2)}\n```"
            f"{links_section}"
        )

        result = await self._agent.invoke_async(
            prompt, structured_output_model=DiscoveryOutput,
        )

        output: DiscoveryOutput | None = getattr(result, "structured_output", None)
        if output is None:
            logger.warning("⚠️ Discovery Agent returned no structured output, returning empty result")
            return DiscoveryResult()

        components = [
            Component(
                id=c.id,
                component_type=c.component_type,
                title=c.title,
                text_snippet=c.text_snippet,
                links=[lk.url for lk in c.links if lk.url],
            )
            for c in output.components
        ]

        # --- Link classification (trust only the pre-extracted set) ---
        # The Discovery Agent is prone to two failure modes:
        #   1. Hallucinating URLs that were never in the input (e.g. cross-domain
        #      avis.ca/com.au links, or made-up paths).
        #   2. Returning anchor text in the `url` field (e.g. "Your Avis account
        #      is already linked...").
        # We defend against both by keying the final output off the pre-extracted
        # set — the agent's job is only to *classify* URLs from that set, not
        # invent new ones. Anything outside the set is dropped with a metric.
        valid_urls: set[str] = set()
        pel_by_url: dict[str, dict] = {}
        if pre_extracted_links:
            for pel in pre_extracted_links:
                url = pel.get("url")
                if url:
                    valid_urls.add(url)
                    pel_by_url[url] = pel

        classified_links: list[ClassifiedLink] = []
        seen_urls: set[str] = set()
        hallucinated_count = 0

        for cl in output.classified_links:
            if not cl.url:
                continue
            if cl.url not in valid_urls:
                hallucinated_count += 1
                logger.warning(
                    "⚠️ Discovery Agent returned URL not in pre-extracted set "
                    "(hallucinated or anchor-text leak) — dropping: %r",
                    cl.url[:120],
                )
                continue
            if cl.url in seen_urls:
                # Duplicate classification from agent — keep the first, drop rest
                continue
            seen_urls.add(cl.url)
            # Enrich with context from pre-extracted entry in case agent dropped it
            pel = pel_by_url.get(cl.url, {})
            classified_links.append(ClassifiedLink(
                url=cl.url,
                anchor_text=cl.anchor_text or pel.get("anchor_text"),
                context=cl.context or pel.get("context"),
                classification=cl.classification,
                reason=cl.reason,
            ))

        # Safety net: any pre-extracted link the LLM missed gets added as uncertain
        fallback_count = 0
        if pre_extracted_links:
            for pel in pre_extracted_links:
                url = pel.get("url")
                if url and url not in seen_urls:
                    fallback_count += 1
                    logger.warning(
                        "⚠️ Discovery Agent missed link %s — adding as uncertain",
                        url[:60],
                    )
                    classified_links.append(ClassifiedLink(
                        url=url,
                        anchor_text=pel.get("anchor_text"),
                        context=pel.get("context"),
                        classification="uncertain",
                        reason="Not classified by agent — added as fallback",
                    ))
                    seen_urls.add(url)

        logger.info(
            "🔎 Discovery Agent finished — %d components, %d classified links "
            "(hallucinated_dropped=%d, fallback_uncertain=%d)",
            len(components), len(classified_links), hallucinated_count, fallback_count,
        )
        return DiscoveryResult(components=components, classified_links=classified_links)

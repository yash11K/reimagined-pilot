"""QA & Uniqueness agents — assess ingestion worthiness and KB overlap of extracted files.

Two independent Strands agents:
  • QAAgent — decides whether a markdown file is worth ingesting as a standalone KB article.
  • UniquenessAgent — compares the file against existing KB content and classifies overlap.

Both agents share a single `QAResult` dataclass consumed by the routing matrix and pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent, tool

from kb_manager.agents._models import get_bedrock_model
from kb_manager.config import get_settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared result dataclass (consumed by pipeline + routing matrix)
# ---------------------------------------------------------------------------

@dataclass
class QAResult:
    """Combined output from the QA and Uniqueness agents."""

    quality_verdict: str          # accepted | rejected
    quality_reasoning: str
    uniqueness_verdict: str       # unique | overlapping | conflicting
    uniqueness_reasoning: str
    similar_file_ids: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════
# QA Agent — ingestion worthiness
# ═══════════════════════════════════════════════════════════════════════════

class QAOutput(BaseModel):
    """Structured output from the QA Agent."""

    verdict: Literal["accepted", "rejected"] = "accepted"
    reasoning: str = ""


QA_SYSTEM_PROMPT = """\
You are a strict quality-gate agent for a customer-facing knowledge base.

Your sole job is to decide whether a given markdown file is worth ingesting \
into the knowledge base as a standalone article. You are NOT judging writing \
style or grammar — you are judging whether the content carries real, \
actionable information that would help a customer or support agent.

## Decision criteria

ACCEPT the file when ALL of the following are true:
  • The content is coherent and readable as a standalone document.
  • It contains substantive information — product details, service terms, \
pricing, how-to steps, policy explanations, regional specifics, or similar.
  • A customer or support agent would gain value from finding this article.

REJECT the file when ANY of the following are true:
  • The content is mostly navigation elements, breadcrumbs, or site chrome \
with no real information.
  • It is gibberish, garbled encoding artefacts, or placeholder/lorem-ipsum text.
  • It is a near-empty stub (e.g. just a title and one generic sentence).
  • It duplicates boilerplate that appears on every page (footers, cookie \
banners, legal disclaimers that are not the primary content).
  • It is a pure listing/index page with only links and no explanatory content.

## Output rules
  • Return exactly one verdict: "accepted" or "rejected".
  • Provide a concise reasoning (1-3 sentences) explaining your decision.
  • Focus on WHAT the content is about and WHY it does or does not qualify — \
do not comment on length alone.
"""


class QAAgent:
    """Decides whether a markdown file is worth ingesting into the KB.

    Builds a fresh Strands ``Agent`` per ``run()`` invocation so conversation
    history from prior files cannot bleed into the next file's verdict.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._model_id = settings.HAIKU_MODEL_ID
        self._max_tokens = settings.HAIKU_MAX_TOKENS
        logger.info("🧪 Initialising QA Agent (model=%s)", self._model_id)

    def _build_agent(self) -> Agent:
        """Create a fresh, stateless agent for a single invocation."""
        return Agent(
            model=get_bedrock_model(self._model_id, self._max_tokens),
            system_prompt=QA_SYSTEM_PROMPT,
        )

    async def run(
        self,
        md_content: str,
        metadata: dict[str, str | None] | None = None,
    ) -> QAOutput:
        """Assess whether *md_content* is worth ingesting.

        Args:
            md_content: Pure markdown content (no YAML frontmatter).
            metadata: Optional dict with title, source_url, region, brand.
        """
        content_len = len(md_content)
        logger.info("🧪 QA Agent running — content_length=%d chars", content_len)

        parts = ["Assess this markdown file for knowledge-base ingestion.\n"]
        if metadata:
            parts.append("Metadata:\n" + "\n".join(
                f"  {k}: {v}" for k, v in metadata.items() if v
            ) + "\n")
        parts.append(f"```markdown\n{md_content}\n```")
        prompt = "\n".join(parts)

        agent = self._build_agent()
        result = await agent.invoke_async(
            prompt, structured_output_model=QAOutput,
        )

        output: QAOutput | None = getattr(result, "structured_output", None)
        if output is None:
            logger.warning("⚠️ QA Agent returned no structured output — defaulting to accepted")
            return QAOutput(
                verdict="accepted",
                reasoning="Failed to get structured output from agent; defaulting to accepted.",
            )

        logger.info("🧪 QA Agent finished — verdict=%s", output.verdict)
        return output


# ═══════════════════════════════════════════════════════════════════════════
# Uniqueness Agent — KB overlap assessment
# ═══════════════════════════════════════════════════════════════════════════

class UniquenessOutput(BaseModel):
    """Structured output from the Uniqueness Agent."""

    verdict: Literal["unique", "overlapping", "conflicting"] = "unique"
    reasoning: str = ""
    similar_file_ids: list[str] = Field(default_factory=list)


@tool
def query_kb(content_snippet: str, limit: int = 3) -> list[dict]:
    """Query the Bedrock knowledge base for documents similar to *content_snippet*.

    Args:
        content_snippet: A representative snippet of the file content to search for.
        limit: Maximum number of similar documents to return.

    Returns:
        A list of dicts, each with keys: file_id, title, score, snippet.
        Returns an empty list when the KB is not configured or no matches are found.
    """
    settings = get_settings()
    if not settings.BEDROCK_KB_ID:
        logger.debug("🔍 KB query skipped — BEDROCK_KB_ID not configured")
        return []
    logger.info(
        "🔍 Querying Bedrock KB (id=%s) for similar docs (limit=%d)",
        settings.BEDROCK_KB_ID, limit,
    )
    # TODO: Wire to Bedrock KB retrieve API.
    # When implemented, this should:
    #   1. Call bedrock-agent-runtime RetrieveAndGenerate or Retrieve with content_snippet.
    #   2. Return results with file_id (from S3 key or metadata), title, relevance score,
    #      and a text snippet so the agent can compare content.
    #   3. Include source_url in results so the agent can apply the detail-vs-listing rule.
    return []


UNIQUENESS_SYSTEM_PROMPT = """\
You are a uniqueness assessment agent for a customer-facing knowledge base.

You will receive a markdown file (with optional metadata) that is a candidate \
for ingestion. Your job is to determine how this file relates to content \
already in the knowledge base by using the `query_kb` tool.

## Workflow
1. Read the candidate file's content and metadata.
2. Use the `query_kb` tool with a representative snippet (first ~500 chars of \
substantive content) to find similar existing documents.
3. If `query_kb` returns no results, classify as "unique".
4. If results are returned, carefully compare the candidate against each match.

## Verdicts

**unique** — No meaningful overlap with existing KB content. The candidate \
covers a topic, product, region, or level of detail not already present.

**overlapping** — Partial overlap exists, but the candidate adds new \
information not found in existing documents. This is acceptable — the file \
should still be ingested. Examples:
  • A detail page for a product when only a listing-page teaser exists.
  • Same product but for a different region with region-specific terms.
  • Updated pricing or features not reflected in the existing article.

**conflicting** — The candidate contains information that directly contradicts \
existing KB content on the same topic. Examples:
  • Different pricing for the same product and region.
  • Contradictory eligibility criteria or terms.
  • Incompatible feature descriptions for the same service.
When marking as conflicting, you MUST list the file_ids of the conflicting \
documents in `similar_file_ids` so they can be reviewed together.

## Important rules
  • A detail page is NEVER a duplicate of a listing page that merely teasers \
it. The detail page is the canonical source; the listing page teaser is a \
summary. Classify as "unique" or "overlapping", not "conflicting".
  • If a file has a specific source_url pointing to a detail sub-page \
(e.g. /products/mobile-wifi), it should be considered unique even if a parent \
listing page mentions the same product briefly.
  • Only mark as "conflicting" when there is a genuine factual contradiction, \
not merely overlapping coverage of the same topic.
  • When the KB query returns no results (empty list), always return "unique".
"""


class UniquenessAgent:
    """Compares a candidate file against existing KB content for overlap/conflicts.

    Builds a fresh Strands ``Agent`` per ``run()`` invocation so conversation
    history from prior files cannot bleed into the next file's verdict.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._model_id = settings.HAIKU_MODEL_ID
        self._max_tokens = settings.HAIKU_MAX_TOKENS
        logger.info("🔎 Initialising Uniqueness Agent (model=%s)", self._model_id)

    def _build_agent(self) -> Agent:
        """Create a fresh, stateless agent for a single invocation."""
        return Agent(
            model=get_bedrock_model(self._model_id, self._max_tokens),
            system_prompt=UNIQUENESS_SYSTEM_PROMPT,
            tools=[query_kb],
        )

    async def run(
        self,
        md_content: str,
        metadata: dict[str, str | None] | None = None,
    ) -> UniquenessOutput:
        """Assess uniqueness of *md_content* against the existing KB.

        Args:
            md_content: Pure markdown content (no YAML frontmatter).
            metadata: Optional dict with title, source_url, region, brand.
        """
        content_len = len(md_content)
        logger.info("🔎 Uniqueness Agent running — content_length=%d chars", content_len)

        parts = ["Assess this candidate file for uniqueness against the existing knowledge base.\n"]
        if metadata:
            parts.append("Metadata:\n" + "\n".join(
                f"  {k}: {v}" for k, v in metadata.items() if v
            ) + "\n")
        parts.append(f"```markdown\n{md_content}\n```")
        prompt = "\n".join(parts)

        agent = self._build_agent()
        result = await agent.invoke_async(
            prompt, structured_output_model=UniquenessOutput,
        )

        output: UniquenessOutput | None = getattr(result, "structured_output", None)
        if output is None:
            logger.warning("⚠️ Uniqueness Agent returned no structured output — defaulting to unique")
            return UniquenessOutput(
                verdict="unique",
                reasoning="Failed to get structured output from agent; defaulting to unique.",
            )

        logger.info("🔎 Uniqueness Agent finished — verdict=%s", output.verdict)
        return output


# ═══════════════════════════════════════════════════════════════════════════
# Combined runner — convenience for pipeline callers
# ═══════════════════════════════════════════════════════════════════════════

async def run_qa_and_uniqueness(
    md_content: str,
    metadata: dict[str, str | None] | None = None,
    *,
    qa_agent: QAAgent | None = None,
    uniqueness_agent: UniquenessAgent | None = None,
) -> QAResult:
    """Run both agents and return a unified `QAResult`.

    Accepts optional pre-built agent instances so callers can reuse them
    across multiple files within a single job.
    """
    qa = qa_agent or QAAgent()
    uq = uniqueness_agent or UniquenessAgent()

    # QA and Uniqueness have no data dependency — run concurrently to
    # halve per-file latency.
    qa_output, uq_output = await asyncio.gather(
        qa.run(md_content, metadata=metadata),
        uq.run(md_content, metadata=metadata),
    )

    return QAResult(
        quality_verdict=qa_output.verdict,
        quality_reasoning=qa_output.reasoning,
        uniqueness_verdict=uq_output.verdict,
        uniqueness_reasoning=uq_output.reasoning,
        similar_file_ids=uq_output.similar_file_ids or [],
    )

"""Bedrock Knowledge Base client — retrieval, RAG generation, and data-source sync.

Wraps ``bedrock-agent-runtime`` for Retrieve / RetrieveAndGenerate,
and ``bedrock-agent`` for StartIngestionJob (KB sync).
"""

import json
import logging
from typing import Any, AsyncGenerator

import boto3
from botocore.exceptions import ClientError

from kb_manager.config import get_settings

logger = logging.getLogger(__name__)


class BedrockKBClient:
    """Thin wrapper around Bedrock Knowledge Base APIs."""

    def __init__(self) -> None:
        settings = get_settings()
        self._kb_id = settings.BEDROCK_KB_ID
        self._model_arn = f"arn:aws:bedrock:{settings.AWS_REGION}::foundation-model/{settings.BEDROCK_MODEL_ID}"
        self._region = settings.AWS_REGION
        self._data_source_id = settings.BEDROCK_DS_ID
        self._max_tokens = settings.BEDROCK_MAX_TOKENS

        self._runtime = boto3.client("bedrock-agent-runtime", region_name=self._region)
        self._agent = boto3.client("bedrock-agent", region_name=self._region)
        logger.info(
            "🧠 BedrockKBClient initialised — kb_id=%s, region=%s, model=%s",
            self._kb_id, self._region, settings.BEDROCK_MODEL_ID,
        )

    # ------------------------------------------------------------------
    # Retrieve (search only — no generation)
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        kb_target: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Call Bedrock Retrieve API and return ranked results.

        Returns a list of dicts with keys:
            rank, title, snippet, source_url, score, s3_uri
        """
        retrieval_config: dict[str, Any] = {
            "vectorSearchConfiguration": {
                "numberOfResults": limit,
            },
        }

        # Apply metadata filter for kb_target if provided
        if kb_target:
            retrieval_config["vectorSearchConfiguration"]["filter"] = {
                "equals": {"key": "kb_target", "value": kb_target},
            }

        try:
            response = self._runtime.retrieve(
                knowledgeBaseId=self._kb_id,
                retrievalQuery={"text": query},
                retrievalConfiguration=retrieval_config,
            )
        except ClientError:
            logger.exception("❌ Bedrock Retrieve failed for query='%s'", query)
            raise

        results: list[dict[str, Any]] = []
        for rank, result in enumerate(response.get("retrievalResults", []), start=1):
            content = result.get("content", {})
            location = result.get("location", {})
            metadata = result.get("metadata", {})

            s3_uri = ""
            if location.get("type") == "S3":
                s3_uri = location.get("s3Location", {}).get("uri", "")

            results.append({
                "rank": rank,
                "title": metadata.get("title", ""),
                "snippet": content.get("text", ""),
                "source_url": metadata.get("source_url", ""),
                "score": result.get("score", 0.0),
                "s3_uri": s3_uri,
            })

        logger.info("🔍 Retrieve returned %d results for query='%s'", len(results), query)
        return results

    # ------------------------------------------------------------------
    # RetrieveAndGenerate (RAG — streaming)
    # ------------------------------------------------------------------

    def retrieve_and_generate(
        self,
        query: str,
        kb_target: str | None = None,
        context_limit: int = 5,
    ) -> dict[str, Any]:
        """Call Bedrock RetrieveAndGenerate and return output + citations.

        Returns dict with keys: output_text, citations (list of source dicts).
        """
        kb_config: dict[str, Any] = {
            "knowledgeBaseId": self._kb_id,
            "modelArn": self._model_arn,
            "retrievalConfiguration": {
                "vectorSearchConfiguration": {
                    "numberOfResults": context_limit,
                },
            },
            "generationConfiguration": {
                "inferenceConfig": {
                    "textInferenceConfig": {
                        "maxTokens": self._max_tokens,
                        "temperature": 0.2,
                        "topP": 0.9,
                    },
                },
            },
        }

        if kb_target:
            kb_config["retrievalConfiguration"]["vectorSearchConfiguration"]["filter"] = {
                "equals": {"key": "kb_target", "value": kb_target},
            }

        try:
            response = self._runtime.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": kb_config,
                },
            )
        except ClientError:
            logger.exception("❌ Bedrock RetrieveAndGenerate failed for query='%s'", query)
            raise

        output_text = response.get("output", {}).get("text", "")
        raw_citations = response.get("citations", [])

        citations: list[dict[str, Any]] = []
        for citation in raw_citations:
            for ref in citation.get("retrievedReferences", []):
                content = ref.get("content", {})
                location = ref.get("location", {})
                metadata = ref.get("metadata", {})

                s3_uri = ""
                if location.get("type") == "S3":
                    s3_uri = location.get("s3Location", {}).get("uri", "")

                citations.append({
                    "title": metadata.get("title", ""),
                    "url": metadata.get("source_url", ""),
                    "snippet": content.get("text", "")[:500],
                    "s3_uri": s3_uri,
                })

        logger.info(
            "💬 RetrieveAndGenerate completed — %d chars output, %d citations",
            len(output_text), len(citations),
        )
        return {"output_text": output_text, "citations": citations}

    # ------------------------------------------------------------------
    # StartIngestionJob (KB sync)
    # ------------------------------------------------------------------

    def start_sync(self) -> str | None:
        """Trigger a Bedrock KB data-source ingestion sync.

        Returns the ingestion job ID on success, or None if no
        data source is configured.
        """
        if not self._data_source_id:
            logger.warning("⚠️ BEDROCK_DS_ID not set — skipping KB sync")
            return None

        try:
            response = self._agent.start_ingestion_job(
                knowledgeBaseId=self._kb_id,
                dataSourceId=self._data_source_id,
            )
            ingestion_job = response.get("ingestionJob", {})
            ingestion_id = ingestion_job.get("ingestionJobId", "unknown")
            logger.info(
                "🔄 KB sync triggered — ingestionJobId=%s, kb=%s, ds=%s",
                ingestion_id, self._kb_id, self._data_source_id,
            )
            return ingestion_id
        except ClientError:
            logger.exception("❌ Failed to start KB ingestion sync")
            return None

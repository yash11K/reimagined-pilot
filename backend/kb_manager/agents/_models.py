"""Shared, cached Strands ``BedrockModel`` factory.

A single ``BedrockModel`` instance per (model_id, max_tokens) pair is reused
across every agent invocation in the process. The model object holds a
boto3 ``bedrock-runtime`` client which is thread-safe for the API calls
issued by Strands, so sharing it removes per-invocation client setup cost.

Agents still construct a *fresh* ``strands.Agent`` per ``run()`` call (so
conversation history cannot bleed across invocations); only the underlying
model is shared.
"""

from __future__ import annotations

from functools import lru_cache

from strands.models import BedrockModel


@lru_cache(maxsize=8)
def get_bedrock_model(model_id: str, max_tokens: int) -> BedrockModel:
    """Return a cached ``BedrockModel`` for the given model + max_tokens.

    The cache is keyed on the two arguments so callers can safely use this
    for both Haiku (classification) and Sonnet (extraction) without leakage.
    """
    return BedrockModel(model_id=model_id, max_tokens=max_tokens)

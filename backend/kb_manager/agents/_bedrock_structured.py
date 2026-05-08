"""Direct Bedrock Converse helper for forced-tool structured outputs.

Workaround for Strands SDK issue #784: when calling
``Agent.invoke_async(structured_output_model=...)`` against Bedrock Claude,
Strands sets ``toolChoice: {auto: {}}`` instead of ``toolChoice: {tool:
{name: ...}}``. The model then often emits prose or malformed args instead
of using the tool, triggering retry loops that exhaust ``max_tokens``.

Here we drive Bedrock Converse directly with:
  - the Pydantic schema as a single tool definition
  - ``toolChoice = {tool: {name: <model_name>}}`` so the model is forced
    to call our schema tool every time

No retry loop. No wandering into prose. One round trip per call.
"""

from __future__ import annotations

import asyncio
import json
import logging
from functools import lru_cache
from typing import Any, Type, TypeVar

import boto3
from pydantic import BaseModel, ValidationError

from kb_manager.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


@lru_cache(maxsize=1)
def _get_client():
    settings = get_settings()
    return boto3.client("bedrock-runtime", region_name=settings.AWS_REGION)


def _strip_titles(schema: Any) -> Any:
    """Strip Pydantic-emitted descriptive ``title`` METADATA keys.

    Pydantic adds a string-valued ``title`` next to ``type``/``properties`` to
    describe the schema (e.g. ``{"title": "ExtractedFileOutput", "type":
    "object", ...}``). Bedrock's strict validator dislikes them.

    Only string-valued ``title`` is stripped — a key named ``title`` whose
    value is a dict is an actual property called ``title`` and must be kept.
    """
    if isinstance(schema, dict):
        return {
            k: _strip_titles(v)
            for k, v in schema.items()
            if not (k == "title" and isinstance(v, str))
        }
    if isinstance(schema, list):
        return [_strip_titles(v) for v in schema]
    return schema


def _inline_refs(schema: Any, defs: dict[str, Any] | None = None) -> Any:
    """Inline ``$ref`` references against ``$defs`` so Bedrock's strict
    validator (which doesn't follow refs across the schema) sees a flat tree."""
    if defs is None:
        defs = schema.get("$defs", {}) if isinstance(schema, dict) else {}
    if isinstance(schema, dict):
        if "$ref" in schema and schema["$ref"].startswith("#/$defs/"):
            name = schema["$ref"].split("/")[-1]
            target = defs.get(name, {})
            return _inline_refs(target, defs)
        return {
            k: _inline_refs(v, defs)
            for k, v in schema.items()
            if k != "$defs"
        }
    if isinstance(schema, list):
        return [_inline_refs(v, defs) for v in schema]
    return schema


def _enforce_additional_properties_false(schema: Any) -> Any:
    """Bedrock strict mode requires every object schema to set
    ``additionalProperties: false`` explicitly. Walk the tree and add it."""
    if isinstance(schema, dict):
        out = {k: _enforce_additional_properties_false(v) for k, v in schema.items()}
        if out.get("type") == "object" and "additionalProperties" not in out:
            out["additionalProperties"] = False
        return out
    if isinstance(schema, list):
        return [_enforce_additional_properties_false(v) for v in schema]
    return schema


async def converse_structured(
    *,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    output_model: Type[T],
    max_tokens: int,
    temperature: float = 0.0,
) -> T | None:
    """Call Bedrock Converse with forced tool_choice and parse the model's tool input."""
    client = _get_client()

    tool_name = output_model.__name__
    schema = output_model.model_json_schema()
    schema = _inline_refs(schema)
    schema = _strip_titles(schema)
    schema = _enforce_additional_properties_false(schema)

    request: dict[str, Any] = {
        "modelId": model_id,
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {
            "maxTokens": max_tokens,
            "temperature": temperature,
        },
        "toolConfig": {
            "tools": [
                {
                    "toolSpec": {
                        "name": tool_name,
                        "description": (
                            output_model.__doc__
                            or f"Return the structured {tool_name} payload."
                        ).strip(),
                        "inputSchema": {"json": schema},
                        # Token-level constrained decoding (boto3 1.42+).
                        # Without this, Claude sometimes emits array/object
                        # fields as JSON-encoded strings.
                        "strict": True,
                    }
                }
            ],
            # Forced tool choice — fixes Strands #784. Model MUST call this tool.
            "toolChoice": {"tool": {"name": tool_name}},
        },
    }

    try:
        response = await asyncio.to_thread(client.converse, **request)
    except Exception:
        logger.exception("💥 Bedrock converse failed for model=%s", model_id)
        raise

    stop_reason = response.get("stopReason")
    output_msg = response.get("output", {}).get("message", {})
    content_blocks = output_msg.get("content", []) or []

    tool_input: dict[str, Any] | None = None
    for block in content_blocks:
        if "toolUse" in block and block["toolUse"].get("name") == tool_name:
            tool_input = block["toolUse"].get("input")
            break

    if tool_input is None:
        # Model declined to use the tool despite forced choice — should not
        # happen, but log defensively.
        text_blocks = [b.get("text", "") for b in content_blocks if "text" in b]
        logger.warning(
            "⚠️ Bedrock did not emit toolUse for %s (stop_reason=%s, "
            "text_preview=%r)",
            tool_name, stop_reason, "".join(text_blocks)[:200],
        )
        return None

    if stop_reason == "max_tokens":
        logger.warning(
            "⚠️ Bedrock hit max_tokens before completing %s tool input "
            "(model=%s, max_tokens=%d). Output may be truncated.",
            tool_name, model_id, max_tokens,
        )
        # Fall through and try to validate; with strict=true the model can
        # only have produced schema-valid output up to the truncation point.

    try:
        return output_model.model_validate(tool_input)
    except ValidationError as exc:
        logger.warning(
            "⚠️ Bedrock %s tool input failed Pydantic validation: %s",
            tool_name, exc,
        )
        return None

"""Helpers that derive S3 upload parameters from a KBFile's folder context.

A file inside a folder gets:
  - ``namespace`` set to the folder's name (replacing the noisy default
    derived from ``source_url`` for synthetic ``upload://`` URIs).
  - ``folder_path`` set to the slash-joined folder chain, which lands as a
    STRING attribute in the Bedrock metadata sidecar so queries can filter
    by folder.

Files with no folder (legacy URL-ingested, or explicitly unfiled) return
``(None, None)`` so the S3 uploader falls back to its source_url-derived
namespace and the sidecar omits ``folder_path``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from kb_manager.queries import folders as folder_queries


async def resolve_upload_context(
    db: AsyncSession,
    kb_file: Any,
) -> tuple[str | None, str | None]:
    """Return ``(namespace, folder_path)`` for an upload of ``kb_file``."""
    if kb_file.folder_id is None:
        return None, None
    folder_path = await folder_queries.get_folder_path(db, kb_file.folder_id)
    folder = await folder_queries.get_folder(db, kb_file.folder_id)
    namespace = folder.name if folder is not None else None
    return namespace, folder_path

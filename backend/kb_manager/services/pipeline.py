"""Two-phase pipeline orchestrator for content ingestion.

Flow:
  Scout phase: fetch → prune → discover → classify → filter /en/ URLs
               → expansion sources collected for inline merge
               → sibling sources enqueued for independent processing
               → uncertain sources marked needs_confirmation
               → auto-advance job to processing

  Process phase: for each expansion source, fetch content + merge with
                 parent page → extractor produces KBFile(s) → all source IDs
                 linked to those files via M2M junction → QA → route → upload
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kb_manager.agents import (
    DiscoveryAgent,
    ExtractorAgent,
    QAAgent,
    UniquenessAgent,
)
from kb_manager.agents.metadata_enricher import MetadataEnricher
from kb_manager.agents.qa import run_qa_and_uniqueness
from kb_manager.config import get_settings
from kb_manager.logging_config import bind_log_context
from kb_manager.models import KBFile, Source
from kb_manager.queries import files as file_queries
from kb_manager.queries import folders as folder_queries
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import queue as queue_queries
from kb_manager.queries import run_pages as run_page_queries
from kb_manager.queries import sources as source_queries

if TYPE_CHECKING:
    from kb_manager.services.bedrock_kb import BedrockKBClient
from kb_manager.services.aem_pruner import (
    extract_links_deterministic,
    is_cross_domain,
    is_denied_url,
    is_ignored_url,
    is_self_link,
    is_valid_url_shape,
    prune_aem_json,
    resolve_aem_link,
)
from kb_manager.services.routing_matrix import route_file
from kb_manager.services.s3_uploader import S3Uploader
from kb_manager.services.stream_manager import StreamManager
from kb_manager.services.upload_context import resolve_upload_context
from kb_manager.services.versioning import VersioningService

logger = logging.getLogger(__name__)

_SUPPORTED_LANGUAGES: set[str] | None = None


def _get_supported_languages() -> set[str]:
    """Lazy-load supported languages from settings."""
    global _SUPPORTED_LANGUAGES
    if _SUPPORTED_LANGUAGES is None:
        _SUPPORTED_LANGUAGES = get_settings().SUPPORTED_LANGUAGES
    return _SUPPORTED_LANGUAGES


def _extract_language(url: str) -> str | None:
    """Extract language code from URL path segments.

    Looks for a supported language code (e.g. 'en', 'fr') as a path segment.
    Returns the language code if found, None otherwise.
    """
    supported = _get_supported_languages()
    # Parse path segments from the URL
    from urllib.parse import urlparse
    path = urlparse(url).path if "://" in url else url
    segments = [s.lower() for s in path.split("/") if s]
    for segment in segments:
        if segment in supported:
            return segment
    return None


class Pipeline:
    """Orchestrates the two-phase ingestion pipeline."""

    def __init__(
        self,
        stream_manager: StreamManager,
        s3_uploader: S3Uploader,
        versioning_service: VersioningService,
        session_factory: async_sessionmaker[AsyncSession],
        kb_client: "BedrockKBClient | None" = None,
    ) -> None:
        settings = get_settings()
        self._stream = stream_manager
        self._s3 = s3_uploader
        self._versioning = versioning_service
        self._session_factory = session_factory
        self._settings = settings

        # Bedrock KB client for post-upload sync. Injected by ``main.lifespan``;
        # when not provided (e.g. some unit tests) sync is silently skipped.
        self._kb_client = kb_client
        logger.info("🔧 Pipeline initialised")

    async def _trigger_kb_sync(self, context: str = "") -> None:
        """Trigger a Bedrock KB data-source sync if configured."""
        if self._kb_client is None:
            return
        try:
            ingestion_id = await self._kb_client.start_sync()
            if ingestion_id:
                logger.info("🔄 KB sync triggered after %s — ingestionJobId=%s", context, ingestion_id)
        except Exception:
            logger.warning("⚠️ KB sync trigger failed after %s — non-fatal, continuing", context, exc_info=True)

    # ------------------------------------------------------------------
    # Scout phase
    # ------------------------------------------------------------------

    async def run_scout(
        self,
        job_id: uuid.UUID,
        source_url: str,
        steering_prompt: str | None = None,
    ) -> None:
        """Phase 1: Fetch → Prune → Extract links → Discover+Classify → Queue certain links → Auto-process."""
        job_id_str = str(job_id)
        bind_log_context(job_id=job_id_str[:8], phase="scout")
        t0 = time.perf_counter()
        logger.info("🔍 [job=%s] Scout STARTED for %s", job_id_str[:8], source_url)

        try:
            await self._stream.publish(
                job_id_str, "scout", "scouting_started",
                {"job_id": job_id_str, "source_url": source_url},
            )

            # Update progress: scout started + display_status
            async with self._session_factory() as db:
                await job_queries.update_job(db, job_id, progress_pct=10)
                job = await job_queries.get_job(db, job_id)
                if job is not None:
                    await source_queries.set_display_status(
                        db, job.source_id, "discovering",
                    )
                await db.commit()

            # 1. Fetch model.json
            async with httpx.AsyncClient(timeout=self._settings.AEM_REQUEST_TIMEOUT) as client:
                resp = await client.get(source_url)
                resp.raise_for_status()
                raw_json = resp.json()

            pruned = prune_aem_json(raw_json)

            # 2. Deterministic link extraction (guaranteed, no misses)
            deterministic_links = extract_links_deterministic(pruned, source_url)
            logger.info("🔗 [job=%s] Deterministic scan found %d links",
                        job_id_str[:8], len(deterministic_links))

            # 3. Discovery Agent — components + link classification in one pass
            discovery_agent = DiscoveryAgent()
            discovery_result = await discovery_agent.run(pruned, pre_extracted_links=deterministic_links)
            logger.info("🔎 [job=%s] Discovery: %d components, %d classified links",
                        job_id_str[:8], len(discovery_result.components),
                        len(discovery_result.classified_links))

            # Publish component events
            components_data: list[dict[str, Any]] = []
            for idx, comp in enumerate(discovery_result.components):
                comp_id = comp.id or f"comp_{idx}"
                comp_data = {
                    "id": comp_id,
                    "type": comp.component_type,
                    "title": comp.title,
                    "snippet": comp.text_snippet,
                    "included": True,
                }
                components_data.append(comp_data)
                await self._stream.publish(job_id_str, "scout", "component_found", comp_data)

            # 4. Process classified links — certain → queue, uncertain → needs_confirmation
            #    Denied links get stored as sources with denied_* status for dedup + audit.

            # --- Session 1: Load parent source data + existing URLs for dedup ---
            async with self._session_factory() as db:
                job = await job_queries.get_job(db, job_id)
                if job is None:
                    raise ValueError(f"Job {job_id} not found")
                parent_source = await source_queries.get_source(db, job.source_id)
                if parent_source is None:
                    raise ValueError(f"Source {job.source_id} not found")
                # Snapshot plain data so we can close this session quickly
                parent_source_id = parent_source.id
                parent_region = parent_source.region
                parent_brand = parent_source.brand
                parent_kb_target = parent_source.kb_target

                # Pre-fetch existing URLs for dedup so the classification
                # loop doesn't need a live DB connection.
                candidate_urls: list[str] = []
                for cl in discovery_result.classified_links:
                    if is_valid_url_shape(cl.url):
                        resolved = resolve_aem_link(cl.url, source_url)
                        if is_valid_url_shape(resolved):
                            candidate_urls.append(resolved)
                existing_url_set: set[str] = set()
                if candidate_urls:
                    result = await db.execute(
                        select(Source.url).where(
                            Source.type == "aem",
                            Source.url.in_(candidate_urls),
                        )
                    )
                    existing_url_set = {row[0] for row in result.all()}
            # Session 1 closed — connection returned to pool.

            # --- In-memory classification (no DB needed) ---
            certain_count = 0
            uncertain_count = 0
            nav_count = 0
            denied_count = 0
            non_en_count = 0
            already_seen_count = 0
            junk_count = 0

            # Collect DB operations into batches
            denied_sources: list[dict] = []
            certain_links: list[dict] = []
            uncertain_links: list[dict] = []

            for cl in discovery_result.classified_links:
                if not is_valid_url_shape(cl.url):
                    junk_count += 1
                    logger.warning(
                        "🗑️ [job=%s] Dropping junk URL from Discovery output: %r",
                        job_id_str[:8], cl.url[:120],
                    )
                    continue

                resolved_url = resolve_aem_link(cl.url, source_url)

                if not is_valid_url_shape(resolved_url):
                    junk_count += 1
                    logger.warning(
                        "🗑️ [job=%s] Dropping junk URL after resolve: %r",
                        job_id_str[:8], resolved_url[:120],
                    )
                    continue

                # --- Dedup using pre-fetched set ---
                if resolved_url in existing_url_set:
                    already_seen_count += 1
                    logger.debug("♻️ [job=%s] Already seen, skipping: %s",
                                 job_id_str[:8], resolved_url[:60])
                    continue

                # --- Filter + collect denied sources (single 'denied' status; reason in metadata) ---
                if is_cross_domain(resolved_url, source_url):
                    denied_sources.append({
                        "url": resolved_url, "denied_reason": "cross_domain",
                        "reason": "Cross-domain link", "anchor": cl.anchor_text,
                    })
                    denied_count += 1
                    continue
                if is_denied_url(resolved_url):
                    denied_sources.append({
                        "url": resolved_url, "denied_reason": "denied_path",
                        "reason": "Denied URL path segment", "anchor": cl.anchor_text,
                    })
                    denied_count += 1
                    continue
                if is_self_link(resolved_url, source_url):
                    nav_count += 1
                    continue
                if is_ignored_url(resolved_url):
                    denied_sources.append({
                        "url": resolved_url, "denied_reason": "ignored",
                        "reason": "Ignored URL (homepage/index)", "anchor": cl.anchor_text,
                    })
                    nav_count += 1
                    continue
                if not _extract_language(resolved_url):
                    denied_sources.append({
                        "url": resolved_url, "denied_reason": "unsupported_language",
                        "reason": "No supported language path segment found", "anchor": cl.anchor_text,
                    })
                    non_en_count += 1
                    continue

                classification = cl.classification

                if classification == "navigation":
                    denied_sources.append({
                        "url": resolved_url, "denied_reason": "navigation",
                        "reason": cl.reason or "Classified as navigation by Discovery Agent",
                        "anchor": cl.anchor_text,
                    })
                    nav_count += 1
                    continue

                if classification == "certain":
                    certain_links.append({
                        "url": resolved_url, "anchor_text": cl.anchor_text,
                        "reason": cl.reason,
                        "language": _extract_language(resolved_url),
                    })
                    certain_count += 1
                else:
                    uncertain_links.append({
                        "url": resolved_url, "anchor_text": cl.anchor_text,
                        "reason": cl.reason,
                        "language": _extract_language(resolved_url),
                    })
                    uncertain_count += 1

            # --- Session 2: Batch-write all classified links + finalise job ---
            async with self._session_factory() as db:
                # Write denied sources — single 'denied' status; reason kept in metadata
                for ds in denied_sources:
                    existing = await source_queries.get_source_by_url(db, ds["url"])
                    if existing is None:
                        await source_queries.create_source(
                            db,
                            type="aem",
                            url=ds["url"],
                            region=parent_region,
                            brand=parent_brand,
                            kb_target=parent_kb_target,
                            status="denied",
                            origin="discovered",
                            parent_source_id=parent_source_id,
                            metadata_={
                                "denied_reason": ds["denied_reason"],
                                "reason": ds["reason"],
                                "discovered_on": source_url,
                                "anchor_text": ds["anchor"],
                            },
                        )

                # Write certain links + queue them
                for cl_data in certain_links:
                    discovered_source = await source_queries.create_source(
                        db,
                        type="aem",
                        url=cl_data["url"],
                        region=parent_region,
                        brand=parent_brand,
                        kb_target=parent_kb_target,
                        language=cl_data["language"],
                        origin="discovered",
                        parent_source_id=parent_source_id,
                    )
                    # Pre-create the job for the discovered source so SSE has
                    # a job_id immediately, then enqueue against that source.
                    discovered_job = await job_queries.create_job(
                        db, source_id=discovered_source.id, status="scouting",
                    )
                    await source_queries.set_active_job(
                        db, discovered_source.id, discovered_job.id,
                    )
                    await source_queries.set_display_status(
                        db, discovered_source.id, "queued",
                    )
                    await queue_queries.add_to_queue(
                        db,
                        source_id=discovered_source.id,
                        job_id=discovered_job.id,
                    )
                    logger.info("✅ [job=%s] Certain link queued: %s",
                                job_id_str[:8], cl_data["url"][:60])

                    await self._stream.publish(
                        job_id_str, "scout", "link_found",
                        {"target_url": cl_data["url"], "anchor_text": cl_data["anchor_text"]},
                    )
                    await self._stream.publish(
                        job_id_str, "scout", "link_classified",
                        {
                            "id": str(discovered_source.id),
                            "target_url": cl_data["url"],
                            "anchor_text": cl_data["anchor_text"],
                            "classification": "certain",
                            "reason": cl_data["reason"],
                        },
                    )

                # Write uncertain links
                for cl_data in uncertain_links:
                    discovered_source = await source_queries.create_source(
                        db,
                        type="aem",
                        url=cl_data["url"],
                        region=parent_region,
                        brand=parent_brand,
                        kb_target=parent_kb_target,
                        language=cl_data["language"],
                        origin="discovered",
                        parent_source_id=parent_source_id,
                    )
                    await source_queries.update_source(
                        db, discovered_source.id,
                        status="needs_confirmation",
                        display_status="needs_review",
                    )
                    logger.info("❓ [job=%s] Uncertain link: %s",
                                job_id_str[:8], cl_data["url"][:60])

                    await self._stream.publish(
                        job_id_str, "scout", "link_found",
                        {"target_url": cl_data["url"], "anchor_text": cl_data["anchor_text"]},
                    )
                    await self._stream.publish(
                        job_id_str, "scout", "link_classified",
                        {
                            "id": str(discovered_source.id),
                            "target_url": cl_data["url"],
                            "anchor_text": cl_data["anchor_text"],
                            "classification": "uncertain",
                            "reason": cl_data["reason"],
                        },
                    )

                summary = {
                    "total_components": len(components_data),
                    "certain_queued": certain_count,
                    "uncertain": uncertain_count,
                    "denied": denied_count,
                    "nav_skipped": nav_count,
                    "unsupported_lang_skipped": non_en_count,
                    "already_seen": already_seen_count,
                    "junk_dropped": junk_count,
                }
                scout_summary = {
                    "components": components_data,
                    "summary": summary,
                }

                await source_queries.mark_scouted(db, parent_source_id, scout_summary)
                await job_queries.update_job(db, job_id, status="processing", progress_pct=40)
                await source_queries.set_display_status(
                    db, parent_source_id, "extracting",
                )
                await db.commit()
            # Session 2 closed.

            await self._stream.publish(
                job_id_str, "scout", "scout_complete",
                {"job_id": job_id_str, "summary": summary},
            )
            await self._stream.close_channel(job_id_str, "scout")

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "✅ [job=%s] Scout DONE in %.1fms — %d certain queued, %d uncertain, %d junk dropped",
                job_id_str[:8], elapsed, certain_count, uncertain_count, junk_count,
            )

            # Process phase is now called by the queue worker separately.
            # Scout just returns after completing discovery.
            await self.run_process(job_id)

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.exception("💥 [job=%s] Scout FAILED after %.1fms: %s", job_id_str[:8], elapsed, exc)
            await self._fail_job(job_id, str(exc), "scout")

    # ------------------------------------------------------------------
    # Process phase
    # ------------------------------------------------------------------

    async def run_process(self, job_id: uuid.UUID) -> None:
        """Phase 2: Fetch single source page → Extract → QA → Route → Upload."""
        job_id_str = str(job_id)
        bind_log_context(job_id=job_id_str[:8], phase="process")
        t0 = time.perf_counter()
        logger.info("⚙️ [job=%s] Process STARTED", job_id_str[:8])

        # Concurrency is managed by the queue worker's semaphore, not the pipeline.
        try:
            async with self._session_factory() as db:
                job = await job_queries.get_job(db, job_id)
                if job is None:
                    raise ValueError(f"Job {job_id} not found")

                source = await source_queries.get_source(db, job.source_id)
                if source is None:
                    raise ValueError(f"Source {job.source_id} not found")
                steering = job.steering_prompt

                await self._stream.publish(
                    job_id_str, "progress", "extraction_started",
                    {"job_id": job_id_str, "total_pages": 1, "progress_pct": 50},
                )

                # Update progress: extraction started
                await job_queries.update_job(db, job.id, progress_pct=50)

                extractor = ExtractorAgent()
                qa_agent = QAAgent()
                uniqueness_agent = UniquenessAgent()

                files_created = 0
                files_approved = 0
                files_review = 0
                files_rejected = 0

                await self._stream.publish(
                    job_id_str, "progress", "page_processing",
                    {"url": source.url, "source_id": str(source.id), "page_number": 1, "total": 1},
                )

                modify_date = datetime.now(timezone.utc)
                skip_source = False
                page_components: list[dict] = []

                # Track whether versioning superseded an existing file
                had_existing_file = False

                if source.url:
                    try:
                        async with httpx.AsyncClient(timeout=self._settings.AEM_REQUEST_TIMEOUT) as client:
                            source_resp = await client.get(source.url)
                            source_resp.raise_for_status()
                            source_json = source_resp.json()
                        modify_date = self._extract_modify_date(source_json)

                        # Check if there's an existing file before versioning decision
                        existing_file_stmt = (
                            select(KBFile)
                            .where(KBFile.source_url == source.url)
                            .where(KBFile.status != "superseded")
                            .limit(1)
                        )
                        existing_result = await db.execute(existing_file_stmt)
                        had_existing_file = existing_result.scalars().first() is not None

                        v_decision = await self._check_versioning_and_cleanup(source.url, modify_date, db)
                        if v_decision == "skip":
                            logger.info("⏭️ [job=%s] Source unchanged — skip", job_id_str[:8])
                            skip_source = True
                            # Record RunPage: skipped
                            try:
                                await run_page_queries.create_run_page(
                                    db,
                                    job_id=job.id,
                                    url=source.url,
                                    outcome="skipped",
                                    reason="unchanged",
                                )
                            except Exception:
                                logger.warning("Failed to record RunPage for %s", source.url, exc_info=True)
                        else:
                            page_components.append({"raw_json": prune_aem_json(source_json)})
                    except Exception as exc:
                        logger.warning("⚠️ [job=%s] Source fetch failed: %s", job_id_str[:8], exc)

                if not skip_source and page_components:
                    extracted_files = await extractor.run(
                        components=page_components,
                        steering_prompt=steering,
                    )

                    for ef in extracted_files:
                        if not ef.source_url:
                            ef.source_url = source.url.replace(".model.json", "")
                        result = await self._process_single_file(
                            db, job, source, [source.id], ef,
                            qa_agent, uniqueness_agent, job_id_str,
                            modify_date=modify_date,
                        )
                        files_created += 1
                        if result == "approved":
                            files_approved += 1
                        elif result == "pending_review":
                            files_review += 1
                        else:
                            files_rejected += 1

                        # Record RunPage: replaced or created
                        try:
                            # Get the file_id from the most recently created file for this source
                            latest_file_stmt = (
                                select(KBFile)
                                .where(KBFile.source_url == ef.source_url)
                                .where(KBFile.status != "superseded")
                                .order_by(KBFile.modify_date.desc())
                                .limit(1)
                            )
                            latest_result = await db.execute(latest_file_stmt)
                            latest_file = latest_result.scalars().first()
                            file_id = latest_file.id if latest_file else None
                            content_bytes = len(ef.md_content.encode()) if ef.md_content else None

                            outcome = "replaced" if had_existing_file else "created"
                            await run_page_queries.create_run_page(
                                db,
                                job_id=job.id,
                                url=source.url,
                                outcome=outcome,
                                file_id=file_id,
                                bytes=content_bytes,
                            )
                        except Exception:
                            logger.warning("Failed to record RunPage for %s", source.url, exc_info=True)

                await source_queries.mark_ingested(db, source.id)
                await job_queries.update_job_status(db, job_id, "completed")
                await job_queries.update_job(db, job_id, progress_pct=100)
                # Trigger handles last_run_at; clear active_job pointer
                await source_queries.set_active_job(db, source.id, None)
                await db.commit()

            await self._stream.publish(
                job_id_str, "progress", "job_complete",
                {
                    "job_id": job_id_str,
                    "files_created": files_created,
                    "files_approved": files_approved,
                    "files_review": files_review,
                    "files_rejected": files_rejected,
                    "progress_pct": 100,
                },
            )
            await self._stream.close_channel(job_id_str, "progress")

            # Trigger KB sync if any files were uploaded to S3
            if files_approved > 0:
                await self._trigger_kb_sync(context=f"run_process job={job_id_str[:8]}")

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("✅ [job=%s] Process DONE in %.1fms — created=%d, approved=%d, review=%d, rejected=%d",
                        job_id_str[:8], elapsed, files_created, files_approved, files_review, files_rejected)

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.exception("💥 [job=%s] Process FAILED after %.1fms: %s", job_id_str[:8], elapsed, exc)
            await self._fail_job(job_id, str(exc), "progress")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_modify_date(aem_json: dict) -> datetime:
        jcr = aem_json.get("jcr:content")
        candidates: list[dict] = [aem_json]
        if isinstance(jcr, dict):
            candidates.append(jcr)
        for source in candidates:
            for key in ("jcr:lastModified", "cq:lastModified", "lastModified"):
                val = source.get(key)
                if not val:
                    continue
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    continue
        return datetime.now(timezone.utc)

    async def _check_versioning_and_cleanup(
        self,
        source_url: str,
        modify_date: datetime,
        db: AsyncSession,
    ) -> str:
        decision = await self._versioning.check_and_supersede(source_url, modify_date, db)
        if decision == "process":
            stmt = (
                select(KBFile)
                .where(KBFile.source_url == source_url)
                .where(KBFile.status == "superseded")
                .order_by(KBFile.modify_date.desc())
            )
            result = await db.execute(stmt)
            superseded_file = result.scalars().first()
            if superseded_file and superseded_file.s3_key:
                await self._s3.delete(superseded_file.s3_key)
        return decision

    async def _process_single_file(
        self,
        db: AsyncSession,
        job: Any,
        source: Any,
        source_ids: list[uuid.UUID],
        extracted_file: Any,
        qa_agent: QAAgent,
        uniqueness_agent: UniquenessAgent,
        job_id_str: str,
        modify_date: datetime | None = None,
    ) -> str:
        """Run QA + Uniqueness, route, optionally upload a single extracted file.

        Links ALL source_ids to the produced KBFile via M2M junction.
        """
        file_title = getattr(extracted_file, "title", "unknown")
        primary_source_id = source_ids[0] if source_ids else None
        s_region = source.region if source is not None else None
        s_brand = source.brand if source is not None else None
        s_kb_target = source.kb_target if source is not None else "public"
        s_language = source.language if source is not None else None
        # Sentinel — set after create_file succeeds so the except branch
        # can reliably mark the row as rejected if anything below fails.
        kb_file = None
        try:
            kb_file = await file_queries.create_file(
                db,
                job_id=job.id,
                title=extracted_file.title,
                md_content=extracted_file.md_content,
                source_url=extracted_file.source_url,
                region=extracted_file.region or s_region,
                brand=extracted_file.brand or s_brand,
                kb_target=s_kb_target,
                language=getattr(extracted_file, "language", None) or s_language,
                category=getattr(extracted_file, "category", None),
                visibility=getattr(extracted_file, "visibility", None),
                tags=getattr(extracted_file, "tags", None) or None,
                modify_date=modify_date,
                status="pending_review",
            )

            # Link all participating sources to this file + update active pointer
            for sid in source_ids:
                await file_queries.link_source_to_file(db, sid, kb_file.id)
                await source_queries.set_active_file(db, sid, kb_file.id)

            await self._stream.publish(
                job_id_str, "progress", "file_created",
                {"file_id": str(kb_file.id), "title": kb_file.title},
            )

            # QA + Uniqueness
            qa_metadata = {
                "title": extracted_file.title,
                "source_url": extracted_file.source_url,
                "region": extracted_file.region or s_region,
                "brand": extracted_file.brand or s_brand,
            }
            qa_result = await run_qa_and_uniqueness(
                extracted_file.md_content,
                metadata=qa_metadata,
                qa_agent=qa_agent,
                uniqueness_agent=uniqueness_agent,
            )

            metadata_complete = all([
                extracted_file.title,
                extracted_file.source_url,
                extracted_file.region or s_region,
                extracted_file.brand or s_brand,
            ])

            status = route_file(
                qa_result.quality_verdict,
                qa_result.uniqueness_verdict,
                metadata_complete,
            )

            await file_queries.update_file(
                db,
                kb_file.id,
                quality_verdict=qa_result.quality_verdict,
                quality_reasoning=qa_result.quality_reasoning,
                uniqueness_verdict=qa_result.uniqueness_verdict,
                uniqueness_reasoning=qa_result.uniqueness_reasoning,
                similar_file_ids=[
                    uuid.UUID(sid) for sid in qa_result.similar_file_ids if sid
                ] or None,
                status=status,
            )

            await self._stream.publish(
                job_id_str, "progress", "qa_complete",
                {
                    "file_id": str(kb_file.id),
                    "quality_verdict": qa_result.quality_verdict,
                    "uniqueness_verdict": qa_result.uniqueness_verdict,
                    "status": status,
                    "progress_pct": 85,
                },
            )

            if status == "approved":
                refreshed = await file_queries.get_file(db, kb_file.id)
                if refreshed:
                    s3_key = await self._s3.upload(refreshed)
                    if s3_key:
                        await file_queries.update_file(db, refreshed.id, s3_key=s3_key)

            return status

        except Exception as exc:
            logger.warning("⚠️ [job=%s] File '%s' failed: %s", job_id_str[:8], file_title, exc)
            if kb_file is not None:
                try:
                    await file_queries.update_file(
                        db, kb_file.id, status="rejected",
                        quality_reasoning=f"Processing error: {exc}",
                    )
                except Exception:
                    logger.exception(
                        "💥 [job=%s] Failed to mark file %s as rejected after error",
                        job_id_str[:8], kb_file.id,
                    )
            await self._stream.publish(
                job_id_str, "progress", "error", {"message": f"File error: {exc}"},
            )
            return "rejected"

    # ------------------------------------------------------------------
    # Upload path — markdown file uploaded via /files/upload
    # ------------------------------------------------------------------

    async def process_upload(
        self,
        file_id: uuid.UUID,
        *,
        folder_defaults: dict[str, str] | None = None,
    ) -> None:
        """Enrich metadata + run QA + Uniqueness on an uploaded markdown file.

        Called as a background task after ``POST /files/upload`` creates the
        KBFile row. Mirrors the post-creation half of ``_process_single_file``,
        but invokes ``MetadataEnricher`` first (the URL flow gets metadata from
        the Extractor; uploads have to derive their own).

        On routing to ``approved`` the S3 upload + Bedrock sync are kicked off
        automatically, matching the URL-ingestion behaviour. Approval still
        runs through the same gates — an upload only auto-approves when QA
        accepts, uniqueness is unique/overlapping, and metadata is complete.
        """
        file_id_str = str(file_id)
        bind_log_context(file_id=file_id_str[:8], phase="upload")
        t0 = time.perf_counter()
        logger.info("📥 [file=%s] Upload pipeline STARTED", file_id_str[:8])

        try:
            async with self._session_factory() as db:
                kb_file = await file_queries.get_file(db, file_id)
                if kb_file is None:
                    logger.warning("⚠️ Upload pipeline: file %s not found", file_id_str)
                    return

                # 1. Enrich metadata via Haiku (folder defaults override LLM)
                enricher = MetadataEnricher()
                enriched = await enricher.run(
                    kb_file.md_content,
                    display_name=kb_file.title,
                    folder_defaults=folder_defaults,
                )

                effective_region = (
                    (folder_defaults or {}).get("region") or kb_file.region
                )
                effective_language = (
                    (folder_defaults or {}).get("language") or kb_file.language
                )

                await file_queries.update_file(
                    db, file_id,
                    title=enriched.title or kb_file.title,
                    brand=enriched.brand,
                    category=enriched.category,
                    visibility=enriched.visibility,
                    tags=enriched.tags or None,
                    region=effective_region,
                    language=effective_language,
                )
                await db.commit()

                # 2. QA + Uniqueness — concurrent
                qa_metadata = {
                    "title": enriched.title,
                    "source_url": kb_file.source_url,
                    "region": effective_region,
                    "brand": enriched.brand,
                }
                qa_result = await run_qa_and_uniqueness(
                    kb_file.md_content, metadata=qa_metadata,
                )

                metadata_complete = all([
                    enriched.title,
                    kb_file.source_url,
                    effective_region,
                    enriched.brand and enriched.brand != "unknown",
                ])
                status = route_file(
                    qa_result.quality_verdict,
                    qa_result.uniqueness_verdict,
                    metadata_complete,
                )

                await file_queries.update_file(
                    db, file_id,
                    quality_verdict=qa_result.quality_verdict,
                    quality_reasoning=qa_result.quality_reasoning,
                    uniqueness_verdict=qa_result.uniqueness_verdict,
                    uniqueness_reasoning=qa_result.uniqueness_reasoning,
                    similar_file_ids=[
                        uuid.UUID(sid) for sid in qa_result.similar_file_ids if sid
                    ] or None,
                    status=status,
                )
                await db.commit()

                # 3. Auto-S3-upload + KB sync if routing said approved.
                if status == "approved":
                    refreshed = await file_queries.get_file(db, file_id)
                    if refreshed is not None:
                        namespace, folder_path = await resolve_upload_context(
                            db, refreshed,
                        )
                        s3_key = await self._s3.upload(
                            refreshed,
                            namespace=namespace,
                            folder_path=folder_path,
                        )
                        if s3_key:
                            await file_queries.update_file(
                                db, refreshed.id, s3_key=s3_key,
                            )
                            await db.commit()

            if status == "approved":
                await self._trigger_kb_sync(
                    context=f"upload file={file_id_str[:8]}",
                )

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "✅ [file=%s] Upload pipeline DONE in %.1fms — status=%s",
                file_id_str[:8], elapsed, status,
            )

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.exception(
                "💥 [file=%s] Upload pipeline FAILED after %.1fms: %s",
                file_id_str[:8], elapsed, exc,
            )
            # Best-effort: mark file rejected so it doesn't dangle in
            # pending_review forever after a transient enrichment failure.
            try:
                async with self._session_factory() as db:
                    await file_queries.update_file(
                        db, file_id,
                        status="rejected",
                        quality_reasoning=f"Upload processing error: {exc}",
                    )
                    await db.commit()
            except Exception:
                logger.exception(
                    "💥 [file=%s] Failed to mark file rejected after error",
                    file_id_str[:8],
                )

    async def _fail_job(self, job_id: uuid.UUID, error_message: str, channel: str) -> None:
        """Mark a job as failed and clear the source's active_job pointer.

        The parent source is also flipped to status='failed' so the UI shows
        the failure and reingest is unblocked.
        """
        job_id_str = str(job_id)
        try:
            async with self._session_factory() as db:
                # Use a fresh session so we do not inherit a poisoned transaction
                # from the caller (e.g. an asyncpg InterfaceError that triggered
                # this failure path in the first place).
                job = await job_queries.get_job(db, job_id)
                await job_queries.update_job_status(
                    db, job_id, "failed", error_message=error_message,
                )
                if job is not None and job.source_id is not None:
                    await source_queries.mark_failed(db, job.source_id)
                await db.commit()
        except Exception:
            logger.exception("💥 [job=%s] Failed to update job/source status", job_id_str[:8])
        try:
            await self._stream.publish(job_id_str, channel, "error",
                                       {"job_id": job_id_str, "message": error_message})
            await self._stream.close_channel(job_id_str, channel)
        except Exception:
            logger.exception("💥 [job=%s] Failed to publish error event", job_id_str[:8])

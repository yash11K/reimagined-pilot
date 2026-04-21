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
from typing import Any

import httpx
from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kb_manager.agents import (
    DiscoveryAgent,
    ExtractorAgent,
    QAAgent,
)
from kb_manager.config import get_settings
from kb_manager.models import KBFile, Source
from kb_manager.queries import files as file_queries
from kb_manager.queries import jobs as job_queries
from kb_manager.queries import queue as queue_queries
from kb_manager.queries import sources as source_queries
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
from kb_manager.services.versioning import VersioningService

logger = logging.getLogger(__name__)

_EN_PATH_MARKER = "/en/"


def _is_english_url(url: str) -> bool:
    """Return True only if URL contains /en/ path segment."""
    return _EN_PATH_MARKER in url


class Pipeline:
    """Orchestrates the two-phase ingestion pipeline."""

    def __init__(
        self,
        stream_manager: StreamManager,
        s3_uploader: S3Uploader,
        versioning_service: VersioningService,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        settings = get_settings()
        self._stream = stream_manager
        self._s3 = s3_uploader
        self._versioning = versioning_service
        self._session_factory = session_factory
        self._settings = settings
        logger.info("🔧 Pipeline initialised")

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
        t0 = time.perf_counter()
        logger.info("🔍 [job=%s] Scout STARTED for %s", job_id_str[:8], source_url)

        try:
            await self._stream.publish(
                job_id_str, "scout", "scouting_started",
                {"job_id": job_id_str, "source_url": source_url},
            )

            # Update progress: scout started
            async with self._session_factory() as db:
                await job_queries.update_job(db, job_id, progress_pct=10)
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
                parent_source = job.source
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

                # --- Filter + collect denied sources ---
                if is_cross_domain(resolved_url, source_url):
                    denied_sources.append({
                        "url": resolved_url, "status": "denied_cross_domain",
                        "reason": "Cross-domain link", "anchor": cl.anchor_text,
                    })
                    denied_count += 1
                    continue
                if is_denied_url(resolved_url):
                    denied_sources.append({
                        "url": resolved_url, "status": "denied_path",
                        "reason": "Denied URL path segment", "anchor": cl.anchor_text,
                    })
                    denied_count += 1
                    continue
                if is_self_link(resolved_url, source_url):
                    nav_count += 1
                    continue
                if is_ignored_url(resolved_url):
                    denied_sources.append({
                        "url": resolved_url, "status": "denied_ignored",
                        "reason": "Ignored URL (homepage/index)", "anchor": cl.anchor_text,
                    })
                    nav_count += 1
                    continue
                if not _is_english_url(resolved_url):
                    denied_sources.append({
                        "url": resolved_url, "status": "denied_non_english",
                        "reason": "Non-English URL (no /en/ path)", "anchor": cl.anchor_text,
                    })
                    non_en_count += 1
                    continue

                classification = cl.classification

                if classification == "navigation":
                    denied_sources.append({
                        "url": resolved_url, "status": "denied_navigation",
                        "reason": cl.reason or "Classified as navigation by Discovery Agent",
                        "anchor": cl.anchor_text,
                    })
                    nav_count += 1
                    continue

                if classification == "certain":
                    certain_links.append({
                        "url": resolved_url, "anchor_text": cl.anchor_text,
                        "reason": cl.reason,
                    })
                    certain_count += 1
                else:
                    uncertain_links.append({
                        "url": resolved_url, "anchor_text": cl.anchor_text,
                        "reason": cl.reason,
                    })
                    uncertain_count += 1

            # --- Session 2: Batch-write all classified links + finalise job ---
            async with self._session_factory() as db:
                # Write denied sources
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
                            status=ds["status"],
                            metadata_={
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
                    )
                    await queue_queries.add_to_queue(
                        db,
                        url=cl_data["url"],
                        region=parent_region,
                        brand=parent_brand,
                        kb_target=parent_kb_target,
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
                    )
                    await source_queries.update_source(
                        db, discovered_source.id, status="needs_confirmation",
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
                    "non_en_skipped": non_en_count,
                    "already_seen": already_seen_count,
                    "junk_dropped": junk_count,
                }
                scout_summary = {
                    "components": components_data,
                    "summary": summary,
                }

                await source_queries.mark_scouted(db, parent_source_id, scout_summary)
                await job_queries.update_job(db, job_id, status="processing", progress_pct=40)
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
        t0 = time.perf_counter()
        logger.info("⚙️ [job=%s] Process STARTED", job_id_str[:8])

        # Concurrency is managed by the queue worker's semaphore, not the pipeline.
        try:
            async with self._session_factory() as db:
                job = await job_queries.get_job(db, job_id)
                if job is None:
                    raise ValueError(f"Job {job_id} not found")

                source = job.source
                steering = job.steering_prompt

                await self._stream.publish(
                    job_id_str, "progress", "extraction_started",
                    {"job_id": job_id_str, "total_pages": 1, "progress_pct": 50},
                )

                # Update progress: extraction started
                await job_queries.update_job(db, job.id, progress_pct=50)

                extractor = ExtractorAgent()
                qa_agent = QAAgent()

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

                if source.url:
                    try:
                        async with httpx.AsyncClient(timeout=self._settings.AEM_REQUEST_TIMEOUT) as client:
                            source_resp = await client.get(source.url)
                            source_resp.raise_for_status()
                            source_json = source_resp.json()
                        modify_date = self._extract_modify_date(source_json)

                        v_decision = await self._check_versioning_and_cleanup(source.url, modify_date, db)
                        if v_decision == "skip":
                            logger.info("⏭️ [job=%s] Source unchanged — skip", job_id_str[:8])
                            skip_source = True
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
                            db, job, [source.id], ef, qa_agent, job_id_str,
                            modify_date=modify_date,
                        )
                        files_created += 1
                        if result == "approved":
                            files_approved += 1
                        elif result == "pending_review":
                            files_review += 1
                        else:
                            files_rejected += 1

                await source_queries.mark_ingested(db, source.id)
                await job_queries.update_job_status(db, job_id, "completed")
                await job_queries.update_job(db, job_id, progress_pct=100)
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

            elapsed = (time.perf_counter() - t0) * 1000
            logger.info("✅ [job=%s] Process DONE in %.1fms — created=%d, approved=%d, review=%d, rejected=%d",
                        job_id_str[:8], elapsed, files_created, files_approved, files_review, files_rejected)

        except Exception as exc:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.exception("💥 [job=%s] Process FAILED after %.1fms: %s", job_id_str[:8], elapsed, exc)
            await self._fail_job(job_id, str(exc), "progress")

    # ------------------------------------------------------------------
    # Upload flow
    # ------------------------------------------------------------------

    async def run_upload_process(
        self,
        job_id: uuid.UUID,
        files: list[UploadFile],
    ) -> None:
        """Upload flow: Parse → QA → Route → Upload approved → Complete."""
        job_id_str = str(job_id)
        t0 = time.perf_counter()
        logger.info("📤 [job=%s] Upload process STARTED — %d files", job_id_str[:8], len(files))

        try:
            async with self._session_factory() as db:
                job = await job_queries.get_job(db, job_id)
                if job is None:
                    raise ValueError(f"Job {job_id} not found")

                source = job.source
                qa_agent = QAAgent()

                await self._stream.publish(
                    job_id_str, "progress", "extraction_started",
                    {"job_id": job_id_str, "total_pages": len(files)},
                )

                files_created = 0
                files_approved = 0
                files_review = 0
                files_rejected = 0

                for idx, upload_file in enumerate(files):
                    try:
                        content = (await upload_file.read()).decode("utf-8")
                        filename = upload_file.filename or f"upload_{idx}"
                        await self._stream.publish(
                            job_id_str, "progress", "page_processing",
                            {"url": filename, "page_number": idx + 1, "total": len(files)},
                        )

                        title = filename.rsplit(".", 1)[0] if "." in filename else filename

                        from kb_manager.agents.extractor import ExtractedFile
                        ef = ExtractedFile(
                            title=title,
                            md_content=content,
                            source_url=filename,
                            content_type="upload",
                            region=source.region,
                            brand=source.brand,
                        )

                        result = await self._process_single_file(
                            db, job, [source.id], ef, qa_agent, job_id_str,
                        )
                        files_created += 1
                        if result == "approved":
                            files_approved += 1
                        elif result == "pending_review":
                            files_review += 1
                        else:
                            files_rejected += 1

                    except Exception as exc:
                        logger.warning("⚠️ [job=%s] Upload failed %s: %s",
                                       job_id_str[:8], upload_file.filename, exc)
                        files_rejected += 1

                await job_queries.update_job_status(db, job_id, "completed")
                await job_queries.update_job(db, job_id, progress_pct=100)
                await db.commit()

            await self._stream.publish(
                job_id_str, "progress", "job_complete",
                {"job_id": job_id_str, "files_created": files_created},
            )
            await self._stream.close_channel(job_id_str, "progress")

        except Exception as exc:
            logger.exception("💥 [job=%s] Upload FAILED: %s", job_id_str[:8], exc)
            await self._fail_job(job_id, str(exc), "progress")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_modify_date(aem_json: dict) -> datetime:
        for key in ("jcr:lastModified", "cq:lastModified", "lastModified"):
            val = aem_json.get(key)
            if val:
                try:
                    return datetime.fromisoformat(val.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass
            jcr = aem_json.get("jcr:content", {})
            if isinstance(jcr, dict):
                val = jcr.get(key)
                if val:
                    try:
                        return datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
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
                self._s3.delete(superseded_file.s3_key)
        return decision

    async def _process_single_file(
        self,
        db: AsyncSession,
        job: Any,
        source_ids: list[uuid.UUID],
        extracted_file: Any,
        qa_agent: QAAgent,
        job_id_str: str,
        modify_date: datetime | None = None,
    ) -> str:
        """Run QA, route, optionally upload a single extracted file.

        Links ALL source_ids to the produced KBFile via M2M junction.
        """
        file_title = getattr(extracted_file, "title", "unknown")
        primary_source_id = source_ids[0] if source_ids else None
        try:
            kb_file = await file_queries.create_file(
                db,
                job_id=job.id,
                title=extracted_file.title,
                md_content=extracted_file.md_content,
                source_url=extracted_file.source_url,
                region=extracted_file.region or (job.source.region if job.source else None),
                brand=extracted_file.brand or (job.source.brand if job.source else None),
                kb_target=job.source.kb_target if job.source else "public",
                category=getattr(extracted_file, "category", None),
                visibility=getattr(extracted_file, "visibility", None),
                tags=getattr(extracted_file, "tags", None) or None,
                modify_date=modify_date,
                status="pending_review",
            )

            # Link all participating sources to this file
            for sid in source_ids:
                await file_queries.link_source_to_file(db, sid, kb_file.id)

            await self._stream.publish(
                job_id_str, "progress", "file_created",
                {"file_id": str(kb_file.id), "title": kb_file.title},
            )

            # QA
            qa_metadata = {
                "title": extracted_file.title,
                "source_url": extracted_file.source_url,
                "region": extracted_file.region or (job.source.region if job.source else None),
                "brand": extracted_file.brand or (job.source.brand if job.source else None),
            }
            qa_result = await qa_agent.run(extracted_file.md_content, metadata=qa_metadata)

            metadata_complete = all([
                extracted_file.title,
                extracted_file.source_url,
                extracted_file.region or (job.source.region if job.source else None),
                extracted_file.brand or (job.source.brand if job.source else None),
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
                kb_file = await file_queries.get_file(db, kb_file.id)
                if kb_file:
                    s3_key = self._s3.upload(kb_file)
                    if s3_key:
                        await file_queries.update_file(db, kb_file.id, s3_key=s3_key)

            return status

        except Exception as exc:
            logger.warning("⚠️ [job=%s] File '%s' failed: %s", job_id_str[:8], file_title, exc)
            try:
                if "kb_file" in dir() and kb_file:
                    await file_queries.update_file(
                        db, kb_file.id, status="rejected",
                        quality_reasoning=f"Processing error: {exc}",
                    )
            except Exception:
                pass
            await self._stream.publish(
                job_id_str, "progress", "error", {"message": f"File error: {exc}"},
            )
            return "rejected"

    async def _fail_job(self, job_id: uuid.UUID, error_message: str, channel: str) -> None:
        """Mark a job as failed and roll the parent source back to a retry-able state.

        Without the source rollback, a crashed job leaves its source stuck at
        `identified` / `is_scouted=True` but never `ingested`, which blocks
        future reruns via the dedup path in scout.
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

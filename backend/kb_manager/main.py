"""FastAPI application factory with async lifespan, CORS, and health endpoint."""

import logging
import time
import uuid
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from kb_manager.database import init_engine, dispose_engine, async_session_factory
from kb_manager.logging_config import (
    bind_log_context,
    clear_log_context,
    configure_logging,
)
from kb_manager.routes.ingest import router as ingest_router
from kb_manager.routes.files import router as files_router
from kb_manager.routes.folders import router as folders_router
from kb_manager.routes.sources import router as sources_router
from kb_manager.routes.jobs import router as jobs_router
from kb_manager.routes.kb import router as kb_router
from kb_manager.routes.stats import router as stats_router
from kb_manager.routes.queue import router as queue_router
from kb_manager.routes.activity import router as activity_router
from kb_manager.routes.search import router as search_router
from kb_manager.services.stream_manager import StreamManager
from kb_manager.services.s3_uploader import S3Uploader
from kb_manager.services.versioning import VersioningService
from kb_manager.services.pipeline import Pipeline
from kb_manager.services.queue_worker import QueueWorker
from kb_manager.services.bedrock_kb import BedrockKBClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: initialise DB engine, services, and pipeline. Shutdown: dispose engine."""
    configure_logging()
    logger.info("🚀 Starting KB Manager v2 — initialising services...")

    init_engine()
    logger.info("🗄️ Database engine initialised")

    # Import here to get the initialised session factory
    from kb_manager.database import async_session_factory as session_factory

    stream_manager = StreamManager()
    s3_uploader = S3Uploader()
    versioning_service = VersioningService()
    bedrock_kb_client = BedrockKBClient()
    pipeline = Pipeline(
        stream_manager=stream_manager,
        s3_uploader=s3_uploader,
        versioning_service=versioning_service,
        session_factory=session_factory,
        kb_client=bedrock_kb_client,
    )

    app.state.stream_manager = stream_manager
    app.state.s3_uploader = s3_uploader
    app.state.session_factory = session_factory
    app.state.pipeline = pipeline
    app.state.bedrock_kb_client = bedrock_kb_client

    # Start the background queue worker
    queue_worker = QueueWorker(
        pipeline=pipeline,
        stream_manager=stream_manager,
        session_factory=session_factory,
    )
    queue_worker.start()
    app.state.queue_worker = queue_worker

    logger.info("✅ All services initialised — StreamManager, S3Uploader, VersioningService, BedrockKBClient, Pipeline, QueueWorker")
    logger.info("🟢 KB Manager v2 is ready to accept requests")

    yield

    logger.info("🛑 Shutting down KB Manager v2...")
    queue_worker.stop()
    await dispose_engine()
    logger.info("🗄️ Database engine disposed — goodbye 👋")


def create_app() -> FastAPI:
    """Build and return the configured FastAPI application."""
    app = FastAPI(title="KB Manager v2", lifespan=lifespan)

    # CORS — allow all origins for development
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Catch-all so internal stack traces never reach API consumers.

        ``HTTPException`` is handled by FastAPI's built-in handler and never
        reaches this one. Domain-specific handlers (IntegrityError,
        ClientError, httpx errors) can be layered on top later — see
        action plan #24 for structlog + correlation IDs.
        """
        # Re-raise HTTPException so FastAPI's default handler returns the
        # proper status + detail set by the route.
        if isinstance(exc, HTTPException):
            raise exc
        logger.exception(
            "💥 Unhandled exception on %s %s", request.method, request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_error",
                "detail": "An unexpected error occurred.",
            },
        )

    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        """Log every incoming request and bind a correlation id to all logs.

        The ``X-Request-Id`` header on the response makes the id visible to
        clients/proxies so they can quote it when reporting issues. Inside
        the process, ``request_id`` is bound to a contextvar so every log
        line emitted while handling this request carries it automatically.
        """
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        bind_log_context(request_id=request_id)
        try:
            start = time.perf_counter()
            method = request.method
            path = request.url.path
            logger.info("📥 %s %s", method, path)

            response: Response = await call_next(request)

            elapsed_ms = (time.perf_counter() - start) * 1000
            status = response.status_code
            if status >= 500:
                logger.error("💥 %s %s → %d (%.1fms)", method, path, status, elapsed_ms)
            elif status >= 400:
                logger.warning("⚠️ %s %s → %d (%.1fms)", method, path, status, elapsed_ms)
            else:
                logger.info("📤 %s %s → %d (%.1fms)", method, path, status, elapsed_ms)

            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            clear_log_context()

    # Mount route modules under /api/v1
    app.include_router(ingest_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(folders_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(kb_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.include_router(queue_router, prefix="/api/v1")
    app.include_router(activity_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

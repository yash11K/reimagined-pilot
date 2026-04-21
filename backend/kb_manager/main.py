"""FastAPI application factory with async lifespan, CORS, and health endpoint."""

import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from kb_manager.database import init_engine, dispose_engine, async_session_factory
from kb_manager.routes.ingest import router as ingest_router
from kb_manager.routes.files import router as files_router
from kb_manager.routes.sources import router as sources_router
from kb_manager.routes.jobs import router as jobs_router
from kb_manager.routes.kb import router as kb_router
from kb_manager.routes.nav import router as nav_router
from kb_manager.routes.stats import router as stats_router
from kb_manager.routes.queue import router as queue_router
from kb_manager.routes.activity import router as activity_router
from kb_manager.routes.search import router as search_router
from kb_manager.services.stream_manager import StreamManager
from kb_manager.services.s3_uploader import S3Uploader
from kb_manager.services.versioning import VersioningService
from kb_manager.services.pipeline import Pipeline
from kb_manager.services.queue_worker import QueueWorker

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """Set up structured logging with emoji prefixes for the entire application."""
    log_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Quiet down noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: initialise DB engine, services, and pipeline. Shutdown: dispose engine."""
    _configure_logging()
    logger.info("🚀 Starting KB Manager v2 — initialising services...")

    init_engine()
    logger.info("🗄️ Database engine initialised")

    # Import here to get the initialised session factory
    from kb_manager.database import async_session_factory as session_factory

    stream_manager = StreamManager()
    s3_uploader = S3Uploader()
    versioning_service = VersioningService()
    pipeline = Pipeline(
        stream_manager=stream_manager,
        s3_uploader=s3_uploader,
        versioning_service=versioning_service,
        session_factory=session_factory,
    )

    app.state.stream_manager = stream_manager
    app.state.s3_uploader = s3_uploader
    app.state.session_factory = session_factory
    app.state.pipeline = pipeline

    # Start the background queue worker
    queue_worker = QueueWorker(
        pipeline=pipeline,
        stream_manager=stream_manager,
        session_factory=session_factory,
    )
    queue_worker.start()
    app.state.queue_worker = queue_worker

    logger.info("✅ All services initialised — StreamManager, S3Uploader, VersioningService, Pipeline, QueueWorker")
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

    @app.middleware("http")
    async def log_requests(request: Request, call_next) -> Response:
        """Log every incoming request and its response time."""
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

        return response

    # Mount route modules under /api/v1
    app.include_router(ingest_router, prefix="/api/v1")
    app.include_router(files_router, prefix="/api/v1")
    app.include_router(sources_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(kb_router, prefix="/api/v1")
    app.include_router(nav_router, prefix="/api/v1")
    app.include_router(stats_router, prefix="/api/v1")
    app.include_router(queue_router, prefix="/api/v1")
    app.include_router(activity_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok"}

    return app


app = create_app()

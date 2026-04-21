"""Centralized configuration loaded from environment variables."""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    DATABASE_URL: str
    S3_BUCKET_NAME: str
    AWS_REGION: str = "us-east-1"
    BEDROCK_MODEL_ID: str = "us.anthropic.claude-sonnet-4-20250514-v1:0"
    HAIKU_MODEL_ID: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    BEDROCK_KB_ID: str | None = None
    BEDROCK_MAX_TOKENS: int = 16000
    HAIKU_MAX_TOKENS: int = 8192
    AEM_REQUEST_TIMEOUT: int = 30
    MAX_CONCURRENT_JOBS: int = 3
    QUEUE_POLL_INTERVAL: int = 3  # seconds between queue checks when idle
    QUEUE_MAX_RETRIES: int = 3
    QUEUE_RETRY_BASE_DELAY: int = 5  # seconds; actual delay = base * 2^retry_count
    QUEUE_STALE_TIMEOUT: int = 300  # seconds before a processing item is considered stale

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    settings = Settings()
    logger.info("⚙️ Settings loaded — region=%s, bucket=%s, max_jobs=%d, bedrock_model=%s",
                settings.AWS_REGION, settings.S3_BUCKET_NAME,
                settings.MAX_CONCURRENT_JOBS, settings.BEDROCK_MODEL_ID)
    return settings

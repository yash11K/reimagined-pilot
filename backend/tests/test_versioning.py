"""Unit tests for the Versioning Service (Requirements 18.1, 18.2, 18.3, 18.4)."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kb_manager.services.versioning import VersioningService


def _make_kb_file(
    *,
    source_url: str = "https://example.com/page",
    modify_date: datetime | None = None,
    status: str = "approved",
    s3_key: str | None = "public/avis/nam/page/page.md",
) -> MagicMock:
    """Create a mock KBFile with sensible defaults."""
    f = MagicMock()
    f.id = uuid.uuid4()
    f.source_url = source_url
    f.modify_date = modify_date
    f.status = status
    f.s3_key = s3_key
    return f


def _mock_db(existing_file=None):
    """Return an AsyncMock db session whose execute returns *existing_file*."""
    db = AsyncMock()
    scalars_mock = MagicMock()
    scalars_mock.first.return_value = existing_file
    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock
    db.execute.return_value = result_mock
    return db


# ---------------------------------------------------------------------------
# No existing file → "process"
# ---------------------------------------------------------------------------

class TestNoExistingFile:
    """When no file exists for the source_url, return 'process'."""

    @pytest.mark.asyncio
    async def test_returns_process_when_no_existing(self):
        db = _mock_db(existing_file=None)
        svc = VersioningService()

        result = await svc.check_and_supersede(
            source_url="https://example.com/new-page",
            new_modify_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            db=db,
        )

        assert result == "process"
        db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# Same modify_date → "skip"
# ---------------------------------------------------------------------------

class TestSameModifyDate:
    """When existing file has the same modify_date, return 'skip'."""

    @pytest.mark.asyncio
    async def test_returns_skip_when_dates_equal(self):
        dt = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        existing = _make_kb_file(modify_date=dt)
        db = _mock_db(existing_file=existing)
        svc = VersioningService()

        result = await svc.check_and_supersede(
            source_url="https://example.com/page",
            new_modify_date=dt,
            db=db,
        )

        assert result == "skip"
        # Status should NOT have changed
        assert existing.status != "superseded"


# ---------------------------------------------------------------------------
# Newer modify_date → "process" + supersede old
# ---------------------------------------------------------------------------

class TestNewerModifyDate:
    """When new modify_date is newer, return 'process' and mark old as superseded."""

    @pytest.mark.asyncio
    async def test_returns_process_and_supersedes_old(self):
        old_dt = datetime(2025, 5, 1, tzinfo=timezone.utc)
        new_dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        existing = _make_kb_file(modify_date=old_dt, status="approved")
        db = _mock_db(existing_file=existing)
        svc = VersioningService()

        result = await svc.check_and_supersede(
            source_url="https://example.com/page",
            new_modify_date=new_dt,
            db=db,
        )

        assert result == "process"
        assert existing.status == "superseded"
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_supersedes_when_existing_has_no_modify_date(self):
        """If existing file has modify_date=None, treat new date as newer."""
        existing = _make_kb_file(modify_date=None, status="pending_review")
        db = _mock_db(existing_file=existing)
        svc = VersioningService()

        result = await svc.check_and_supersede(
            source_url="https://example.com/page",
            new_modify_date=datetime(2025, 6, 1, tzinfo=timezone.utc),
            db=db,
        )

        assert result == "process"
        assert existing.status == "superseded"
        db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# Older modify_date → "skip"
# ---------------------------------------------------------------------------

class TestOlderModifyDate:
    """When new modify_date is older than existing, return 'skip'."""

    @pytest.mark.asyncio
    async def test_returns_skip_when_new_is_older(self):
        existing_dt = datetime(2025, 6, 1, tzinfo=timezone.utc)
        older_dt = datetime(2025, 5, 1, tzinfo=timezone.utc)
        existing = _make_kb_file(modify_date=existing_dt, status="approved")
        db = _mock_db(existing_file=existing)
        svc = VersioningService()

        result = await svc.check_and_supersede(
            source_url="https://example.com/page",
            new_modify_date=older_dt,
            db=db,
        )

        assert result == "skip"
        assert existing.status != "superseded"

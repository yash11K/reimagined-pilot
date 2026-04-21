"""Unit tests for the S3 Uploader service (Requirements 17.1, 17.2, 17.3)."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from kb_manager.services.s3_uploader import S3Uploader


# ---------------------------------------------------------------------------
# build_s3_key — pure function, no mocking needed
# ---------------------------------------------------------------------------

class TestBuildS3Key:
    """Tests for S3 key construction (Requirement 17.1)."""

    def test_basic_key(self):
        key = S3Uploader.build_s3_key("public", "avis", "nam", "protections", "loss-damage-waiver.md")
        assert key == "public/avis/nam/protections/loss-damage-waiver.md"

    def test_no_leading_slash(self):
        key = S3Uploader.build_s3_key("/public", "avis", "nam", "ns", "file.md")
        assert not key.startswith("/")

    def test_no_trailing_slash(self):
        key = S3Uploader.build_s3_key("public", "avis", "nam", "ns", "file.md/")
        assert not key.endswith("/")

    def test_no_double_slashes(self):
        key = S3Uploader.build_s3_key("public/", "/avis", "/nam/", "ns", "file.md")
        assert "//" not in key

    def test_strips_slashes_from_all_parts(self):
        key = S3Uploader.build_s3_key("/public/", "/brand/", "/region/", "/ns/", "/file.md/")
        assert key == "public/brand/region/ns/file.md"

    def test_empty_parts_skipped(self):
        key = S3Uploader.build_s3_key("public", "", "nam", "", "file.md")
        assert key == "public/nam/file.md"
        assert "//" not in key

    def test_internal_kb_target(self):
        key = S3Uploader.build_s3_key("internal", "budget", "emea", "faq", "pricing.md")
        assert key == "internal/budget/emea/faq/pricing.md"


# ---------------------------------------------------------------------------
# upload — requires mocked boto3 client
# ---------------------------------------------------------------------------

class TestUpload:
    """Tests for S3 upload (Requirements 17.1, 17.2, 17.3)."""

    def _make_file(self, **overrides) -> MagicMock:
        """Create a mock KBFile with sensible defaults."""
        defaults = {
            "id": uuid.uuid4(),
            "title": "Loss Damage Waiver",
            "md_content": "# LDW\nContent here.",
            "kb_target": "public",
            "brand": "avis",
            "region": "nam",
            "source_url": "https://example.com/protections/ldw",
            "status": "approved",
            "quality_verdict": "good",
            "quality_reasoning": "Well structured",
            "uniqueness_verdict": "unique",
            "uniqueness_reasoning": "No duplicates",
            "reviewed_by": None,
            "review_notes": None,
            "s3_key": None,
            "modify_date": None,
            "created_at": None,
            "merged_from_urls": None,
        }
        defaults.update(overrides)
        file = MagicMock(spec=[])
        for k, v in defaults.items():
            setattr(file, k, v)
        return file

    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    def test_upload_success_returns_key(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="my-bucket", AWS_REGION="us-east-1"
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = self._make_file()
        result = uploader.upload(file)

        assert result is not None
        assert result.startswith("public/avis/nam/")
        assert result.endswith(".md")
        # Should upload both the .md file and the .metadata.json sidecar
        assert mock_client.put_object.call_count == 2

    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    def test_upload_failure_returns_none(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="my-bucket", AWS_REGION="us-east-1"
        )
        mock_client = MagicMock()
        mock_client.put_object.side_effect = Exception("S3 error")
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = self._make_file()
        result = uploader.upload(file)

        assert result is None

    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    def test_upload_with_no_brand_uses_unknown(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="my-bucket", AWS_REGION="us-east-1"
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = self._make_file(brand=None, region=None)
        result = uploader.upload(file)

        assert result is not None
        assert "unknown" in result


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:
    """Tests for S3 delete (used for superseding)."""

    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    def test_delete_success(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="my-bucket", AWS_REGION="us-east-1"
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        assert uploader.delete("public/avis/nam/ns/file.md") is True
        # Should delete both the .md file and the .metadata.json sidecar
        assert mock_client.delete_object.call_count == 2
        mock_client.delete_object.assert_any_call(
            Bucket="my-bucket", Key="public/avis/nam/ns/file.md"
        )
        mock_client.delete_object.assert_any_call(
            Bucket="my-bucket", Key="public/avis/nam/ns/file.md.metadata.json"
        )

    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    def test_delete_failure(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="my-bucket", AWS_REGION="us-east-1"
        )
        mock_client = MagicMock()
        mock_client.delete_object.side_effect = Exception("S3 error")
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        assert uploader.delete("some/key.md") is False


# ---------------------------------------------------------------------------
# generate_presigned_url
# ---------------------------------------------------------------------------

class TestGeneratePresignedUrl:
    """Tests for presigned URL generation (Requirement 19.4)."""

    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    def test_presigned_url_from_s3_uri(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="my-bucket", AWS_REGION="us-east-1"
        )
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://presigned.example.com"
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        url = uploader.generate_presigned_url("s3://other-bucket/some/key.md")

        assert url == "https://presigned.example.com"
        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "other-bucket", "Key": "some/key.md"},
            ExpiresIn=3600,
        )

    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    def test_presigned_url_from_plain_key(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="my-bucket", AWS_REGION="us-east-1"
        )
        mock_client = MagicMock()
        mock_client.generate_presigned_url.return_value = "https://presigned.example.com"
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        url = uploader.generate_presigned_url("public/avis/nam/ns/file.md")

        mock_client.generate_presigned_url.assert_called_once_with(
            "get_object",
            Params={"Bucket": "my-bucket", "Key": "public/avis/nam/ns/file.md"},
            ExpiresIn=3600,
        )

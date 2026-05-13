"""Tests for the M3 sidecar / namespace / recompute additions on S3Uploader."""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from kb_manager.services.s3_uploader import S3Uploader


def _make_file(**overrides) -> MagicMock:
    defaults = {
        "id": uuid.uuid4(),
        "title": "Refueling Policy",
        "md_content": "# Refueling\nContent.",
        "kb_target": "public",
        "brand": "avis",
        "region": "nam",
        "language": "en",
        "source_url": "upload://abc123/refueling.md",
        "status": "approved",
        "quality_verdict": "accepted",
        "quality_reasoning": "ok",
        "uniqueness_verdict": "unique",
        "uniqueness_reasoning": "no match",
        "reviewed_by": None,
        "review_notes": None,
        "s3_key": None,
        "modify_date": None,
        "created_at": None,
        "category": "policy",
        "visibility": "public",
        "tags": ["fuel"],
        "folder_id": None,
    }
    defaults.update(overrides)
    f = MagicMock(spec=[])
    for k, v in defaults.items():
        setattr(f, k, v)
    return f


# ---------------------------------------------------------------------------
# _build_metadata_document folder_path attribute
# ---------------------------------------------------------------------------

class TestSidecarFolderPath:
    def test_folder_path_attribute_present_when_provided(self):
        doc = S3Uploader._build_metadata_document(
            _make_file(), folder_path="Marketing/Brand/Region",
        )
        attrs = doc["metadataAttributes"]
        assert attrs["folder_path"] == {
            "value": "Marketing/Brand/Region", "type": "STRING",
        }

    def test_folder_path_absent_when_none(self):
        doc = S3Uploader._build_metadata_document(_make_file(), folder_path=None)
        assert "folder_path" not in doc["metadataAttributes"]

    def test_folder_path_absent_when_empty_string(self):
        # Helper drops falsy values
        doc = S3Uploader._build_metadata_document(_make_file(), folder_path="")
        assert "folder_path" not in doc["metadataAttributes"]


# ---------------------------------------------------------------------------
# upload — explicit namespace override + folder_path → sidecar
# ---------------------------------------------------------------------------

class TestUploadOverrides:
    @pytest.mark.asyncio
    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    async def test_explicit_namespace_used_in_key(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="b", AWS_REGION="us-east-1",
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = _make_file()
        key = await uploader.upload(file, namespace="my-folder")

        assert key is not None
        # Key path: kb_target/brand/region/language/namespace/filename
        assert "/my-folder/" in key
        # Default behaviour (sniffing source_url) would have produced
        # "refueling.md/" — make sure we did NOT pick that up.
        assert "refueling.md/" not in key

    @pytest.mark.asyncio
    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    async def test_folder_path_lands_in_sidecar(self, mock_boto3, mock_settings):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="b", AWS_REGION="us-east-1",
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = _make_file()
        await uploader.upload(file, folder_path="Docs/Policies")

        # Find the sidecar put_object call
        sidecar_call = next(
            c for c in mock_client.put_object.call_args_list
            if c.kwargs["Key"].endswith(".metadata.json")
        )
        body = json.loads(sidecar_call.kwargs["Body"].decode("utf-8"))
        assert body["metadataAttributes"]["folder_path"]["value"] == "Docs/Policies"

    @pytest.mark.asyncio
    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    async def test_namespace_falls_back_to_source_url_when_none(
        self, mock_boto3, mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="b", AWS_REGION="us-east-1",
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        # Use a URL whose tail is a stable namespace; "refueling.md" → "refueling.md"
        # would also work but use a cleaner URL to keep the assertion obvious.
        file = _make_file(source_url="https://example.com/policies/fuel")
        key = await uploader.upload(file, namespace=None)

        assert "/fuel/" in key


# ---------------------------------------------------------------------------
# recompute_s3_location
# ---------------------------------------------------------------------------

class TestRecompute:
    @pytest.mark.asyncio
    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    async def test_recompute_uploads_new_then_deletes_old(
        self, mock_boto3, mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="b", AWS_REGION="us-east-1",
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        # Simulate metadata change: brand was 'avis', now 'budget' — same
        # filename, new key path.
        file = _make_file(brand="budget")
        old_key = "public/avis/nam/en/general/refueling-policy.md"

        new_key = await uploader.recompute_s3_location(file, old_key)

        assert new_key is not None
        assert new_key.startswith("public/budget/nam/en/")
        # 2 put_object (md + sidecar) + 2 delete_object (md + sidecar)
        assert mock_client.put_object.call_count == 2
        assert mock_client.delete_object.call_count == 2
        # Old key deleted
        delete_keys = {c.kwargs["Key"] for c in mock_client.delete_object.call_args_list}
        assert old_key in delete_keys
        assert f"{old_key}.metadata.json" in delete_keys

    @pytest.mark.asyncio
    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    async def test_recompute_no_delete_when_key_unchanged(
        self, mock_boto3, mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="b", AWS_REGION="us-east-1",
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = _make_file()
        # Compute the key the upload will produce; pass that as old_key so
        # delete is skipped (cosmetic edit produced no key change).
        same_key = await uploader.upload(file)
        mock_client.delete_object.reset_mock()

        new_key = await uploader.recompute_s3_location(file, same_key)
        assert new_key == same_key
        mock_client.delete_object.assert_not_called()

    @pytest.mark.asyncio
    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    async def test_recompute_no_old_key_treats_as_fresh_upload(
        self, mock_boto3, mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="b", AWS_REGION="us-east-1",
        )
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = _make_file()
        new_key = await uploader.recompute_s3_location(file, None)

        assert new_key is not None
        # No delete because there was no previous key
        mock_client.delete_object.assert_not_called()

    @pytest.mark.asyncio
    @patch("kb_manager.services.s3_uploader.get_settings")
    @patch("kb_manager.services.s3_uploader.boto3")
    async def test_recompute_upload_failure_keeps_old_key(
        self, mock_boto3, mock_settings,
    ):
        mock_settings.return_value = MagicMock(
            S3_BUCKET_NAME="b", AWS_REGION="us-east-1",
        )
        mock_client = MagicMock()
        mock_client.put_object.side_effect = Exception("boom")
        mock_boto3.client.return_value = mock_client

        uploader = S3Uploader()
        file = _make_file()
        old_key = "public/avis/nam/en/ns/old.md"
        new_key = await uploader.recompute_s3_location(file, old_key)

        assert new_key is None
        # Crucially: old key NOT deleted when new upload failed.
        mock_client.delete_object.assert_not_called()

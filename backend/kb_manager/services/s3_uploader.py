"""S3 upload service for KB files.

Handles uploading markdown content to S3, deleting superseded files,
and generating presigned download URLs. Uses boto3 with bucket name
from application settings.
"""

import json
import logging
import re

import boto3
from botocore.exceptions import ClientError

from kb_manager.config import get_settings
from kb_manager.models import KBFile

logger = logging.getLogger(__name__)


class S3Uploader:
    """Manages S3 operations for KB file storage."""

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket = settings.S3_BUCKET_NAME
        self._region = settings.AWS_REGION
        self._client = boto3.client("s3", region_name=self._region)
        logger.info("☁️ S3Uploader initialised — bucket=%s, region=%s", self._bucket, self._region)

    @staticmethod
    def build_s3_key(
        kb_target: str,
        brand: str,
        region: str,
        namespace: str,
        filename: str,
    ) -> str:
        """Construct an S3 key from path segments.

        Returns ``{kb_target}/{brand}/{region}/{namespace}/{filename}``
        with no leading/trailing/double slashes.
        """
        parts = [kb_target, brand, region, namespace, filename]
        # Strip slashes from each part, drop empties, join
        raw = "/".join(p.strip("/") for p in parts if p.strip("/"))
        # Collapse any remaining double slashes
        return re.sub(r"/+", "/", raw)

    @staticmethod
    def _build_metadata_key(s3_key: str) -> str:
        """Derive the Bedrock metadata sidecar key from a content key.

        ``some/path/file.md`` → ``some/path/file.md.metadata.json``
        """
        return f"{s3_key}.metadata.json"

    @staticmethod
    def _build_metadata_document(file: KBFile) -> dict:
        """Build a Bedrock Knowledge Base metadata document from a KBFile."""
        attrs: dict[str, dict] = {}

        def _add(name: str, value: str | None, type_: str = "STRING") -> None:
            if value:
                attrs[name] = {"value": value, "type": type_}

        _add("title", file.title)
        _add("source_url", file.source_url)
        _add("region", file.region)
        _add("brand", file.brand)
        _add("kb_target", file.kb_target)
        _add("category", getattr(file, "category", None))
        _add("visibility", getattr(file, "visibility", None))
        _add("status", file.status)
        _add("quality_verdict", file.quality_verdict)
        _add("quality_reasoning", file.quality_reasoning)
        _add("uniqueness_verdict", file.uniqueness_verdict)
        _add("uniqueness_reasoning", file.uniqueness_reasoning)
        _add("reviewed_by", file.reviewed_by)
        _add("review_notes", file.review_notes)
        _add("s3_key", file.s3_key)

        # Tags as STRING_LIST for Bedrock native filtering
        tags = getattr(file, "tags", None)
        if tags:
            attrs["tags"] = {"value": tags, "type": "STRING_LIST"}

        if file.modify_date:
            attrs["modify_date"] = {
                "value": file.modify_date.isoformat(),
                "type": "STRING",
            }
        if file.created_at:
            attrs["created_at"] = {
                "value": file.created_at.isoformat(),
                "type": "STRING",
            }
        # merged_from_urls now tracked via source_kb_files junction table
        # Source URLs available through file.sources relationship

        return {"metadataAttributes": attrs}

    def _upload_metadata(self, s3_key: str, file: KBFile) -> bool:
        """Upload the metadata sidecar JSON for a content file."""
        meta_key = self._build_metadata_key(s3_key)
        meta_doc = self._build_metadata_document(file)
        body = json.dumps(meta_doc, ensure_ascii=False)

        logger.info("📋 Uploading metadata sidecar → s3://%s/%s", self._bucket, meta_key)
        self._client.put_object(
            Bucket=self._bucket,
            Key=meta_key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        logger.info("📋 Metadata sidecar uploaded: %s (%d bytes)", meta_key, len(body))
        return True

    def upload(self, file: KBFile) -> str | None:
        """Upload a KBFile's markdown content and metadata sidecar to S3.

        Args:
            file: The KBFile ORM instance to upload.

        Returns:
            The s3_key on success, or None on failure.
        """
        try:
            # Derive namespace from source_url or fall back to "general"
            namespace = "general"
            if file.source_url:
                # Use the last meaningful path segment as namespace
                path = file.source_url.rstrip("/").rsplit("/", 1)[-1]
                if path:
                    namespace = path

            # Build a safe filename from the title
            safe_title = re.sub(r"[^\w\-]", "-", file.title.lower()).strip("-")
            filename = f"{safe_title}.md"

            s3_key = self.build_s3_key(
                kb_target=file.kb_target,
                brand=file.brand or "unknown",
                region=file.region or "unknown",
                namespace=namespace,
                filename=filename,
            )

            logger.info("☁️ Uploading file %s → s3://%s/%s", file.id, self._bucket, s3_key)
            self._client.put_object(
                Bucket=self._bucket,
                Key=s3_key,
                Body=file.md_content.encode("utf-8"),
                ContentType="text/markdown; charset=utf-8",
            )
            logger.info("☁️ Upload successful: %s (%d bytes)", s3_key, len(file.md_content.encode("utf-8")))

            # Upload metadata sidecar for Bedrock KB filtering
            self._upload_metadata(s3_key, file)

            return s3_key
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code == "NoSuchBucket":
                logger.warning("⚠️ S3 bucket '%s' does not exist — skipping upload for file %s. "
                               "Create the bucket or set S3_BUCKET_NAME in .env",
                               self._bucket, file.id)
            else:
                logger.exception("❌ Failed to upload file %s to S3", file.id)
            return None
        except Exception:
            logger.exception("❌ Failed to upload file %s to S3", file.id)
            return None

    def delete(self, s3_key: str) -> bool:
        """Delete a file and its metadata sidecar from S3.

        Args:
            s3_key: The S3 object key to delete.

        Returns:
            True if deletion succeeded, False otherwise.
        """
        try:
            logger.info("🗑️ Deleting S3 key: %s", s3_key)
            self._client.delete_object(Bucket=self._bucket, Key=s3_key)
            logger.info("🗑️ S3 key deleted successfully: %s", s3_key)

            # Cascade: delete the metadata sidecar
            meta_key = self._build_metadata_key(s3_key)
            logger.info("🗑️ Deleting metadata sidecar: %s", meta_key)
            self._client.delete_object(Bucket=self._bucket, Key=meta_key)
            logger.info("🗑️ Metadata sidecar deleted: %s", meta_key)

            return True
        except Exception:
            logger.exception("❌ Failed to delete S3 key %s", s3_key)
            return False

    def generate_presigned_url(self, s3_uri: str, expires_in: int = 3600) -> str:
        """Generate a presigned download URL for an S3 URI.

        Args:
            s3_uri: An ``s3://bucket/key`` URI or a plain S3 key.
            expires_in: URL expiry in seconds (default 1 hour).

        Returns:
            A presigned URL string.
        """
        # Parse s3://bucket/key format
        if s3_uri.startswith("s3://"):
            without_scheme = s3_uri[5:]
            bucket, _, key = without_scheme.partition("/")
        else:
            bucket = self._bucket
            key = s3_uri

        logger.info("🔗 Generating presigned URL for s3://%s/%s (expires_in=%ds)", bucket, key, expires_in)
        url = self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        logger.debug("🔗 Presigned URL generated for %s", key)
        return url

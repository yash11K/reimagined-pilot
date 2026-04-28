# S3 Uploader — File Storage & Metadata Sidecars

**File:** `kb_manager/services/s3_uploader.py`

---

## Overview

The S3Uploader handles all interactions with AWS S3: uploading markdown content, generating metadata sidecar files for Bedrock KB filtering, deleting superseded files, and generating presigned download URLs.

---

## Class: `S3Uploader`

### Constructor
Reads `S3_BUCKET_NAME` and `AWS_REGION` from settings. Creates a boto3 S3 client.

---

## S3 Key Structure

```
{kb_target}/{brand}/{region}/{namespace}/{filename}.md
{kb_target}/{brand}/{region}/{namespace}/{filename}.md.metadata.json
```

Example:
```
public/avis/nam/products-and-services/refueling-policies.md
public/avis/nam/products-and-services/refueling-policies.md.metadata.json
```

### Key Builder
```python
S3Uploader.build_s3_key(kb_target, brand, region, namespace, filename) -> str
```
Strips slashes, drops empties, collapses double slashes.

---

## Upload Flow

### `upload(kb_file: KBFile) -> str | None`

1. Build S3 key from file metadata
2. Upload markdown content (`ContentType: text/markdown`)
3. Build metadata sidecar JSON
4. Upload sidecar (`ContentType: application/json`)
5. Return the S3 key

### Metadata Sidecar Format

The sidecar enables Bedrock KB to filter search results by attributes:

```json
{
    "metadataAttributes": {
        "title": "Refueling Policies and Fees",
        "source_url": "https://www.avis.com/en/products-and-services/refueling",
        "region": "nam",
        "brand": "avis",
        "kb_target": "public",
        "category": "policy",
        "visibility": "public",
        "tags": ["refueling", "fees", "fuel"],
        "modify_date": "2026-04-15T10:30:00+00:00"
    }
}
```

---

## Other Operations

### `delete(s3_key: str)`
Deletes a single object from S3. Used when superseding old versions or deleting files.

### `generate_presigned_url(s3_key: str, expiry: int = 3600) -> str`
Generates a time-limited download URL for a file.

---

## Error Handling

All S3 operations catch `botocore.exceptions.ClientError` and log warnings. Upload failures are non-fatal to the pipeline — the file record is still created in the database, just without an `s3_key`.

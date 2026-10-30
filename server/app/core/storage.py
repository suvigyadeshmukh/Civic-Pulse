"""Civic Pulse — S3 / MinIO object storage service.

Wraps a ``boto3`` S3 client and exposes high-level helpers consumed by every
domain module that persists media (audio TTS files, grievance photos, forensic
evidence snapshots, agent screenshots, etc.).

The bucket is created once at application startup via :meth:`ensure_bucket_exists`
and a public-read policy is applied to a whitelist of path prefixes so the React
SPA can stream audio, images, and PDFs directly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.settings import get_settings

logger = logging.getLogger(__name__)


class StorageService:
    """Thin async-friendly wrapper around the boto3 S3 client.

    All blocking ``boto3`` calls are dispatched via :func:`asyncio.to_thread`
    so the FastAPI event loop is never blocked.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket: str = settings.S3_BUCKET_NAME
        self._public_base_url: str = settings.S3_PUBLIC_BASE_URL.rstrip("/")
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=BotoConfig(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
            ),
        )

    # ------------------------------------------------------------------ #
    # Bucket bootstrap
    # ------------------------------------------------------------------ #

    def _sync_ensure_bucket_exists(self) -> None:
        """Create the bucket if absent and apply a public-read policy for
        whitelisted path prefixes.
        """
        try:
            self._client.head_bucket(Bucket=self._bucket)
            logger.info("S3 bucket '%s' already exists.", self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)
            logger.info("Created S3 bucket '%s'.", self._bucket)

        # Public-read for media folders the React SPA accesses directly
        public_prefixes = [
            "explainers/*",
            "grievances/*",
            "forensics/*",
            "receipts/*",
            "agent/*",
        ]

        statements = [
            {
                "Sid": f"PublicRead-{prefix.replace('/', '-').replace('*', 'star')}",
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{self._bucket}/{prefix}"],
            }
            for prefix in public_prefixes
        ]

        policy = json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": statements,
            }
        )

        try:
            self._client.put_bucket_policy(Bucket=self._bucket, Policy=policy)
            logger.info(
                "Applied public-read policy for prefixes: %s",
                public_prefixes,
            )
        except ClientError:
            logger.warning(
                "Could not set bucket policy — public-read may not be available. "
                "Ensure MinIO/S3 permissions allow PutBucketPolicy.",
                exc_info=True,
            )

    async def ensure_bucket_exists(self) -> None:
        """Async wrapper delegating to :meth:`_sync_ensure_bucket_exists`."""
        await asyncio.to_thread(self._sync_ensure_bucket_exists)

    # ------------------------------------------------------------------ #
    # Upload
    # ------------------------------------------------------------------ #

    def _sync_upload_bytes(
        self,
        data: bytes,
        object_key: str,
        content_type: str,
    ) -> str:
        """Upload bytes synchronously and return the public URL."""
        self._client.put_object(
            Bucket=self._bucket,
            Key=object_key,
            Body=data,
            ContentType=content_type,
        )
        public_url = f"{self._public_base_url}/{object_key}"
        logger.debug("Uploaded %d bytes → %s", len(data), public_url)
        return public_url

    async def upload_bytes(
        self,
        data: bytes,
        folder: str,
        filename: str,
        content_type: str,
    ) -> str:
        """Upload *data* into ``<folder>/<filename>`` and return its public URL.

        A short UUID prefix is prepended to *filename* to prevent collisions.

        Parameters
        ----------
        data:
            Raw bytes to store.
        folder:
            Logical folder inside the bucket (e.g. ``"explainers"``).
        filename:
            Human-readable file name (e.g. ``"summary.mp3"``).
        content_type:
            MIME type string (e.g. ``"audio/mpeg"``).

        Returns
        -------
        str
            Full public URL of the uploaded object.
        """
        unique_prefix = uuid.uuid4().hex[:8]
        object_key = f"{folder.strip('/')}/{unique_prefix}_{filename}"
        return await asyncio.to_thread(
            self._sync_upload_bytes,
            data,
            object_key,
            content_type,
        )

    # ------------------------------------------------------------------ #
    # Download / presigned URL helpers
    # ------------------------------------------------------------------ #

    async def download_bytes(self, object_key: str) -> bytes:
        """Download the object at *object_key* and return its bytes."""

        def _download() -> bytes:
            resp = self._client.get_object(Bucket=self._bucket, Key=object_key)
            return resp["Body"].read()

        return await asyncio.to_thread(_download)

    async def generate_presigned_url(
        self,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """Return a pre-signed download URL valid for *expires_in* seconds."""

        def _presign() -> str:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_key},
                ExpiresIn=expires_in,
            )

        return await asyncio.to_thread(_presign)

    # ------------------------------------------------------------------ #
    # Delete
    # ------------------------------------------------------------------ #

    async def delete_object(self, object_key: str) -> None:
        """Delete the object at *object_key*."""

        def _delete() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)

        await asyncio.to_thread(_delete)

    # ------------------------------------------------------------------ #
    # Health probe
    # ------------------------------------------------------------------ #

    async def health_check(self) -> dict[str, object]:
        """Return a simple dict indicating whether the bucket is reachable."""
        try:
            await asyncio.to_thread(
                self._client.head_bucket, Bucket=self._bucket
            )
            return {"status": "ok", "bucket": self._bucket}
        except ClientError as exc:
            return {
                "status": "error",
                "bucket": self._bucket,
                "detail": str(exc),
            }


# Module-level singleton — imported by other modules
storage_service = StorageService()


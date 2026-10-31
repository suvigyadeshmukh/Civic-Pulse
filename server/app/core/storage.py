"""Civic Pulse — S3 / MinIO object storage service.

Wraps a ``boto3`` S3 client and exposes high-level helpers consumed by every
domain module that persists media (audio TTS files, grievance photos, forensic
evidence snapshots, agent screenshots, etc.).

The bucket is created once at application startup via :meth:`ensure_bucket_exists`
and a public-read policy is applied to a whitelist of path prefixes so the React
SPA can stream audio, images, and PDFs directly.

If S3/MinIO is unreachable the service transparently falls back to local disk
storage under ``server/.local_storage/<bucket>/`` so that application startup
never depends on the object-storage container being up. The FastAPI app mounts
that directory at ``/local-media`` (see ``app.main``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.settings import get_settings

logger = logging.getLogger(__name__)

#: URL prefix under which ``app.main`` serves the local-disk fallback.
LOCAL_MEDIA_URL_PREFIX = "/local-media"

#: Root of the local-disk fallback: ``<workspace>/server/.local_storage``.
LOCAL_STORAGE_ROOT = Path(__file__).resolve().parents[2] / ".local_storage"


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
                # Short timeouts keep offline startup fast: when MinIO/S3 is not
                # running the local-disk fallback activates within seconds rather
                # than after botocore's default long connect retries.
                connect_timeout=2,
                read_timeout=4,
                retries={"max_attempts": 1, "mode": "standard"},
            ),
        )
        self._local_root: Path = LOCAL_STORAGE_ROOT / self._bucket
        self._using_local_fallback: bool = False

    # ------------------------------------------------------------------ #
    # Local-disk fallback state
    # ------------------------------------------------------------------ #

    @property
    def local_root(self) -> Path:
        """Directory backing the local-disk fallback for this bucket."""
        return self._local_root

    @property
    def using_local_fallback(self) -> bool:
        """``True`` when S3/MinIO is unreachable and local disk is in use."""
        return self._using_local_fallback

    def _activate_local_fallback(self, exc: Exception) -> None:
        """Switch to local-disk storage after an S3/MinIO failure."""
        self._using_local_fallback = True
        self._local_root.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "S3/MinIO unavailable (%s) — using local disk storage at '%s'.",
            type(exc).__name__,
            self._local_root,
        )

    def _local_url(self, object_key: str) -> str:
        return f"{LOCAL_MEDIA_URL_PREFIX}/{quote(object_key)}"

    def _sync_upload_local(self, data: bytes, object_key: str) -> str:
        """Persist *data* under the local fallback root and return its URL."""
        destination = self._local_root / object_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        local_url = self._local_url(object_key)
        logger.debug("Wrote %d bytes → %s", len(data), destination)
        return local_url

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
        """Async wrapper delegating to :meth:`_sync_ensure_bucket_exists`.

        Never raises: if S3/MinIO is unreachable the service activates the
        local-disk fallback instead, so application startup always succeeds.
        """
        try:
            await asyncio.to_thread(self._sync_ensure_bucket_exists)
        except Exception as exc:  # noqa: BLE001 — startup must never fail here
            self._activate_local_fallback(exc)
        else:
            # A previously activated fallback can be turned off once S3 recovers.
            self._using_local_fallback = False

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
        When S3/MinIO is unavailable the bytes are written to the local-disk
        fallback instead and served from ``/local-media``.

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

        if self._using_local_fallback:
            return await asyncio.to_thread(self._sync_upload_local, data, object_key)

        try:
            return await asyncio.to_thread(
                self._sync_upload_bytes,
                data,
                object_key,
                content_type,
            )
        except (ClientError, BotoCoreError) as exc:
            self._activate_local_fallback(exc)
            return await asyncio.to_thread(self._sync_upload_local, data, object_key)

    # ------------------------------------------------------------------ #
    # Download / presigned URL helpers
    # ------------------------------------------------------------------ #

    async def download_bytes(self, object_key: str) -> bytes:
        """Download the object at *object_key* and return its bytes."""

        def _download_local() -> bytes:
            return (self._local_root / object_key).read_bytes()

        if self._using_local_fallback:
            return await asyncio.to_thread(_download_local)

        def _download() -> bytes:
            resp = self._client.get_object(Bucket=self._bucket, Key=object_key)
            return resp["Body"].read()

        try:
            return await asyncio.to_thread(_download)
        except (ClientError, BotoCoreError):
            # The object may have been written while the local fallback was active.
            return await asyncio.to_thread(_download_local)

    async def generate_presigned_url(
        self,
        object_key: str,
        expires_in: int = 3600,
    ) -> str:
        """Return a pre-signed download URL valid for *expires_in* seconds."""
        if self._using_local_fallback:
            return self._local_url(object_key)

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

        def _delete_local() -> None:
            (self._local_root / object_key).unlink(missing_ok=True)

        if self._using_local_fallback:
            await asyncio.to_thread(_delete_local)
            return

        def _delete() -> None:
            self._client.delete_object(Bucket=self._bucket, Key=object_key)

        try:
            await asyncio.to_thread(_delete)
        except (ClientError, BotoCoreError):
            await asyncio.to_thread(_delete_local)

    # ------------------------------------------------------------------ #
    # Health probe
    # ------------------------------------------------------------------ #

    async def health_check(self) -> dict[str, object]:
        """Return a simple dict indicating whether storage is reachable."""
        if self._using_local_fallback:
            return {
                "status": "ok" if self._local_root.exists() else "error",
                "bucket": self._bucket,
                "backend": "local",
            }

        try:
            await asyncio.to_thread(
                self._client.head_bucket, Bucket=self._bucket
            )
            return {"status": "ok", "bucket": self._bucket, "backend": "s3"}
        except (ClientError, BotoCoreError) as exc:
            logger.warning(
                "S3 bucket health check failed for '%s' (%s).",
                self._bucket,
                type(exc).__name__,
            )
            return {
                "status": "error",
                "bucket": self._bucket,
                "detail": type(exc).__name__,
                "backend": "s3",
            }


# Module-level singleton — imported by other modules
storage_service = StorageService()

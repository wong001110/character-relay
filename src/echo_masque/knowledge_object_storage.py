"""Private S3-compatible object storage for Knowledge Fabric artifacts.

Cloudflare R2 is the configured production provider.  This module intentionally
uses only the S3-compatible object operations needed by the Fabric, so a later
explicit AWS S3 deployment keeps the same persistence and caller boundary.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from typing import TYPE_CHECKING, Protocol, cast

if TYPE_CHECKING:
    from echo_masque.config import Settings


class ObjectStorageError(RuntimeError):
    """A safe, non-secret object storage failure."""


class ObjectStorageUnavailable(ObjectStorageError):
    """Raised when an ingest needs storage that deployment has not configured."""


class ObjectStorageConflict(ObjectStorageError):
    """Raised when an existing content-addressed object disagrees with its metadata."""


@dataclass(frozen=True, slots=True)
class StoredKnowledgeObject:
    """Private object metadata safe to persist; it deliberately has no public URL."""

    provider: str
    bucket: str
    object_key: str
    content_sha256: str
    byte_size: int
    content_type: str


class KnowledgeObjectStorage(Protocol):
    """Storage operations needed by ingestion and lifecycle cleanup only."""

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject: ...

    def get_private(self, *, object_key: str) -> bytes: ...

    def delete_private(self, *, object_key: str) -> bool: ...


class _S3Body(Protocol):
    def read(self) -> bytes: ...


class _S3CompatibleClient(Protocol):
    def put_object(self, **kwargs: object) -> Mapping[str, object]: ...

    def head_object(self, **kwargs: object) -> Mapping[str, object]: ...

    def get_object(self, **kwargs: object) -> Mapping[str, object]: ...

    def delete_object(self, **kwargs: object) -> Mapping[str, object]: ...


class S3CompatibleKnowledgeObjectStorage:
    """Private R2/S3 implementation with idempotent content-addressed uploads."""

    def __init__(
        self,
        *,
        provider: str,
        bucket: str,
        client: _S3CompatibleClient,
    ) -> None:
        self.provider = provider
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_settings(cls, settings: Settings) -> S3CompatibleKnowledgeObjectStorage:
        """Create a client only when all deployment-only credentials are present."""

        bucket = settings.knowledge_object_storage_bucket
        access_key = settings.knowledge_object_storage_access_key_id
        secret_key = settings.knowledge_object_storage_secret_access_key
        if bucket is None or access_key is None or secret_key is None:
            raise ObjectStorageUnavailable("Knowledge object storage is not configured.")
        access_key_value = access_key.get_secret_value()
        secret_key_value = secret_key.get_secret_value()
        if not access_key_value or not secret_key_value:
            raise ObjectStorageUnavailable("Knowledge object storage is not configured.")

        endpoint = settings.knowledge_object_storage_endpoint
        if settings.knowledge_object_storage_provider == "cloudflare_r2":
            if endpoint is None:
                raise ObjectStorageUnavailable("Cloudflare R2 endpoint is not configured.")
            region = settings.knowledge_object_storage_region or "auto"
        else:
            aws_region = settings.knowledge_object_storage_region
            if aws_region is None:
                raise ObjectStorageUnavailable("AWS S3 region is not configured.")
            region = aws_region

        try:
            import boto3  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover - package dependency is tested by install.
            raise ObjectStorageUnavailable(
                "S3-compatible object storage support is unavailable."
            ) from exc
        client = boto3.client(
            service_name="s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key_value,
            aws_secret_access_key=secret_key_value,
            region_name=region,
        )
        return cls(
            provider=settings.knowledge_object_storage_provider,
            bucket=bucket,
            client=cast(_S3CompatibleClient, client),
        )

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        content_hash = sha256(content).hexdigest()
        existing = self._head_or_none(object_key)
        if existing is not None:
            if (
                existing.content_sha256 != content_hash
                or existing.byte_size != len(content)
                or existing.content_type != content_type
            ):
                raise ObjectStorageConflict("Knowledge object key already has different content.")
            return existing
        safe_metadata = {"content-sha256": content_hash, **dict(metadata)}
        try:
            # No ACL/public URL is ever requested. Bucket policy remains private-by-default.
            self.client.put_object(
                Bucket=self.bucket,
                Key=object_key,
                Body=content,
                ContentType=content_type,
                Metadata=safe_metadata,
            )
        except Exception as exc:
            raise ObjectStorageError("Knowledge object upload failed.") from exc
        return StoredKnowledgeObject(
            provider=self.provider,
            bucket=self.bucket,
            object_key=object_key,
            content_sha256=content_hash,
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        try:
            response = self.client.get_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            raise ObjectStorageError("Knowledge object download failed.") from exc
        body = response.get("Body")
        reader = getattr(body, "read", None)
        if not callable(reader):
            raise ObjectStorageError("Knowledge object response is invalid.")
        content = cast(_S3Body, body).read()
        if not isinstance(content, bytes):
            raise ObjectStorageError("Knowledge object response is invalid.")
        return content

    def delete_private(self, *, object_key: str) -> bool:
        if self._head_or_none(object_key) is None:
            return False
        try:
            self.client.delete_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            raise ObjectStorageError("Knowledge object deletion failed.") from exc
        return True

    def _head_or_none(self, object_key: str) -> StoredKnowledgeObject | None:
        try:
            response = self.client.head_object(Bucket=self.bucket, Key=object_key)
        except Exception as exc:
            if _is_missing_object(exc):
                return None
            raise ObjectStorageError("Knowledge object metadata lookup failed.") from exc
        metadata = response.get("Metadata")
        metadata_map = metadata if isinstance(metadata, Mapping) else {}
        content_hash = metadata_map.get("content-sha256")
        content_length = response.get("ContentLength")
        content_type = response.get("ContentType")
        if (
            not isinstance(content_hash, str)
            or not isinstance(content_length, int)
            or not isinstance(content_type, str)
        ):
            raise ObjectStorageConflict("Knowledge object metadata is incomplete.")
        return StoredKnowledgeObject(
            provider=self.provider,
            bucket=self.bucket,
            object_key=object_key,
            content_sha256=content_hash,
            byte_size=content_length,
            content_type=content_type,
        )


class UnavailableKnowledgeObjectStorage:
    """Fail ingest before it can publish a partial source version."""

    def __init__(self, reason: str = "Knowledge object storage is not configured.") -> None:
        self.reason = reason

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        raise ObjectStorageUnavailable(self.reason)

    def get_private(self, *, object_key: str) -> bytes:
        raise ObjectStorageUnavailable(self.reason)

    def delete_private(self, *, object_key: str) -> bool:
        raise ObjectStorageUnavailable(self.reason)


def object_storage_from_settings(settings: Settings) -> KnowledgeObjectStorage:
    """Compose storage without making an unconfigured app fail at startup."""

    try:
        return S3CompatibleKnowledgeObjectStorage.from_settings(settings)
    except ObjectStorageUnavailable as exc:
        return UnavailableKnowledgeObjectStorage(str(exc))


def _is_missing_object(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    if not isinstance(response, Mapping):
        return False
    error = response.get("Error")
    if not isinstance(error, Mapping):
        return False
    return str(error.get("Code", "")) in {"404", "NoSuchKey", "NotFound"}


__all__ = [
    "KnowledgeObjectStorage",
    "ObjectStorageConflict",
    "ObjectStorageError",
    "ObjectStorageUnavailable",
    "S3CompatibleKnowledgeObjectStorage",
    "StoredKnowledgeObject",
    "UnavailableKnowledgeObjectStorage",
    "object_storage_from_settings",
]

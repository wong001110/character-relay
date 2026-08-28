"""Private S3-compatible object storage for Knowledge Fabric artifacts.

Cloudflare R2 is the configured production provider.  This module intentionally
uses only the S3-compatible object operations needed by the Fabric, so a later
explicit AWS S3 deployment keeps the same persistence and caller boundary.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Protocol, cast
from uuid import uuid4

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
        elif settings.knowledge_object_storage_provider == "aws_s3":
            aws_region = settings.knowledge_object_storage_region
            if aws_region is None:
                raise ObjectStorageUnavailable("AWS S3 region is not configured.")
            region = aws_region
        else:
            raise ObjectStorageUnavailable("S3-compatible object storage is not configured.")

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


class FilesystemKnowledgeObjectStorage:
    """Private, mounted-volume storage for an explicitly configured single-node deployment.

    This is intentionally never selected by default and does not create public URLs.  Its root
    must be a persistent private volume shared with the one process that owns the application.
    Multi-replica deployments should use the S3-compatible implementation instead.
    """

    _METADATA_SUFFIX = ".metadata.json"

    def __init__(self, *, root: Path) -> None:
        try:
            root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.root = root.resolve(strict=True)
        except OSError as exc:
            raise ObjectStorageUnavailable("Private filesystem storage is unavailable.") from exc
        if not self.root.is_dir():
            raise ObjectStorageUnavailable("Private filesystem storage root is not a directory.")

    @classmethod
    def from_settings(cls, settings: Settings) -> FilesystemKnowledgeObjectStorage:
        path = settings.knowledge_object_storage_filesystem_path
        if path is None:
            raise ObjectStorageUnavailable("Private filesystem storage path is not configured.")
        return cls(root=Path(path))

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        target, metadata_target = self._targets(object_key)
        content_hash = sha256(content).hexdigest()
        if target.exists() or metadata_target.exists():
            return self._require_matching_existing(
                object_key=object_key,
                target=target,
                metadata_target=metadata_target,
                content=content,
                content_type=content_type,
                content_hash=content_hash,
            )
        try:
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            self._require_within_root(target)
            self._write_new(target, content)
            try:
                self._write_new(
                    metadata_target,
                    json.dumps(
                        {"content_type": content_type, "metadata": dict(metadata)},
                        separators=(",", ":"),
                        sort_keys=True,
                    ).encode("utf-8"),
                )
            except Exception:
                self._unlink_if_present(target)
                raise
        except ObjectStorageError:
            raise
        except (OSError, TypeError, ValueError) as exc:
            raise ObjectStorageError("Private filesystem object upload failed.") from exc
        return self._stored_object(
            object_key=object_key,
            content_sha256=content_hash,
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        target, _ = self._targets(object_key)
        try:
            return target.read_bytes()
        except OSError as exc:
            raise ObjectStorageError("Private filesystem object download failed.") from exc

    def delete_private(self, *, object_key: str) -> bool:
        target, metadata_target = self._targets(object_key)
        deleted = False
        try:
            for path in (target, metadata_target):
                if path.exists():
                    path.unlink()
                    deleted = True
        except OSError as exc:
            raise ObjectStorageError("Private filesystem object deletion failed.") from exc
        return deleted

    def _require_matching_existing(
        self,
        *,
        object_key: str,
        target: Path,
        metadata_target: Path,
        content: bytes,
        content_type: str,
        content_hash: str,
    ) -> StoredKnowledgeObject:
        if not target.is_file() or not metadata_target.is_file():
            raise ObjectStorageConflict("Private filesystem object metadata is incomplete.")
        try:
            existing = target.read_bytes()
            stored_metadata = json.loads(metadata_target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ObjectStorageConflict("Private filesystem object metadata is invalid.") from exc
        stored_content_type = (
            stored_metadata.get("content_type") if isinstance(stored_metadata, dict) else None
        )
        if (
            sha256(existing).hexdigest() != content_hash
            or len(existing) != len(content)
            or stored_content_type != content_type
        ):
            raise ObjectStorageConflict("Knowledge object key already has different content.")
        return self._stored_object(
            object_key=object_key,
            content_sha256=content_hash,
            byte_size=len(existing),
            content_type=content_type,
        )

    def _targets(self, object_key: str) -> tuple[Path, Path]:
        key = PurePosixPath(object_key)
        if (
            not object_key
            or "\\" in object_key
            or key.is_absolute()
            or any(part in {"", ".", ".."} for part in key.parts)
        ):
            raise ObjectStorageError("Private filesystem object key is invalid.")
        target = self.root.joinpath(*key.parts)
        self._require_within_root(target)
        return target, target.with_name(f"{target.name}{self._METADATA_SUFFIX}")

    def _require_within_root(self, target: Path) -> None:
        try:
            target.resolve(strict=False).relative_to(self.root)
        except ValueError as exc:
            raise ObjectStorageError("Private filesystem object key is invalid.") from exc

    @staticmethod
    def _write_new(target: Path, content: bytes) -> None:
        temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as handle:
                handle.write(content)
            os.chmod(temporary, 0o600)
            os.replace(temporary, target)
        except OSError:
            FilesystemKnowledgeObjectStorage._unlink_if_present(temporary)
            raise

    @staticmethod
    def _unlink_if_present(path: Path) -> None:
        with suppress(OSError):
            path.unlink(missing_ok=True)

    @staticmethod
    def _stored_object(
        *,
        object_key: str,
        content_sha256: str,
        byte_size: int,
        content_type: str,
    ) -> StoredKnowledgeObject:
        return StoredKnowledgeObject(
            provider="local_filesystem",
            bucket="private-volume",
            object_key=object_key,
            content_sha256=content_sha256,
            byte_size=byte_size,
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
        if settings.knowledge_object_storage_provider == "local_filesystem":
            return FilesystemKnowledgeObjectStorage.from_settings(settings)
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
    "FilesystemKnowledgeObjectStorage",
    "KnowledgeObjectStorage",
    "ObjectStorageConflict",
    "ObjectStorageError",
    "ObjectStorageUnavailable",
    "S3CompatibleKnowledgeObjectStorage",
    "StoredKnowledgeObject",
    "UnavailableKnowledgeObjectStorage",
    "object_storage_from_settings",
]

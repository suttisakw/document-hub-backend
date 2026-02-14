from __future__ import annotations

import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO
from uuid import UUID

from fastapi import HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core.config import settings


class StorageError(Exception):
    """Base storage exception."""


class StorageObjectNotFoundError(StorageError):
    """Object/key not found in backing storage."""


class StorageConfigurationError(StorageError):
    """Storage provider is misconfigured."""


@dataclass(frozen=True)
class StoredObject:
    path: str
    size: int


def _normalize_rel_path(path: str) -> str:
    raw = str(path).replace("\\", "/").strip()
    while raw.startswith("/"):
        raw = raw[1:]
    parts = [p for p in raw.split("/") if p and p != "."]
    if any(p == ".." for p in parts):
        raise ValueError("Invalid storage path")
    return "/".join(parts)


def _safe_posix_join(*parts: str) -> str:
    normalized = [_normalize_rel_path(p) for p in parts if p]
    normalized = [p for p in normalized if p]
    return "/".join(normalized)


def safe_filename(name: str) -> str:
    keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    cleaned = "".join(ch if ch in keep else "_" for ch in name)
    return cleaned.strip("._") or "file"


class StorageBackend(ABC):
    provider: str

    @abstractmethod
    def save_upload(self, document_id: UUID, upload: UploadFile) -> StoredObject:
        raise NotImplementedError

    @abstractmethod
    def save_bytes(self, rel_path: str, data: bytes) -> str:
        raise NotImplementedError

    @abstractmethod
    def read_bytes(self, rel_path: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def exists(self, rel_path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete(self, rel_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_prefix(self, prefix: str) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def build_file_response(
        self, rel_path: str, *, media_type: str | None = None, filename: str | None = None
    ) -> Response:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self, *, perform_write: bool = False) -> tuple[bool, str | None]:
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> dict:
        raise NotImplementedError


class LocalFilesystemStorage(StorageBackend):
    provider = "local"

    def __init__(self, root_dir: str):
        self.root = Path(root_dir)
        self.root.mkdir(parents=True, exist_ok=True)

    def _abs_path(self, rel_path: str) -> Path:
        normalized = _normalize_rel_path(rel_path)
        path = self.root.joinpath(*normalized.split("/"))
        try:
            path.relative_to(self.root)
        except ValueError as e:
            raise StorageError("Invalid local storage path") from e
        return path

    def save_upload(self, document_id: UUID, upload: UploadFile) -> StoredObject:
        original = upload.filename or "upload"
        filename = safe_filename(original)
        rel_path = _safe_posix_join(f"{document_id}_{filename}")
        abs_path = self._abs_path(rel_path)
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        size = 0
        with abs_path.open("wb") as file_obj:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                file_obj.write(chunk)

        return StoredObject(path=rel_path, size=size)

    def save_bytes(self, rel_path: str, data: bytes) -> str:
        rel = _normalize_rel_path(rel_path)
        abs_path = self._abs_path(rel)
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(data)
        return rel

    def read_bytes(self, rel_path: str) -> bytes:
        abs_path = self._abs_path(rel_path)
        try:
            return abs_path.read_bytes()
        except FileNotFoundError as e:
            raise StorageObjectNotFoundError(rel_path) from e
        except OSError as e:
            raise StorageError(str(e)) from e

    def exists(self, rel_path: str) -> bool:
        return self._abs_path(rel_path).exists()

    def delete(self, rel_path: str) -> None:
        abs_path = self._abs_path(rel_path)
        try:
            abs_path.unlink()
        except FileNotFoundError:
            return
        except OSError as e:
            raise StorageError(str(e)) from e

    def list_prefix(self, prefix: str) -> list[str]:
        normalized = _normalize_rel_path(prefix)
        base = self._abs_path(normalized)
        if not base.exists() or not base.is_dir():
            return []
        return [
            p.relative_to(self.root).as_posix()
            for p in base.rglob("*")
            if p.is_file()
        ]

    def build_file_response(
        self, rel_path: str, *, media_type: str | None = None, filename: str | None = None
    ) -> Response:
        abs_path = self._abs_path(rel_path)
        if not abs_path.exists() or not abs_path.is_file():
            raise StorageObjectNotFoundError(rel_path)
        return FileResponse(path=abs_path, media_type=media_type, filename=filename)

    def healthcheck(self, *, perform_write: bool = False) -> tuple[bool, str | None]:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            if perform_write:
                marker_name = f".storage-check-{next(tempfile._get_candidate_names())}"
                marker = self.root / marker_name
                marker.write_bytes(b"ok")
                marker.unlink(missing_ok=True)
        except OSError as e:
            return (False, str(e))
        return (True, None)

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "storage_dir": str(self.root),
        }


class S3ObjectStorage(StorageBackend):
    provider = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        prefix: str = "",
        access_key_id: str = "",
        secret_access_key: str = "",
    ):
        self.bucket = bucket
        self.region = region
        self.prefix = _normalize_rel_path(prefix) if prefix else ""
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self._client = None

    def _key(self, rel_path: str) -> str:
        rel = _normalize_rel_path(rel_path)
        return _safe_posix_join(self.prefix, rel)

    def _client_or_raise(self):
        if self._client is not None:
            return self._client
        try:
            import boto3
        except ModuleNotFoundError as e:
            raise StorageConfigurationError(
                "boto3 is required for S3 storage provider"
            ) from e

        kwargs: dict = {"region_name": self.region}
        if self.access_key_id and self.secret_access_key:
            kwargs["aws_access_key_id"] = self.access_key_id
            kwargs["aws_secret_access_key"] = self.secret_access_key
        self._client = boto3.client("s3", **kwargs)
        return self._client

    def _raise_client_error(self, error: Exception, rel_path: str) -> None:
        try:
            from botocore.exceptions import ClientError
        except ModuleNotFoundError as e:
            raise StorageConfigurationError(
                "botocore is required for S3 storage provider"
            ) from e

        if isinstance(error, ClientError):
            code = str(error.response.get("Error", {}).get("Code", ""))
            if code in {"NoSuchKey", "404", "NotFound"}:
                raise StorageObjectNotFoundError(rel_path) from error
        raise StorageError(str(error)) from error

    def save_upload(self, document_id: UUID, upload: UploadFile) -> StoredObject:
        original = upload.filename or "upload"
        filename = safe_filename(original)
        rel_path = _safe_posix_join(f"{document_id}_{filename}")
        key = self._key(rel_path)

        size = 0
        with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as temp_file:
            while True:
                chunk = upload.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                temp_file.write(chunk)
            temp_file.seek(0)
            try:
                self._client_or_raise().upload_fileobj(temp_file, self.bucket, key)
            except Exception as e:
                self._raise_client_error(e, rel_path)

        return StoredObject(path=rel_path, size=size)

    def save_bytes(self, rel_path: str, data: bytes) -> str:
        rel = _normalize_rel_path(rel_path)
        key = self._key(rel)
        try:
            self._client_or_raise().put_object(Bucket=self.bucket, Key=key, Body=data)
        except Exception as e:
            self._raise_client_error(e, rel)
        return rel

    def read_bytes(self, rel_path: str) -> bytes:
        rel = _normalize_rel_path(rel_path)
        key = self._key(rel)
        try:
            response = self._client_or_raise().get_object(Bucket=self.bucket, Key=key)
            return response["Body"].read()
        except Exception as e:
            self._raise_client_error(e, rel)
        raise StorageError("Unexpected storage read failure")

    def exists(self, rel_path: str) -> bool:
        rel = _normalize_rel_path(rel_path)
        key = self._key(rel)
        try:
            self._client_or_raise().head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def delete(self, rel_path: str) -> None:
        rel = _normalize_rel_path(rel_path)
        key = self._key(rel)
        try:
            self._client_or_raise().delete_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            self._raise_client_error(e, rel)

    def list_prefix(self, prefix: str) -> list[str]:
        rel_prefix = _normalize_rel_path(prefix)
        full_prefix = self._key(rel_prefix)
        client = self._client_or_raise()
        paginator = client.get_paginator("list_objects_v2")
        items: list[str] = []
        for page in paginator.paginate(Bucket=self.bucket, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                key = obj.get("Key")
                if not isinstance(key, str):
                    continue
                rel = key
                if self.prefix and rel.startswith(f"{self.prefix}/"):
                    rel = rel[len(self.prefix) + 1 :]
                elif self.prefix and rel == self.prefix:
                    rel = ""
                rel = rel.strip("/")
                if rel:
                    items.append(rel)
        return items

    def build_file_response(
        self, rel_path: str, *, media_type: str | None = None, filename: str | None = None
    ) -> Response:
        rel = _normalize_rel_path(rel_path)
        key = self._key(rel)
        try:
            obj = self._client_or_raise().get_object(Bucket=self.bucket, Key=key)
        except Exception as e:
            self._raise_client_error(e, rel)
            raise StorageError("Unexpected storage response error") from e

        body: BinaryIO = obj["Body"]
        headers = {}
        if filename:
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        content_length = obj.get("ContentLength")
        if content_length is not None:
            headers["Content-Length"] = str(content_length)

        content_type = media_type or obj.get("ContentType") or "application/octet-stream"
        return StreamingResponse(body.iter_chunks(), media_type=content_type, headers=headers)

    def healthcheck(self, *, perform_write: bool = False) -> tuple[bool, str | None]:
        client = self._client_or_raise()
        try:
            client.head_bucket(Bucket=self.bucket)
            if perform_write:
                marker = _safe_posix_join(
                    self.prefix,
                    f".storage-check-{next(tempfile._get_candidate_names())}",
                )
                client.put_object(Bucket=self.bucket, Key=marker, Body=b"ok")
                client.delete_object(Bucket=self.bucket, Key=marker)
        except Exception as e:
            return (False, str(e))
        return (True, None)

    def describe(self) -> dict:
        return {
            "provider": self.provider,
            "bucket": self.bucket,
            "region": self.region,
            "prefix": self.prefix,
            "iam_role_mode": not (self.access_key_id and self.secret_access_key),
        }


_storage_instance: StorageBackend | None = None
_storage_signature: tuple | None = None


def _build_storage_signature() -> tuple:
    return (
        settings.storage_provider,
        settings.storage_dir,
        settings.s3_bucket_name,
        settings.aws_default_region,
        settings.s3_prefix,
        settings.aws_access_key_id,
        settings.aws_secret_access_key,
    )


def get_storage() -> StorageBackend:
    global _storage_instance, _storage_signature

    signature = _build_storage_signature()
    if _storage_instance is not None and _storage_signature == signature:
        return _storage_instance

    provider = (settings.storage_provider or "local").strip().lower()
    if provider == "local":
        storage = LocalFilesystemStorage(settings.storage_dir)
    elif provider == "s3":
        if not settings.s3_bucket_name:
            raise StorageConfigurationError("S3_BUCKET_NAME is required for s3 provider")
        storage = S3ObjectStorage(
            bucket=settings.s3_bucket_name,
            region=settings.aws_default_region,
            prefix=settings.s3_prefix,
            access_key_id=settings.aws_access_key_id,
            secret_access_key=settings.aws_secret_access_key,
        )
    else:
        raise StorageConfigurationError(f"Unsupported storage provider: {provider}")

    _storage_instance = storage
    _storage_signature = signature
    return storage


def save_document_file(storage_dir: str, document_id: UUID, upload: UploadFile) -> str:
    return LocalFilesystemStorage(storage_dir).save_upload(document_id, upload).path


def save_bytes(storage_dir: str, rel_path: str, data: bytes) -> str:
    return LocalFilesystemStorage(storage_dir).save_bytes(rel_path, data)


def resolve_storage_path(storage_dir: str, stored_path: str) -> Path:
    return LocalFilesystemStorage(storage_dir)._abs_path(stored_path)


def storage_http_exception(error: StorageError, *, not_found_detail: str) -> HTTPException:
    if isinstance(error, StorageObjectNotFoundError):
        return HTTPException(status_code=404, detail=not_found_detail)
    if isinstance(error, StorageConfigurationError):
        return HTTPException(status_code=500, detail="Storage configuration error")
    return HTTPException(status_code=500, detail="Storage operation failed")

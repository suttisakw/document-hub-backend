from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from fastapi import UploadFile


def ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def safe_filename(name: str) -> str:
    # Keep it simple and filesystem-friendly.
    keep = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-"
    cleaned = "".join(ch if ch in keep else "_" for ch in name)
    return cleaned.strip("._") or "file"


def save_document_file(storage_dir: str, document_id: UUID, upload: UploadFile) -> str:
    ensure_dir(storage_dir)

    original = upload.filename or "upload"
    filename = safe_filename(original)
    dest = Path(storage_dir) / f"{document_id}_{filename}"

    with dest.open("wb") as f:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    # Return relative-to-storage path (portable across environments)
    return os.path.relpath(dest, start=Path(storage_dir))


def save_bytes(storage_dir: str, rel_path: str, data: bytes) -> str:
    ensure_dir(str(Path(storage_dir) / Path(rel_path).parent))
    dest = Path(storage_dir) / rel_path
    with dest.open("wb") as f:
        f.write(data)
    return rel_path


def resolve_storage_path(storage_dir: str, stored_path: str) -> Path:
    # stored_path is relative to storage_dir
    return Path(storage_dir) / stored_path

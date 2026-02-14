from __future__ import annotations

import os
import uuid

from redis.exceptions import RedisError

from app.core.config import settings
from app.services.redis_client import get_redis_client

_worker_id = f"{os.getpid()}-{uuid.uuid4()}"


def _lock_key(*, job_id: str) -> str:
    prefix = settings.redis_key_prefix.strip() or "document-hub"
    return f"{prefix}:ocr:claim:{job_id}"


def acquire_ocr_claim_lock(*, job_id: str) -> bool:
    """Acquire a short-lived Redis lock for OCR job claim.

    If Redis is unavailable, this returns True as a safe fallback for
    single-worker/dev mode so processing can continue.
    """

    try:
        client = get_redis_client()
        ttl = max(5, settings.ocr_claim_lock_ttl_seconds)
        return bool(client.set(_lock_key(job_id=job_id), _worker_id, nx=True, ex=ttl))
    except RedisError:
        return True


def release_ocr_claim_lock(*, job_id: str) -> None:
    try:
        client = get_redis_client()
        client.delete(_lock_key(job_id=job_id))
    except RedisError:
        return

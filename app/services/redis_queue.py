from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from redis.exceptions import RedisError

from app.core.config import settings
from app.services.redis_client import get_redis_client


def _queue_key(name: str = "jobs") -> str:
    prefix = settings.redis_key_prefix.strip() or "document-hub"
    return f"{prefix}:ocr:easyocr:{name}"


def _processing_queue_key(name: str = "jobs") -> str:
    prefix = settings.redis_key_prefix.strip() or "document-hub"
    return f"{prefix}:ocr:easyocr:{name}:processing"

def _delayed_queue_key() -> str:
    prefix = settings.redis_key_prefix.strip() or "document-hub"
    return f"{prefix}:ocr:easyocr:delayed"


def _dlq_key(name: str = "dlq") -> str:
    prefix = settings.redis_key_prefix.strip() or "document-hub"
    return f"{prefix}:ocr:easyocr:{name}"


def _ops_log_key() -> str:
    prefix = settings.redis_key_prefix.strip() or "document-hub"
    return f"{prefix}:ocr:easyocr:opslog"


def publish_job(job_id: str, queue_name: str = "jobs") -> None:
    try:
        client: Any = get_redis_client()
        client.rpush(_queue_key(queue_name), job_id)
    except RedisError:
        return


def pop_job(queue_name: str = "jobs", timeout_seconds: int = 2) -> str | None:
    try:
        client: Any = get_redis_client()
        item = client.blpop([_queue_key(queue_name)], timeout=max(0, timeout_seconds))
        if not item:
            return None
        _, value = item
        return value
    except RedisError:
        return None


def pop_job_reliable(queue_name: str = "jobs", timeout_seconds: int = 2) -> str | None:
    """Pop job reliably by moving it to a processing list."""
    try:
        client: Any = get_redis_client()
        # Use BRPOPLPUSH for atomic move from queue to processing
        # Note: it returns the value directly
        item = client.brpoplpush(
            _queue_key(queue_name), 
            _processing_queue_key(queue_name), 
            timeout=max(0, timeout_seconds)
        )
        if not item:
            return None
        return item.decode("utf-8") if isinstance(item, bytes) else item
    except RedisError:
        return None


def mark_job_complete(job_id: str, queue_name: str = "jobs") -> None:
    """Remove job from processing list upon completion."""
    try:
        client: Any = get_redis_client()
        client.lrem(_processing_queue_key(queue_name), 0, job_id)
    except RedisError:
        pass


def move_back_stale_jobs(queue_name: str = "jobs") -> int:
    """Move all jobs from processing back to main queue (e.g. on worker restart)."""
    moved = 0
    try:
        client: Any = get_redis_client()
        while True:
            # Atomic move back
            item = client.rpoplpush(_processing_queue_key(queue_name), _queue_key(queue_name))
            if not item:
                break
            moved += 1
    except RedisError:
        pass
    return moved


def cleanup_processing_queue(queue_name: str = "jobs", dlq_threshold_seconds: int = 3600) -> int:
    """
    Experimental: Move jobs from processing to DLQ if they are stuck.
    Note: Current implementation doesn't track timestamp in processing list yet.
    For now, this just provides the interface.
    """
    return 0


# Legacy aliases
def publish_easyocr_job(job_id: str) -> None:
    publish_job(job_id, "jobs")


def pop_easyocr_job(*, timeout_seconds: int) -> str | None:
    return pop_job("jobs", timeout_seconds)


def schedule_easyocr_retry(*, job_id: str, delay_seconds: int) -> None:
    try:
        due_ts = int(datetime.now(UTC).timestamp()) + max(1, int(delay_seconds))
        client: Any = get_redis_client()
        client.zadd(_delayed_queue_key(), {job_id: due_ts})
    except RedisError:
        return


def move_due_delayed_jobs(*, limit: int = 100) -> int:
    moved = 0
    try:
        client: Any = get_redis_client()
        now_ts = int(datetime.now(UTC).timestamp())
        due_jobs: list[str] = list(
            client.zrangebyscore(_delayed_queue_key(), min=0, max=now_ts, start=0, num=limit)
        )
        for job_id in due_jobs:
            removed = client.zrem(_delayed_queue_key(), job_id)
            if removed:
                client.rpush(_queue_key(), job_id)
                moved += 1
    except RedisError:
        return moved
    return moved


def push_easyocr_dlq(*, job_id: str, payload: dict) -> None:
    try:
        body = {"job_id": job_id, **payload}
        client: Any = get_redis_client()
        client.rpush(_dlq_key(), json.dumps(body, ensure_ascii=True))
    except RedisError:
        return


def get_easyocr_queue_stats() -> dict[str, int]:
    try:
        client: Any = get_redis_client()
        return {
            "queue_depth": int(client.llen(_queue_key())),
            "processing_depth": int(client.llen(_processing_queue_key())),
            "delayed_depth": int(client.zcard(_delayed_queue_key())),
            "dlq_depth": int(client.llen(_dlq_key())),
        }
    except RedisError:
        return {
            "queue_depth": 0,
            "processing_depth": 0,
            "delayed_depth": 0,
            "dlq_depth": 0,
        }


def list_easyocr_dlq(*, limit: int = 50) -> list[dict]:
    try:
        client: Any = get_redis_client()
        rows: list[str] = list(client.lrange(_dlq_key(), 0, max(0, limit - 1)))
    except RedisError:
        return []

    items: list[dict] = []
    for row in rows:
        try:
            parsed = json.loads(row)
        except Exception:
            parsed = {"raw": row}
        if not isinstance(parsed, dict):
            parsed = {"raw": parsed}
        items.append(parsed)
    return items


def requeue_easyocr_dlq_job(*, job_id: str, scan_limit: int = 500) -> bool:
    try:
        client: Any = get_redis_client()
        rows: list[str] = list(client.lrange(_dlq_key(), 0, max(0, scan_limit - 1)))
        for row in rows:
            try:
                payload = json.loads(row)
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                continue
            if str(payload.get("job_id") or "") != job_id:
                continue

            removed = client.lrem(_dlq_key(), 1, row)
            if removed:
                client.rpush(_queue_key(), job_id)
                return True
    except RedisError:
        return False

    return False


def remove_easyocr_dlq_job(*, job_id: str, scan_limit: int = 500) -> bool:
    try:
        client: Any = get_redis_client()
        rows: list[str] = list(client.lrange(_dlq_key(), 0, max(0, scan_limit - 1)))
        for row in rows:
            try:
                payload = json.loads(row)
            except Exception:
                payload = {}
            if not isinstance(payload, dict):
                continue
            if str(payload.get("job_id") or "") != job_id:
                continue

            removed = client.lrem(_dlq_key(), 1, row)
            return bool(removed)
    except RedisError:
        return False

    return False


def purge_easyocr_dlq() -> int:
    try:
        client: Any = get_redis_client()
        rows: list[str] = list(client.lrange(_dlq_key(), 0, -1))
        if not rows:
            return 0
        client.delete(_dlq_key())
        return len(rows)
    except RedisError:
        return 0


def append_easyocr_ops_log(*, payload: dict, limit: int = 200) -> None:
    try:
        client: Any = get_redis_client()
        client.lpush(_ops_log_key(), json.dumps(payload, ensure_ascii=True))
        client.ltrim(_ops_log_key(), 0, max(0, limit - 1))
    except RedisError:
        return


def list_easyocr_ops_log(*, limit: int = 50) -> list[dict]:
    try:
        client: Any = get_redis_client()
        rows: list[str] = list(client.lrange(_ops_log_key(), 0, max(0, limit - 1)))
    except RedisError:
        return []

    out: list[dict] = []
    for row in rows:
        try:
            item = json.loads(row)
        except Exception:
            item = {"raw": row}
        if isinstance(item, dict):
            out.append(item)
    return out

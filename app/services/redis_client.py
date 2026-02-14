from __future__ import annotations

from redis import Redis

from app.core.config import settings

_redis_client: Redis | None = None
_redis_signature: tuple[str] | None = None


def get_redis_client() -> Redis:
    global _redis_client, _redis_signature

    signature = (settings.redis_url,)
    if _redis_client is not None and _redis_signature == signature:
        return _redis_client

    _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    _redis_signature = signature
    return _redis_client

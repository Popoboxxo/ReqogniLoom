import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from django.conf import settings
from django.core import signing

logger = logging.getLogger(__name__)

# TTL for the server-side session -> api-key binding (REQ-018 / audit P-02).
# Long enough for a normal SSE session, short enough to bound stale bindings.
SESSION_TTL_SECONDS = 8 * 3600

# Salt namespacing the signed session api-key payloads (REQ-036 / audit BE-5).
# Django signing derives its HMAC from SECRET_KEY, so a raw Redis dump cannot
# be reversed without the server secret.
_API_KEY_SIGNING_SALT = "sse-api-key"

# Module-level Redis connection pool (REQ-035 / audit BE-4). Reusing a single
# pool avoids opening a fresh TCP connection on every publish/store/lookup call.
_redis_pool = None

def _get_redis_url() -> str:
    # Use Celery broker URL as Redis URL
    return getattr(settings, "CELERY_BROKER_URL", "redis://redis:6379/0")

def _get_redis_pool():
    """Return the shared module-level Redis connection pool (lazy init)."""
    global _redis_pool
    if _redis_pool is None:
        import redis
        _redis_pool = redis.ConnectionPool.from_url(_get_redis_url())
    return _redis_pool

def _get_redis_client():
    """Return a Redis client backed by the shared module-level pool."""
    import redis
    return redis.Redis(connection_pool=_get_redis_pool())

def _session_auth_key(session_id: str) -> str:
    """Return the Redis key holding the API key bound to an SSE session."""
    return f"mcp:session:{session_id}:auth"

def store_session_api_key(
    session_id: str, api_key: str, ttl: int = SESSION_TTL_SECONDS
) -> None:
    """Bind an authenticated API key to an SSE session (server-side).

    Storing the key server-side lets the message endpoint authorise
    subsequent POSTs by ``session_id`` alone, so the secret never has to
    travel in the SSE message URL (REQ-018 / SYSTEM_AUDIT P-02).

    The key is symmetrically encrypted with Django signing before it hits
    Redis (REQ-036 / audit BE-5) so a Redis compromise does not directly
    expose usable API keys. The auth flow still receives the plaintext key
    on read.
    """
    try:
        r = _get_redis_client()
        signed = signing.dumps(api_key, salt=_API_KEY_SIGNING_SALT)
        r.set(_session_auth_key(session_id), signed, ex=ttl)
    except Exception:
        logger.exception(f"Failed to store session api key for {session_id}")

def get_session_api_key(session_id: str) -> Optional[str]:
    """Return the API key bound to an SSE session, or None if unknown/expired."""
    try:
        r = _get_redis_client()
        value = r.get(_session_auth_key(session_id))
        if value is None:
            return None
        signed = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        try:
            return signing.loads(signed, salt=_API_KEY_SIGNING_SALT)
        except signing.BadSignature:
            logger.warning(f"Invalid session api key signature for {session_id}")
            return None
    except Exception:
        logger.exception(f"Failed to read session api key for {session_id}")
        return None

def publish_mcp_message(session_id: str, message: Dict[str, Any]) -> None:
    """Publish a JSON-RPC message to a specific SSE session."""
    try:
        r = _get_redis_client()
        channel = f"mcp:session:{session_id}"
        r.publish(channel, json.dumps(message))
    except Exception:
        logger.exception(f"Failed to publish MCP message to session {session_id}")

async def async_sse_generator(session_id: str, endpoint_url: str) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE events from Redis PubSub."""
    import redis.asyncio as redis
    import asyncio

    redis_url = _get_redis_url()
    r = redis.from_url(redis_url)
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    channel = f"mcp:session:{session_id}"

    try:
        await pubsub.subscribe(channel)
        # Yield the endpoint event per MCP spec
        yield "event: endpoint\n"
        yield f"data: {endpoint_url}\n\n"

        while True:
            # Wait for message with timeout to send keepalives
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if message is not None:
                data = message["data"].decode("utf-8")
                yield "event: message\n"
                yield f"data: {data}\n\n"
            else:
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception(f"Error in SSE generator for session {session_id}")
    finally:
        await pubsub.unsubscribe(channel)
        await r.aclose()

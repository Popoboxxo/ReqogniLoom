from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Dict, Any, Optional
from django.conf import settings
from cryptography.fernet import InvalidToken

from persistence.encryption import ENCRYPTED_PREFIX, decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

# TTL for the server-side session -> api-key binding (REQ-018 / audit P-02).
# Long enough for a normal SSE session, short enough to bound stale bindings.
SESSION_TTL_SECONDS = 8 * 3600

# Bounded per-session replay buffer for SSE Last-Event-ID recovery (REQ-107 /
# audit F8.3). Every published event gets a monotonic id and is appended to a
# capped Redis list; on reconnect the client sends the last id it saw and we
# replay the tail of the buffer with a larger id. This upgrades the transport
# from at-most-once to best-effort at-least-once within the buffer window.
EVENT_BUFFER_MAX = 100
EVENT_BUFFER_TTL_SECONDS = SESSION_TTL_SECONDS

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

def _event_counter_key(session_id: str) -> str:
    """Return the Redis key holding the monotonic event-id counter (REQ-107)."""
    return f"mcp:session:{session_id}:eventid"

def _event_buffer_key(session_id: str) -> str:
    """Return the Redis key holding the capped replay buffer (REQ-107)."""
    return f"mcp:session:{session_id}:buffer"

def _parse_event_envelope(raw: str) -> tuple[Optional[int], str]:
    """Split a stored/published event into ``(event_id, data_json)``.

    Events are wrapped as ``{"id": <int>, "data": <message>}`` (REQ-107).
    A payload that does not match this shape (e.g. a legacy plain message) is
    returned with ``event_id = None`` and the raw string as data, so the stream
    degrades gracefully instead of dropping the event.
    """
    try:
        envelope = json.loads(raw)
        if isinstance(envelope, dict) and "id" in envelope and "data" in envelope:
            return int(envelope["id"]), json.dumps(envelope["data"])
    except (ValueError, TypeError):
        pass
    return None, raw

def store_session_api_key(
    session_id: str, api_key: str, ttl: int = SESSION_TTL_SECONDS
) -> None:
    """Bind an authenticated API key to an SSE session (server-side).

    Storing the key server-side lets the message endpoint authorise
    subsequent POSTs by ``session_id`` alone, so the secret never has to
    travel in the SSE message URL (REQ-018 / SYSTEM_AUDIT P-02).

    The key is symmetrically *encrypted* (Fernet, via
    :mod:`persistence.encryption`, keyed by ``FIELD_ENCRYPTION_KEY``) before
    it hits Redis (REQ-036 / audit BE-5) so a Redis compromise does not
    directly expose usable API keys — unlike a bare HMAC signature, the
    ciphertext cannot be read without the encryption key. The auth flow
    still receives the plaintext key on read.

    Raises:
        Exception: whatever the Redis client / encryption layer raises. A
            session whose key binding failed to persist is unusable — every
            subsequent ``GET /mcp/messages/`` for it would fail server-side
            lookup and dead-end in ``SESSION_EXPIRED`` anyway, so it is more
            honest to fail session creation immediately here than to hand
            the caller a session id that is already dead (deep-dive review
            D-5b).
    """
    try:
        r = _get_redis_client()
        encrypted = encrypt_secret(api_key)
        r.set(_session_auth_key(session_id), encrypted, ex=ttl)
    except Exception:
        logger.exception(f"Failed to store session api key for {session_id}")
        raise

def get_session_api_key(session_id: str) -> Optional[str]:
    """Return the API key bound to an SSE session, or None if unknown/expired."""
    try:
        r = _get_redis_client()
        value = r.get(_session_auth_key(session_id))
        if value is None:
            return None
        encrypted = value.decode("utf-8") if isinstance(value, bytes) else str(value)
        # Every value stored here goes through encrypt_secret(), so unlike
        # persistence.encryption's legacy-plaintext migration path, a value
        # that does not even carry the Fernet token prefix is never a
        # legitimate binding for this key — treat it as tampered/unknown
        # rather than falling back to "use it as-is" (which decrypt_secret
        # otherwise does for un-prefixed input).
        if not encrypted.startswith(ENCRYPTED_PREFIX):
            logger.warning(f"Invalid session api key ciphertext for {session_id}")
            return None
        try:
            return decrypt_secret(encrypted)
        except InvalidToken:
            logger.warning(f"Invalid session api key ciphertext for {session_id}")
            return None
    except Exception:
        logger.exception(f"Failed to read session api key for {session_id}")
        return None

def publish_mcp_message(session_id: str, message: Dict[str, Any]) -> None:
    """Publish a JSON-RPC message to a specific SSE session.

    Each message is assigned a monotonic per-session event id and appended to a
    capped replay buffer before being published, so a client that reconnects
    with a ``Last-Event-ID`` header can recover events it missed during a
    connection drop (REQ-107 / audit F8.3).
    """
    try:
        r = _get_redis_client()
        channel = f"mcp:session:{session_id}"

        # Monotonic id per session; INCR is atomic so concurrent publishers on
        # the bounded worker pool never collide on an id.
        event_id = r.incr(_event_counter_key(session_id))
        envelope = json.dumps({"id": event_id, "data": message})

        # Append to the capped buffer and keep only the newest EVENT_BUFFER_MAX
        # entries. Both keys expire with the session so stale sessions do not
        # leak memory in Redis.
        buffer_key = _event_buffer_key(session_id)
        pipe = r.pipeline()
        pipe.rpush(buffer_key, envelope)
        pipe.ltrim(buffer_key, -EVENT_BUFFER_MAX, -1)
        pipe.expire(buffer_key, EVENT_BUFFER_TTL_SECONDS)
        pipe.expire(_event_counter_key(session_id), EVENT_BUFFER_TTL_SECONDS)
        pipe.execute()

        r.publish(channel, envelope)
    except Exception:
        logger.exception(f"Failed to publish MCP message to session {session_id}")

def get_buffered_events(
    session_id: str, after_event_id: Optional[int] = None
) -> list[Dict[str, Any]]:
    """Return buffered replay events for a session (REQ-107).

    Yields the wrapped ``{"id", "data"}`` envelopes still held in the capped
    buffer, oldest first. When ``after_event_id`` is given, only events with a
    strictly larger id are returned — the exact set a reconnecting client needs.
    """
    try:
        r = _get_redis_client()
        raw_items = r.lrange(_event_buffer_key(session_id), 0, -1)
    except Exception:
        logger.exception(f"Failed to read replay buffer for session {session_id}")
        return []

    events: list[Dict[str, Any]] = []
    for item in raw_items:
        raw = item.decode("utf-8") if isinstance(item, bytes) else str(item)
        try:
            envelope = json.loads(raw)
        except ValueError:
            continue
        if after_event_id is not None and envelope.get("id", 0) <= after_event_id:
            continue
        events.append(envelope)
    return events

async def async_sse_generator(
    session_id: str,
    endpoint_url: str,
    last_event_id: Optional[int] = None,
) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE events from Redis PubSub.

    Every ``message`` event carries an ``id:`` line so clients can track their
    position in the stream (REQ-107). When ``last_event_id`` is supplied (from a
    reconnecting client's ``Last-Event-ID`` header) the buffered events with a
    larger id are replayed first, then live streaming continues.
    """
    import redis.asyncio as redis
    import asyncio

    redis_url = _get_redis_url()
    r = redis.from_url(redis_url)
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    channel = f"mcp:session:{session_id}"

    try:
        # Subscribe before reading the buffer so no live event is lost in the
        # gap between replay and the streaming loop.
        await pubsub.subscribe(channel)
        # Yield the endpoint event per MCP spec
        yield "event: endpoint\n"
        yield f"data: {endpoint_url}\n\n"

        # Replay missed events for a reconnecting client (REQ-107).
        replayed_ids: set[int] = set()
        if last_event_id is not None:
            try:
                raw_items = await r.lrange(_event_buffer_key(session_id), 0, -1)
            except Exception:
                logger.exception(
                    f"Failed to replay buffer for session {session_id}"
                )
                raw_items = []
            for item in raw_items:
                raw = item.decode("utf-8") if isinstance(item, bytes) else str(item)
                event_id, data = _parse_event_envelope(raw)
                if event_id is None or event_id <= last_event_id:
                    continue
                replayed_ids.add(event_id)
                yield f"id: {event_id}\n"
                yield "event: message\n"
                yield f"data: {data}\n\n"

        while True:
            # Wait for message with timeout to send keepalives
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15.0)
            if message is not None:
                raw = message["data"].decode("utf-8")
                event_id, data = _parse_event_envelope(raw)
                # Skip an event already delivered via replay to avoid a
                # duplicate in the tiny subscribe/replay overlap window.
                if event_id is not None and event_id in replayed_ids:
                    replayed_ids.discard(event_id)
                    continue
                if event_id is not None:
                    yield f"id: {event_id}\n"
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

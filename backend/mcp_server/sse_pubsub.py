import json
import logging
from typing import AsyncGenerator, Dict, Any
from django.conf import settings

logger = logging.getLogger(__name__)

def _get_redis_url() -> str:
    # Use Celery broker URL as Redis URL
    return getattr(settings, "CELERY_BROKER_URL", "redis://redis:6379/0")

def publish_mcp_message(session_id: str, message: Dict[str, Any]) -> None:
    """Publish a JSON-RPC message to a specific SSE session."""
    import redis
    redis_url = _get_redis_url()
    try:
        r = redis.from_url(redis_url)
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

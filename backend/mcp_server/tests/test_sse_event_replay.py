"""
Unit tests for SSE event ids and Last-Event-ID replay (REQ-107 / audit F8.3).

Verifies that the MCP SSE transport:

  (a) assigns a monotonic event id to every published message and buffers it;
  (b) caps the replay buffer at EVENT_BUFFER_MAX entries;
  (c) returns only events newer than a given id via get_buffered_events;
  (d) emits an ``id:`` line for each live/replayed message event in the stream;
  (e) replays buffered events with a larger id on reconnect, then streams live;
  (f) reads the ``Last-Event-ID`` header and resumes a matching session in the
      GET handler.

These tests use an in-memory Redis stand-in (sync + async) so they run without
a live Redis / full application stack.

leaf_id : COMP-MC-001 (sse_pubsub, McpSseTransportView)
req_id  : REQ-107 (SSE event ids + Last-Event-ID replay)
"""
from __future__ import annotations

import json
from typing import AsyncGenerator, List, Optional
from unittest import mock

from asgiref.sync import async_to_sync
from django.test import RequestFactory

from mcp_server import sse_pubsub
from mcp_server.sse_pubsub import EVENT_BUFFER_MAX
from mcp_server.views import McpSseTransportView


_API_KEY = "rfk_test_key_value"


class _FakePipeline:
    """Minimal Redis pipeline stand-in that records and applies operations."""

    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis

    def rpush(self, key: str, value: str) -> "_FakePipeline":
        self._redis.rpush(key, value)
        return self

    def ltrim(self, key: str, start: int, end: int) -> "_FakePipeline":
        self._redis.ltrim(key, start, end)
        return self

    def expire(self, key: str, ttl: int) -> "_FakePipeline":
        return self

    def execute(self) -> None:
        return None


class _FakeRedis:
    """In-memory Redis stand-in covering the ops sse_pubsub needs."""

    def __init__(self) -> None:
        self.counters: dict = {}
        self.lists: dict = {}

    def incr(self, key: str) -> int:
        self.counters[key] = self.counters.get(key, 0) + 1
        return self.counters[key]

    def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    def ltrim(self, key: str, start: int, end: int) -> None:
        items = self.lists.get(key, [])
        # Emulate Redis LTRIM inclusive indexing with negative offsets.
        self.lists[key] = items[start:] if end == -1 else items[start : end + 1]

    def lrange(self, key: str, start: int, end: int) -> list:
        items = self.lists.get(key, [])
        return items if (start == 0 and end == -1) else items[start : end + 1]

    def expire(self, key: str, ttl: int) -> None:
        return None

    def pipeline(self) -> _FakePipeline:
        return _FakePipeline(self)


class _AsyncFakeRedis:
    """Async wrapper so the SSE generator can lrange the shared buffer."""

    def __init__(self, backing: _FakeRedis) -> None:
        self._backing = backing

    async def lrange(self, key: str, start: int, end: int) -> list:
        return self._backing.lrange(key, start, end)


# ---------------------------------------------------------------------------
# (a) + (b) publish assigns monotonic ids and buffers with a cap
# ---------------------------------------------------------------------------


def test_publish_assigns_monotonic_ids_and_buffers() -> None:
    fake = _FakeRedis()
    session_id = "sess-a"

    with mock.patch.object(sse_pubsub, "_get_redis_client", return_value=fake):
        sse_pubsub.publish_mcp_message(session_id, {"result": 1})
        sse_pubsub.publish_mcp_message(session_id, {"result": 2})

    stored = fake.lists[sse_pubsub._event_buffer_key(session_id)]
    ids = [json.loads(item)["id"] for item in stored]
    assert ids == [1, 2]
    assert json.loads(stored[0])["data"] == {"result": 1}


def test_publish_buffer_is_capped() -> None:
    fake = _FakeRedis()
    session_id = "sess-cap"

    with mock.patch.object(sse_pubsub, "_get_redis_client", return_value=fake):
        for i in range(EVENT_BUFFER_MAX + 25):
            sse_pubsub.publish_mcp_message(session_id, {"n": i})

    stored = fake.lists[sse_pubsub._event_buffer_key(session_id)]
    assert len(stored) == EVENT_BUFFER_MAX
    # Only the newest EVENT_BUFFER_MAX events survive; ids stay monotonic.
    ids = [json.loads(item)["id"] for item in stored]
    assert ids[0] == 26
    assert ids[-1] == EVENT_BUFFER_MAX + 25


# ---------------------------------------------------------------------------
# (c) get_buffered_events filters by after_event_id
# ---------------------------------------------------------------------------


def test_get_buffered_events_filters_by_id() -> None:
    fake = _FakeRedis()
    session_id = "sess-filter"

    with mock.patch.object(sse_pubsub, "_get_redis_client", return_value=fake):
        for i in range(5):
            sse_pubsub.publish_mcp_message(session_id, {"n": i})
        newer = sse_pubsub.get_buffered_events(session_id, after_event_id=3)

    assert [e["id"] for e in newer] == [4, 5]


# ---------------------------------------------------------------------------
# (d) + (e) generator emits id lines and replays on reconnect
# ---------------------------------------------------------------------------


async def _drain(gen: AsyncGenerator[str, None], stop_after: int) -> List[str]:
    """Collect up to ``stop_after`` chunks, then close the generator."""
    chunks: List[str] = []
    async for chunk in gen:
        chunks.append(chunk)
        if len(chunks) >= stop_after:
            break
    await gen.aclose()
    return chunks


def test_generator_replays_buffered_events_with_id_lines() -> None:
    fake = _FakeRedis()
    session_id = "sess-replay"

    # Pre-populate the buffer as if three events had been published.
    with mock.patch.object(sse_pubsub, "_get_redis_client", return_value=fake):
        for i in range(1, 4):
            sse_pubsub.publish_mcp_message(session_id, {"n": i})

    async_fake = _AsyncFakeRedis(fake)

    class _FakePubSub:
        async def subscribe(self, channel: str) -> None:
            return None

        async def get_message(self, ignore_subscribe_messages=True, timeout=0.0):
            # No live messages after replay; the drain stops before we reach
            # the streaming loop, so this simply returns None.
            return None

        async def unsubscribe(self, channel: str) -> None:
            return None

    async_fake.pubsub = lambda *a, **kw: _FakePubSub()  # type: ignore[attr-defined]
    async_fake.aclose = mock.AsyncMock()  # type: ignore[attr-defined]

    with mock.patch("redis.asyncio.from_url", return_value=async_fake):
        # last_event_id=1 → replay events 2 and 3 only.
        gen = sse_pubsub.async_sse_generator(
            session_id, "/mcp/messages/?session_id=" + session_id, last_event_id=1
        )
        # endpoint(2) + event 2 (id/event/data = 3) + event 3 (3) = 8 chunks.
        chunks = async_to_sync(_drain)(gen, stop_after=8)

    joined = "".join(chunks)
    assert "id: 2\n" in joined
    assert "id: 3\n" in joined
    assert "id: 1\n" not in joined  # not newer than last_event_id
    assert '"n": 2' in joined
    assert '"n": 3' in joined


# ---------------------------------------------------------------------------
# (f) GET handler parses Last-Event-ID and resumes a matching session
# ---------------------------------------------------------------------------


def test_get_handler_reads_last_event_id_and_resumes_session() -> None:
    captured: dict = {}

    def _fake_generator(
        session_id: str, endpoint_url: str, last_event_id: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        captured["session_id"] = session_id
        captured["last_event_id"] = last_event_id

        async def _gen() -> AsyncGenerator[str, None]:
            yield "event: endpoint\n"

        return _gen()

    existing_session = "resume-me"
    request = RequestFactory().get(
        f"/mcp/sse/?session_id={existing_session}",
        HTTP_X_API_KEY=_API_KEY,
        HTTP_LAST_EVENT_ID="7",
    )
    view = McpSseTransportView()

    auth_svc = mock.Mock()
    auth_svc.validate_api_key.return_value = mock.Mock()

    with mock.patch(
        "mcp_server.sse_pubsub.async_sse_generator", side_effect=_fake_generator
    ), mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value=_API_KEY
    ) as get_key, mock.patch(
        "mcp_server.sse_pubsub.store_session_api_key"
    ) as store, mock.patch(
        "mcp_server.views._get_auth_service", return_value=auth_svc
    ):
        response = async_to_sync(view.get)(request)

    assert response.status_code == 200
    # Matching binding → resumed session, no fresh binding stored.
    get_key.assert_called_once_with(existing_session)
    store.assert_not_called()
    assert captured["session_id"] == existing_session
    assert captured["last_event_id"] == 7


def test_get_handler_mints_new_session_when_binding_mismatches() -> None:
    captured: dict = {}

    def _fake_generator(
        session_id: str, endpoint_url: str, last_event_id: Optional[int] = None
    ) -> AsyncGenerator[str, None]:
        captured["session_id"] = session_id

        async def _gen() -> AsyncGenerator[str, None]:
            yield "event: endpoint\n"

        return _gen()

    request = RequestFactory().get(
        "/mcp/sse/?session_id=someone-elses",
        HTTP_X_API_KEY=_API_KEY,
    )
    view = McpSseTransportView()

    auth_svc = mock.Mock()
    auth_svc.validate_api_key.return_value = mock.Mock()

    with mock.patch(
        "mcp_server.sse_pubsub.async_sse_generator", side_effect=_fake_generator
    ), mock.patch(
        "mcp_server.sse_pubsub.get_session_api_key", return_value="different-key"
    ), mock.patch(
        "mcp_server.sse_pubsub.store_session_api_key"
    ) as store, mock.patch(
        "mcp_server.views._get_auth_service", return_value=auth_svc
    ):
        response = async_to_sync(view.get)(request)

    assert response.status_code == 200
    # Key mismatch → do NOT reuse the foreign session; mint and bind a new one.
    assert captured["session_id"] != "someone-elses"
    store.assert_called_once_with(captured["session_id"], _API_KEY)

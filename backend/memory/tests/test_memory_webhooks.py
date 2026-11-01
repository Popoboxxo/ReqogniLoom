"""Inbound Honcho webhook receiver (Plan A T-A4-7, security-reviewed path).

Covers the three contract tests named in the task plus the properties a security
review will ask for:

* ``test_webhook_rejects_bad_signature`` — missing header, wrong length, correct
  body under the wrong secret, and a non-ASCII header (which must be a 401, not
  a 500 from ``hmac.compare_digest``).
* ``test_webhook_disabled_without_secret`` — ``503`` with the constant
  ``"webhooks disabled"`` and no configuration detail.
* ``test_webhook_invalidates_digest_cache`` — ``204`` and the cached digest/health
  probes are gone.
* signature over the **raw** body, not over a re-serialised parse.
* the per-IP throttle actually answers ``429`` — and cannot be dodged by rotating
  ``X-Forwarded-For`` (S-F1), nor does it let a throttled request reach the HMAC.
* the declared body size is checked first: ``413`` oversized (S-F3).
* a rejection log line carries no body, secret or signature.
* a replayed delivery cannot keep the cache cold (S-F2 coalescing).
* the route is reachable **without** a JWT but useless without a signature.
* the registration command: read-only default, list/register/delete dispatch,
  local URL validation (S-F4), and command errors for a bad ``--tenant``.

Everything runs against the real URLconf and a real ``APIClient``; no network is
involved and no real secret is used (the test secret is generated per test).
"""
from __future__ import annotations

import ipaddress
import json
import logging
import socket

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from memory.health import (
    ASK_CACHE_KEY,
    DERIVATION_CACHE_KEY,
    DIGEST_CACHE_KEY,
    HEALTH_CACHE_KEY,
    invalidate_health_cache,
)
from memory.webhooks import (
    DISABLED_MESSAGE,
    MAX_BODY_BYTES,
    SECRET_ENV_VAR,
    SIGNATURE_HEADER,
    body_size_problem,
    expected_signature,
    resolve_webhook_secret,
    verify_signature,
)

URL = "/api/v1/memory/webhooks/honcho/"

#: Not a real secret. Long enough to make the HMAC meaningful, short enough to
#: read in a failure message.
SECRET = "test-webhook-secret-not-a-real-key"

#: A representative delivery: the three documented keys plus memory-bearing
#: content, so a test that accidentally echoes the body would fail loudly.
PAYLOAD = {
    "type": "queue.empty",
    "timestamp": "2026-10-21T12:00:00Z",
    "data": {"session_id": "s_demo", "memory": "secret-shaped payload text"},
}

RAW_BODY = json.dumps(PAYLOAD, sort_keys=True).encode("utf-8")


@pytest.fixture(autouse=True)
def _clear_caches():
    """A locmem cache is process-wide: keep probe values from leaking per test."""
    invalidate_health_cache()
    cache.clear()
    yield
    invalidate_health_cache()
    cache.clear()


@pytest.fixture
def client() -> APIClient:
    return APIClient()


def _post(
    client: APIClient,
    *,
    body: bytes = RAW_BODY,
    signature: str | None = None,
    x_forwarded_for: str | None = None,
):
    """POST a raw body with an optional signature header."""
    # Django's test client expects the WSGI form of the header; ``request.headers``
    # maps ``HTTP_X_HONCHO_SIGNATURE`` back to ``X-Honcho-Signature``.
    headers = (
        {}
        if signature is None
        else {f"HTTP_{SIGNATURE_HEADER.upper().replace('-', '_')}": signature}
    )
    if x_forwarded_for is not None:
        headers["HTTP_X_FORWARDED_FOR"] = x_forwarded_for
    return client.post(URL, data=body, content_type="application/json", **headers)


def _valid_signature(body: bytes = RAW_BODY, secret: str = SECRET) -> str:
    return expected_signature(secret, body)


# ---------------------------------------------------------------------------
# The three contract tests
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_webhook_rejects_bad_signature(client: APIClient, monkeypatch) -> None:
    """Every bad-signature shape answers 401 — and none of them answers 500.

    The four cases are the ones an attacker controls: no header at all, a header
    of the wrong length (truncated digest), the *correct body* signed with a
    different secret, and a non-ASCII header (which would raise ``TypeError`` in
    ``hmac.compare_digest`` if both sides were compared as ``str``).
    """
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)

    missing = _post(client)
    truncated = _post(client, signature=_valid_signature()[:32])
    wrong_secret = _post(client, signature=expected_signature("another-secret", RAW_BODY))
    non_ascii = _post(client, signature="ä" * 64)
    # Correct signature, different body: the classic replay/mutation attempt.
    mutated = _post(
        client, body=RAW_BODY.replace(b"queue.empty", b"test.event"), signature=_valid_signature()
    )

    for response in (missing, truncated, wrong_secret, non_ascii, mutated):
        assert response.status_code == 401, response.content
        body = response.json()
        assert body["error"]["code"] == "AUTHENTICATION_REQUIRED"
        # Nothing from the request is reflected back.
        assert "secret-shaped" not in json.dumps(body)
        assert b"queue.empty" not in response.content


@pytest.mark.django_db
def test_webhook_disabled_without_secret(client: APIClient, monkeypatch) -> None:
    """No secret configured -> 503 "webhooks disabled", even for a signed body."""
    monkeypatch.delenv(SECRET_ENV_VAR, raising=False)
    assert resolve_webhook_secret() is None

    unsigned = _post(client)
    signed_anyway = _post(client, signature="deadbeef" * 8)

    for response in (unsigned, signed_anyway):
        assert response.status_code == 503, response.content
        body = response.json()
        assert body["error"]["message"] == DISABLED_MESSAGE
        assert body["error"]["message"] == "webhooks disabled"
        # No hint about which variable is missing or which deployment this is.
        assert SECRET_ENV_VAR not in json.dumps(body)
        assert body["error"]["details"] == []


@pytest.mark.django_db
def test_webhook_invalidates_digest_cache(client: APIClient, monkeypatch) -> None:
    """A valid delivery answers 204 and drops the digest AND health caches."""
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
    # Seed the same values the read path would have cached.
    from memory.backends import MemoryHealth

    cache.set(DIGEST_CACHE_KEY, True)
    cache.set(ASK_CACHE_KEY, True)
    cache.set(DERIVATION_CACHE_KEY, "unknown")
    cache.set(
        HEALTH_CACHE_KEY,
        MemoryHealth(ok=True, backend="honcho", detail="ok", degraded=False),
    )
    assert cache.get(DIGEST_CACHE_KEY) is True

    response = _post(client, signature=_valid_signature())

    assert response.status_code == 204, response.content
    assert response.content == b""
    assert cache.get(DIGEST_CACHE_KEY) is None
    assert cache.get(HEALTH_CACHE_KEY) is None
    # The sibling probes are dropped as a set -- a torn envelope would report a
    # fresh health result next to a stale digest capability.
    assert cache.get(ASK_CACHE_KEY) is None
    assert cache.get(DERIVATION_CACHE_KEY) is None


# ---------------------------------------------------------------------------
# Signature covers the raw bytes, not a re-serialised parse
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_signature_covers_raw_bytes_not_a_reserialised_body(
    client: APIClient, monkeypatch
) -> None:
    """A body with unusual whitespace verifies only over its exact wire bytes.

    ``{"a":1}`` and ``{"a": 1}`` are the same JSON document but different bytes.
    A receiver that parsed first and re-serialised would accept both under one
    signature — so this pins the contract: signature over the raw body only.
    """
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
    wire_body = b'{"type":  "queue.empty",  "data": {}}'

    good = _post(client, body=wire_body, signature=_valid_signature(wire_body))
    # Signature of the *canonicalised* document must not be accepted for the
    # wire bytes (and vice versa).
    canonical = json.dumps(json.loads(wire_body)).encode("utf-8")
    assert canonical != wire_body
    canonicalised = _post(client, body=wire_body, signature=_valid_signature(canonical))

    assert good.status_code == 204, good.content
    assert canonicalised.status_code == 401, canonicalised.content


# ---------------------------------------------------------------------------
# Reachability: no JWT required, no signature -> useless
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_route_is_reachable_without_a_jwt(client: APIClient, monkeypatch) -> None:
    """The route must not sit behind the API's authentication.

    Asserted on the view's declared classes (a 401 from DRF's authenticator
    would be indistinguishable from our own 401) *and* behaviourally: an
    anonymous client gets the webhook's own 503/204, never a JWT error.
    """
    from memory.memory_rest import HonchoWebhookView

    assert HonchoWebhookView.authentication_classes == []
    assert HonchoWebhookView.permission_classes == [AllowAny]
    assert HonchoWebhookView.throttle_classes, "the endpoint must be rate-limited"

    monkeypatch.delenv(SECRET_ENV_VAR, raising=False)
    anonymous = APIClient()  # no Authorization header, no session
    assert _post(anonymous).status_code == 503

    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
    assert _post(anonymous, signature=_valid_signature()).status_code == 204
    # ... and without a signature the endpoint is not usable even so.
    assert _post(anonymous).status_code == 401


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def _rest_framework_with_rates(**rates: object) -> dict:
    """Full ``REST_FRAMEWORK`` dict with only the named rates changed."""
    merged = dict(settings.REST_FRAMEWORK)
    merged["DEFAULT_THROTTLE_RATES"] = {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"],
        **rates,
    }
    return merged


@pytest.mark.django_db
@override_settings(REST_FRAMEWORK=_rest_framework_with_rates(memory_webhook="3/min"))
def test_webhook_is_rate_limited(client: APIClient, monkeypatch) -> None:
    """A flood of deliveries is answered with 429, not with unbounded work.

    Counted before the signature is checked (DRF's throttle runs in
    ``initial()``), so a forged flood cannot buy more HMAC computations than a
    legitimate one.
    """
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)

    statuses = [_post(client).status_code for _ in range(5)]

    assert statuses[:3] == [401, 401, 401], statuses
    assert 429 in statuses[3:], statuses


@pytest.mark.django_db
@override_settings(REST_FRAMEWORK=_rest_framework_with_rates(memory_webhook="3/min"))
def test_forwarded_for_header_cannot_buy_a_second_bucket(
    client: APIClient, monkeypatch
) -> None:
    """S-F1: rotating ``X-Forwarded-For`` must NOT reset the per-IP counter.

    DRF's stock ``get_ident`` keys on that header whenever ``NUM_PROXIES`` is
    unset (the project default), so every request with a fresh value would get a
    fresh bucket — the documented 120/min ceiling would not exist, and the
    attacker would also steer the Redis key space and the WARNING log. All four
    requests come from the same ``REMOTE_ADDR`` (the test client's
    ``127.0.0.1``) but carry different forwarded addresses, so the 4th must
    still be a 429.
    """
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)

    statuses = [
        _post(client, x_forwarded_for=f"203.0.113.{n}").status_code for n in range(1, 5)
    ]

    assert statuses[:3] == [401, 401, 401], statuses
    assert statuses[3] == 429, statuses


@pytest.mark.django_db
@override_settings(REST_FRAMEWORK=_rest_framework_with_rates(memory_webhook="2/min"))
def test_throttled_delivery_never_reaches_signature_verification(
    client: APIClient, monkeypatch
) -> None:
    """A 429 must be decided before the HMAC is computed.

    DRF throttles in ``initial()``, i.e. before the handler runs, so a forged
    flood cannot buy more HMAC work than a legitimate delivery — which is the
    whole point of putting a cheap counter in front of an expensive check.
    """
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
    verified: list[bytes] = []

    def spy(*, secret, raw_body, provided):
        verified.append(raw_body)
        return False

    monkeypatch.setattr("memory.memory_rest.verify_signature", spy)

    statuses = [_post(client, signature="0" * 64).status_code for _ in range(4)]

    assert statuses == [401, 401, 429, 429], statuses
    assert len(verified) == 2, "a throttled delivery must not be verified"


# ---------------------------------------------------------------------------
# Body-size guard (S-F3)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_oversized_body_is_rejected_with_413(client: APIClient, monkeypatch) -> None:
    """An oversized delivery is refused on its declared length, before the HMAC."""
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)

    response = client.post(
        URL, data=b"x" * (MAX_BODY_BYTES + 1), content_type="application/json"
    )

    assert response.status_code == 413, response.content
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


class TestBodySizeProblem:
    """The declared-size classifier, independent of Django's own limit."""

    @staticmethod
    def _request(**meta) -> object:
        from types import SimpleNamespace

        return SimpleNamespace(META=meta)

    def test_absent_length_is_reported(self) -> None:
        assert body_size_problem(self._request()) == "length"

    def test_blank_or_invalid_length_is_reported(self) -> None:
        assert body_size_problem(self._request(CONTENT_LENGTH="")) == "length"
        assert body_size_problem(self._request(CONTENT_LENGTH="nope")) == "length"
        assert body_size_problem(self._request(CONTENT_LENGTH="-1")) == "length"

    def test_oversized_is_reported(self) -> None:
        assert (
            body_size_problem(self._request(CONTENT_LENGTH=str(MAX_BODY_BYTES + 1)))
            == "size"
        )

    def test_exact_limit_and_smaller_body_pass(self) -> None:
        assert body_size_problem(self._request(CONTENT_LENGTH=str(MAX_BODY_BYTES))) is None
        assert body_size_problem(self._request(CONTENT_LENGTH="0")) is None


# ---------------------------------------------------------------------------
# Log hygiene and replay coalescing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rejection_log_carries_no_body_secret_or_signature(
    client: APIClient, monkeypatch, caplog
) -> None:
    """The one WARNING names the peer only — never payload, key or digest."""
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
    provided = "deadbeef" * 8

    with caplog.at_level(logging.WARNING, logger="memory.webhooks"):
        response = _post(client, signature=provided)

    assert response.status_code == 401
    assert "honcho webhook rejected" in caplog.text
    assert "secret-shaped payload text" not in caplog.text
    assert SECRET not in caplog.text
    assert provided not in caplog.text


@pytest.mark.django_db
def test_replay_inside_the_coalescing_window_does_not_re_drop_the_cache(
    client: APIClient, monkeypatch
) -> None:
    """S-F2: a replayed (still valid) delivery cannot keep the cache cold.

    The signature carries no timestamp, so a captured delivery verifies again
    forever. What stops that from becoming "attacker controls cache
    availability" is the coalescing window: the second 204 still answers 204 but
    does not drop the probes the first one already dropped.
    """
    monkeypatch.setenv(SECRET_ENV_VAR, SECRET)
    signature = _valid_signature()

    assert _post(client, signature=signature).status_code == 204
    # Simulate the warm-up a real read would have done between the two replays.
    cache.set(DIGEST_CACHE_KEY, True)

    assert _post(client, signature=signature).status_code == 204
    assert cache.get(DIGEST_CACHE_KEY) is True, "a replay must not re-drop the cache"


def test_short_secret_is_accepted_but_warned_once(monkeypatch, caplog) -> None:
    """S-F8: a weak key must not be silently usable, and must not be rejected."""
    monkeypatch.setattr("memory.webhooks._short_secret_warned", False)
    monkeypatch.setenv(SECRET_ENV_VAR, "too-short")

    with caplog.at_level(logging.WARNING, logger="memory.webhooks"):
        assert resolve_webhook_secret() == "too-short"
        assert resolve_webhook_secret() == "too-short"

    warnings = [r for r in caplog.records if "shorter than" in r.getMessage()]
    assert len(warnings) == 1, "warn exactly once per process, not per delivery"
    assert "too-short" not in caplog.text, "the value itself is never logged"


# ---------------------------------------------------------------------------
# Pure-function level guards
# ---------------------------------------------------------------------------


class TestVerifySignature:
    """The comparison itself: constant time, bytes-based, case-insensitive hex."""

    def test_accepts_the_expected_hex(self) -> None:
        assert verify_signature(
            secret=SECRET, raw_body=RAW_BODY, provided=_valid_signature()
        )

    def test_accepts_uppercase_hex(self) -> None:
        """Hex is case-insensitive; normalising it must not weaken the check."""
        assert verify_signature(
            secret=SECRET, raw_body=RAW_BODY, provided=_valid_signature().upper()
        )

    @pytest.mark.parametrize("provided", [None, "", "   ", "not-hex", "ä" * 64, "0" * 64])
    def test_rejects_missing_or_wrong_headers(self, provided: str | None) -> None:
        assert not verify_signature(
            secret=SECRET, raw_body=RAW_BODY, provided=provided
        )

    def test_empty_secret_is_treated_as_disabled(self, monkeypatch) -> None:
        """``""`` must never behave like a usable key (HMAC("") is predictable)."""
        monkeypatch.setenv(SECRET_ENV_VAR, "   ")
        assert resolve_webhook_secret() is None

    def test_uses_compare_digest(self, monkeypatch) -> None:
        """Regression guard: never compare with ``==`` (early-exit timing leak)."""
        import hmac

        calls: list[tuple] = []
        real = hmac.compare_digest

        def spy(left, right):
            calls.append((left, right))
            return real(left, right)

        monkeypatch.setattr(hmac, "compare_digest", spy)
        verify_signature(secret=SECRET, raw_body=RAW_BODY, provided=_valid_signature())
        assert calls, "signature comparison must use hmac.compare_digest"
        # Both sides are bytes: comparing str to str raises on non-ASCII input.
        assert all(isinstance(side, bytes) for pair in calls for side in pair)


# ---------------------------------------------------------------------------
# honcho_register_webhooks (the registration side of the same feature)
# ---------------------------------------------------------------------------


#: Documentation-range address (RFC 5737), i.e. guaranteed not routable. Used as
#: the fake resolution of every non-literal hostname so no test ever touches DNS.
PUBLIC_IP = "93.184.216.34"


def _fake_getaddrinfo(host, port, **kwargs):
    """Deterministic resolver: names -> one public IP, IP literals pass through.

    Passing literals through is what lets the private/loopback rejection test
    reach the address check at all; using a public IP for names keeps every
    "happy path" test offline and stable.
    """
    try:
        ipaddress.ip_address(str(host).split("%", 1)[0])
        literal = str(host)
    except ValueError:
        literal = PUBLIC_IP
    return [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (literal, port))
    ]


class TestRegisterCommand:
    """The command must be read-only by default and never retry a failure."""

    def _run(self, *args: str) -> str:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("honcho_register_webhooks", *args, stdout=out)
        return out.getvalue()

    @pytest.fixture
    def honcho_env(self, monkeypatch):
        monkeypatch.setenv("HONCHO_BASE_URL", "http://honcho.test:8000")
        monkeypatch.setenv("HONCHO_API_KEY", "not-a-real-key")

    @pytest.fixture(autouse=True)
    def _no_dns(self, monkeypatch):
        """No test in this class may depend on real name resolution."""
        monkeypatch.setattr(
            "memory.management.commands.honcho_register_webhooks.socket.getaddrinfo",
            _fake_getaddrinfo,
        )

    @pytest.fixture
    def no_http(self, monkeypatch):
        """Fail loudly if an invalid URL is allowed to reach Honcho."""

        def boom(*args, **kwargs):
            raise AssertionError("no Honcho request should be sent")

        monkeypatch.setattr(
            "memory.management.commands.honcho_register_webhooks._request", boom
        )

    @pytest.mark.django_db
    def test_default_action_lists_and_writes_nothing(self, honcho_env, monkeypatch):
        """No flag = --list: one GET per tenant, no POST and no DELETE."""
        from persistence.tests.factories import active_tenant

        seen: list[tuple[str, str]] = []

        def fake_request(method, url, *, api_key, payload=None):
            seen.append((method, url))
            assert api_key == "not-a-real-key"
            assert payload is None, "a list must never send a body"
            return 200, [{"id": "ep-1", "url": "https://example.test/hook"}]

        monkeypatch.setattr(
            "memory.management.commands.honcho_register_webhooks._request", fake_request
        )
        with active_tenant() as tenant:
            line = json.loads(self._run())

        assert [method for method, _ in seen] == ["GET"]
        assert line["action"] == "list"
        assert line["tenant"] == str(tenant.id)
        assert line["workspace"] == f"reqogniloom_{tenant.id}"
        assert line["endpoints"] == [
            {"id": "ep-1", "url": "https://example.test/hook"}
        ]
        # The operational preconditions travel with every line.
        joined = " ".join(line["notes"])
        assert "WEBHOOK_SECRET" in joined
        assert "30 s timeout" in joined
        assert "no retries" in joined

    @pytest.mark.django_db
    def test_explicit_list_switch_is_honoured(self, honcho_env, monkeypatch):
        """F4: --list is a real selector (default False), not an inert switch."""
        from persistence.tests.factories import active_tenant

        seen: list[str] = []

        def fake_request(method, url, *, api_key, payload=None):
            seen.append(method)
            return 200, [{"id": "ep-1", "url": "https://example.test/hook"}]

        monkeypatch.setattr(
            "memory.management.commands.honcho_register_webhooks._request", fake_request
        )
        with active_tenant():
            line = json.loads(self._run("--list"))

        assert seen == ["GET"]
        assert line["action"] == "list"

    @pytest.mark.django_db
    @pytest.mark.parametrize("status", [200, 201])
    def test_register_is_idempotent(self, honcho_env, monkeypatch, status):
        """200 (already registered) and 201 (created) are both success."""
        from persistence.tests.factories import active_tenant

        bodies: list[dict] = []

        def fake_request(method, url, *, api_key, payload=None):
            bodies.append(payload or {})
            assert method == "POST"
            return status, {"id": "ep-1", "url": payload["url"]}

        monkeypatch.setattr(
            "memory.management.commands.honcho_register_webhooks._request", fake_request
        )
        with active_tenant():
            line = json.loads(self._run("--url", "https://reqogniloom.test/hook"))

        assert line["ok"] is True
        assert line["status"] == status
        assert bodies == [{"url": "https://reqogniloom.test/hook"}]
        # F2: --url must REPORT the endpoint it just registered. It used to print
        # "endpoints": [] because a single-object answer was not normalised.
        assert line["endpoints"] == [
            {"id": "ep-1", "url": "https://reqogniloom.test/hook"}
        ]

    @pytest.mark.django_db
    def test_delete_removes_the_named_endpoint(self, honcho_env, monkeypatch):
        """--delete issues exactly one DELETE against the collection/<id> path."""
        from persistence.tests.factories import active_tenant

        seen: list[tuple[str, str, dict | None]] = []

        def fake_request(method, url, *, api_key, payload=None):
            seen.append((method, url, payload))
            return 204, None

        monkeypatch.setattr(
            "memory.management.commands.honcho_register_webhooks._request", fake_request
        )
        with active_tenant() as tenant:
            line = json.loads(self._run("--delete", "ep-1"))

        assert line["action"] == "delete"
        assert line["ok"] is True
        assert line["status"] == 204
        assert line["endpoints"] is None
        expected_url = (
            f"http://honcho.test:8000/v3/workspaces/reqogniloom_{tenant.id}"
            "/webhooks/ep-1"
        )
        assert seen == [("DELETE", expected_url, None)]

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("tenant_arg", "match"),
        [("not-a-uuid", "valid UUID"), ("00000000-0000-4000-8000-000000000000", "unknown tenant")],
    )
    def test_bad_tenant_argument_is_a_command_error(
        self, honcho_env, no_http, tenant_arg, match
    ):
        """A malformed or unknown --tenant fails before any Honcho call."""
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match=match):
            self._run("--tenant", tenant_arg)

    @pytest.mark.django_db
    @pytest.mark.parametrize(
        ("url", "match"),
        [
            ("http://127.0.0.1/x", "non-public"),
            ("http://honcho-redis:6379/", "port 80 or 443"),
            ("http://10.1.2.3/hook", "non-public"),
            ("http://[::1]/hook", "non-public"),
            ("ftp://reqogniloom.test/hook", "http:// or https://"),
            ("https://user:pw@reqogniloom.test/hook", "userinfo"),
            ("http://reqogniloom.test:99999/hook", "invalid host or port"),
        ],
    )
    def test_callback_url_is_validated_locally(self, honcho_env, no_http, url, match):
        """S-F4: the private/loopback/non-public shapes are refused before the trip."""
        from django.core.management.base import CommandError

        with pytest.raises(CommandError, match=match):
            self._run("--url", url)

    @pytest.mark.django_db
    def test_documented_failures_are_reported_with_a_hint(self, honcho_env, monkeypatch):
        """409/422 are documented Honcho answers, so the line names the cause."""
        from django.core.management.base import CommandError

        from persistence.tests.factories import active_tenant

        def fake_request(method, url, *, api_key, payload=None):
            return 409, {"detail": "webhook limit reached"}

        monkeypatch.setattr(
            "memory.management.commands.honcho_register_webhooks._request", fake_request
        )
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        with active_tenant(), pytest.raises(CommandError, match="failed"):
            call_command(
                "honcho_register_webhooks",
                "--url",
                "https://reqogniloom.test/hook",
                stdout=out,
            )

        line = json.loads(out.getvalue().strip())
        assert line["ok"] is False
        assert line["status"] == 409
        assert "limit" in line["hint"]

    @pytest.mark.django_db
    def test_missing_honcho_configuration_is_a_command_error(self, monkeypatch):
        """Without a base URL/key the command refuses instead of guessing."""
        from django.core.management import call_command
        from django.core.management.base import CommandError

        monkeypatch.delenv("HONCHO_BASE_URL", raising=False)
        monkeypatch.delenv("HONCHO_API_KEY", raising=False)
        with pytest.raises(CommandError, match="HONCHO_BASE_URL"):
            call_command("honcho_register_webhooks")

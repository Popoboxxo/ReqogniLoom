"""GitHub #1050 — a *required* LLM variable that nothing reported.

``llm_adapter.providers.OpencodeGoProvider`` sends the ``x-opencode-session``
header the OpenCode Zen-Go endpoint demands, and omits it when
``LLM_OPENCODE_SESSION`` is unset. Omitting is correct (an empty header is worse
than none) — but the endpoint then answers ``400 MissingSessionID`` for *every*
chat completion, the resilience wrapper treats 4xx as permanent, and the only
trace is a provider-side log line. The provider docstring used to call the
variable "optional", which is exactly the belief that kept the misconfiguration
alive: an operator reading the docs had no reason to set it.

Two things are pinned here:

* the ``llm_adapter.W003`` system check fires on exactly the bad combination
  (``LLM_PROVIDER=opencode_go`` + no session) and stays silent otherwise, in
  both directions (a warning where there is nothing wrong is its own bug — it
  trains operators to ignore ``manage.py check``);
* the docstring-level contract is *enforced*, not merely asserted in prose: the
  provider's own docstring must not describe ``LLM_OPENCODE_SESSION`` as
  optional. A test is worth more than a comment here, because the comment is
  what drifted in the first place.
"""
from __future__ import annotations

import inspect

import pytest

from llm_adapter.checks import (
    OPENCODE_PROVIDER_NAME,
    OPENCODE_SESSION_MISSING,
    check_opencode_session_required,
)
from llm_adapter.providers import OpencodeGoProvider

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    """Every test states the full LLM_PROVIDER / LLM_OPENCODE_SESSION pair.

    Without this the suite would inherit whatever the developer's shell exports
    and a "fires" test could pass for the wrong reason.
    """
    monkeypatch.delenv("LLM_OPENCODE_SESSION", raising=False)
    monkeypatch.setenv("LLM_PROVIDER", "mock")


# ---------------------------------------------------------------------------
# The check fires
# ---------------------------------------------------------------------------


def test_check_fires_for_opencode_go_without_a_session(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", OPENCODE_PROVIDER_NAME)

    warnings = check_opencode_session_required()

    assert [w.id for w in warnings] == [OPENCODE_SESSION_MISSING]
    warning = warnings[0]
    assert "LLM_OPENCODE_SESSION" in warning.msg
    assert "LLM_PROVIDER='opencode_go'" in warning.msg
    # The hint has to carry the consequence, or it is just a variable name.
    assert "400 MissingSessionID" in warning.hint
    assert "x-opencode-session" in warning.hint
    assert "LLM_OPENCODE_SESSION" in warning.hint


def test_check_treats_a_whitespace_only_session_as_missing(monkeypatch):
    """A blank value would be sent as a header the endpoint still refuses.

    ``OpencodeGoProvider._chat`` already strips the value, so a whitespace-only
    session is *not sent* — the check must agree with the provider rather than
    treat the two as different states.
    """
    monkeypatch.setenv("LLM_PROVIDER", OPENCODE_PROVIDER_NAME)
    monkeypatch.setenv("LLM_OPENCODE_SESSION", "   ")

    warnings = check_opencode_session_required()

    assert [w.id for w in warnings] == [OPENCODE_SESSION_MISSING]


# ---------------------------------------------------------------------------
# The check stays silent
# ---------------------------------------------------------------------------


def test_check_is_silent_for_opencode_go_with_a_session(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", OPENCODE_PROVIDER_NAME)
    monkeypatch.setenv("LLM_OPENCODE_SESSION", "sess-abc123")

    assert check_opencode_session_required() == []


@pytest.mark.parametrize("provider", ["mock", "anthropic", "openai", "ollama"])
def test_check_is_silent_for_every_other_provider(provider, monkeypatch):
    """The variable is required by *one* provider, not by the LLM layer."""
    monkeypatch.setenv("LLM_PROVIDER", provider)

    assert check_opencode_session_required() == []


def test_check_is_silent_for_an_empty_session_on_another_provider(monkeypatch):
    """A stale empty ``LLM_OPENCODE_SESSION`` is not a reason to warn."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_OPENCODE_SESSION", "")

    assert check_opencode_session_required() == []


def test_check_never_raises_when_the_config_cannot_be_resolved(monkeypatch):
    """A system check that crashes would take ``migrate`` down with it."""
    import llm_adapter.providers as providers_module

    def _boom():
        raise RuntimeError("no DB, no env, nothing resolvable")

    monkeypatch.setattr(
        providers_module, "resolve_provider_config", _boom, raising=True
    )

    assert check_opencode_session_required() == []


# ---------------------------------------------------------------------------
# The docstring contract, enforced
# ---------------------------------------------------------------------------


def test_provider_docstring_states_the_session_is_required():
    """The docstring is the thing that drifted; a test keeps it from drifting.

    The check runs over the variable's whole *entry* (its first line plus the
    wrapped continuation), not a single physical line — asserting on one line
    would be a formatting accident waiting to fail, or worse, to pass.
    """
    doc = inspect.getdoc(OpencodeGoProvider) or ""
    lines = doc.splitlines()

    start = next(
        i for i, line in enumerate(lines) if "LLM_OPENCODE_SESSION=" in line
    )
    declaration = lines[start]
    entry = [declaration]
    for line in lines[start + 1:]:
        # The entry ends at the next line that starts a new env-var item.
        if line.strip() and not line.startswith("        "):
            break
        if line.strip() and line.strip().split(" ")[0].isupper() and "=" in line:
            break
        entry.append(line)
    entry_text = "\n".join(entry)

    # The *declaration* must not call it optional — that was the exact bug
    # (#1050). Only the declaration line is checked for the word: the
    # continuation legitimately quotes the old wording to explain the history,
    # and a test that banned the word everywhere would forbid documenting the
    # mistake.
    assert "optional" not in declaration.lower(), (
        f"LLM_OPENCODE_SESSION must not be declared optional: {declaration!r}"
    )
    assert "REQUIRED" in entry_text
    # And the reason must be in the entry, not a paragraph away.
    assert "x-opencode-session" in entry_text


def test_check_id_and_provider_name_are_stable_public_names():
    """Clients/greps key on these; renaming them is a contract change."""
    from llm_adapter import checks

    assert OPENCODE_SESSION_MISSING == "llm_adapter.W003"
    assert OPENCODE_PROVIDER_NAME == "opencode_go"
    assert "check_opencode_session_required" in checks.__all__


def test_check_is_registered_with_django():
    """Registered from ``LlmAdapterConfig.ready`` so ``manage.py check`` runs it.

    Asserted through the public Django registry rather than by re-reading
    ``apps.py``, so a future refactor that forgets ``register(...)`` fails here
    instead of only in an operator's terminal.
    """
    from django.core.checks import registry

    assert check_opencode_session_required in registry.registry.get_checks()


# ---------------------------------------------------------------------------
# The admin health surface (GET /api/v1/admin/health/)
# ---------------------------------------------------------------------------


def test_health_row_is_degraded_and_actionable_without_a_session(monkeypatch):
    """``manage.py check`` is one surface; the dashboard is the other.

    Without this row the dashboard would either show ``llm_provider: ok`` (a lie)
    or spend ``_LLM_PROBE_TIMEOUT_S`` per poll rediscovering a certain 400.
    """
    from admin_ops.health_rest import _check_llm_provider

    monkeypatch.setattr(
        "django.conf.settings.LLM_PROVIDER", OPENCODE_PROVIDER_NAME, raising=True
    )
    monkeypatch.setattr(
        "django.conf.settings.LLM_API_KEY", "sk-dummy", raising=True
    )

    row = _check_llm_provider()

    assert row["status"] == "degraded"
    assert "LLM_OPENCODE_SESSION" in row["detail"]
    assert "MissingSessionID" in row["detail"]


def test_health_row_does_not_probe_when_the_session_is_missing(monkeypatch):
    """A certain failure must not cost a probe round-trip on every poll."""
    from admin_ops.health_rest import _check_llm_provider

    monkeypatch.setattr(
        "django.conf.settings.LLM_PROVIDER", OPENCODE_PROVIDER_NAME, raising=True
    )
    monkeypatch.setattr(
        "django.conf.settings.LLM_API_KEY", "sk-dummy", raising=True
    )

    def _explode(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("the health probe must not run without a session id")

    monkeypatch.setattr("llm_adapter.providers.get_provider", _explode)

    assert _check_llm_provider()["status"] == "degraded"


def test_health_check_ignores_the_variable_for_other_providers(monkeypatch):
    from admin_ops.health_rest import _check_llm_provider

    monkeypatch.setattr("django.conf.settings.LLM_PROVIDER", "mock", raising=True)

    row = _check_llm_provider()

    assert row["status"] == "ok"
    assert "LLM_OPENCODE_SESSION" not in row["detail"]


def test_health_probe_sends_the_configured_session_header(monkeypatch):
    """The probe must build the same config the request path builds.

    A probe that omits ``opencode_session`` reports a correctly configured
    deployment as DOWN — the inverse of the bug #1050 reports, and just as
    misleading.
    """
    from admin_ops.health_rest import _check_llm_provider

    monkeypatch.setattr(
        "django.conf.settings.LLM_PROVIDER", OPENCODE_PROVIDER_NAME, raising=True
    )
    monkeypatch.setattr(
        "django.conf.settings.LLM_API_KEY", "sk-dummy", raising=True
    )
    monkeypatch.setenv("LLM_OPENCODE_SESSION", "sess-abc123")

    captured: dict = {}

    class _Probe:
        _resilient = None

        def complete(self, *args, **kwargs):
            return "pong"

    def _fake_get_provider(config):
        captured["config"] = config
        return _Probe()

    monkeypatch.setattr("llm_adapter.providers.get_provider", _fake_get_provider)

    row = _check_llm_provider()

    assert row["status"] == "ok"
    assert captured["config"].opencode_session == "sess-abc123"

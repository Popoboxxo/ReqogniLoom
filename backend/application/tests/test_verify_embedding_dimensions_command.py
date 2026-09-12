"""Tests for ``manage.py verify_embedding_dimensions`` (#826).

The command is the pre-deploy counterpart to the ``llm_adapter.W001`` system
check: the check compares the configured provider against the *models*, while
this command compares it against the *live database columns*. Only the latter
sees the "changed ``EMBEDDING_VECTOR_DIMENSIONS`` + ran ``makemigrations`` but
forgot ``migrate``" state, where the models already agree with the provider but
the physical columns are still the old width.
"""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _run() -> str:
    out = StringIO()
    call_command("verify_embedding_dimensions", stdout=out, stderr=out)
    return out.getvalue()


@pytest.mark.django_db
class TestVerifyEmbeddingDimensions:
    def test_passes_when_the_db_matches_the_default_provider(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "mock")  # 384-dim, matches vector(384)

        output = _run()

        assert "OK:" in output
        assert "vector(384)" in output

    def test_fails_when_the_provider_is_wider_than_the_columns(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "ollama")  # 768-dim

        with pytest.raises(CommandError) as excinfo:
            _run()

        message = str(excinfo.value)
        assert "768" in message
        assert "vector(384)" in message
        assert "EMBEDDING_VECTOR_DIMENSIONS" in message

    def test_fails_on_an_unknown_provider(self, monkeypatch):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "not-a-real-provider")

        with pytest.raises(CommandError, match="not a known provider"):
            _run()

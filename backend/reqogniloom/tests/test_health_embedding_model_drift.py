"""T-A0-6: the ``embedding_model_drift`` advisory must be honest, not blind.

``_embedding_model_drift()`` reads through ``Model.unscoped``, which skips the
ORM tenant filter but is **not** an RLS bypass: the embedding tables are
``ENABLE`` + ``FORCE ROW LEVEL SECURITY`` keyed on
``current_setting('app.current_tenant')``. ``/health*`` is an unauthenticated
plain Django view and sets no tenant, so under an RLS-bound role the aggregate
is structurally 0 — a clean bill of health during a real model change.

These tests pin the three properties of the fix:

* the key stays VERBOSE-ONLY (``?verbose=1``), so the default probe is cheap;
* every per-table value is a number or the literal ``unknown`` — never a
  misleading ``0`` for a table this endpoint could not see;
* when the probe reports an RLS-shadowed aggregate (no tenant, unprivileged
  role, monkeypatched instead of provisioning a DB role), the payload says
  ``unknown`` AND one warning points at the authoritative command.
"""
from __future__ import annotations

import re

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

#: ``requirement=3,tracelink=0,icd=unknown,memory=0`` -> one match per table.
_VALUE = re.compile(r"^(\d+|unknown)$")


def _ready(monkeypatch: pytest.MonkeyPatch):
    """GET /health/ready with the mandatory probes stubbed as healthy.

    Only the dependency probes are stubbed: the advisory block under test runs
    for real against the test database (the migration/owner role there can see
    past RLS, which is the "numeric" branch).
    """
    from reqogniloom import health

    monkeypatch.setattr(
        health,
        "_run_required_checks",
        lambda: {name: "ok" for name in health._REQUIRED_CHECK_NAMES},
    )
    monkeypatch.setattr(health, "_embedding_dimension_mismatches", lambda: [])
    return Client()


def test_drift_advisory_is_absent_without_verbose(monkeypatch) -> None:
    """The aggregate must not run — or appear — on the cheap default probe."""
    client = _ready(monkeypatch)

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert "embedding_model_drift" not in response.json()["advisory"]


def test_verbose_drift_values_are_numeric_or_unknown(monkeypatch) -> None:
    """Every table reports a count or ``unknown`` — never a bare, wrong zero."""
    client = _ready(monkeypatch)

    response = client.get("/health/ready?verbose=1")

    assert response.status_code == 200
    body = response.json()
    advisory = body["advisory"]
    assert "embedding_model_drift" in advisory
    entries = advisory["embedding_model_drift"].split(",")
    assert {entry.split("=", 1)[0] for entry in entries} == {
        "requirement",
        "tracelink",
        "icd",
        "memory",
    }
    for entry in entries:
        label, value = entry.split("=", 1)
        assert _VALUE.match(value), f"{label} reported a non-count value {value!r}"


def test_rls_shadowed_aggregate_reports_unknown_and_warns(monkeypatch) -> None:
    """A count this endpoint cannot trust is withheld, not reported as clean.

    The RLS verdict is monkeypatched rather than provisioned: the point under
    test is the branch, and creating a real unprivileged role inside a test
    would leak into the shared ``--reuse-db`` cluster.
    """
    client = _ready(monkeypatch)
    from reqogniloom import health

    monkeypatch.setattr(
        health, "_embedding_count_scope", lambda: "shadowed"
    )

    response = client.get("/health/ready?verbose=1")

    assert response.status_code == 200
    body = response.json()
    drift = body["advisory"]["embedding_model_drift"]
    values = [entry.split("=", 1)[1] for entry in drift.split(",")]
    assert set(values) == {"unknown"}
    # One pointer to the authoritative cross-corpus view, and no bogus count.
    guidance = [
        warning
        for warning in body["warnings"]
        if "verify_embedding_dimensions --models" in warning
    ]
    assert len(guidance) == 1
    assert not any(
        "were produced by a different model" in warning for warning in body["warnings"]
    )

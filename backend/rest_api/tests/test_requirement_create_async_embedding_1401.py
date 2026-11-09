"""#1401 at the REST boundary — the 201 must not wait for the embedding provider.

``application/tests/test_embedding_async_1401.py`` pins the service contract.
This module pins the two things only the HTTP seam can show:

* the response is still ``201`` when the broker is down (a warning, not a 500);
* the provider is not called *inside* the request — exactly one post-commit
  callback is registered instead, which is what ``embed_rows_task`` runs on.

``transaction=True`` is load-bearing: pytest-django's default rolled-back test
transaction never runs ``on_commit`` callbacks, so the outage path would never
be reached and a passing test would prove nothing.
"""
from __future__ import annotations

import uuid
from unittest.mock import patch

import pytest
from django.db import OperationalError
from rest_framework.test import APIClient

from application.tasks import embed_rows_task
from auth_tenancy.models import ROLE_ADMIN, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Requirement, Tenant, User, Workspace

pytestmark = pytest.mark.django_db(transaction=True)

_GENERATE = "llm_adapter.embedding_service.generate_embedding_with_model"
_PASSWORD = "rfpass123"


@pytest.fixture
def api_env():
    """Tenant + admin + one workspace, all uniquely named per test.

    ``transaction=True`` means no rollback between tests, so the identifiers
    carry a uuid suffix instead of relying on isolation.
    """
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"Async Embed {suffix}", slug=f"async-embed-{suffix}", is_active=True
    )
    admin = User.objects.create(
        username=f"async-embed-{suffix}", email=f"ae-{suffix}@t.test", tenant=tenant
    )
    admin.set_password(_PASSWORD)
    admin.save(update_fields=["password"])
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.create(
            tenant=tenant, name=f"AE WS {suffix}", preset={"name": "standard"}
        )
        UserRole.objects.create(
            tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
        )
        yield {"tenant": tenant, "workspace": workspace, "username": admin.username}
    finally:
        clear_request_tenant()


def _client(env: dict) -> APIClient:
    client = APIClient()
    resp = client.post(
        "/api/v1/auth/login/",
        {"username": env["username"], "password": _PASSWORD},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.json()['token']}")
    return client


def test_create_returns_201_when_the_broker_is_down(api_env, caplog):
    """A queue outage must not turn a persisted requirement into a 500."""
    client = _client(api_env)

    def _broker_down(*args, **kwargs):
        raise OperationalError("broker unreachable")

    with patch.object(embed_rows_task, "delay", _broker_down), caplog.at_level("WARNING"):
        resp = client.post(
            "/api/v1/requirements/",
            {"workspace_id": str(api_env["workspace"].id), "title": "Survives"},
            format="json",
        )

    assert resp.status_code == 201, resp.content
    assert Requirement.objects.filter(title="Survives").exists()
    assert any(
        "could not enqueue embedding" in record.getMessage()
        for record in caplog.records
    ), "the degraded path must be observable in the log"


def test_create_dispatches_exactly_one_embedding_task(api_env):
    """The request hands the vector to the queue and never computes it itself.

    ``delay`` is mocked, so the only way the provider could be reached is an
    inline call inside the request — which is exactly what #1401 removed. (The
    *deferral* — that the dispatch only fires on commit — is pinned in
    ``application/tests/test_embedding_async_1401.py``, where the default
    rolled-back test transaction keeps the callback pending. In
    ``transaction=True`` mode the service's own atomic block is the outermost
    one, so its callbacks run as soon as the service returns.)
    """
    client = _client(api_env)

    with patch(_GENERATE) as provider, patch.object(embed_rows_task, "delay") as delay:
        resp = client.post(
            "/api/v1/requirements/",
            {"workspace_id": str(api_env["workspace"].id), "title": "No inline embed"},
            format="json",
        )

    assert resp.status_code == 201, resp.content
    provider.assert_not_called()
    delay.assert_called_once()
    assert delay.call_args.args[0] == "requirement"
    assert delay.call_args.args[2] == str(api_env["tenant"].id)

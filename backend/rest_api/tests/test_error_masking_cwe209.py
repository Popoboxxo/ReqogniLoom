"""Internal exception detail must never reach a REST client (CWE-209).

SYSTEMAUDIT-2026-08-27 finding B. ``rest_api.metrics_views`` and
``rest_api.icd_views`` each wrapped their endpoint bodies in a bare
``except Exception as exc`` and put ``str(exc)`` into the 500 response body.
On that path ``exc`` is by construction an exception no typed handler above
claimed — ``IntegrityError``, ``ProgrammingError``, a driver error — and its
``str()`` routinely carries SQL fragments, table and column names, constraint
names or connection details.

The policy these tests pin down is the one ``rest_api.views._service_error_response``
established for fix #108: forward the message only for explicitly mapped,
safe-to-surface exception types, and replace everything else with the canonical
localised message for the error code while the real detail goes to the log.

Deliberately free of a database: the fault is injected at the service boundary,
which is the only thing these endpoints do before the ``except`` block runs.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from django.db.utils import ProgrammingError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from rest_api.icd_views import IcdViewSet, _internal_error
from rest_api.metrics_views import MetricsViewSet

#: A message with the shape of a real leak: driver class, credentials, host,
#: schema names. Any of these reaching a client is the vulnerability.
SENSITIVE = (
    'ProgrammingError: relation "persistence_requirement" does not exist '
    'LINE 1: SELECT "persistence_requirement"."tenant_id" ... '
    '(host=db.internal user=reqogniloom_app)'
)

_CANONICAL_500 = "An internal server error occurred."


def _assert_masked(response, caplog) -> None:
    """The client got the canonical message; the operator got the real one."""
    assert response.status_code == 500
    assert response.data["error"]["code"] == "INTERNAL_SERVER_ERROR"
    assert response.data["error"]["message"] == _CANONICAL_500
    # Check the whole body, not just ``message``: smuggling the detail into
    # ``details`` would be the same leak wearing a different key.
    assert SENSITIVE not in str(response.data)
    assert SENSITIVE in caplog.text


class TestMetricsViewMasksInternalError:
    def test_compute_metrics_failure_is_masked_but_logged(self, caplog):
        # Wrapped in a DRF ``Request``: that is what a ViewSet method receives,
        # and the view reads ``query_params``, which the bare WSGI request the
        # factory returns does not have.
        request = Request(
            APIRequestFactory().get(f"/api/v1/metrics/?workspace_id={uuid.uuid4()}")
        )
        ctx = MagicMock(tenant_id=uuid.uuid4())

        with patch("rest_api.metrics_views.get_auth_context", return_value=ctx), patch(
            "rest_api.metrics_views.WorkspaceService"
        ), patch(
            "rest_api.metrics_views.compute_metrics",
            side_effect=ProgrammingError(SENSITIVE),
        ), caplog.at_level("ERROR"):
            response = MetricsViewSet().list(request)

        _assert_masked(response, caplog)


class TestIcdViewMasksInternalError:
    def test_unmapped_failure_is_masked_but_logged(self, caplog):
        """Exercised through a real endpoint, not just the helper.

        ``list`` is representative: every endpoint in ``icd_views`` funnels its
        unmapped failures into the same helper, so a regression in the wiring
        would show up here rather than in a helper-only test.
        """
        request = Request(
            APIRequestFactory().get(f"/api/v1/icds/?workspace_id={uuid.uuid4()}")
        )
        ctx = MagicMock(tenant_id=uuid.uuid4())

        with patch("rest_api.icd_views.get_auth_context", return_value=ctx), patch(
            "rest_api.icd_views.Icd"
        ) as icd_model, caplog.at_level("ERROR"):
            icd_model.objects.filter.side_effect = ProgrammingError(SENSITIVE)
            response = IcdViewSet().list(request)

        _assert_masked(response, caplog)

    def test_helper_requires_an_active_exception_context(self, caplog):
        """``_internal_error`` relies on ``sys.exc_info()`` for the traceback.

        Pinned because the helper looks callable from anywhere: called outside an
        ``except`` block it would still return a correct response but log no
        cause at all, silently turning every 500 into an unattributable one.
        """
        with caplog.at_level("ERROR"):
            try:
                raise ProgrammingError(SENSITIVE)
            except ProgrammingError:
                response = _internal_error("en", "list")

        _assert_masked(response, caplog)

    def test_german_client_gets_the_localised_canonical_message(self):
        """Masking must not silently drop i18n (REQ-L3-RA002-002)."""
        try:
            raise ProgrammingError(SENSITIVE)
        except ProgrammingError:
            response = _internal_error("de", "list")

        assert response.data["error"]["message"] == (
            "Ein interner Serverfehler ist aufgetreten."
        )
        assert SENSITIVE not in str(response.data)

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

import pytest
from django.db.utils import ProgrammingError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from rest_api.icd_views import IcdViewSet, _client_message, _internal_error
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

        SA-19: ``list()`` no longer queries ``Icd.objects`` directly — it
        delegates to ``icd.services.list_icds`` (ADR-01 facade) — so the
        failure is now injected at that seam instead of the ORM manager.
        """
        request = Request(
            APIRequestFactory().get(f"/api/v1/icds/?workspace_id={uuid.uuid4()}")
        )
        ctx = MagicMock(tenant_id=uuid.uuid4())

        with patch("rest_api.icd_views.get_auth_context", return_value=ctx), patch(
            "rest_api.icd_views.list_icds",
            side_effect=ProgrammingError(SENSITIVE),
        ), caplog.at_level("ERROR"):
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


# ---------------------------------------------------------------------------
# #697: the sweep must hold for *every* endpoint of the module, not only for
# the one (`list`) pinned above. Each endpoint funnels its unmapped failures
# into ``_internal_error`` through its own ``except`` clause, so a single
# mis-wired handler is enough to reintroduce the leak.
# ---------------------------------------------------------------------------

_ANY_ID = str(uuid.uuid4())

#: (endpoint id, HTTP method, view method name, extra kwargs)
_ICD_ENDPOINTS = (
    ("list", "get", "list", {}),
    ("create", "post", "create", {}),
    ("retrieve", "get", "retrieve", {"pk": _ANY_ID}),
    ("partial_update", "patch", "partial_update", {"pk": _ANY_ID}),
    ("destroy", "delete", "destroy", {"pk": _ANY_ID}),
    ("versions", "get", "versions", {"pk": _ANY_ID}),
    ("diff", "get", "diff", {"pk": _ANY_ID}),
    ("similar", "get", "similar", {"pk": _ANY_ID}),
    ("parameters", "get", "parameters", {"pk": _ANY_ID}),
    (
        "parameter_detail",
        "patch",
        "parameter_detail",
        {"pk": _ANY_ID, "parameter_id": _ANY_ID},
    ),
)


class TestEveryIcdEndpointMasksInternalError:
    """#697: the whole ``icd_views`` module, endpoint by endpoint.

    ``get_auth_context`` is the first call inside every endpoint's guarded
    block, so patching it to raise is the one injection point that reaches the
    shared masking helper from all of them without a database.
    """

    @pytest.mark.parametrize(
        "endpoint,http_method,view_method,kwargs",
        _ICD_ENDPOINTS,
        ids=[e[0] for e in _ICD_ENDPOINTS],
    )
    def test_endpoint_masks_unmapped_failure_but_logs_it(
        self, endpoint, http_method, view_method, kwargs, caplog
    ):
        factory = APIRequestFactory()
        request = Request(
            getattr(factory, http_method)(
                f"/api/v1/icds/{_ANY_ID}/?workspace_id={uuid.uuid4()}"
            )
        )

        with patch(
            "rest_api.icd_views.get_auth_context",
            side_effect=ProgrammingError(SENSITIVE),
        ), caplog.at_level("ERROR"):
            response = getattr(IcdViewSet(), view_method)(request, **kwargs)

        _assert_masked(response, caplog)

    def test_masking_helper_withholds_a_non_allow_listed_type(self, caplog):
        """The allow-list is consulted by exact type, not by message shape.

        A non-allow-listed type is withheld whatever its message says — so a
        future refactor cannot "optimise" this into a message-content check.
        """
        with caplog.at_level("ERROR"):
            try:
                raise ProgrammingError(SENSITIVE)
            except ProgrammingError as exc:
                assert _client_message(exc, "list") is None
        assert SENSITIVE in caplog.text

    def test_allow_listed_types_still_reach_the_client(self):
        """Control: masking must not blunt the #104 field-validation contract."""
        try:
            raise ValueError("title must not be empty")
        except ValueError as exc:
            assert _client_message(exc, "create") == "title must not be empty"


class TestGlobalWorkflowErrorMappingMasksUnmapped:
    """#697: ``_map_workflow_error``'s last branch is an unmapped exemption.

    The two ``isinstance`` branches above it forward domain-authored messages
    (safe); the fallback catches everything else — a driver error, a ``KeyError``
    — and used to hand its ``str()`` to the client under HTTP 500.
    """

    def test_unmapped_exception_is_masked_but_logged(self, caplog):
        from rest_api.global_default_views import _map_workflow_error

        # Called from inside an ``except`` block, like every real caller: the
        # helper's ``logger.exception`` reads the cause from ``sys.exc_info()``.
        with caplog.at_level("ERROR"):
            try:
                raise ProgrammingError(SENSITIVE)
            except ProgrammingError as exc:
                response = _map_workflow_error(exc, "en")

        assert response.status_code == 500
        assert response.data["error"]["code"] == "INTERNAL_SERVER_ERROR"
        assert response.data["error"]["message"] == _CANONICAL_500
        assert SENSITIVE not in str(response.data)
        assert SENSITIVE in caplog.text

    def test_domain_errors_still_forward_their_own_message(self):
        """Control: masking the fallback must not swallow the mapped branches."""
        from workflow.services import WorkflowDefinitionError

        from rest_api.global_default_views import _map_workflow_error

        response = _map_workflow_error(WorkflowDefinitionError("no initial state"), "en")

        assert response.status_code == 400
        assert response.data["error"]["message"] == "no initial state"

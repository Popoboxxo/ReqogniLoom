"""
Tests for COMP-RA-001 — IcdViewSet.create / partial_update error mapping.

leaf_id : COMP-RA-001
req_id  : REQ-L2-ICD-001, REQ-L2-ICD-002

Covers #104 (see docs/ANALYSE_SYSENG20_TESTBERICHT_FIXLISTE.md): IcdViewSet
builds the IcdCreateDTO/IcdUpdateDTO straight from request.data — there is no
DRF serializer in this path, so the only guard against unbounded free-text
(``semantic_description``) is ContractValidator.validate_syntax(), which
raises ValueError via icd.services.create_icd()/update_icd(). Before this
fix that ValueError fell through to the generic ``except Exception`` handler
and surfaced as an unhelpful HTTP 500. It must now map to a clean HTTP 400
(VALIDATION_ERROR), mirroring the CR-02 fix for DiagramViewSet
(test_diagram_crud_views.py).

All tests use mock services to avoid a database dependency, consistent with
rest_api/tests/test_diagram_crud_views.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

from rest_framework.test import APIRequestFactory

from rest_api.icd_views import IcdViewSet

FAKE_TENANT_ID = uuid.uuid4()
FAKE_USER_ID = uuid.uuid4()
FAKE_ICD_ID = uuid.uuid4()


def _make_auth_context() -> MagicMock:
    from auth_tenancy.context import AuthContext, AuthMethod

    return AuthContext(
        user_id=FAKE_USER_ID,
        tenant_id=FAKE_TENANT_ID,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


class TestIcdViewSetCreateValidation:
    """#104: syntax/size ValueError from create_icd() must surface as HTTP 400, not 500."""

    def test_create_with_oversized_semantic_description_returns_400(self) -> None:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/",
            data={
                "name": "My ICD",
                "workspace_id": str(uuid.uuid4()),
                "source_element_id": str(uuid.uuid4()),
                "target_element_id": str(uuid.uuid4()),
                "semantic_description": "A" * 10001,
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"post": "create"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_tenant"), patch("rest_api.icd_views.get_user"):
                with patch(
                    "rest_api.icd_views.create_icd",
                    side_effect=ValueError(
                        "ICD payload failed syntax validation: "
                        "[\"Field 'semantic_description' exceeds maximum length "
                        "of 10000 characters (got 10001)\"]"
                    ),
                ):
                    response = view(req)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "semantic_description" in response.data["error"]["message"]

    def test_create_success_still_returns_201(self) -> None:
        """Sanity check: a valid payload is unaffected by the new error mapping."""
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/",
            data={
                "name": "My ICD",
                "workspace_id": str(uuid.uuid4()),
                "source_element_id": str(uuid.uuid4()),
                "target_element_id": str(uuid.uuid4()),
                "semantic_description": "short",
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"post": "create"})

        fake_icd = MagicMock()
        fake_icd.id = FAKE_ICD_ID
        fake_icd.name = "My ICD"
        fake_icd.workspace_id = uuid.uuid4()
        fake_icd.source_element_id = uuid.uuid4()
        fake_icd.target_element_id = uuid.uuid4()
        fake_icd.created_at = None
        fake_result = MagicMock()
        fake_result.icd = fake_icd
        fake_result.current_version.version_number = 1

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_tenant"), patch("rest_api.icd_views.get_user"):
                with patch(
                    "rest_api.icd_views.create_icd", return_value=fake_result
                ):
                    response = view(req)

        assert response.status_code == 201
        assert response.data["name"] == "My ICD"

    def test_partial_update_oversized_semantic_description_returns_400(self) -> None:
        """PATCH with an oversized payload must also fail cleanly with 400."""
        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/icds/{FAKE_ICD_ID}/",
            data={"semantic_description": "A" * 10001},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"patch": "partial_update"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_user"):
                with patch(
                    "rest_api.icd_views.update_icd",
                    side_effect=ValueError(
                        "ICD update payload failed syntax validation: "
                        "[\"Field 'semantic_description' exceeds maximum length "
                        "of 10000 characters (got 10001)\"]"
                    ),
                ):
                    response = view(req, pk=str(FAKE_ICD_ID))

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "semantic_description" in response.data["error"]["message"]


class TestIcdViewSetErrorMessageMasking:
    """SA-03 / issue #697 (CWE-209): typed handlers must not forward arbitrary
    exception text.

    The P0 sweep (commit 2069e2e1) only covered this module's bare
    ``except Exception`` handlers via ``_internal_error``. The *typed* handlers
    kept doing ``message=str(exc)``, and ``except ValueError`` /
    ``except <Model>.DoesNotExist`` catch far more than the hand-authored
    domain errors they were written for — every ``ValueError`` subclass raised
    anywhere inside the handler body lands there too.

    The rule is now an explicit exact-type allow-list (``_CLIENT_SAFE_EXCEPTIONS``),
    so these tests pin both halves of it: authored domain messages still reach
    the client (the #104 contract above depends on that), foreign ones do not.
    """

    def _similar_request(self):
        factory = APIRequestFactory()
        req = factory.get(f"/api/v1/icds/{FAKE_ICD_ID}/similar/")
        req.auth_context = _make_auth_context()
        return req

    def _call_similar(self, side_effect):
        req = self._similar_request()
        view = IcdViewSet.as_view({"get": "similar"})
        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch(
                "rest_api.icd_views.find_similar_icds", side_effect=side_effect
            ):
                return view(req, pk=str(FAKE_ICD_ID))

    def test_authored_value_error_is_still_forwarded(self) -> None:
        """The allow-list must not regress the #104 validation-feedback contract."""
        response = self._call_similar(
            ValueError("ICD has no embedding — similarity search not possible")
        )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "no embedding" in response.data["error"]["message"]

    def test_value_error_subclass_is_masked(self) -> None:
        """A ValueError *subclass* is not a domain error — mask it.

        ``json.JSONDecodeError`` is the realistic case: it carries the raw
        document it failed on.
        """
        import json

        response = self._call_similar(
            json.JSONDecodeError("Expecting value", '{"secret": "internal"}', 0)
        )

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        assert "secret" not in response.data["error"]["message"]
        assert "Expecting value" not in response.data["error"]["message"]

    def test_pgvector_unavailable_message_is_masked(self) -> None:
        """503 must not name the backing technology (CWE-209).

        Status code and error code are unchanged — only the free-text detail is
        withheld, so clients keying off ``error.code`` are unaffected.
        """
        from icd.services import IcdPgVectorUnavailableError

        response = self._call_similar(
            IcdPgVectorUnavailableError(
                "pgvector extension not available — similarity search unavailable"
            )
        )

        assert response.status_code == 503
        assert response.data["error"]["code"] == "SERVICE_UNAVAILABLE"
        assert "pgvector" not in response.data["error"]["message"].lower()


class TestIcdViewSetFreeTextSanitization:
    """SA-20: IcdViewSet now inherits BaseEntityViewSet, so
    FreeTextSanitizationMixin.initial() must reject HTML markup in ICD's
    narrative fields *before* create()/partial_update() run — the same
    guarantee every other entity ViewSet already has (#269 finding 4).
    ``free_text_extra_fields`` is used (rather than a serializer_class)
    because Icd has no dedicated DRF serializer (create()/partial_update()
    hand-build IcdCreateDTO/IcdUpdateDTO).
    """

    _PAYLOAD = "<img src=x onerror=alert(1)>"

    def test_create_rejects_html_markup_in_name(self) -> None:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/",
            data={
                "name": self._PAYLOAD,
                "workspace_id": str(uuid.uuid4()),
                "source_element_id": str(uuid.uuid4()),
                "target_element_id": str(uuid.uuid4()),
                "semantic_description": "harmless",
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"post": "create"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            # create_icd is deliberately NOT given a happy-path return: the
            # guard runs in initial(), before create() is even entered, so a
            # reached create_icd call would prove the bug, not the fix.
            with patch(
                "rest_api.icd_views.create_icd",
                side_effect=AssertionError(
                    "create_icd must not be reached — the free-text guard "
                    "should have rejected the request in initial()"
                ),
            ):
                response = view(req)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_create_rejects_html_markup_in_semantic_description(self) -> None:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/",
            data={
                "name": "My ICD",
                "workspace_id": str(uuid.uuid4()),
                "source_element_id": str(uuid.uuid4()),
                "target_element_id": str(uuid.uuid4()),
                "semantic_description": self._PAYLOAD,
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"post": "create"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch(
                "rest_api.icd_views.create_icd",
                side_effect=AssertionError(
                    "create_icd must not be reached — the free-text guard "
                    "should have rejected the request in initial()"
                ),
            ):
                response = view(req)

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_partial_update_rejects_html_markup_in_semantic_description(self) -> None:
        factory = APIRequestFactory()
        req = factory.patch(
            f"/api/v1/icds/{FAKE_ICD_ID}/",
            data={"semantic_description": self._PAYLOAD},
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"patch": "partial_update"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch(
                "rest_api.icd_views.update_icd",
                side_effect=AssertionError(
                    "update_icd must not be reached — the free-text guard "
                    "should have rejected the request in initial()"
                ),
            ):
                response = view(req, pk=str(FAKE_ICD_ID))

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"

    def test_create_with_clean_fields_is_unaffected(self) -> None:
        """No-regression: benign narrative fields still pass the guard."""
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/",
            data={
                "name": "My ICD",
                "workspace_id": str(uuid.uuid4()),
                "source_element_id": str(uuid.uuid4()),
                "target_element_id": str(uuid.uuid4()),
                "semantic_description": "short",
            },
            format="json",
        )
        req.auth_context = _make_auth_context()

        view = IcdViewSet.as_view({"post": "create"})

        fake_icd = MagicMock()
        fake_icd.id = FAKE_ICD_ID
        fake_icd.name = "My ICD"
        fake_icd.workspace_id = uuid.uuid4()
        fake_icd.source_element_id = uuid.uuid4()
        fake_icd.target_element_id = uuid.uuid4()
        fake_icd.created_at = None
        fake_result = MagicMock()
        fake_result.icd = fake_icd
        fake_result.current_version.version_number = 1

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_tenant"), patch("rest_api.icd_views.get_user"):
                with patch(
                    "rest_api.icd_views.create_icd", return_value=fake_result
                ):
                    response = view(req)

        assert response.status_code == 201


# ---------------------------------------------------------------------------
# Task 28c-2: the ?version= contract on the parameters endpoints
# ---------------------------------------------------------------------------


class TestParametersVersionParam:
    """Pins the ``?version=`` decision Task 28c-2 had to make.

    ``IcdParameter`` became current-state-only, so ``?version=`` no longer
    selects a live row set. It is honoured from the recorded
    ``parameters_snapshot`` rather than ignored, because ignoring it would
    answer a question about revision N with revision "current"'s data — see
    the module docstring of ``rest_api.icd_views``.
    """

    def _icd(self, current_revision: int = 2):
        from icd.models import Icd

        icd = MagicMock(spec=Icd)
        icd.id = FAKE_ICD_ID
        icd.tenant_id = FAKE_TENANT_ID
        icd.current_revision = current_revision
        return icd

    def _get(self, version: str | None):
        factory = APIRequestFactory()
        path = "/api/v1/icds/%s/parameters/" % FAKE_ICD_ID
        if version is not None:
            path += "?version=%s" % version
        req = factory.get(path)
        req.auth_context = _make_auth_context()
        return req

    def _call_get(self, version, icd, *, history=None, live=()):
        from icd.models import IcdRevision

        view = IcdViewSet.as_view({"get": "parameters"})
        req = self._get(version)
        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_icd", return_value=icd):
                with patch(
                    "rest_api.icd_views.IcdRevision.from_icd",
                    return_value=IcdRevision(
                        icd_id=icd.id, version_number=icd.current_revision
                    ),
                ):
                    with patch(
                        "rest_api.icd_views.get_icd_history",
                        return_value=history or [],
                    ):
                        with patch(
                            "rest_api.icd_views.list_icd_parameters",
                            return_value=list(live),
                        ):
                            return view(req, pk=str(FAKE_ICD_ID))

    def test_current_revision_serves_the_live_rows(self) -> None:
        param = MagicMock()
        param.id = uuid.uuid4()
        param.icd_id = FAKE_ICD_ID
        param.name = "voltage"
        param.description = ""
        param.unit = "V"
        param.data_type = "float"
        param.direction = "input"
        param.min_value = None
        param.max_value = None
        param.nominal_value = ""
        param.tolerance = ""
        param.ordering = 0
        param.created_at = None
        param.modified_at = None

        response = self._call_get(None, self._icd(), live=[param])

        assert response.status_code == 200
        body = response.data["results"] if "results" in response.data else response.data
        assert [p["name"] for p in body] == ["voltage"]
        assert body[0]["id"] == str(param.id)

    def test_historical_revision_serves_the_recorded_snapshot(self) -> None:
        from icd.models import IcdRevision

        historical = IcdRevision(
            icd_id=FAKE_ICD_ID,
            version_number=1,
            parameters_snapshot=[{"name": "voltage", "unit": "V", "ordering": 0}],
            parameters_captured=True,
        )

        response = self._call_get("1", self._icd(), history=[historical])

        assert response.status_code == 200
        body = response.data["results"] if "results" in response.data else response.data
        assert [p["name"] for p in body] == ["voltage"]
        # A snapshot entry is a recorded value, not an addressable row.
        assert body[0]["id"] is None

    def test_revision_without_a_recorded_snapshot_is_404_not_an_empty_list(self) -> None:
        """A revision written before the cut-over never captured its parameter
        set; answering ``[]`` would be a confident wrong answer."""
        from icd.models import IcdRevision

        historical = IcdRevision(
            icd_id=FAKE_ICD_ID, version_number=1, parameters_captured=False
        )

        response = self._call_get("1", self._icd(), history=[historical])

        assert response.status_code == 404

    def test_unknown_revision_is_404(self) -> None:
        response = self._call_get("99", self._icd(), history=[])

        assert response.status_code == 404

    def test_non_integer_version_is_400_not_500(self) -> None:
        response = self._call_get("not-a-number", self._icd())

        assert response.status_code == 400

    def test_post_to_a_historical_revision_is_rejected(self) -> None:
        factory = APIRequestFactory()
        req = factory.post(
            "/api/v1/icds/%s/parameters/" % FAKE_ICD_ID,
            data={"name": "voltage", "version": 1},
            format="json",
        )
        req.auth_context = _make_auth_context()
        view = IcdViewSet.as_view({"post": "parameters"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_icd", return_value=self._icd()):
                with patch("rest_api.icd_views.create_icd_parameter") as create:
                    response = view(req, pk=str(FAKE_ICD_ID))

        assert response.status_code == 400
        assert response.data["error"]["code"] == "VALIDATION_ERROR"
        create.assert_not_called()


# ---------------------------------------------------------------------------
# Datenmodell-Konsolidierung Task 29 (Milestone M5): versions/diff unified
# onto the generic ArtifactDiffService, replacing the hand-rolled dispatch
# against icd.services.get_icd_history / a fixed six-field DBC comparison.
# ---------------------------------------------------------------------------


class TestIcdViewSetVersionsAndDiff:
    def _icd(self, artifact_id=None, current_revision: int = 2):
        from icd.models import Icd

        icd = MagicMock(spec=Icd)
        icd.id = FAKE_ICD_ID
        icd.tenant_id = FAKE_TENANT_ID
        icd.artifact_id = artifact_id or uuid.uuid4()
        icd.current_revision = current_revision
        return icd

    def test_versions_delegates_to_the_generic_service(self) -> None:
        factory = APIRequestFactory()
        req = factory.get("/api/v1/icds/%s/versions/" % FAKE_ICD_ID)
        req.auth_context = _make_auth_context()

        icd = self._icd()
        expected = [{"version": 0, "label": "Creation baseline"}]

        view = IcdViewSet.as_view({"get": "versions"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_icd", return_value=icd):
                with patch("rest_api.icd_views.ArtifactDiffService") as svc_cls:
                    svc_cls.return_value.list_versions.return_value = expected
                    response = view(req, pk=str(FAKE_ICD_ID))

        assert response.status_code == 200
        assert response.data == expected
        svc_cls.return_value.list_versions.assert_called_once_with(
            icd.artifact_id, req.auth_context
        )

    def test_diff_delegates_to_the_generic_service(self) -> None:
        factory = APIRequestFactory()
        req = factory.get(
            "/api/v1/icds/%s/diff/?from_version=1&to_version=2" % FAKE_ICD_ID
        )
        req.query_params = {"from_version": "1", "to_version": "2"}
        req.auth_context = _make_auth_context()

        icd = self._icd()
        diff_result = {
            "from_version": 1,
            "to_version": 2,
            "entity_type": "Icd",
            "fields": [
                {"name": "name", "status": "unchanged", "from": "x", "to": "x"}
            ],
        }

        view = IcdViewSet.as_view({"get": "diff"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_icd", return_value=icd):
                with patch("rest_api.icd_views.ArtifactDiffService") as svc_cls:
                    svc_cls.return_value.diff.return_value = diff_result
                    response = view(req, pk=str(FAKE_ICD_ID))

        assert response.status_code == 200
        assert response.data == diff_result
        svc_cls.return_value.diff.assert_called_once_with(
            artifact_id=icd.artifact_id,
            from_version=1,
            to_version=2,
            ctx=req.auth_context,
        )

    def test_diff_returns_404_when_service_raises_not_found(self) -> None:
        from application.base import NotFoundError

        factory = APIRequestFactory()
        req = factory.get("/api/v1/icds/%s/diff/" % FAKE_ICD_ID)
        req.query_params = {}
        req.auth_context = _make_auth_context()

        icd = self._icd()

        view = IcdViewSet.as_view({"get": "diff"})

        with patch(
            "rest_api.icd_views.get_auth_context", return_value=req.auth_context
        ):
            with patch("rest_api.icd_views.get_icd", return_value=icd):
                with patch("rest_api.icd_views.ArtifactDiffService") as svc_cls:
                    svc_cls.return_value.diff.side_effect = NotFoundError(
                        "Version 99 not available"
                    )
                    response = view(req, pk=str(FAKE_ICD_ID))

        assert response.status_code == 404

"""
Tests for COMP-AS-014 RiskService.

leaf_id : COMP-AS-014
req_id  : REQ-L1-029, REQ-L3-RISK-001..010

Static tests (no DB): CRUD, score calculation, severity derivation,
query_risks_by_severity (SeMetrics contract), workflow init, TraceLink,
audit entry, event emission, tenant isolation.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from application.base import NotFoundError, PermissionDeniedError, ValidationError
from application.risk_service import RiskService, RiskDTO, RiskValidator, RISK_LINK_TYPES
from application.models import Risk

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx(*, roles=("editor",), tenant_id=None, user_id=None):
    ctx = MagicMock()
    ctx.active_roles = roles
    ctx.tenant_id = tenant_id or uuid.uuid4()
    ctx.user_id = user_id or uuid.uuid4()
    ctx.has_role = lambda role: role in roles
    return ctx


WS_ID = uuid.uuid4()
RISK_ID = uuid.uuid4()
TENANT_ID = uuid.uuid4()


def _make_risk(**kwargs):
    risk = MagicMock(spec=Risk)
    risk.id = kwargs.get("id", RISK_ID)
    risk.workspace_id = kwargs.get("workspace_id", WS_ID)
    risk.tenant_id = kwargs.get("tenant_id", TENANT_ID)
    risk.title = kwargs.get("title", "Data breach")
    risk.description = kwargs.get("description", "Sensitive data exposure")
    risk.category = kwargs.get("category", "technical")
    risk.probability = kwargs.get("probability", "high")
    risk.impact = kwargs.get("impact", "high")
    risk.risk_score = kwargs.get("risk_score", 9)
    risk.severity = kwargs.get("severity", "high")
    risk.owner = kwargs.get("owner", "")
    risk.mitigation_strategy = kwargs.get("mitigation_strategy", "")
    risk.status = kwargs.get("status", "Identified")
    risk.version = kwargs.get("version", 1)
    # Real compute_score / score_to_severity from model class
    risk.compute_score = lambda: risk.risk_score
    return risk


# ---------------------------------------------------------------------------
# Risk model helpers (pure unit tests — no DB)
# ---------------------------------------------------------------------------


class TestRiskScoreCalculation:
    """Tests for Risk.compute_score and Risk.score_to_severity (REQ-L3-RISK-007)."""

    def test_low_low_score_is_1(self):
        r = Risk()
        r.probability = "low"
        r.impact = "low"
        assert r.compute_score() == 1

    def test_high_high_score_is_9(self):
        r = Risk()
        r.probability = "high"
        r.impact = "high"
        assert r.compute_score() == 9

    def test_medium_medium_score_is_4(self):
        r = Risk()
        r.probability = "medium"
        r.impact = "medium"
        assert r.compute_score() == 4

    def test_score_to_severity_low(self):
        assert Risk.score_to_severity(1) == "low"
        assert Risk.score_to_severity(3) == "low"

    def test_score_to_severity_medium(self):
        assert Risk.score_to_severity(4) == "medium"
        assert Risk.score_to_severity(8) == "medium"

    def test_score_to_severity_high(self):
        assert Risk.score_to_severity(9) == "high"


# ---------------------------------------------------------------------------
# RiskValidator
# ---------------------------------------------------------------------------


class TestRiskValidator:
    def test_valid_create_passes(self):
        RiskValidator.validate_create(
            title="DB failure risk", probability="high", impact="medium"
        )

    def test_empty_title_raises(self):
        with pytest.raises(ValidationError, match="required"):
            RiskValidator.validate_create(title="", probability="low", impact="low")

    def test_invalid_probability_raises(self):
        with pytest.raises(ValidationError, match="probability"):
            RiskValidator.validate_create(
                title="Risk", probability="extreme", impact="low"
            )

    def test_invalid_impact_raises(self):
        with pytest.raises(ValidationError, match="impact"):
            RiskValidator.validate_create(
                title="Risk", probability="low", impact="catastrophic"
            )

    def test_invalid_category_raises(self):
        with pytest.raises(ValidationError, match="category"):
            RiskValidator.validate_create(
                title="Risk", probability="low", impact="low", category="unknown"
            )

    def test_all_probability_values_valid(self):
        for p in Risk.Probability.values:
            RiskValidator.validate_create(title="Risk", probability=p, impact="low")

    def test_all_impact_values_valid(self):
        for i in Risk.Impact.values:
            RiskValidator.validate_create(title="Risk", probability="low", impact=i)


# ---------------------------------------------------------------------------
# RiskDTO
# ---------------------------------------------------------------------------


class TestRiskDTO:
    def test_from_orm_maps_all_fields(self):
        risk = _make_risk()
        dto = RiskDTO.from_orm(risk)
        assert dto.id == risk.id
        assert dto.risk_score == risk.risk_score
        assert dto.severity == risk.severity
        assert dto.probability == risk.probability
        assert dto.impact == risk.impact


# ---------------------------------------------------------------------------
# create_risk
# ---------------------------------------------------------------------------


class TestCreateRisk:
    def test_creates_risk_with_correct_score(self):
        """create_risk sets risk_score and severity before save."""
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        # Real Risk instance to test score calculation path
        real_risk = Risk()
        real_risk.probability = "high"
        real_risk.impact = "high"
        real_risk.id = RISK_ID
        real_risk.workspace_id = WS_ID

        with (
            patch("application.risk_service.Risk") as mock_risk_cls,
            patch("application.risk_service.RiskService._set_tenant_context"),
            patch("application.risk_service.RiskService._assert_write_permission"),
            patch("application.risk_service.RiskService._audit"),
            patch("application.risk_service.RiskService._emit_event"),
            patch("application.risk_service.RiskService._make_event", return_value=MagicMock()),
            patch("workflow.services.initialize_workflow_states"),
        ):
            mock_instance = MagicMock()
            mock_instance.probability = "high"
            mock_instance.impact = "high"
            mock_instance.id = RISK_ID
            mock_instance.workspace_id = WS_ID
            mock_instance.compute_score.return_value = 9
            mock_risk_cls.return_value = mock_instance
            mock_risk_cls.score_to_severity = Risk.score_to_severity

            result = svc.create_risk(
                workspace_id=WS_ID,
                title="Critical infrastructure risk",
                probability="high",
                impact="high",
                ctx=ctx,
            )

        # score and severity should be set
        assert mock_instance.risk_score == 9
        assert mock_instance.severity == "high"
        mock_instance.save.assert_called_once()

    def test_viewer_cannot_create(self):
        svc = RiskService()
        ctx = _make_ctx(roles=("viewer",))
        with pytest.raises(PermissionDeniedError):
            svc.create_risk(
                workspace_id=WS_ID,
                title="Risk",
                probability="low",
                impact="low",
                ctx=ctx,
            )

    def test_workflow_init_failure_does_not_abort(self):
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.risk_service.Risk") as mock_risk_cls,
            patch("application.risk_service.RiskService._set_tenant_context"),
            patch("application.risk_service.RiskService._assert_write_permission"),
            patch("application.risk_service.RiskService._audit"),
            patch("application.risk_service.RiskService._emit_event"),
            patch("application.risk_service.RiskService._make_event", return_value=MagicMock()),
            patch(
                "workflow.services.initialize_workflow_states",
                side_effect=RuntimeError("no workflow"),
            ),
        ):
            mock_instance = MagicMock()
            mock_instance.probability = "low"
            mock_instance.impact = "low"
            mock_instance.id = RISK_ID
            mock_instance.workspace_id = WS_ID
            mock_instance.compute_score.return_value = 1
            mock_risk_cls.return_value = mock_instance
            mock_risk_cls.score_to_severity = Risk.score_to_severity

            result = svc.create_risk(
                workspace_id=WS_ID,
                title="Risk",
                probability="low",
                impact="low",
                ctx=ctx,
            )

        assert result is mock_instance

    def test_audit_entry_written_on_create(self):
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.risk_service.Risk") as mock_risk_cls,
            patch("application.risk_service.RiskService._set_tenant_context"),
            patch("application.risk_service.RiskService._assert_write_permission"),
            patch("application.risk_service.RiskService._audit") as mock_audit,
            patch("application.risk_service.RiskService._emit_event"),
            patch("application.risk_service.RiskService._make_event", return_value=MagicMock()),
            patch("workflow.services.initialize_workflow_states"),
        ):
            mock_instance = MagicMock()
            mock_instance.probability = "low"
            mock_instance.impact = "low"
            mock_instance.id = RISK_ID
            mock_instance.workspace_id = WS_ID
            mock_instance.compute_score.return_value = 1
            mock_risk_cls.return_value = mock_instance
            mock_risk_cls.score_to_severity = Risk.score_to_severity

            svc.create_risk(
                workspace_id=WS_ID,
                title="Audit test risk",
                probability="low",
                impact="low",
                ctx=ctx,
            )

        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["operation"] == "create"
        assert mock_audit.call_args.kwargs["entity_type"] == "Risk"


# ---------------------------------------------------------------------------
# update_risk
# ---------------------------------------------------------------------------


class TestUpdateRisk:
    def test_score_recalculated_on_probability_change(self):
        """Updating probability triggers score and severity recalculation."""
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing = _make_risk(probability="low", impact="low", risk_score=1, severity="low", version=1)
        existing.save = MagicMock()
        # Make compute_score delegate to actual logic
        existing.compute_score = lambda: Risk._PROB_NUMERIC.get(existing.probability, 1) * Risk._IMPACT_NUMERIC.get(existing.impact, 1)

        with (
            patch("application.risk_service.Risk.objects") as mock_mgr,
            patch("application.risk_service.Risk.score_to_severity", side_effect=Risk.score_to_severity),
            patch("application.risk_service.RiskService._set_tenant_context"),
            patch("application.risk_service.RiskService._assert_write_permission"),
            patch("application.risk_service.RiskService._audit"),
            patch("application.risk_service.RiskService._emit_event"),
            patch("application.risk_service.RiskService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing
            result = svc.update_risk(risk_id=RISK_ID, ctx=ctx, probability="high")

        assert result.probability == "high"
        assert result.risk_score == 3  # high(3) × low(1)
        assert result.severity == "low"  # 3 < 4 → low

    def test_not_found_raises(self):
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.risk_service.Risk.objects") as mock_mgr,
            patch("application.risk_service.RiskService._set_tenant_context"),
            patch("application.risk_service.RiskService._assert_write_permission"),
        ):
            mock_mgr.filter.return_value.first.return_value = None
            with pytest.raises(NotFoundError):
                svc.update_risk(risk_id=RISK_ID, ctx=ctx)


# ---------------------------------------------------------------------------
# delete_risk
# ---------------------------------------------------------------------------


class TestDeleteRisk:
    def test_cascades_tracelinks_and_deletes(self):
        mock_tls = MagicMock()
        svc = RiskService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        existing = _make_risk()

        with (
            patch("application.risk_service.Risk.objects") as mock_mgr,
            patch("application.risk_service.RiskService._set_tenant_context"),
            patch("application.risk_service.RiskService._assert_write_permission"),
            patch("application.risk_service.RiskService._audit"),
            patch("application.risk_service.RiskService._emit_event"),
            patch("application.risk_service.RiskService._make_event", return_value=MagicMock()),
        ):
            mock_mgr.filter.return_value.first.return_value = existing
            svc.delete_risk(risk_id=RISK_ID, ctx=ctx)

        mock_tls.cascade_delete_trace_links.assert_called_once_with(RISK_ID, ctx)
        existing.delete.assert_called_once()


# ---------------------------------------------------------------------------
# query_risks_by_severity — SeMetrics contract
# ---------------------------------------------------------------------------


class TestQueryRisksBySeverity:
    """Tests for the SeMetrics integration contract (ADR-L3-RISK-03).

    Stable signature: query_risks_by_severity(workspace_id, severity, ctx) -> List[Risk]
    """

    def test_filters_by_severity_high(self):
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)
        high_risks = [_make_risk(severity="high"), _make_risk(severity="high")]

        with (
            patch("application.risk_service.Risk.objects") as mock_mgr,
            patch("application.risk_service.RiskService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.order_by.return_value = high_risks
            result = svc.query_risks_by_severity(WS_ID, "high", ctx)

        mock_mgr.filter.assert_called_once_with(
            workspace_id=WS_ID,
            tenant_id=ctx.tenant_id,
            severity="high",
        )
        assert result == high_risks

    def test_filters_by_severity_medium(self):
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        with (
            patch("application.risk_service.Risk.objects") as mock_mgr,
            patch("application.risk_service.RiskService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.order_by.return_value = []
            result = svc.query_risks_by_severity(WS_ID, "medium", ctx)

        mock_mgr.filter.assert_called_once_with(
            workspace_id=WS_ID,
            tenant_id=ctx.tenant_id,
            severity="medium",
        )
        assert result == []

    def test_invalid_severity_raises_validation_error(self):
        """Non-enum severity value raises ValidationError."""
        svc = RiskService()
        ctx = _make_ctx()

        with (
            patch("application.risk_service.RiskService._set_tenant_context"),
        ):
            with pytest.raises(ValidationError, match="Invalid severity"):
                svc.query_risks_by_severity(WS_ID, "critical", ctx)

    def test_all_valid_severity_values_pass(self):
        svc = RiskService()
        ctx = _make_ctx(tenant_id=TENANT_ID)

        for severity in Risk.Severity.values:
            with (
                patch("application.risk_service.Risk.objects") as mock_mgr,
                patch("application.risk_service.RiskService._set_tenant_context"),
            ):
                mock_mgr.filter.return_value.order_by.return_value = []
                result = svc.query_risks_by_severity(WS_ID, severity, ctx)
                assert isinstance(result, list)

    def test_tenant_isolation_in_severity_query(self):
        """query_risks_by_severity always filters by tenant_id (REQ-L3-RISK-008)."""
        svc = RiskService()
        tenant_a = uuid.uuid4()
        tenant_b = uuid.uuid4()
        ctx_a = _make_ctx(tenant_id=tenant_a)
        ctx_b = _make_ctx(tenant_id=tenant_b)

        with (
            patch("application.risk_service.Risk.objects") as mock_mgr,
            patch("application.risk_service.RiskService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.order_by.return_value = []
            svc.query_risks_by_severity(WS_ID, "high", ctx_a)
            svc.query_risks_by_severity(WS_ID, "high", ctx_b)

        calls = mock_mgr.filter.call_args_list
        assert calls[0].kwargs["tenant_id"] == tenant_a
        assert calls[1].kwargs["tenant_id"] == tenant_b


# ---------------------------------------------------------------------------
# create_tracelink
# ---------------------------------------------------------------------------


class TestRiskCreateTracelink:
    def test_valid_link_type_delegates(self):
        mock_tls = MagicMock()
        mock_tls.create_trace_link.return_value = MagicMock()
        svc = RiskService(trace_link_service=mock_tls)
        ctx = _make_ctx(tenant_id=TENANT_ID)
        target_id = uuid.uuid4()

        with (
            patch("application.risk_service.Risk.objects") as mock_mgr,
            patch("application.risk_service.RiskService._set_tenant_context"),
        ):
            mock_mgr.filter.return_value.first.return_value = _make_risk()
            svc.create_tracelink(
                risk_id=RISK_ID,
                target_id=target_id,
                link_type="threatens",
                ctx=ctx,
            )

        mock_tls.create_trace_link.assert_called_once_with(
            source_id=RISK_ID,
            target_id=target_id,
            link_type="threatens",
            ctx=ctx,
        )

    def test_invalid_link_type_raises(self):
        svc = RiskService()
        ctx = _make_ctx()

        with patch("application.risk_service.RiskService._set_tenant_context"):
            with pytest.raises(ValidationError, match="Invalid Risk link type"):
                svc.create_tracelink(
                    risk_id=RISK_ID,
                    target_id=uuid.uuid4(),
                    link_type="addresses",  # ADR-type, invalid here
                    ctx=ctx,
                )

    def test_all_valid_link_types(self):
        for lt in RISK_LINK_TYPES:
            mock_tls = MagicMock()
            mock_tls.create_trace_link.return_value = MagicMock()
            svc = RiskService(trace_link_service=mock_tls)
            ctx = _make_ctx(tenant_id=TENANT_ID)

            with (
                patch("application.risk_service.Risk.objects") as mock_mgr,
                patch("application.risk_service.RiskService._set_tenant_context"),
            ):
                mock_mgr.filter.return_value.first.return_value = _make_risk()
                svc.create_tracelink(
                    risk_id=RISK_ID,
                    target_id=uuid.uuid4(),
                    link_type=lt,
                    ctx=ctx,
                )

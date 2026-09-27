"""SE-rule vocabulary collapse onto the audit registry (ADR-007, issue #19).

Three vocabularies used to coexist and reference each other, which is why #19
stayed open: the work was never missing, the *decision* about which vocabulary is
authoritative was. A second, purely documented set of rule ids named obligations
that this registry already implemented, and one documented id named an obligation
for a field that nothing in the codebase can fill. ADR-007 closed that:

  * the allocation obligation is carried by ``TRACE-P2`` (WARNING at every tier);
  * the test-link obligation is carried by ``TRACE-P6`` + ``VERIF-P8``;
  * ``source`` is a coverage convention, deliberately not a rule;
  * relation rules are enforced at the baseline gate, never at create/update.

This module pins the parts of that decision that can silently regress. It is
deliberately a *decision* net, not a re-implementation of the rules' behaviour:
the rules themselves are covered by the sibling rule-module tests.

Note on the create/update half: the regression guard for "``mandatory_fields``
must not re-enter the create gate" needs a REST surface and therefore lives in
``rest_api/tests/test_audit_adr007_create_gate_scope.py``. What is pinned here is
the code-side counterpart — the baseline gate stays the only blocking producer,
so there is nothing a future create/update gate could call.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from traceability.audit import RuleEngine
from traceability.audit.registry import TRACE_P2, TRACE_P6, VERIF_P8
from traceability.audit.types import Severity
from traceability.tests.conftest import (
    active_tenant,
    make_requirement,
    make_test_case,
    make_trace_link,
)

#: The second, documented-only rule vocabulary retired by ADR-007. Three of these
#: were mapped onto existing registry rules and deleted from the documentation; two
#: had no implementation and no code occurrence at all, anywhere in the repo, and
#: are simply gone. None of them may reappear in the audit package or in the SE
#: documentation: a rewritten id is a fourth vocabulary waiting to happen.
RETIRED_RULE_IDS = (
    "REQ_MUST_HAVE_SOURCE",
    "REQ_MUST_HAVE_ALLOCATION",
    "REQ_MUST_HAVE_TEST_LINK",
    "REQ_MUST_BE_ATOMIC",
    "NO_ORPHAN_TRACE_LINKS",
)

#: Where the sources this file guards actually live, in BOTH topologies the suite
#: runs in. Guessing one layout is what would make these guards inert:
#:
#: * on a host / in CI checkout this file is at ``<repo>/backend/traceability/tests/``,
#:   so the backend root is ``parents[2]`` and ``docs/`` sits at ``parents[3]``;
#: * in the ``backend-test`` container ``./backend`` is bind-mounted at ``/app``, so
#:   the backend root is ``/app`` (``parents[2]``) and the repository's ``docs/`` is
#:   bind-mounted alongside it at ``/app/docs`` -- *not* at ``/app/../docs``.
#:
#: A fixed ``parents[3]`` resolves to ``/`` in the container and skips four of the
#: guards silently, which is worse than not having them: the file would look green.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]
_AUDIT_PACKAGE = _BACKEND_ROOT / "traceability" / "audit"


def _se_docs() -> Path | None:
    for candidate in (_BACKEND_ROOT / "docs" / "se", _BACKEND_ROOT.parent / "docs" / "se"):
        if candidate.is_dir():
            return candidate
    return None


_SE_DOCS = _se_docs()

#: ADR files are the decision record: they have to name the ids they retired, or
#: the decision would be unreadable. They are the one place under ``docs/se/`` where
#: a retired id is legitimate, so they are excluded from the documentation scan.
_ADR_DIR_NAME = "ADR"


def _python_sources(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if p.is_file())


def _markdown_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p.is_file())


def _offenders(paths: list[Path], needle: str) -> list[str]:
    hits = []
    for path in paths:
        if needle in path.read_text(encoding="utf-8", errors="replace"):
            # Relative to the *scanned* tree's parent, not to a repo root: the
            # container mounts backend/ and docs/ side by side, so a repo root
            # does not exist there to be relative to.
            try:
                shown = str(path.relative_to(_BACKEND_ROOT))
            except ValueError:
                shown = str(path)
            hits.append(shown.replace("\\", "/"))
    return hits


def _run(tier, workspace, tenant):
    return RuleEngine().run(
        tier=tier, workspace_id=str(workspace.id), tenant_id=str(tenant.id)
    )


def _findings(result, rule_id):
    return [f for f in result.findings if f.rule_id == rule_id]


# ---------------------------------------------------------------------------
# The retired vocabulary is gone from the code
# ---------------------------------------------------------------------------


class TestRetiredVocabularyIsAbsentFromTheAuditPackage:
    def test_audit_package_carries_no_retired_rule_id(self) -> None:
        """The registry must speak in registry ids only.

        Whoever reads ``registry.py`` while adding a rule must not be able to
        conclude from a second, documented name that the obligation still needs
        implementing somewhere else.
        """
        if not _AUDIT_PACKAGE.is_dir():
            pytest.skip("backend sources are not mounted in the backend test image")

        sources = _python_sources(_AUDIT_PACKAGE)
        assert sources, _AUDIT_PACKAGE
        for retired in RETIRED_RULE_IDS:
            assert _offenders(sources, retired) == [], retired

    def test_registry_documents_the_baseline_gate_as_the_enforcement_point(self) -> None:
        """The answer to "where do I enforce this?" must live in registry.py.

        This is the one file every rule author reads before writing a rule
        (module docstring, "Adding a new rule" guide), so the enforcement point
        and the refuted alternative are recorded there rather than only in a
        decision record nobody opens mid-task.
        """
        registry = _AUDIT_PACKAGE / "registry.py"
        if not registry.is_file():
            pytest.skip("registry.py is not mounted in the backend test image")

        text = registry.read_text(encoding="utf-8")
        assert "application/baseline_facade.py" in text
        assert "blocking_findings" in text
        assert "0005_relax_requirement_create_required" in text


# ---------------------------------------------------------------------------
# The retired vocabulary is gone from the SE documentation
# ---------------------------------------------------------------------------


class TestRetiredVocabularyIsAbsentFromTheSeDocumentation:
    def test_no_se_doc_except_adrs_names_a_retired_rule_id(self) -> None:
        """``docs/se/`` must not name a retired rule id outside the ADRs.

        The attribute documents are where the drift started: they listed three
        ids that no code implemented, next to a registry that implemented
        different ones. Asserting their absence is what keeps the collapse from
        silently undoing itself.
        """
        if _SE_DOCS is None:
            pytest.skip("docs/se is not mounted in the backend test image")

        documents = [
            path
            for path in _markdown_files(_SE_DOCS)
            if _ADR_DIR_NAME not in path.relative_to(_SE_DOCS).parts
        ]
        assert documents, _SE_DOCS
        for retired in RETIRED_RULE_IDS:
            assert _offenders(documents, retired) == [], retired


# ---------------------------------------------------------------------------
# The baseline gate is the only blocking producer
# ---------------------------------------------------------------------------


class TestBaselineGateIsTheOnlyBlockingProducer:
    def test_blocking_findings_has_exactly_one_production_caller(self) -> None:
        """ADR-007 rejected create/update enforcement empirically, not by taste.

        The rejection only holds while there is a single place that can turn a
        BLOCKER into a rejection. A second production **call** of
        ``AuditService.blocking_findings`` would be exactly that second
        enforcement point, re-opening the decision without anyone superseding
        ADR-007.

        Two exclusions, both deliberate: test modules (they call it to assert on
        findings — that is the point of a test), and the definition file itself.
        A docstring *mentioning* the method is not a call and is not counted.
        """
        backend = _BACKEND_ROOT
        definition = backend / "application" / "audit_service.py"
        if not (backend / "application" / "baseline_facade.py").is_file():
            pytest.skip("backend sources are not mounted in the backend test image")

        callers: list[str] = []
        for path in _python_sources(backend):
            relative = path.relative_to(backend)
            if "tests" in relative.parts or "test_" in path.name:
                continue
            if path == definition:
                continue
            if "blocking_findings(" in path.read_text(encoding="utf-8", errors="replace"):
                callers.append(str(relative).replace("\\", "/"))

        assert callers == ["application/baseline_facade.py"], callers


# ---------------------------------------------------------------------------
# TRACE-P2 stays advisory — the #581 calibration, re-confirmed by ADR-007
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTraceP2StaysWarning:
    @pytest.mark.parametrize("tier", ["standard", "extended"])
    def test_unallocated_requirement_is_a_warning_at_every_tier(
        self, tier, tenant_a, workspace_a
    ) -> None:
        """Severity is asserted, not merely "the rule fires".

        ADR-007 had the chance to promote the allocation obligation to BLOCKER
        and declined to: doing so reproduces the #581 calibration break (a 100%
        blocker rate and an unpassable baseline gate, #490/#513/#821).
        ``test_audit_calibration_581.py`` pins the extended tier; the standard
        tier is pinned here, because the tier-conditional claim is the one the
        decision had to reject.
        """
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, title="Unallocated")

            result = _run(tier, workspace_a, tenant_a)

        findings = _findings(result, TRACE_P2)
        assert len(findings) == 1, (tier, [f.rule_id for f in result.findings])
        assert findings[0].severity is Severity.WARNING, tier
        assert TRACE_P2 not in {f.rule_id for f in result.blockers()}, tier

    def test_trace_p2_is_not_in_the_full_se_rule_ids(self) -> None:
        """The calibration is not a tier artefact: the rule is advisory overall.

        ``FULL_SE_RULE_IDS`` is the set whose members are expected to have teeth
        at a Full-SE baseline. TRACE-P2 belongs to the standard baseline set
        instead, so a future change that promotes it to BLOCKER has to move it
        here as well.
        """
        from traceability.audit.registry import full_se_rule_ids

        assert TRACE_P2 not in full_se_rule_ids()


# ---------------------------------------------------------------------------
# "Covered" must be true, not a deletion
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTestLinkObligationIsReallyCovered:
    def test_trace_p6_fires_for_a_testcase_without_a_verifies_link(
        self, tenant_a, workspace_a
    ) -> None:
        """TRACE-P6: the test side still detects a TestCase that verifies nothing."""
        with active_tenant(tenant_a):
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="Orphan TC")

            result = _run("standard", workspace_a, tenant_a)

        findings = _findings(result, TRACE_P6)
        assert len(findings) == 1
        assert str(tc_artifact.id) in findings[0].artifact_ids
        assert findings[0].severity is Severity.BLOCKER

    def test_verif_p8_fires_for_an_uncovered_leaf_requirement(
        self, tenant_a, workspace_a
    ) -> None:
        """VERIF-P8: the requirement side still detects a missing verification."""
        with active_tenant(tenant_a):
            make_requirement(tenant_a, workspace_a, title="Uncovered")

            result = _run("extended", workspace_a, tenant_a)

        findings = _findings(result, VERIF_P8)
        assert len(findings) == 1
        assert findings[0].severity is Severity.BLOCKER

    def test_a_verified_leaf_requirement_clears_both_rules(
        self, tenant_a, workspace_a
    ) -> None:
        """Both halves agree when the obligation is actually met.

        Without this, "TRACE-P6 and VERIF-P8 cover the obligation" would be
        satisfiable by two rules that can never both be silent.
        """
        with active_tenant(tenant_a):
            req_artifact, _ = make_requirement(tenant_a, workspace_a, title="Verified")
            tc_artifact, _ = make_test_case(tenant_a, workspace_a, title="TC")
            make_trace_link(tc_artifact, req_artifact, tenant_a, "verifies")

            result = _run("extended", workspace_a, tenant_a)

        assert _findings(result, TRACE_P6) == []
        assert _findings(result, VERIF_P8) == []

"""
COMP-TE-003 CoverageCalculator — Requirement-to-TestCase coverage reports.

leaf_id: COMP-TE-003_CoverageCalculator
req_id: REQ-L2-TE-006, REQ-L2-TE-007, REQ-L2-TE-011, REQ-L2-TE-012

Responsibilities:
- Calculate test coverage: % of Requirements with ≥1 `verifies` TraceLink
  to a TestCase (REQ-L2-TE-006)
- Optional filtering by artifact_type and link_type (REQ-L2-TE-007)
- Provide per-requirement coverage data for VCRM (IF-TE-INT-004)
- Performance SLA: ≤500ms for 10k Requirements (REQ-L2-TE-012)

Interface contracts consumed:
- IF-TE-INT-002: TraceLinkManager.get_trace_links(workspace_id, link_type)
- IF-TE-EXT-OUT-001: Django ORM (Requirement, TestCase, TraceLink)

Interface contracts exposed:
- IF-TE-EXT-IN-002: coverage(workspace_id, filters?, ctx) -> CoverageReport
- IF-TE-INT-004: get_coverage_data(workspace_id, baseline_id?) -> CoverageData

Architecture:
  docs/se/L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/
  COMP-TE-003_CoverageCalculator/L3_COMP-TE-003_CoverageCalculator_Architecture.md
"""
from __future__ import annotations

import logging
import time
import uuid
from typing import Optional

from django.db import connection

from persistence.models import Requirement, TraceLink
from persistence.tenancy import TenantContext

from traceability.exceptions import BaselineCoverageNotSupportedError, InvalidFilterError
from traceability.types import (
    CoverageData,
    CoverageReport,
    RequirementCoverageEntry,
)

logger = logging.getLogger(__name__)

COVERAGE_SLA_MS = 500

# Valid artifact types for filter validation (REQ-L2-TE-007)
_VALID_ARTIFACT_TYPES = frozenset(
    ["Requirement", "ArchitectureElement", "TestCase", "requirement",
     "architecture_element", "testcase"]
)

#: #424: the three-valued provenance vocabulary of ``TestCase.origin``. Kept as
#: plain strings so this Layer-1 module never import-cycles on
#: ``persistence.models`` at module load; ``TestCaseOrigin`` in
#: ``persistence.models`` is the authoritative model definition.
ORIGIN_AI_GENERATED = "ai_generated"

#: #424: link label that carries verification coverage (ADR-L3-TE3-01).
_VERIFIES_LINK_TYPE = "verifies"


def counts_as_verification_evidence(origin: str, reviewed: bool) -> bool:
    """Return whether a TestCase counts as verification evidence (#424).

    **Single source of truth** for the false-green exclusion, shared by all
    three consumers (``CoverageCalculator``, ``workflow.precondition_rules``
    and ``traceability.audit.rules.coverage_consistency``) so they cannot drift
    apart.

    ``False`` exactly when ``origin == "ai_generated"`` **and** ``reviewed`` is
    falsy. The exclusion is deliberately the *pair*: ``reviewed`` alone is not
    an exclusion criterion, and ``origin == "unknown"`` (pre-#424 rows) is
    grandfathered — it counts as evidence because the row claims neither
    "manual" nor "AI". See the cluster-5 spec section 3.
    """
    return not (origin == ORIGIN_AI_GENERATED and not reviewed)


def _is_ai_unreviewed(origin: str, reviewed: bool) -> bool:
    """Return whether *origin*/*reviewed* describe an unreviewed AI test case.

    The complement of :func:`counts_as_verification_evidence`, named separately
    so the ``pending_ai_review`` counter does not have to read a negated
    predicate.
    """
    return origin == ORIGIN_AI_GENERATED and not reviewed


class CoverageCalculator:
    """COMP-TE-003: Test coverage computation for Requirements.

    ADR-L3-TE3-01: Only `verifies` links count for test coverage.
    ADR-L3-TE3-02: percentage rounded to 1 decimal place.

    REQ-L2-TE-006 / REQ-L2-TE-007 / REQ-L2-TE-011 / REQ-L2-TE-012
    """

    # IF-TE-EXT-IN-002
    def coverage(
        self,
        workspace_id: uuid.UUID,
        artifact_type: Optional[str] = None,
        link_type: Optional[str] = None,
        *,
        include_outdated: bool = False,
        include_unreviewed_ai: bool = False,
    ) -> CoverageReport:
        """Compute test coverage for Requirements in a workspace.

        REQ-L2-TE-006: Percentage = covered / total * 100 (1 decimal place).
        REQ-L2-TE-007: Optional filtering by artifact_type and link_type.

        Args:
            workspace_id: The workspace to compute coverage for.
            artifact_type: Optional artifact type filter.
            link_type: Optional link type filter (default: "verifies").
            include_unreviewed_ai: #424. When False (default), a ``verifies``
                link whose SOURCE TestCase is ``origin="ai_generated"`` and
                ``reviewed=False`` does **not** count as coverage — the
                false-green path. ``origin="unknown"`` (pre-#424 rows) is
                grandfathered and still counts. Pass ``True`` for the raw
                "everything that is linked" view.
            include_outdated: GH-443/GH-484. When False (default):
                - soft-deleted (``status="outdated"``) Requirements are
                  excluded from both ``total`` and ``uncovered`` — deleting a
                  requirement must not keep dragging the coverage KPI down,
                  and it must not reappear in the uncovered list. This
                  mirrors the long-standing default of the sibling
                  :meth:`get_coverage_data`.
                - ``verifies`` links whose SOURCE TestCase is itself
                  soft-deleted (``status="outdated"``) no longer count as
                  coverage (GH-484). TestCase/Issue/Risk soft-delete used to
                  hard-cascade-delete their TraceLinks, so an outdated
                  TestCase's link was already gone by the time ``coverage()``
                  ran; now that the cascade is gone (TraceLinks survive
                  ``reactivate()``), this method filters them out explicitly
                  instead, using the same criterion as
                  :meth:`_filter_to_testcase_ids` (used by the sibling
                  :meth:`get_coverage_data`) for consistency. Independently
                  of this flag, a ``verifies`` link whose SOURCE is not a
                  TestCase at all (e.g. an ADR) never counts as coverage
                  (GH-396).

        Returns:
            CoverageReport with total, covered, uncovered, percentage.
        """
        t0 = time.monotonic()
        tenant_id = TenantContext.get_tenant()

        # Validate optional filters (REQ-L2-TE-007)
        if artifact_type is not None and artifact_type not in _VALID_ARTIFACT_TYPES:
            raise InvalidFilterError("artifact_type", artifact_type)
        effective_link_type = link_type or "verifies"

        # Load all Requirements in the workspace (tenant-scoped via manager)
        req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
        requirements = list(req_qs.values("id", "artifact_id"))
        if not include_outdated:
            requirements = self._exclude_outdated(requirements, "Requirement")

        total = len(requirements)
        if total == 0:
            return CoverageReport(
                total=0, covered=0, uncovered=[], percentage=0.0
            )

        req_artifact_ids = [str(r["artifact_id"]) for r in requirements]
        req_id_map = {str(r["artifact_id"]): str(r["id"]) for r in requirements}

        # Find which requirement artifacts have a `verifies` link to a TestCase
        # We look at links where source is a requirement artifact and link_type matches
        link_rows = self._fetch_link_rows(
            req_artifact_ids, effective_link_type, tenant_id
        )
        covered_artifact_ids, pending_ai_review_ids = self._evaluate_link_rows(
            link_rows,
            effective_link_type,
            include_outdated=include_outdated,
            include_unreviewed_ai=include_unreviewed_ai,
        )

        covered_req_ids = [req_id_map[aid] for aid in covered_artifact_ids if aid in req_id_map]
        covered_count = len(covered_req_ids)
        uncovered_req_ids = [
            req_id_map[aid]
            for aid in req_artifact_ids
            if aid not in covered_artifact_ids
        ]

        percentage = round(covered_count / total * 100, 1) if total > 0 else 0.0

        elapsed_ms = (time.monotonic() - t0) * 1000
        if elapsed_ms > COVERAGE_SLA_MS:
            logger.warning(
                "CoverageCalculator SLA breach: coverage took %.1fms (SLA: %dms)",
                elapsed_ms,
                COVERAGE_SLA_MS,
            )

        return CoverageReport(
            total=total,
            covered=covered_count,
            uncovered=uncovered_req_ids,
            percentage=percentage,
            # #424: distinct TestCase artifacts excluded *solely* because they
            # are unreviewed AI content. Always 0 on the raw view.
            pending_ai_review=len(pending_ai_review_ids),
        )

    # IF-TE-INT-004
    def get_coverage_data(
        self,
        workspace_id: uuid.UUID,
        baseline_id: Optional[uuid.UUID] = None,
        include_outdated: bool = False,
        include_unreviewed_ai: bool = False,
    ) -> CoverageData:
        """Return per-requirement test-case assignments for VCRM generation.

        IF-TE-INT-004: consumed by COMP-TE-004 VCRMReportGenerator.
        ADR-L3-TE3-03 (GH-397): ``baseline_id`` is intentionally rejected
        rather than silently ignored. It used to be accepted and forwarded
        but never actually applied — this method always computed against
        live data while the caller was led to believe it got a baseline
        snapshot comparison. See :class:`BaselineCoverageNotSupportedError`
        for why a partial implementation was rejected in favour of an
        explicit error: the Baseline delta index does not capture the
        TraceLink/TestRunResult data needed for this consistently across
        baseline scopes (``baseline.delta_index_builder.ScopeResolver`` only
        captures ``trace_link`` entries for ``scope="document"`` and
        ``test_run``/``test_run_result`` entries for
        ``scope="project"``/``"global"`` — never both for the same baseline).

        Args:
            workspace_id: The workspace to compute coverage data for.
            baseline_id: Not supported yet — must be ``None``. Passing a
                value raises :class:`BaselineCoverageNotSupportedError`
                (GH-397) instead of silently falling back to live data.
            include_outdated: When False (default), outdated Requirements are
                excluded from ``entries`` entirely, and outdated verifying
                TestCases are excluded from each remaining entry's
                ``test_cases`` list. Both Requirement and TestCase mirror
                lifecycle state via a denormalized ``status`` column (same
                pattern as ``mcp_server.tools.cross_cutting._entity_counts``).
            include_unreviewed_ai: #424. When False (default), an
                ``origin="ai_generated"``, unreviewed TestCase is excluded from
                every entry's ``test_cases`` list — the same predicate
                :meth:`coverage` applies (``counts_as_verification_evidence``).

        Returns:
            CoverageData with per-requirement test-case lists.

        Raises:
            BaselineCoverageNotSupportedError: ``baseline_id`` is not None.
        """
        if baseline_id is not None:
            raise BaselineCoverageNotSupportedError(baseline_id)

        tenant_id = TenantContext.get_tenant()

        # Load requirements in workspace
        req_qs = Requirement.objects.filter(artifact__workspace_id=workspace_id)
        requirements = list(
            req_qs.values("id", "artifact_id", "title", "uid", "level")
        )
        if not include_outdated:
            requirements = self._exclude_outdated(requirements, "Requirement")

        if not requirements:
            return CoverageData(entries=[])

        req_artifact_ids = [str(r["artifact_id"]) for r in requirements]
        req_id_map = {str(r["artifact_id"]): str(r["id"]) for r in requirements}

        # Load verifies links for requirement artifacts
        verifies_links = self._get_verifies_links_detail(
            req_artifact_ids=req_artifact_ids,
            tenant_id=tenant_id,
        )

        # Resolve the latest TestRun result per verifying TestCase so the VCRM
        # reflects actual execution status instead of a hard-coded "Not Run".
        testcase_artifact_ids = {
            link_info["testcase_artifact_id"] for link_info in verifies_links
        }
        result_by_testcase = self._latest_testrun_status(testcase_artifact_ids)

        # GH-396: a `verifies` link's SOURCE must actually be a TestCase for
        # it to count as verification coverage — some other artifact type
        # (e.g. an ADR) can technically create a `verifies` link pointing at
        # a Requirement, and such a link must never show up as a covering
        # TestCase in the VCRM. Restrict unconditionally (not just when
        # excluding outdated ones). #424: the same pass now also drops
        # unreviewed AI test cases unless explicitly requested.
        testcase_artifact_ids = self._filter_to_testcase_ids(
            testcase_artifact_ids,
            include_outdated=include_outdated,
            include_unreviewed_ai=include_unreviewed_ai,
        )
        testcase_meta = self._testcase_meta_by_artifact(testcase_artifact_ids)

        # Build per-requirement test-case map. The Requirement is the link
        # TARGET and the TestCase is the SOURCE (SE `verifies` convention).
        req_testcases: dict[str, list[dict]] = {
            str(r["id"]): [] for r in requirements
        }
        for link_info in verifies_links:
            req_art_id = link_info["req_artifact_id"]
            tc_art_id = link_info["testcase_artifact_id"]
            if req_art_id in req_id_map and tc_art_id in testcase_artifact_ids:
                req_id = req_id_map[req_art_id]
                meta = testcase_meta.get(tc_art_id, {})
                req_testcases[req_id].append({
                    "id": tc_art_id,
                    "result": result_by_testcase.get(tc_art_id, "Not Run"),
                    # #424/#402: provenance + off-nominal category are carried
                    # per test case so report consumers (and the REST coverage
                    # report) can render them without a second request.
                    "origin": meta.get("origin", ""),
                    "reviewed": bool(meta.get("reviewed", False)),
                    "scenario_kind": meta.get("scenario_kind", ""),
                    "uid": meta.get("uid") or "",
                    "title": meta.get("title") or "",
                })

        entries = [
            RequirementCoverageEntry(
                requirement_id=str(r["id"]),
                test_cases=req_testcases.get(str(r["id"]), []),
                uid=r["uid"] or "",
                title=r["title"] or "",
                level=r["level"],
            )
            for r in requirements
        ]
        return CoverageData(entries=entries)

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _latest_testrun_status(
        self,
        testcase_artifact_ids: set[str],
    ) -> dict[str, str]:
        """Map TestCase artifact id -> display label of its latest run result.

        IF-TE-INT-004: wires the most recent ``TestRunResult`` status into the
        VCRM coverage data. TestCases without any recorded run are absent from
        the returned map, so callers fall back to "Not Run".

        "Latest" is the result with the most recent ``executed_at`` (NULLs —
        never-executed rows — rank last), tie-broken by insertion id.
        """
        if not testcase_artifact_ids:
            return {}

        from django.db.models import F

        from persistence.models import TestRunResult

        status_labels = dict(
            TestRunResult._meta.get_field("status").choices
        )

        rows = (
            TestRunResult.objects.filter(
                test_case__artifact_id__in=testcase_artifact_ids
            )
            .order_by(
                "test_case__artifact_id",
                F("executed_at").desc(nulls_last=True),
                "-id",
            )
            .values("test_case__artifact_id", "status")
        )

        latest: dict[str, str] = {}
        for row in rows:
            tc_art_id = str(row["test_case__artifact_id"])
            if tc_art_id in latest:
                continue  # first row per TestCase is the latest (ordering)
            latest[tc_art_id] = status_labels.get(row["status"], "Not Run")
        return latest

    def _exclude_outdated_testcase_ids(
        self,
        testcase_artifact_ids: set[str],
        *,
        include_unreviewed_ai: bool = False,
    ) -> set[str]:
        """Filter *testcase_artifact_ids* down to valid verification evidence.

        Task 12: TestCase's lifecycle status is resolved through
        ``WorkflowItemState`` (the denormalized ``status`` mirror column this
        docstring used to describe is dropped) — see
        ``_filter_to_testcase_ids``.

        #424: this is also the wrapper ``workflow.precondition_rules`` calls
        directly, so it forwards ``include_unreviewed_ai`` (default ``False``).
        Despite the historical name it applies both exclusions now — an
        outdated TestCase *and* an unreviewed AI-generated TestCase are not
        evidence.
        """
        return self._filter_to_testcase_ids(
            testcase_artifact_ids,
            include_outdated=False,
            include_unreviewed_ai=include_unreviewed_ai,
        )

    @staticmethod
    def _exclude_outdated(rows: list[dict], item_type: str) -> list[dict]:
        """Drop rows whose current state is "outdated".

        Datenmodell-Konsolidierung Phase 1: resolved through WorkflowItemState
        (batched). *rows* must each carry an ``"id"`` key (e.g. from a
        ``.values()`` call). Task 12: the ``status`` column is dropped, so a
        row never wired into one falls back to *item_type*'s preset initial
        state instead (documented, reviewed data-loss tradeoff, see Task 12
        report Finding 2); the initial state is never "outdated", so it is
        still kept.
        """
        from workflow import state_reader

        states = state_reader.current_states(item_type, (row["id"] for row in rows))
        initial_state = state_reader.initial_state(item_type)
        return [
            row
            for row in rows
            if (states.get(str(row["id"])) or initial_state) != "outdated"
        ]

    @staticmethod
    def _load_testcase_rows(artifact_ids: set[str]) -> list[dict]:
        """Return TestCase rows backing *artifact_ids*, with #424 provenance.

        A batch query (no N+1) selecting exactly the columns the evidence
        filter, the ``pending_ai_review`` counter and the per-requirement
        ``test_cases`` payload need.
        """
        from persistence.models import TestCase

        return list(
            TestCase.objects.filter(artifact_id__in=artifact_ids).values(
                "id", "artifact_id", "origin", "reviewed", "scenario_kind",
                "uid", "title",
            )
        )

    @staticmethod
    def _outdated_testcase_row_ids(rows: list[dict]) -> set[str]:
        """Return the TestCase row ids of *rows* whose state is "outdated".

        Datenmodell-Konsolidierung Phase 1: "outdated" is resolved through
        ``WorkflowItemState`` (batched). Task 12: the ``status`` column is
        dropped, so a TestCase never wired into one falls back to the
        testcase_default preset's initial state instead (documented, reviewed
        data-loss tradeoff, see Task 12 report Finding 2).
        """
        from workflow import state_reader

        states = state_reader.current_states(
            "TestCase", (row["id"] for row in rows)
        )
        testcase_initial_state = state_reader.initial_state("TestCase")
        return {
            str(row["id"])
            for row in rows
            if (states.get(str(row["id"])) or testcase_initial_state) == "outdated"
        }

    def _filter_to_testcase_ids(
        self,
        source_ids: set[str],
        *,
        include_outdated: bool = False,
        include_unreviewed_ai: bool = False,
    ) -> set[str]:
        """Restrict *source_ids* to artifact ids that are valid TestCase evidence.

        GH-396: the SQL behind ``coverage()``/``get_coverage_data()`` only
        matches ``link_type``/``target_id`` — it does not check what kind of
        artifact the link SOURCE is. Some other artifact type (e.g. an ADR)
        can technically create a ``verifies`` link pointing at a Requirement;
        such a link must never be counted as verification coverage
        (ADR-L3-TE3-01: only TestCase-sourced ``verifies`` links count).
        Querying the ``TestCase`` table for *source_ids* is both the type
        check (non-TestCase ids simply have no matching row) and, when
        *include_outdated* is False, the soft-delete exclusion (GH-484) in
        one pass.

        #424: additionally applies :func:`counts_as_verification_evidence`
        unless *include_unreviewed_ai* is True — an ``origin="ai_generated"``,
        unreviewed TestCase is not evidence (the false-green path).
        """
        if not source_ids:
            return set()

        rows = self._load_testcase_rows(source_ids)
        outdated = (
            set() if include_outdated else self._outdated_testcase_row_ids(rows)
        )
        return {
            str(row["artifact_id"])
            for row in rows
            if str(row["id"]) not in outdated
            and (
                include_unreviewed_ai
                or counts_as_verification_evidence(row["origin"], row["reviewed"])
            )
        }

    def _testcase_meta_by_artifact(
        self, artifact_ids: set[str]
    ) -> dict[str, dict]:
        """Return ``{artifact_id: {origin, reviewed, scenario_kind, uid, title}}``."""
        return {
            str(row["artifact_id"]): row
            for row in self._load_testcase_rows(artifact_ids)
        }

    def _fetch_link_rows(
        self,
        req_artifact_ids: list[str],
        link_type: str,
        tenant_id: uuid.UUID,
    ) -> list[tuple[str, str]]:
        """Return ``(source_id, target_id)`` pairs of *link_type* links.

        Parameterised IN clause, one query regardless of the requirement count
        (REQ-L2-TE-012). SE link convention
        (``traceability/types.py``): for a ``verifies`` link the TestCase is
        the SOURCE and the Requirement is the TARGET
        (TC --verifies--> Req). A Requirement is therefore "covered" when its
        artifact id appears as the link TARGET, not the source.
        """
        if not req_artifact_ids:
            return []

        placeholders = ", ".join(["%s"] * len(req_artifact_ids))
        sql = f"""
            SELECT DISTINCT source_id, target_id
            FROM pl_tracelink
            WHERE target_id IN ({placeholders})
              AND link_type = %s
              AND tenant_id = %s
        """
        params = [*req_artifact_ids, link_type, str(tenant_id)]

        with connection.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [(str(row[0]), str(row[1])) for row in rows]

    def _evaluate_link_rows(
        self,
        link_rows: list[tuple[str, str]],
        link_type: str,
        *,
        include_outdated: bool = False,
        include_unreviewed_ai: bool = False,
    ) -> tuple[set[str], set[str]]:
        """Resolve link rows to ``(covered targets, pending-AI-review ids)``.

        For a ``verifies`` link (ADR-L3-TE3-01: the only coverage-relevant
        type) the source must be a live TestCase and must not be an unreviewed
        AI-generated one (GH-396/GH-484/#424). Any other link type keeps the
        historical behaviour: every target counts.

        The second element is the set of TestCase artifact ids excluded
        *solely* because of #424 — feeding ``CoverageReport.pending_ai_review``.
        It is empty on the raw view (``include_unreviewed_ai=True``) and empty
        for non-``verifies`` link types.
        """
        if not link_rows:
            return set(), set()

        if link_type != _VERIFIES_LINK_TYPE:
            return {target for _, target in link_rows}, set()

        rows = self._load_testcase_rows({source for source, _ in link_rows})
        outdated = (
            set() if include_outdated else self._outdated_testcase_row_ids(rows)
        )

        valid_source_ids: set[str] = set()
        pending_ai_review_ids: set[str] = set()
        for row in rows:
            if str(row["id"]) in outdated:
                continue
            artifact_id = str(row["artifact_id"])
            if include_unreviewed_ai or counts_as_verification_evidence(
                row["origin"], row["reviewed"]
            ):
                valid_source_ids.add(artifact_id)
            elif _is_ai_unreviewed(row["origin"], row["reviewed"]):
                pending_ai_review_ids.add(artifact_id)

        covered = {
            target for source, target in link_rows if source in valid_source_ids
        }
        return covered, pending_ai_review_ids

    def _get_covered_artifact_ids(
        self,
        req_artifact_ids: list[str],
        link_type: str,
        tenant_id: uuid.UUID,
        *,
        include_outdated: bool = False,
        include_unreviewed_ai: bool = False,
    ) -> set[str]:
        """Return the set of requirement artifact IDs that have a matching link.

        Thin wrapper over :meth:`_fetch_link_rows` + :meth:`_evaluate_link_rows`
        (see their docstrings for the GH-396/GH-484/#424 semantics).
        """
        covered, _ = self._evaluate_link_rows(
            self._fetch_link_rows(req_artifact_ids, link_type, tenant_id),
            link_type,
            include_outdated=include_outdated,
            include_unreviewed_ai=include_unreviewed_ai,
        )
        return covered

    def _get_verifies_links_detail(
        self,
        req_artifact_ids: list[str],
        tenant_id: uuid.UUID,
    ) -> list[dict]:
        """Return verifies-link detail rows for VCRM data building."""
        if not req_artifact_ids:
            return []

        # SE link convention: TestCase is the SOURCE, Requirement the TARGET
        # of a `verifies` link. Select links whose TARGET is a requirement
        # artifact; the SOURCE is then the verifying TestCase.
        placeholders = ", ".join(["%s"] * len(req_artifact_ids))
        sql = f"""
            SELECT source_id, target_id
            FROM pl_tracelink
            WHERE target_id IN ({placeholders})
              AND link_type = 'verifies'
              AND tenant_id = %s
        """
        params = [*req_artifact_ids, str(tenant_id)]

        with connection.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            {"testcase_artifact_id": str(row[0]), "req_artifact_id": str(row[1])}
            for row in rows
        ]


__all__ = ["CoverageCalculator", "counts_as_verification_evidence"]

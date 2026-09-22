"""``seed_full_chain`` — realistic, audit-clean SE fixture (#272, cluster 5).

Separate from ``seed_demo`` on purpose: that command's contract is "login base
data only, fast", and every E2E setup builds on it — a full SE data set there
would slow each setup down. ``seed_toothbrush`` proves the *product* story
(2 700+ artifacts) but has no Goals, no baseline and no CCB record, so it cannot
demonstrate the validation pillar end to end.

This command seeds the **golden path** of an Extended-rigor workspace:

  * 3 Goals, 4 StakeholderNeeds, every need ``satisfies`` a Goal (VAL-P1 clean),
  * 24 Requirements (12 × L1 with `derives-from` to a need, 12 × L2 derived from
    an L1 requirement, each with ``acceptance_criteria`` +
    ``verification_method`` — the Extended field policy),
  * 8 ArchitectureElements in two decomposed levels, each carrying at least one
    allocated Requirement, every L2 requirement deriving from an L1 requirement
    of its parent element (TRACE-P3/ARCH-003 clean),
  * 12 TestCases (8 ``nominal``, 4 ``off_nominal``), one per leaf requirement,
    all ``origin="manual"`` / ``reviewed=True`` (fixture material is human —
    spec section 4.8 **producer P6**),
  * 3 TestRuns with mixed ``passed``/``failed`` results,
  * 1 project Baseline and 1 approved ChangeRequest with ≥2 affected items
    linked to that baseline.

Idempotent: the workspace name is the marker, mirroring ``seed_toothbrush``.
Everything goes through the existing services — no direct model writes for
domain data.
"""
from __future__ import annotations

from typing import Any, Optional

from django.core.management.base import BaseCommand

from application.architecture_service import ArchitectureService
from application.baseline_facade import BaselineFacade
from application.change_request_service import ChangeRequestService
from application.goal_service import GoalService
from application.requirement_service import RequirementService
from application.stakeholder_need_service import StakeholderNeedService
from application.test_run_service import TestRunService
from application.test_service import TestService
from application.trace_link_service import TraceLinkService
from application.workspace_service import WorkspaceService
from auth_tenancy.context import AuthContext, AuthMethod
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import (
    ElementType,
    MoSCoWPriority,
    RequirementLevel,
    ScenarioKind,
    Tenant,
    TestCaseOrigin,
    User,
    Workspace,
)

#: Idempotency marker — the workspace name is unique per tenant.
WORKSPACE_NAME = "SysEng Full-Chain Demo"

DEFAULT_ADMIN_EMAIL = "admin@example.com"
DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_REVIEWER_USERNAME = "full-chain-reviewer"

_VERIFICATION_METHOD = "Test"

_GOALS = [
    ("Zuverlässiger Betrieb", "Das System arbeitet im Dauerbetrieb fehlerfrei."),
    ("Nachvollziehbare Lieferkette", "Jede Anforderung ist bis zur Komponente belegt."),
    ("Schnelle Inbetriebnahme", "Die Inbetriebnahme dauert unter einer Stunde."),
]

_NEEDS = [
    ("Ganzheitliche Abdeckung", "Alle Systemfunktionen sind gefordert."),
    ("Wartbarkeit", "Komponenten lassen sich einzeln tauschen."),
    ("Rückverfolgbarkeit", "Anforderungen sind bis zum Test belegt."),
    ("Betriebssicherheit", "Fehlerfälle sind getestet."),
]


def _ctx(tenant: Tenant, user: User, workspace_id) -> AuthContext:
    return AuthContext(
        tenant_id=tenant.id,
        user_id=user.id,
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
        workspace_id=workspace_id,
    )


def _seed(tenant: Tenant, user: User) -> None:
    """Create the full chain. Caller has already armed the tenant context."""
    ws_svc = WorkspaceService()
    ctx = _ctx(tenant, user, None)
    workspace = ws_svc.create_workspace(
        ctx=ctx,
        name=WORKSPACE_NAME,
        preset="extended",
        terminology_profile="se_mode",
    )
    ws_id = workspace.id
    ctx = _ctx(tenant, user, ws_id)

    requirement_svc = RequirementService()
    need_svc = StakeholderNeedService()
    goal_svc = GoalService()
    arch_svc = ArchitectureService()
    test_svc = TestService()
    run_svc = TestRunService()
    link_svc = TraceLinkService()

    # --- Goals -----------------------------------------------------------------
    print("Creating Goals...")
    goals = [
        goal_svc.create_version(
            workspace_id=ws_id, title=title, description=description, ctx=ctx
        )
        for title, description in _GOALS
    ]
    print(f"  Goals: {len(goals)}")

    # --- Stakeholder needs (each satisfies a Goal => VAL-P1 clean) -------------
    print("Creating Stakeholder Needs...")
    needs = []
    for index, (title, description) in enumerate(_NEEDS):
        need = need_svc.create(
            ctx=ctx,
            workspace_id=ws_id,
            title=title,
            description=description,
            moscow_priority=MoSCoWPriority.MUST,
        )
        needs.append(need)
        goal = goals[index % len(goals)]
        link_svc.create_trace_link(
            source_id=need.artifact_id,
            target_id=goal["artifact_id"],
            link_type="satisfies",
            ctx=ctx,
        )
    print(f"  StakeholderNeeds: {len(needs)}")

    # --- Architecture: one root (invariant I5) + 7 components ----------------
    print("Creating Architecture Elements...")
    root_element = arch_svc.create_architecture_element(
        workspace_id=ws_id,
        title="Gesamtsystem",
        ctx=ctx,
        element_type=ElementType.SUBSYSTEM,
    )
    components = [
        arch_svc.create_architecture_element(
            workspace_id=ws_id,
            title=f"Component {index + 1}",
            ctx=ctx,
            element_type=ElementType.COMPONENT,
            parent_id=root_element.id,
        )
        for index in range(7)
    ]
    for component in components:
        link_svc.create_trace_link(
            source_id=root_element.artifact_id,
            target_id=component.artifact_id,
            link_type="decomposes",
            ctx=ctx,
        )
    architecture = [root_element, *components]
    print(f"  ArchitectureElements: {len(architecture)}")

    # --- Requirements: 12 x L1 (from a need), 12 x L2 (from L1) ---------------
    print("Creating Requirements...")
    l1_requirements = []
    for index in range(12):
        requirement = requirement_svc.create_requirement(
            workspace_id=ws_id,
            title=f"Systemanforderung L1-{index + 1:02d}",
            ctx=ctx,
            description=f"Systemanforderung {index + 1} der Gesamtsystemebene.",
            acceptance_criteria="Nachweis über Test TC-01 mit dokumentiertem Ergebnis.",
            verification_method=_VERIFICATION_METHOD,
            level=int(RequirementLevel.L1_SYSTEM),
        )
        l1_requirements.append(requirement)
        need = needs[index % len(needs)]
        link_svc.create_trace_link(
            source_id=requirement.artifact_id,
            target_id=need.artifact_id,
            link_type="derives-from",
            ctx=ctx,
        )
        # Validation pillar: a requirement satisfies a Goal (advisory edge).
        link_svc.create_trace_link(
            source_id=requirement.artifact_id,
            target_id=goals[index % len(goals)]["artifact_id"],
            link_type="satisfies",
            ctx=ctx,
        )
        # Every L1 requirement is allocated to the root element, so each L2
        # requirement (allocated to a component of that root) satisfies
        # ARCH-003 — and TRACE-P3 sees the root covered.
        link_svc.create_trace_link(
            source_id=requirement.artifact_id,
            target_id=root_element.artifact_id,
            link_type="allocated-to",
            ctx=ctx,
        )

    l2_requirements = []
    for index in range(12):
        component = components[index % len(components)]
        requirement = requirement_svc.create_requirement(
            workspace_id=ws_id,
            title=f"Subsystemanforderung L2-{index + 1:02d}",
            ctx=ctx,
            description=f"Verfeinerte Anforderung {index + 1} der Subsystemebene.",
            acceptance_criteria="Nachweis über den zugeordneten TestCase.",
            verification_method=_VERIFICATION_METHOD,
            level=int(RequirementLevel.L2_SUBSYSTEM),
        )
        l2_requirements.append(requirement)
        # 1:1 parent so *every* L1 requirement has a child (otherwise it counts
        # as a leaf and VERIF-P8 demands a verifying test case for it too).
        link_svc.create_trace_link(
            source_id=requirement.artifact_id,
            target_id=l1_requirements[index].artifact_id,
            link_type="derives-from",
            ctx=ctx,
        )
        link_svc.create_trace_link(
            source_id=requirement.artifact_id,
            target_id=component.artifact_id,
            link_type="allocated-to",
            ctx=ctx,
        )
    print(f"  Requirements: {len(l1_requirements) + len(l2_requirements)}")

    # --- TestCases: 12, one per leaf (L2) requirement --------------------------
    print("Creating TestCases...")
    test_cases = []
    for index, requirement in enumerate(l2_requirements):
        scenario = (
            ScenarioKind.OFF_NOMINAL if index % 3 == 2 else ScenarioKind.NOMINAL
        )
        test_case = test_svc.create_test_case(
            workspace_id=ws_id,
            title=f"TC-{index + 1:02d} für {requirement.title}",
            ctx=ctx,
            description="Automatisierter Nachweis der zugeordneten Anforderung.",
            steps=[
                {"step": "Vorbedingung herstellen", "expected_result": "System bereit"},
                {"step": "Prüffall ausführen", "expected_result": "Erwartung erfüllt"},
            ],
            # Producer P6: fixture material is human-authored and reviewed.
            origin=TestCaseOrigin.MANUAL,
            reviewed=True,
            scenario_kind=scenario,
        )
        test_cases.append(test_case)
        link_svc.create_trace_link(
            source_id=test_case.artifact_id,
            target_id=requirement.artifact_id,
            link_type="verifies",
            ctx=ctx,
        )
    off_nominal = sum(
        1 for tc in test_cases if tc.scenario_kind == ScenarioKind.OFF_NOMINAL
    )
    print(f"  TestCases: {len(test_cases)} ({off_nominal} off-nominal)")

    # --- TestRuns with mixed results ------------------------------------------
    print("Creating TestRuns...")
    runs = []
    for run_index in range(3):
        run = run_svc.create_test_run(
            workspace_id=ws_id,
            name=f"Testlauf {run_index + 1}",
            ctx=ctx,
        )
        for offset, test_case in enumerate(test_cases):
            # Every third case fails in the first run, every fifth in the
            # second; the third run is clean.
            failed = (run_index == 0 and offset % 3 == 0) or (
                run_index == 1 and offset % 5 == 0
            )
            run_svc.add_result(
                test_run_id=run.id,
                test_case_id=test_case.id,
                status="failed" if failed else "passed",
                ctx=ctx,
                message="Fixture-Ergebnis",
            )
        runs.append(run)
    print(f"  TestRuns: {len(runs)}")

    # --- Baseline -------------------------------------------------------------
    print("Creating Baseline (project scope)...")
    baseline_id = BaselineFacade().create_baseline(
        scope="project",
        workspace_id=ws_id,
        name="Full-Chain Baseline 1.0",
        ctx=ctx,
    )
    print(f"  Baseline: {baseline_id}")

    # --- ChangeRequest: approved, 2 affected items, baseline linked -----------
    print("Creating ChangeRequest...")
    reviewer = _ensure_reviewer(tenant)
    reviewer_ctx = _ctx(tenant, reviewer, ws_id)
    cr = ChangeRequestService().create_change_request(
        workspace_id=ws_id,
        title="Anpassung der Subsystemanforderungen 01 und 02",
        ctx=ctx,
        description="Fixture-Change-Request für den CCB-Pfad.",
        impact_assessment="Zwei Subsystemanforderungen werden angepasst.",
        change_reason="Fixture: CCB-Pfad demonstrieren",
        assigned_reviewer_id=reviewer.id,
        affected_item_ids=[
            l2_requirements[0].artifact_id,
            l2_requirements[1].artifact_id,
        ],
    )
    for target in ("submitted", "under_review", "approved"):
        cr = ChangeRequestService().transition_status(
            cr.id,
            target,
            reviewer_ctx,
            change_reason="Fixture: CCB-Freigabe dokumentieren",
        )
    ChangeRequestService().link_baseline(cr.id, reviewer_ctx, baseline_id=baseline_id)
    print(f"  ChangeRequest: {cr.id}")


def _ensure_reviewer(tenant: Tenant) -> User:
    """A second user so the CCB separation-of-duties gate can be satisfied."""
    reviewer = User.objects.filter(
        tenant_id=tenant.id, username=DEFAULT_REVIEWER_USERNAME
    ).first()
    if reviewer is None:
        reviewer = User.objects.create(
            email=DEFAULT_REVIEWER_EMAIL,
            username=DEFAULT_REVIEWER_USERNAME,
            tenant=tenant,
        )
    return reviewer


DEFAULT_REVIEWER_EMAIL = "reviewer@example.com"


class Command(BaseCommand):
    help = (
        "Seed a realistic, audit-clean Extended-rigor workspace "
        f"('{WORKSPACE_NAME}') with the full SE chain (#272)."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        tenant: Optional[Tenant] = Tenant.objects.first()
        if tenant is None:
            tenant = Tenant.objects.create(name="Default Tenant")
        admin = User.objects.filter(
            tenant_id=tenant.id, username=DEFAULT_ADMIN_USERNAME
        ).first()
        if admin is None:
            admin = User.objects.create(
                email=DEFAULT_ADMIN_EMAIL,
                username=DEFAULT_ADMIN_USERNAME,
                tenant=tenant,
            )

        # Outside a request no middleware arms the RLS layer, so every write
        # below would be rejected by the Postgres policy (COMP-PL-006).
        set_request_tenant(tenant.id)
        try:
            existing = Workspace.objects.filter(
                tenant_id=tenant.id, name=WORKSPACE_NAME
            ).first()
            if existing is not None:
                print(f"Workspace created with ID: {existing.id}")
                print("Seeding skipped — workspace already present.")
                return
            _seed(tenant, admin)
        finally:
            clear_request_tenant()
        print("Full-chain fixture seeded.")

r"""Structural architecture gates for the application facade (S4.2 WP-A).

This module is the pytest-native equivalent of an import-linter setup — the
project does **not** ship ``import-linter`` in its test dependencies, so the
contracts below are enforced directly (no new dependency, same ratchet
semantics as ``rest_api/tests/test_architecture.py``).

Three contracts are guarded:

1. **Facade export surface** (R2S-002 safety net): ``application.services``
   must keep its exact ``__all__`` list and ``_registry`` insertion order.
   Wildcard ``from application.services_stepN import *`` re-exports are
   forbidden; the facade must use explicit named re-exports so its symbol set
   is statically visible.

2. **Module-level import cycles** (R2S-009): the strongly connected components
   (SCCs) of size >= 2 in the ``application`` package are a frozen baseline.
   A new cycle, or a module joining an existing cycle, fails the build.
   Shrinking a cycle (removing an edge) is always allowed.

3. **Layer-0 -> layer-2 edges** (R2S-004, contract only): ``persistence``,
   ``auth_tenancy``, ``presets`` and ``audit`` must not import ``application``
   unless the exact edge is allowlisted with an ``added_at`` date and a reason.
   Extracting ``ServiceBase`` out of ``application.base`` needs an se-architect
   ADR and is deliberately out of scope here — the four existing
   ``ServiceBase`` inherit/import edges are documented exemptions, not an
   endorsement.

Every allowlist entry carries ``added_at`` and ``reason``. Never raise a
ceiling or add an exemption without a matching review decision.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Frozen baselines
# ---------------------------------------------------------------------------

#: Exact public export surface of ``application.services`` (69 symbols).
#: Byte-identical before and after the R2S-002 facade cycle break.
EXPECTED_FACADE_ALL: tuple[str, ...] = (
    "ArtifactService",
    "RequirementService",
    "ArchitectureService",
    "TestService",
    "TraceLinkService",
    "PresetPolicyService",
    "DomainEventBus",
    "DomainEvent",
    "get_event_bus",
    "poll_and_dispatch",
    "TreeNodeDTO",
    "RequirementDTO",
    "DecompositionResultDTO",
    "SimilarRequirementDTO",
    "PermissionDeniedError",
    "NotFoundError",
    "ValidationError",
    "BaselineGateBlockedError",
    "OptimisticLockError",
    "LlmNotConfiguredError",
    "PgVectorUnavailableError",
    "ServiceBase",
    "_registry",
    "VALID_LINK_TYPES",
    "MANUAL_LINK_TYPES",
    "get_preset_policy_service",
    "BaselineFacade",
    "BaselineTagValidationError",
    "WorkflowFacade",
    "ExportService",
    "ExportResult",
    "ImportService",
    "ImportResult",
    "ImportRowError",
    "SearchService",
    "SearchResult",
    "SearchHit",
    "QueryParser",
    "WebhookDispatcher",
    "SUBSCRIBED_EVENT_TYPES",
    "get_webhook_dispatcher",
    "AdrService",
    "AdrDTO",
    "RiskService",
    "RiskDTO",
    "IssueService",
    "IssueDTO",
    "TestRunService",
    "VALID_RESULT_STATUSES",
    "ChangeRequestService",
    "ChangeRequestDTO",
    "ChangeRequestValidator",
    "ArtifactDiffService",
    "GlossaryService",
    "GlossaryTermDTO",
    "ReqifExportService",
    "ReqifImportService",
    "ReqifImportResult",
    "ReqifParseError",
    "ReqifEntityReport",
    "ArtifactVersionService",
    "CommentService",
    "NotificationService",
    "EffectivePermissionService",
    "EffectivePermission",
    "SuggestionService",
    "ProducerContextRequiredError",
    "BaselineRollbackService",
    "RollbackResult",
)

#: Exact registry insertion order (implicit service-discovery contract, 18 keys).
EXPECTED_REGISTRY_KEYS: tuple[str, ...] = (
    "ArtifactService",
    "RequirementService",
    "ArchitectureService",
    "TestService",
    "TraceLinkService",
    "PresetPolicyService",
    "BaselineFacade",
    "WorkflowFacade",
    "ExportService",
    "ImportService",
    "SearchService",
    "WebhookDispatcher",
    "WorkspaceService",
    "AdrService",
    "RiskService",
    "IssueService",
    "TestRunService",
    "ChangeRequestService",
)

#: Facade modules that participate in the R2S-002 cycle break.
_FACADE_MODULES = frozenset(
    {
        "application.services",
        "application.services_step2",
        "application.services_step3",
        "application.services_step4",
    }
)

_APPLICATION = "application"
_LAYER0_PACKAGES = frozenset({"persistence", "auth_tenancy", "presets", "audit"})

_BACKEND_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Import-graph helpers (AST based — no module import, no Django side effects)
# ---------------------------------------------------------------------------


def _first_party_modules() -> set[str]:
    """Return every first-party module name under the backend root."""
    modules: set[str] = set()
    for path in _BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(_BACKEND_ROOT)
        if any(part.startswith(".") for part in rel.parts):
            continue
        parts = list(rel.parts)
        if parts[-1] == "__init__.py":
            parts = parts[:-1]
        else:
            parts[-1] = parts[-1][:-3]
        if parts:
            modules.add(".".join(parts))
    return modules


def _module_name(path: Path) -> str:
    """Derive the dotted module name of a source file."""
    parts = list(path.relative_to(_BACKEND_ROOT).parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(parts)


def _module_graph() -> dict[str, set[str]]:
    """Build a first-party import graph ``{module: {imported modules}}``.

    Absolute ``from X import Y`` / ``import X`` edges and one-level relative
    imports (``from .base import ...``) are resolved. Relative imports appear
    in four ``application`` modules and all target ``application.base`` or
    ``application.models``; resolving them makes the graph conservative.
    """
    modules = _first_party_modules()
    graph: dict[str, set[str]] = defaultdict(set)
    for path in _BACKEND_ROOT.rglob("*.py"):
        rel = path.relative_to(_BACKEND_ROOT)
        if any(part.startswith(".") for part in rel.parts):
            continue
        src = _module_name(path)
        if not src:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError):
            continue
        src_parts = src.split(".")
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    base = src_parts[: len(src_parts) - node.level]
                    prefix = ".".join(base)
                    target = f"{prefix}.{node.module}" if node.module else prefix
                else:
                    target = node.module or ""
                if target in modules and target != src:
                    graph[src].add(target)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in modules and alias.name != src:
                        graph[src].add(alias.name)
    return dict(graph)


def _cyclic_sccs(
    nodes: set[str], graph: dict[str, set[str]]
) -> list[frozenset[str]]:
    """Return all strongly connected components of size >= 2 (Tarjan)."""
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    components: list[frozenset[str]] = []
    counter = [0]

    def strongconnect(vertex: str) -> None:
        index[vertex] = low[vertex] = counter[0]
        counter[0] += 1
        stack.append(vertex)
        on_stack.add(vertex)
        for neighbour in sorted(graph.get(vertex, ())):
            if neighbour not in nodes:
                continue
            if neighbour not in index:
                strongconnect(neighbour)
                low[vertex] = min(low[vertex], low[neighbour])
            elif neighbour in on_stack:
                low[vertex] = min(low[vertex], index[neighbour])
        if low[vertex] == index[vertex]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.discard(member)
                component.append(member)
                if member == vertex:
                    break
            components.append(frozenset(component))

    for vertex in sorted(nodes):
        if vertex not in index:
            strongconnect(vertex)
    return [component for component in components if len(component) > 1]


def _application_cyclic_sccs() -> list[frozenset[str]]:
    """Cyclic SCCs restricted to the ``application`` package."""
    graph = _module_graph()
    nodes = {name for name in graph if name == _APPLICATION or name.startswith(_APPLICATION + ".")}
    return _cyclic_sccs(nodes, graph)


def _layer0_to_application_edges() -> set[tuple[str, str]]:
    """Production (non-test, non-migration) layer-0 -> layer-2 import edges."""
    edges: set[tuple[str, str]] = set()
    for src, targets in _module_graph().items():
        if src.split(".")[0] not in _LAYER0_PACKAGES:
            continue
        if ".tests." in f".{src}." or ".migrations." in f".{src}.":
            continue
        for target in targets:
            if target == _APPLICATION or target.startswith(_APPLICATION + "."):
                edges.add((src, target))
    return edges


# ---------------------------------------------------------------------------
# Allowlists — every entry carries added_at + reason
# ---------------------------------------------------------------------------

#: Frozen cyclic-SCC baseline. The S4.2 base tree had 3 components; R2S-002
#: removed the facade component, leaving 2 (below). Each component may shrink
#: as edges are removed; a new component or a module joining an existing one
#: fails the gate.
CYCLIC_SCC_ALLOWLIST: tuple[tuple[frozenset[str], str, str], ...] = (
    (
        frozenset(
            {
                "application.adr_service",
                "application.ai_derivation_service",
                "application.ai_proposal_service",
                "application.allocation_settings",
                "application.architecture_decompose_service",
                "application.architecture_service",
                "application.artifact_diff_service",
                "application.artifact_index_projector",
                "application.artifact_indexer",
                "application.artifact_service",
                "application.artifact_summary_service",
                "application.artifact_summary_sweep",
                "application.artifact_vector_store",
                "application.artifact_version_service",
                "application.attribute_definition_service",
                "application.audit_service",
                "application.base",
                "application.baseline_facade",
                "application.cache_invalidation",
                "application.comment_service",
                "application.create_form_config_service",
                "application.effective_permission_service",
                "application.embedding_dispatch",
                "application.event_bus",
                "application.glossary_service",
                "application.goal_service",
                "application.interview_multi_protocol",
                "application.interview_protocol",
                "application.main_goal_service",
                "application.notification_preference_service",
                "application.notification_service",
                "application.optimistic_lock",
                "application.preference_service",
                "application.prompt_resolver",
                "application.prompt_slots",
                "application.quality_auto_assess",
                "application.quality_service",
                "application.release_service",
                "application.requirement_service",
                "application.risk_service",
                "application.search_service",
                "application.settings_service",
                "application.stakeholder_need_service",
                "application.suggestion_adapters",
                "application.suggestion_service",
                "application.tasks",
                "application.test_steps",
                "application.trace_link_service",
                "application.traceability_suggest_service",
                "application.validators",
                "application.vector_port",
                "application.workflow_facade",
            }
        ),
        "2026-11-17",
        "Pre-existing application-service cluster (ServiceBase/event-bus/task "
        "mutual imports). Tracked by a separate decomposition ticket, not by "
        "S4.2 WP-A; freezing it prevents new edges while work continues.",
    ),
    (
        frozenset(
            {
                "application.tier_compute",
                "application.tier_ladder_service",
            }
        ),
        "2026-11-17",
        "Pre-existing tier-compute/tier-ladder two-module cycle; frozen here "
        "so it can be reduced independently of the facade work.",
    ),
)

#: Layer-0 -> application exemptions. Key = source module; value =
#: (added_at, reason, allowed application targets).
LAYER0_TO_APPLICATION_ALLOWLIST: dict[str, tuple[str, str, frozenset[str]]] = {
    "auth_tenancy.apps": (
        "2026-11-17",
        "AppConfig.ready() registers preference keys from the application "
        "registry at startup; bootstrap wiring, not a runtime dependency.",
        frozenset({"application.preference_registry"}),
    ),
    "auth_tenancy.management.commands.bootstrap_admin": (
        "2026-11-17",
        "Seed/management command; seeds are legitimate exemptions (S4.2 WP-A).",
        frozenset({"application.workspace_provisioning"}),
    ),
    "auth_tenancy.management.commands.seed_demo": (
        "2026-11-17",
        "Seed/management command; seeds are legitimate exemptions (S4.2 WP-A).",
        frozenset(
            {"application.attribute_bootstrap", "application.workspace_provisioning"}
        ),
    ),
    "auth_tenancy.management.commands.seed_full_chain": (
        "2026-11-17",
        "Seed/management command; seeds are legitimate exemptions (S4.2 WP-A).",
        frozenset(
            {
                "application.architecture_service",
                "application.baseline_facade",
                "application.change_request_service",
                "application.goal_service",
                "application.requirement_service",
                "application.stakeholder_need_service",
                "application.test_run_service",
                "application.test_service",
                "application.trace_link_service",
                "application.workspace_service",
            }
        ),
    ),
    "auth_tenancy.management.commands.seed_toothbrush": (
        "2026-11-17",
        "Seed/management command; seeds are legitimate exemptions (S4.2 WP-A).",
        frozenset(
            {
                "application.actor_service",
                "application.adr_service",
                "application.architecture_service",
                "application.artifact_attribute_gateway",
                "application.attribute_definition_service",
                "application.glossary_service",
                "application.issue_service",
                "application.requirement_service",
                "application.risk_service",
                "application.test_run_service",
                "application.test_service",
                "application.trace_link_service",
                "application.workspace_service",
            }
        ),
    ),
    "auth_tenancy.resource_scope": (
        "2026-11-17",
        "Resource-scope resolution reuses the read-only workspace_lookup seam.",
        frozenset({"application.workspace_lookup"}),
    ),
    "auth_tenancy.rest_workspace_members": (
        "2026-11-17",
        "R2S-004 exemption: calls ServiceBase._audit for admin audit trail. "
        "Extracting ServiceBase needs an se-architect ADR (out of scope).",
        frozenset({"application.base"}),
    ),
    "auth_tenancy.services.item_permission": (
        "2026-11-17",
        "R2S-004 exemption: inherits/uses ServiceBase RBAC + tenant helpers. "
        "Extraction needs an se-architect ADR (out of scope).",
        frozenset({"application.base"}),
    ),
    "auth_tenancy.services.permission_definition": (
        "2026-11-17",
        "R2S-004 exemption: subclasses ServiceBase. Extraction needs an "
        "se-architect ADR (out of scope).",
        frozenset({"application.base"}),
    ),
    "auth_tenancy.services.preference_service": (
        "2026-11-17",
        "R2S-004 exemption: subclasses ServiceBase for tenant context. "
        "Extraction needs an se-architect ADR (out of scope).",
        frozenset({"application.base"}),
    ),
    "persistence.management.commands.normalize_testcase_steps": (
        "2026-11-17",
        "Seed/management command data backfill; legitimate exemption.",
        frozenset({"application.test_steps"}),
    ),
    "persistence.management.commands.report_requirement_levels": (
        "2026-11-17",
        "Seed/management command reporting helper; legitimate exemption.",
        frozenset({"application.tier_compute"}),
    ),
}


def _assert_no_new_cycles(
    actual: list[frozenset[str]],
    allowlist: tuple[tuple[frozenset[str], str, str], ...],
) -> None:
    """Fail unless every cyclic component is contained in an allowlisted one."""
    allowed = [component for component, _, _ in allowlist]
    for component in sorted(actual, key=sorted):
        if not any(component <= baseline for baseline in allowed):
            raise AssertionError(
                "New module-level import cycle detected: "
                f"{sorted(component)}. Add an entry with added_at/reason only "
                "after an architecture review."
            )


def _assert_no_unexempted_layer_edges(
    actual: set[tuple[str, str]],
    allowlist: dict[str, tuple[str, str, frozenset[str]]],
) -> None:
    """Fail unless every layer-0 -> application edge is allowlisted."""
    for src, target in sorted(actual):
        exemption = allowlist.get(src)
        if exemption is None or target not in exemption[2]:
            raise AssertionError(
                "New layer-0 -> layer-2 import edge detected: "
                f"{src} -> {target}. Add an exemption with added_at/reason "
                "only after an architecture review (or route through a service)."
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_facade_export_surface_is_byte_identical() -> None:
    """R2S-002 safety net: __all__ and registry order must not drift."""
    import application.services as facade

    assert list(facade.__all__) == list(EXPECTED_FACADE_ALL), (
        "application.services.__all__ changed; public surface is a contract."
    )
    assert list(facade._registry) == list(EXPECTED_REGISTRY_KEYS), (
        "application.services._registry insertion order changed; service "
        "discovery order is an implicit contract."
    )
    # An explicit re-export list can list a name in __all__ without actually
    # binding it (a wildcard import used to bind it implicitly). Pin that too.
    unbound = [name for name in facade.__all__ if not hasattr(facade, name)]
    assert not unbound, f"__all__ names not bound on the facade: {unbound}"


def test_facade_uses_explicit_step_reexports() -> None:
    """No wildcard re-export from a stepN shim in the facade or the shims."""
    guarded = [
        _BACKEND_ROOT / "application" / "services.py",
        *_BACKEND_ROOT.glob("application/services_step*.py"),
    ]
    for path in guarded:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not any(alias.name == "*" for alias in node.names), (
                    f"{path.name}: wildcard import from {node.module} is "
                    "forbidden; use explicit named re-exports."
                )


def test_no_new_module_level_import_cycles() -> None:
    """R2S-009: fail-closed against new application module-level cycles."""
    _assert_no_new_cycles(_application_cyclic_sccs(), CYCLIC_SCC_ALLOWLIST)


def test_facade_is_not_part_of_an_import_cycle() -> None:
    """R2S-002 verification: the facade and its shims must be acyclic.

    Before the fix this failed — ``services -> stepN -> services._registry``
    formed the third application SCC. The neutral ``service_registry`` module
    removes the back-import, so none of these modules may appear in a cycle.
    """
    offending = [
        sorted(component & _FACADE_MODULES)
        for component in _application_cyclic_sccs()
        if component & _FACADE_MODULES
    ]
    assert not offending, f"Facade modules still in an import cycle: {offending}"


def test_layer0_does_not_import_application_without_exemption() -> None:
    """R2S-004: fail-closed against new layer-0 -> layer-2 edges."""
    _assert_no_unexempted_layer_edges(
        _layer0_to_application_edges(), LAYER0_TO_APPLICATION_ALLOWLIST
    )


def test_cycle_gate_is_red_on_a_new_artificial_edge() -> None:
    """Proves the SCC gate fails when a genuinely new cycle is introduced."""
    graph = defaultdict(set, _module_graph())
    graph["application._synthetic_cycle_a"].add("application._synthetic_cycle_b")
    graph["application._synthetic_cycle_b"].add("application._synthetic_cycle_a")
    nodes = set(graph) | {
        "application._synthetic_cycle_a",
        "application._synthetic_cycle_b",
    }
    synthetic = _cyclic_sccs(nodes, graph)
    assert any(
        {"application._synthetic_cycle_a", "application._synthetic_cycle_b"}
        <= component
        for component in synthetic
    )
    with pytest.raises(AssertionError, match="New module-level import cycle"):
        _assert_no_new_cycles(synthetic, CYCLIC_SCC_ALLOWLIST)


def test_layer_contract_is_red_on_a_new_artificial_edge() -> None:
    """Proves the layer contract fails on a new unexempted layer-0 edge."""
    edges = _layer0_to_application_edges() | {
        ("auth_tenancy.services.item_permission", "application.glossary_service")
    }
    with pytest.raises(AssertionError, match="New layer-0 -> layer-2 import edge"):
        _assert_no_unexempted_layer_edges(edges, LAYER0_TO_APPLICATION_ALLOWLIST)

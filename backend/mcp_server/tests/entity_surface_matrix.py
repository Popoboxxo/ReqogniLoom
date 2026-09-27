"""The REST/MCP entity-surface contract table (issue #1080).

Why this module exists
----------------------
#1080 was found by a human QA run, not by CI: ``GET /api/v1/test-runs/``
answered 200 with two rows while ``tools/list`` advertised no tool that could
reach a TestRun — ``test.run_list`` was simply not there, and a direct
``test.run_list`` call answered ``-32601 not found in McpTestToolGroup``. The
TestRun was the *only* break; all nine comparable entities (Requirement,
StakeholderNeed, TestCase, Adr, Risk, Issue, GlossaryTerm, ArchitectureElement,
Goal) were symmetric across both transports.

The invariant that was missing is therefore narrow and cheap to state: **every
entity that REST exposes must be readable over MCP.** Not "the same tools" —
the two transports deliberately differ (MCP has ``traceability.vcrm``,
``context.change_impact``, ``test.derive_from_requirement``, none of which have
a REST route) — but *readable*. An entity you can list on one transport and
not the other is invisible to every agent, which is the whole point of MCP.

This module holds the table; ``test_entity_surface_parity.py`` is the executable
form, in the ratchet style of
``attribute_definitions/tests/test_transport_contract_matrix.py``:

* :data:`ENTITY_SPECS` — one row per entity: its REST collection and the MCP
  read tool(s) an agent must have.
* :data:`REST_ONLY_BY_DESIGN` — the entities that are REST-only *on purpose*,
  each with the reason and, where one exists, the decision that says so. A
  deliberate exclusion is a documented decision; an unlisted one is a gap.
* :data:`MCP_ONLY_BY_DESIGN` — the reverse, for the same reason.

Kept as data rather than as assertions because both directions of the check
are data questions: "does this tool exist" and "does this route exist" are
answered against the *live* registry and the *live* URLconf, not against a
hard-coded count that silently rots.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class _Spec:
    """One entity's two-transport surface.

    ``rest_collection`` is the collection path relative to ``/api/v1/``
    (trailing slash included — DRF's ``DefaultRouter`` requires it). It is
    resolved against the live URLconf, so a renamed or removed route fails
    here instead of silently dropping the entity from the matrix.

    ``mcp_reads`` are the tool names an agent needs to *read* the entity: a
    fetch-by-id and a list, because "I know it exists" and "show me all of
    them" are different questions and #1080 was precisely a list that was
    missing. Deliberately not the full tool set — write parity is covered by
    the per-group tests, and asserting it here would make every new write tool
    a matrix edit.

    ``needs_collection_tool`` requires that at least one ``mcp_reads`` entry
    can enumerate the entity *without* an object id. #1080's shape was a
    working fetch-by-id and no list, so a new entity that only has a fetch is
    the regression this catches. It is ``False`` for two pre-existing,
    pre-#1080 gaps that are documented rather than fixed here; the reason is
    mandatory in that case.
    """

    rest_collection: str
    mcp_reads: tuple[str, ...]
    #: Human-readable name of the thing the REST collection and the MCP
    #: tools both speak about, used in assertion messages.
    entity: str = ""
    needs_collection_tool: bool = True
    #: Why the collection tool is missing. Mandatory iff
    #: ``needs_collection_tool`` is ``False``.
    collection_gap: str = ""


#: The entity-surface contract. Keys are stable ids; values carry the two
#: transport locations.
#:
#: Read-tool names are taken from the live ``tools/list`` catalogue
#: (``docs/agent-templates/tool-manifest.json``), verified by
#: ``test_entity_surface_parity.py`` against the live registry on every run —
#: so a name that no longer exists fails loudly here rather than rotting in the
#: table.
ENTITY_SPECS: dict[str, _Spec] = {
    "requirement": _Spec(
        "/api/v1/requirements/",
        ("requirement.get", "requirement.query"),
        "Requirement",
    ),
    "stakeholder_need": _Spec(
        "/api/v1/needs/",
        ("needs.read", "needs.query"),
        "StakeholderNeed",
    ),
    "architecture_element": _Spec(
        "/api/v1/architecture/",
        ("architecture.get", "architecture.query"),
        "ArchitectureElement",
    ),
    "test_case": _Spec(
        "/api/v1/testcases/",
        ("test.get", "test.query"),
        "TestCase",
    ),
    # #1080: the entity this matrix was written for. The four run tools live
    # in the ``test`` group rather than a ``test_run`` prefix -- see the
    # rationale in mcp_server/tools/tests.py's module docstring.
    "test_run": _Spec(
        "/api/v1/test-runs/",
        ("test.run_get", "test.run_list"),
        "TestRun",
    ),
    "adr": _Spec("/api/v1/adrs/", ("adr.read", "adr.query"), "Adr"),
    "risk": _Spec("/api/v1/risks/", ("risk.read", "risk.query"), "Risk"),
    "issue": _Spec("/api/v1/issues/", ("issue.read", "issue.query"), "Issue"),
    "glossary_term": _Spec(
        "/api/v1/glossary/", ("glossary.read", "glossary.query"), "GlossaryTerm"
    ),
    "goal": _Spec("/api/v1/goals/", ("goal.read", "goal.query"), "Goal"),
    "main_goal": _Spec(
        "/api/v1/main-goals/",
        ("main_goal.read", "main_goal.list_versions"),
        "MainGoal",
        # KNOWN GAP, pre-#1080, not fixed here: MCP offers no
        # ``main_goal.query``, so a MainGoal is only reachable by an id or by
        # a lineage id. REST's ``GET /api/v1/main-goals/?workspace_id=``
        # enumerates a workspace's main goals. Same *shape* as #1080 (fetch
        # without list), found by this matrix when it was written — reported
        # in the #1080 sweep and left as a follow-up, because closing it means
        # adding a new tool to a governance-gated group (main_goal is
        # ADMIN-tier), which is a product decision, not a docs fix.
        needs_collection_tool=False,
        collection_gap=(
            "no main_goal.query; only main_goal.read (by id) and "
            "main_goal.list_versions (by lineage_id) exist"
        ),
    ),
    "change_request": _Spec(
        "/api/v1/change-requests/",
        ("change_request.read", "change_request.query"),
        "ChangeRequest",
    ),
    "icd": _Spec("/api/v1/icds/", ("icd.read", "icd.query"), "Icd"),
    "diagram": _Spec(
        "/api/v1/diagrams/", ("diagram.get", "diagram.query"), "Diagram"
    ),
    "artifact": _Spec(
        "/api/v1/artifacts/",
        ("artifact.search", "artifact.get_tree"),
        "Artifact",
    ),
    "trace_link": _Spec(
        "/api/v1/tracelinks/",
        ("traceability.query",),
        "TraceLink",
        # KNOWN GAP, pre-#1080, not fixed here: ``traceability.query`` requires
        # an ``artifact_id``, so MCP can answer "what links does this artifact
        # have" but not "list every link in the workspace", which
        # ``GET /api/v1/tracelinks/?workspace_id=`` does. Reported in the #1080
        # sweep; the closest read-only aggregate that would close it is
        # ``traceability.coverage``, which counts rather than enumerates.
        needs_collection_tool=False,
        collection_gap=(
            "traceability.query needs an artifact_id; no workspace-wide link "
            "enumeration tool exists"
        ),
    ),
    "baseline": _Spec(
        "/api/v1/baselines/", ("baseline.list", "baseline.get"), "Baseline"
    ),
    "interview_session": _Spec(
        "/api/v1/interviews/", ("interview.list", "interview.get"), "InterviewSession"
    ),
    "comment": _Spec("/api/v1/comments/", ("comment.list",), "Comment"),
    "workspace": _Spec(
        "/api/v1/workspaces/", ("workspace.get_context", "workspace.list"), "Workspace"
    ),
    "link_type": _Spec(
        "/api/v1/workspaces/{workspace_id}/link-type-definitions/",
        ("link_type.list", "link_type.get"),
        "WorkspaceLinkType",
    ),
}


@dataclass(frozen=True)
class _Exclusion:
    """A collection/tool that exists on one transport only, with the reason.

    ``reason`` is mandatory and free-form: the value of the list is that the
    judgement is written down, so the next reader does not have to re-derive
    whether the asymmetry is intentional.
    """

    surface: str
    reason: str
    issue: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


#: REST collections deliberately NOT exposed over MCP.
#:
#: Every entry needs a reason. An entity that becomes agent-relevant must be
#: removed from this list *and* added to :data:`ENTITY_SPECS` in the same
#: change -- that is the discipline the list exists to force.
REST_ONLY_BY_DESIGN: tuple[_Exclusion, ...] = (
    _Exclusion(
        "/api/v1/api-keys/",
        "API-key management is a REST-only governance path by decision: MCP "
        "exposes no key-management tool, so a compromised MCP client cannot "
        "mint itself a key. See tool_registry._GOVERNANCE_TOOL_NAMESPACES "
        "and mcp_server/tools/base.py::write_mcp_audit's key-hashing note.",
        issue="#865",
    ),
    _Exclusion(
        "/api/v1/notifications/",
        "The notification feed is human-facing only; agents do not read a "
        "notification centre (Menschen-im-System spec section 5, rest_api/"
        "collaboration_views.py).",
        issue="",
    ),
    _Exclusion(
        "/api/v1/workflows/",
        "Workflow definitions are configuration, served by the dedicated "
        "workflow-definition REST surface and the preset/attribute tooling; "
        "the MCP surface reads item *state* through each entity's own tools "
        "rather than exposing the definition editor.",
        issue="",
    ),
    _Exclusion(
        "/api/v1/search/",
        "SearchViewSet is a REST-only convenience aggregate; the MCP "
        "equivalent is artifact.search, which is listed against Artifact.",
        issue="",
    ),
    _Exclusion(
        "/api/v1/metrics/",
        "KPI aggregation for dashboards; the agent-facing equivalents are "
        "traceability.coverage, context.test_coverage and "
        "workspace.coverage (all read-only MCP tools).",
        issue="",
    ),
    _Exclusion(
        "/api/v1/traceability/",
        "TraceabilityViewSet is a namespaced alias of the TraceLink actions "
        "(impact/path/cycles); those live on /api/v1/tracelinks/ and are "
        "listed against TraceLink.",
        issue="",
    ),
)


#: MCP tools deliberately NOT exposed over REST.
#:
#: The mirror image, and the reason #1085 point 5 exists: ``traceability.vcrm``
#: and ``audit.se_audit`` are findable only in the MCP catalogue, so a reader
#: of the REST/OpenAPI docs never learns the capability exists. Recorded here
#: so the asymmetry is a decision, not an omission.
MCP_ONLY_BY_DESIGN: tuple[_Exclusion, ...] = (
    _Exclusion(
        "traceability.vcrm",
        "Verification Cross Reference Matrix export. MCP-only; the REST "
        "surface has no VCRM route and no OpenAPI operation mentioning "
        "``vcrm``, so REST documentation cannot point at it. Documented in "
        "docs/api/MCP-SURFACE.md.",
        issue="#1085",
    ),
    _Exclusion(
        "traceability.coverage",
        "Coverage aggregation for an agent deciding what to test next. "
        "MCP-only; no REST route.",
        issue="#1001",
    ),
    _Exclusion(
        "audit.se_audit",
        "SE-Auditor run over a workspace. MCP-only; the REST equivalents are "
        "the workspace audit dashboard views, not a VCRM-style named export.",
        issue="#1001",
    ),
    _Exclusion(
        "context.change_impact",
        "LLM-annotated blast-radius analysis built for agent context "
        "assembly. MCP-only by design (needs an LLM provider configured).",
        issue="",
    ),
    _Exclusion(
        "test.derive_from_requirement",
        "Draft/accept test-case derivation. MCP-only: the write path is the "
        "AI derivation surface, REST exposes the resulting TestCase as a "
        "normal CRUD object.",
        issue="",
    ),
)


__all__ = [
    "ENTITY_SPECS",
    "MCP_ONLY_BY_DESIGN",
    "REST_ONLY_BY_DESIGN",
]

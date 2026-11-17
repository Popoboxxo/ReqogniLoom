"""S6.2 part B guard: SE frontmatter coverage, ``open_adrs`` and schemas.

The SE cascade is active, so AGENTS.md requires ``type``, ``scope``, ``status``,
``date`` and ``author_agent`` on every SE document. Files that already carried
a *different* (legacy) frontmatter at migration time are frozen in the
allowlist below: they are owned by other workstreams and were not rewritten.

Stdlib + PyYAML only; reads the repository as data (mirrors the other script
guards).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

# scripts/tests/<file>.py -> parents[2] is the repository root.
REPO_ROOT = Path(__file__).resolve().parents[2]
SE_ROOT = REPO_ROOT / "docs" / "se"
SCHEMA_DIR = REPO_ROOT / "schemas"
MIGRATION = REPO_ROOT / "scripts" / "add_se_frontmatter.py"
REQUIRED_KEYS = ("type", "scope", "status", "date", "author_agent")

# ADR files (part A) and review protocols (part C) use their own frontmatter
# schemas and are excluded by path, not by name.
PATH_EXEMPT_PREFIXES = ("ADR/", "reviews/")

# Frozen at migration time: legacy-frontmatter L1 documents that were NOT
# rewritten (component cards, L3 architecture docs, implementation notes,
# clarification/decomposition drafts). New files must carry the five keys.
FROZEN_LEGACY_ALLOWLIST = frozenset({
    "L1/Gesamtsystem/L1_clarifications_iter-1.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-001_ArtifactService/L3_COMP-AS-001_ArtifactService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-002_RequirementService/L3_COMP-AS-002_RequirementService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-003_ArchitectureService/L3_COMP-AS-003_ArchitectureService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-004_TestService/L3_COMP-AS-004_TestService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-005_TraceLinkService/L3_COMP-AS-005_TraceLinkService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-006_BaselineFacade/L3_COMP-AS-006_BaselineFacade_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-007_WorkflowFacade/L3_COMP-AS-007_WorkflowFacade_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-007_WorkflowFacade/L3_COMP-AS-007_WorkflowFacade_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-008_ExportService/L3_COMP-AS-008_ExportService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-008_ExportService/L3_COMP-AS-008_ExportService_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-009_ImportService/L3_COMP-AS-009_ImportService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-009_ImportService/L3_COMP-AS-009_ImportService_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-010_SearchService/L3_COMP-AS-010_SearchService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-010_SearchService/L3_COMP-AS-010_SearchService_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-011_WebhookDispatcher/L3_COMP-AS-011_WebhookDispatcher_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-011_WebhookDispatcher/L3_COMP-AS-011_WebhookDispatcher_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-012_PresetPolicyService/L3_COMP-AS-012_PresetPolicyService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-012_PresetPolicyService/L3_COMP-AS-012_PresetPolicyService_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-013_AdrService/L3_COMP-AS-013_AdrService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-013_AdrService/L3_COMP-AS-013_AdrService_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-014_RiskService/L3_COMP-AS-014_RiskService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-014_RiskService/L3_COMP-AS-014_RiskService_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-015_IssueService/L3_COMP-AS-015_IssueService_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-015_IssueService/L3_COMP-AS-015_IssueService_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-016_DomainEventBus/L3_COMP-AS-016_DomainEventBus_Architecture.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-016_DomainEventBus/L3_COMP-AS-016_DomainEventBus_Requirements.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-017_TestRunService/COMP-AS-017_TestRunService.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-018_TestResultIngestion/COMP-AS-018_TestResultIngestion.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/Components/COMP-AS-019_ArtifactDiffService/COMP-AS-019_ArtifactDiffService.md",
    "L1/Gesamtsystem/L2/ApplicationServiceSystem/implementation/L2_ApplicationServiceSystem_Impl.md",
    "L1/Gesamtsystem/L2/AuditLogSystem/Components/COMP-AL-001_AuditLogWriter/L3_COMP-AL-001_AuditLogWriter_Architecture.md",
    "L1/Gesamtsystem/L2/AuditLogSystem/Components/COMP-AL-002_AuditLogQuery/L3_COMP-AL-002_AuditLogQuery_Architecture.md",
    "L1/Gesamtsystem/L2/AuditLogSystem/Components/COMP-AL-003_ArchiveLifecycleManager/L3_COMP-AL-003_ArchiveLifecycleManager_Architecture.md",
    "L1/Gesamtsystem/L2/AuthAndTenancySystem/Components/COMP-AT-001_AuthenticationService/L3_COMP-AT-001_AuthenticationService_Architecture.md",
    "L1/Gesamtsystem/L2/AuthAndTenancySystem/Components/COMP-AT-002_AuthorizationService/L3_COMP-AT-002_AuthorizationService_Architecture.md",
    "L1/Gesamtsystem/L2/AuthAndTenancySystem/Components/COMP-AT-003_TenantContextService/L3_COMP-AT-003_TenantContextService_Architecture.md",
    "L1/Gesamtsystem/L2/AuthAndTenancySystem/Components/COMP-AT-004_CredentialAuthenticationService/L3_COMP-AT-004_CredentialAuthenticationService_Architecture.md",
    "L1/Gesamtsystem/L2/AuthAndTenancySystem/Components/COMP-AT-005_ItemPermissionStore/COMP-AT-005_ItemPermissionStore.md",
    "L1/Gesamtsystem/L2/AuthAndTenancySystem/Components/COMP-AT-005_ItemPermissionStore/implementation/L2_COMP-AT-005_ItemPermissionStore_Impl.md",
    "L1/Gesamtsystem/L2/BaselineServiceSystem/Components/COMP-BL-001_DeltaIndexBuilder/L3_COMP-BL-001_DeltaIndexBuilder_Architecture.md",
    "L1/Gesamtsystem/L2/BaselineServiceSystem/Components/COMP-BL-002_DiffEngine/L3_COMP-BL-002_DiffEngine_Architecture.md",
    "L1/Gesamtsystem/L2/BaselineServiceSystem/Components/COMP-BL-003_BaselineStore/L3_COMP-BL-003_BaselineStore_Architecture.md",
    "L1/Gesamtsystem/L2/BaselineServiceSystem/Components/COMP-BL-004_VersionReconstructor/L3_COMP-BL-004_VersionReconstructor_Architecture.md",
    "L1/Gesamtsystem/L2/BaselineServiceSystem/implementation/L2_BaselineServiceSystem_Impl.md",
    "L1/Gesamtsystem/L2/CommentServiceSystem/Components/COMP-CM-001_CommentManager/COMP-CM-001_CommentManager.md",
    "L1/Gesamtsystem/L2/CommentServiceSystem/Components/COMP-CM-002_MentionResolver/COMP-CM-002_MentionResolver.md",
    "L1/Gesamtsystem/L2/CommentServiceSystem/Components/COMP-CM-003_NotificationDispatcher/COMP-CM-003_NotificationDispatcher.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-001_DiagramManager/L3_COMP-DS-001_DiagramManager_Architecture.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-001_DiagramManager/L3_COMP-DS-001_DiagramManager_Requirements.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-002_DiagramValidator/L3_COMP-DS-002_DiagramValidator_Architecture.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-002_DiagramValidator/L3_COMP-DS-002_DiagramValidator_Requirements.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-003_DiagramRenderer/L3_COMP-DS-003_DiagramRenderer_Architecture.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-003_DiagramRenderer/L3_COMP-DS-003_DiagramRenderer_Requirements.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-004_TraceabilityConnector/L3_COMP-DS-004_TraceabilityConnector_Architecture.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-004_TraceabilityConnector/L3_COMP-DS-004_TraceabilityConnector_Requirements.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-005_McpArtifactProvider/L3_COMP-DS-005_McpArtifactProvider_Architecture.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/Components/COMP-DS-005_McpArtifactProvider/L3_COMP-DS-005_McpArtifactProvider_Requirements.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/L2_DiagramServiceSystem_Interfaces.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/L2_DiagramServiceSystem_TestModel.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/implementation/COMP-DS-006_CanvasEditor_Impl.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/implementation/COMP-DS-007_MermaidLiveRenderer_Impl.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/implementation/L2_DiagramServiceSystem_Impl.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/validation/L2_DiagramServiceSystem_TestPlan.md",
    "L1/Gesamtsystem/L2/DiagramServiceSystem/validation/L2_DiagramServiceSystem_Verification.md",
    "L1/Gesamtsystem/L2/IcdManagementSystem/implementation/L2_IcdManagementSystem_Impl.md",
    "L1/Gesamtsystem/L2/LlmAdapterSystem/Components/COMP-LA-001_CapabilityInterface/L3_COMP-LA-001_CapabilityInterface_Architecture.md",
    "L1/Gesamtsystem/L2/LlmAdapterSystem/Components/COMP-LA-002_ProviderRegistry/L3_COMP-LA-002_ProviderRegistry_Architecture.md",
    "L1/Gesamtsystem/L2/LlmAdapterSystem/Components/COMP-LA-003_CapabilityRouter/L3_COMP-LA-003_CapabilityRouter_Architecture.md",
    "L1/Gesamtsystem/L2/LlmAdapterSystem/Components/COMP-LA-004_LlmAuditLogger/L3_COMP-LA-004_LlmAuditLogger_Architecture.md",
    "L1/Gesamtsystem/L2/LlmAdapterSystem/Components/COMP-LA-005_AsyncTaskDispatcher/L3_COMP-LA-005_AsyncTaskDispatcher_Architecture.md",
    "L1/Gesamtsystem/L2/LlmAdapterSystem/implementation/L2_LlmAdapterSystem_Impl.md",
    "L1/Gesamtsystem/L2/McpServerSystem/Components/COMP-MC-001_ProtocolHandler/L3_COMP-MC-001_ProtocolHandler_Architecture.md",
    "L1/Gesamtsystem/L2/McpServerSystem/Components/COMP-MC-002_ToolRegistry/L3_COMP-MC-002_ToolRegistry_Architecture.md",
    "L1/Gesamtsystem/L2/McpServerSystem/Components/COMP-MC-003_RequirementsToolGroup/L3_COMP-MC-003_RequirementsToolGroup_Architecture.md",
    "L1/Gesamtsystem/L2/McpServerSystem/Components/COMP-MC-004_ArchitectureToolGroup/L3_COMP-MC-004_ArchitectureToolGroup_Architecture.md",
    "L1/Gesamtsystem/L2/McpServerSystem/Components/COMP-MC-005_TestToolGroup/L3_COMP-MC-005_TestToolGroup_Architecture.md",
    "L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/COMP-PL-001_EntitySchemaManager/L3_COMP-PL-001_EntitySchemaManager_Architecture.md",
    "L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/COMP-PL-002_TenantIsolationManager/L3_COMP-PL-002_TenantIsolationManager_Architecture.md",
    "L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/COMP-PL-003_TransactionCoordinator/L3_COMP-PL-003_TransactionCoordinator_Architecture.md",
    "L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/COMP-PL-004_SchemaMigrationEngine/L3_COMP-PL-004_SchemaMigrationEngine_Architecture.md",
    "L1/Gesamtsystem/L2/PersistenceLayerSystem/Components/COMP-PL-005_PerformanceOptimizationLayer/L3_COMP-PL-005_PerformanceOptimizationLayer_Architecture.md",
    "L1/Gesamtsystem/L2/PersistenceLayerSystem/implementation/L2_PersistenceLayerSystem_Impl.md",
    "L1/Gesamtsystem/L2/PresetConfigEngineSystem/Components/COMP-PC-001_PresetRegistry/L3_COMP-PC-001_PresetRegistry_Architecture.md",
    "L1/Gesamtsystem/L2/PresetConfigEngineSystem/Components/COMP-PC-002_TerminologyProfileService/L3_COMP-PC-002_TerminologyProfileService_Architecture.md",
    "L1/Gesamtsystem/L2/PresetConfigEngineSystem/Components/COMP-PC-003_FeatureGateService/L3_COMP-PC-003_FeatureGateService_Architecture.md",
    "L1/Gesamtsystem/L2/ReactFrontendSystem/Components/COMP-RF-001_NavigationShell/L3_COMP-RF-001_NavigationShell_Architecture.md",
    "L1/Gesamtsystem/L2/ReactFrontendSystem/Components/COMP-RF-002_DashboardViews/L3_COMP-RF-002_DashboardViews_Architecture.md",
    "L1/Gesamtsystem/L2/ReactFrontendSystem/Components/COMP-RF-003_RequirementEditors/L3_COMP-RF-003_RequirementEditors_Architecture.md",
    "L1/Gesamtsystem/L2/ReactFrontendSystem/Components/COMP-RF-004_ArchitectureEditors/L3_COMP-RF-004_ArchitectureEditors_Architecture.md",
    "L1/Gesamtsystem/L2/ReqIFServiceSystem/Components/COMP-RQ-001_ReqIFParser/COMP-RQ-001_ReqIFParser.md",
    "L1/Gesamtsystem/L2/ReqIFServiceSystem/Components/COMP-RQ-002_ReqIFSerializer/COMP-RQ-002_ReqIFSerializer.md",
    "L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/COMP-RA-001_HttpEndpointController/L3_COMP-RA-001_HttpEndpointController_Architecture.md",
    "L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/COMP-RA-002_DataSerializer/L3_COMP-RA-002_DataSerializer_Architecture.md",
    "L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/COMP-RA-003_AuthEnforcer/L3_COMP-RA-003_AuthEnforcer_Architecture.md",
    "L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/COMP-RA-004_PresetGuard/L3_COMP-RA-004_PresetGuard_Architecture.md",
    "L1/Gesamtsystem/L2/RestApiAdapterSystem/Components/COMP-RA-005_OpenApiGenerator/L3_COMP-RA-005_OpenApiGenerator_Architecture.md",
    "L1/Gesamtsystem/L2/RestApiAdapterSystem/implementation/L2_RestApiAdapterSystem_Impl.md",
    "L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-001_MetricsQueryController/L3_COMP-SM-001_MetricsQueryController_Architecture.md",
    "L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-002_MetricsAggregator/L3_COMP-SM-002_MetricsAggregator_Architecture.md",
    "L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-003_VolatilityCalculator/L3_COMP-SM-003_VolatilityCalculator_Architecture.md",
    "L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-004_CoverageCalculator/L3_COMP-SM-004_CoverageCalculator_Architecture.md",
    "L1/Gesamtsystem/L2/SeMetricsSystem/Components/COMP-SM-005_WorkflowGapDetector/L3_COMP-SM-005_WorkflowGapDetector_Architecture.md",
    "L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/COMP-TE-001_TraceLinkManager/L3_COMP-TE-001_TraceLinkManager_Architecture.md",
    "L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/COMP-TE-002_QueryEngine/L3_COMP-TE-002_QueryEngine_Architecture.md",
    "L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/COMP-TE-003_CoverageCalculator/L3_COMP-TE-003_CoverageCalculator_Architecture.md",
    "L1/Gesamtsystem/L2/TraceabilityEngineSystem/Components/COMP-TE-004_VCRMReportGenerator/L3_COMP-TE-004_VCRMReportGenerator_Architecture.md",
    "L1/Gesamtsystem/L2/TraceabilityEngineSystem/implementation/L2_TraceabilityEngineSystem_Impl.md",
    "L1/Gesamtsystem/L2/VectorSearchServiceSystem/Components/COMP-VS-001_VectorSearchEngine/COMP-VS-001_VectorSearchEngine.md",
    "L1/Gesamtsystem/L2/VectorSearchServiceSystem/Components/COMP-VS-002_EmbeddingPipeline/COMP-VS-002_EmbeddingPipeline.md",
    "L1/Gesamtsystem/L2/VectorSearchServiceSystem/Components/COMP-VS-003_HybridQueryRouter/COMP-VS-003_HybridQueryRouter.md",
    "L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/COMP-WE-001_WorkflowDefinitionStore/L3_COMP-WE-001_WorkflowDefinitionStore_Architecture.md",
    "L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/COMP-WE-002_TransitionValidator/L3_COMP-WE-002_TransitionValidator_Architecture.md",
    "L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/COMP-WE-003_StateLifecycleManager/L3_COMP-WE-003_StateLifecycleManager_Architecture.md",
    "L1/Gesamtsystem/L2/WorkflowEngineSystem/Components/COMP-WE-004_SignatureGateVerifier/L3_COMP-WE-004_SignatureGateVerifier_Architecture.md",
    "L1/Gesamtsystem/L2_architectural_decomposition.critic.final.md",
    "L1/Gesamtsystem/L2_architectural_decomposition.critic.iter-1.md",
    "L1/Gesamtsystem/L2_architectural_decomposition_iter-1.md",
    "L1/Gesamtsystem/validation/L1_Gesamtsystem_Validation.md",
})


def _load_migration() -> ModuleType:
    """Load the migration helper as a module (dataclasses need sys.modules)."""
    spec = importlib.util.spec_from_file_location("add_se_frontmatter", MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_migration()


def _frontmatter(path: Path) -> dict[str, object] | None:
    """Parse the leading YAML frontmatter of ``path`` into a dict, if present."""
    text = MODULE.read_text(path)
    lines = MODULE.frontmatter_block(text)
    if lines is None:
        return None
    data = yaml.safe_load("".join(lines[1:-1]))
    return data if isinstance(data, dict) else None


def _se_docs():
    """Yield ``(absolute_path, repository_relative_posix_path)`` for SE docs."""
    for path in sorted(SE_ROOT.rglob("*.md")):
        yield path, path.relative_to(SE_ROOT).as_posix()


def test_every_se_doc_has_required_frontmatter() -> None:
    """All non-exempt SE documents carry the five normative frontmatter keys."""
    checked = 0
    failures: list[str] = []
    for path, rel in _se_docs():
        if rel.startswith(PATH_EXEMPT_PREFIXES) or rel in FROZEN_LEGACY_ALLOWLIST:
            continue
        checked += 1
        frontmatter = _frontmatter(path)
        if frontmatter is None:
            failures.append(f"{rel}: missing leading YAML frontmatter")
            continue
        missing = [key for key in REQUIRED_KEYS if key not in frontmatter]
        if missing:
            failures.append(f"{rel}: missing keys {missing}")
    assert checked > 100, f"guard became vacuous: only {checked} files checked"
    # F-B1: the frozen legacy exemption must never grow silently.
    assert len(FROZEN_LEGACY_ALLOWLIST) <= 119, (
        f"legacy allowlist grew to {len(FROZEN_LEGACY_ALLOWLIST)} — add a "
        "shrink decision instead of hiding new violations"
    )
    for rel in FROZEN_LEGACY_ALLOWLIST:
        path = SE_ROOT / rel
        if not path.exists():
            continue  # file removed — allowlist should be pruned in a follow-up
        fm = _frontmatter(path)
        assert fm is not None and any(k not in fm for k in REQUIRED_KEYS), (
            f"{rel} is in the frozen allowlist but now compliant — remove it "
            "so the list only shrinks"
        )
    assert not failures, "frontmatter violations:\n" + "\n".join(failures)


def test_all_req_docs_have_open_adrs() -> None:
    """Every SE requirement document declares ``open_adrs`` (possibly empty)."""
    req_docs: list[str] = []
    failures: list[str] = []
    for path, rel in _se_docs():
        frontmatter = _frontmatter(path)
        is_req = MODULE.is_req_name(path.name) or (
            frontmatter is not None
            and str(frontmatter.get("type", "")).upper() == "REQ"
        )
        if not is_req:
            continue
        req_docs.append(rel)
        if frontmatter is None or "open_adrs" not in frontmatter:
            failures.append(f"{rel}: missing open_adrs")
    assert len(req_docs) > 100, f"guard became vacuous: only {len(req_docs)} REQ docs"
    assert not failures, "open_adrs violations:\n" + "\n".join(failures)


@pytest.mark.parametrize(
    ("filename", "required"),
    [
        (
            "se-adr.schema.json",
            ["adr_id", "title", "status", "date", "deciders", "affected_reqs", "superseded_by"],
        ),
        (
            "se-review.schema.json",
            ["review_id", "target_req", "iteration", "status", "date", "reviewer", "findings"],
        ),
    ],
)
def test_schema_files_exist_and_parse(filename: str, required: list[str]) -> None:
    """Both SE schemas exist, are valid JSON and declare the documented fields."""
    path = SCHEMA_DIR / filename
    assert path.is_file(), f"missing schema {path}"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("type") == "object"
    assert isinstance(data.get("properties"), dict)
    assert isinstance(data.get("required"), list)
    for key in required:
        assert key in data["properties"], f"{filename}: missing property {key}"
        assert key in data["required"], f"{filename}: required lacks {key}"


def test_migration_is_idempotent_on_temp_copy(tmp_path: Path) -> None:
    """A second migration run changes nothing, including BOM and legacy bodies."""
    cell = tmp_path / "L1" / "Gesamtsystem"
    cell.mkdir(parents=True)
    adr = tmp_path / "ADR"
    adr.mkdir()

    files = {
        cell / "REQ-X_Requirements.md": "# Req\n\nRequirement body.\n",
        cell / "Plain.md": "# Plain\n\nUnchanged body.\n",
        cell / "Legacy_Requirements.md": (
            "---\nstep: requirements\nagent: se-requirements\nstatus: done\n---\n"
            "# Legacy\n\nKeep this body exactly.\n"
        ),
        cell / "REQ-L2-RF-209_sample.md": "# S6.1\n\nOwned elsewhere.\n",
        cell / "Already.md": (
            "---\ntype: ARCH\nscope: already\nstatus: draft\n"
            "date: 2026-11-17\nauthor_agent: human\nopen_adrs: []\n---\n# Already\n"
        ),
        adr / "ADR-999_owned.md": "# ADR\n\nPart A owns this.\n",
    }
    for path, body in files.items():
        path.write_text(body, encoding="utf-8")
    bom_path = tmp_path / "VV_Bom.md"
    bom_path.write_bytes(b"\xef\xbb\xbf# Bom\n\nBody.\n")

    before = {path: path.read_bytes() for path in list(files) + [bom_path]}

    first = MODULE.migrate(tmp_path)
    assert len(first.frontmatter_added) == 3
    assert len(first.open_adrs_added) == 1
    assert len(first.excluded) == 2
    assert first.changed == 4

    # Generated frontmatter on a REQ file includes open_adrs; the body is kept.
    req_text = (cell / "REQ-X_Requirements.md").read_text(encoding="utf-8")
    assert req_text.startswith("---\ntype: REQ\n")
    assert "open_adrs: []" in req_text.split("---", 2)[1]
    assert req_text.endswith("# Req\n\nRequirement body.\n")

    # Legacy frontmatter gets exactly one inserted key; its body is untouched.
    legacy_text = (cell / "Legacy_Requirements.md").read_text(encoding="utf-8")
    assert legacy_text.count("open_adrs: []") == 1
    assert legacy_text.startswith("---\nstep: requirements\n")
    assert legacy_text.endswith("# Legacy\n\nKeep this body exactly.\n")

    # BOM is stripped and excluded files are never touched.
    assert not bom_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert (cell / "REQ-L2-RF-209_sample.md").read_bytes() == before[cell / "REQ-L2-RF-209_sample.md"]
    assert (adr / "ADR-999_owned.md").read_bytes() == before[adr / "ADR-999_owned.md"]

    after_first = {path: path.read_bytes() for path in list(files) + [bom_path]}

    second = MODULE.migrate(tmp_path)
    assert second.frontmatter_added == []
    assert second.open_adrs_added == []
    assert second.changed == 0
    after_second = {path: path.read_bytes() for path in list(files) + [bom_path]}
    assert after_second == after_first

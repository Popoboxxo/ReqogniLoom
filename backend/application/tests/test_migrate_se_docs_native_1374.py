"""``migrate_se_docs`` on the native row path (plan F1.3-T3, issue #1374).

Three properties are pinned here:

1. heading-derived bodies reach the database byte-exactly — the command no
   longer escapes multi-line text for the CSV transport, so a ``#``-prefixed
   line in a body is stored as-is;
2. one source document = one ``ImportService.import_rows`` call = one
   transaction, so a document that fails is reported as a WARNING while its
   neighbours still import;
3. ``--repair-hash-indent`` removes the ``'\\n #'`` scar that the removed CSV
   escaping helper left in already-migrated descriptions — ``--dry-run`` only
   counts, ``--apply`` writes one new artifact version per artifact and never
   touches an artifact whose ``uid`` does not derive from ``docs/se``.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest
from django.core.management import call_command

from application.import_service import ImportService
from auth_tenancy.provisioning import DEFAULT_WORKSPACE_ID
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import ArtifactVersion, Requirement, Workspace

pytestmark = pytest.mark.django_db


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(tmp_path: Path, **options) -> str:
    out = io.StringIO()
    call_command(
        "migrate_se_docs",
        docs_root=str(tmp_path),
        stdout=out,
        stderr=io.StringIO(),
        **options,
    )
    return out.getvalue()


def test_imported_description_matches_the_markdown_body(tmp_path):
    """A body line starting with ``#`` is stored verbatim (no transport scar)."""
    body = "The template uses:\n#comment\n- item | pipe, comma \"quote\""
    _write(
        tmp_path / "L1" / "Gesamtsystem" / "L1_Gesamtsystem_Requirements.md",
        "# System Requirements\n\n"
        "### REQ-L1-101: Comment syntax\n"
        f"{body}\n",
    )
    call_command("seed_demo")

    _run(tmp_path)

    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)
    set_request_tenant(workspace.tenant_id)
    try:
        requirement = Requirement.objects.get(
            uid="REQ-L1-101", artifact__workspace_id=workspace.id
        )
        assert requirement.description == body
        assert " #comment" not in requirement.description
    finally:
        clear_request_tenant()


def test_one_call_per_source_file_and_a_broken_document_only_warns(
    tmp_path, monkeypatch
):
    """A failing document is isolated: the good document still imports."""
    good = tmp_path / "L1" / "Gesamtsystem" / "L1_Gesamtsystem_Requirements.md"
    broken = tmp_path / "L1" / "Gesamtsystem" / "L1_Gesamtsystem_Broken_Requirements.md"
    _write(good, "# Good\n\n### REQ-L1-201: Good requirement\nBody.\n")
    # A heading whose title is empty after stripping -> fails row validation in
    # ImportService, i.e. at the import seam, not in this command's parser.
    _write(broken, "# Broken\n\n### REQ-L1-202: \nBody.\n")

    original = ImportService.import_rows
    calls: list[tuple[str, list[str]]] = []

    def _spy(self, rows, entity_type, workspace_id, ctx, *args, **kwargs):
        calls.append((entity_type, [row.get("uid", "") for row in rows]))
        return original(self, rows, entity_type, workspace_id, ctx, *args, **kwargs)

    monkeypatch.setattr(ImportService, "import_rows", _spy)
    call_command("seed_demo")

    output = _run(tmp_path)

    requirement_calls = [call for call in calls if call[0] == "Requirement"]
    # Two source documents -> two calls, each carrying only its own rows.
    assert len(requirement_calls) == 2
    assert sorted(call[1] for call in requirement_calls) == [
        ["REQ-L1-201"],
        ["REQ-L1-202"],
    ]

    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)
    set_request_tenant(workspace.tenant_id)
    try:
        assert Requirement.objects.filter(
            uid="REQ-L1-201", artifact__workspace_id=workspace.id
        ).exists()
        assert not Requirement.objects.filter(
            uid="REQ-L1-202", artifact__workspace_id=workspace.id
        ).exists()
    finally:
        clear_request_tenant()

    # The failure is reported, and reported as a WARNING (not an abort).
    assert "WARNINGS" in output
    assert "L1_Gesamtsystem_Broken_Requirements.md" in output
    assert "Required field 'title'" in output


def _scarred_requirement(workspace, uid: str, description: str) -> Requirement:
    """Point *description* at an existing Requirement (simulates an old import)."""
    set_request_tenant(workspace.tenant_id)
    try:
        Requirement.objects.filter(
            uid=uid, artifact__workspace_id=workspace.id
        ).update(description=description)
        return Requirement.objects.get(
            uid=uid, artifact__workspace_id=workspace.id
        )
    finally:
        clear_request_tenant()


def test_file_above_the_row_limit_is_chunked_with_a_warning(tmp_path, monkeypatch):
    """A document above ``_MAX_ROWS_PER_CALL`` is chunked, and says so."""
    from application.management.commands import migrate_se_docs as command_module

    monkeypatch.setattr(command_module, "_MAX_ROWS_PER_CALL", 2)
    headings = "".join(
        f"### REQ-L1-30{index}: Row {index}\nBody {index}.\n\n" for index in range(3)
    )
    _write(
        tmp_path / "L1" / "Gesamtsystem" / "L1_Gesamtsystem_Requirements.md",
        f"# System Requirements\n\n{headings}",
    )
    call_command("seed_demo")

    output = _run(tmp_path)

    assert "3 rows exceed the 2-row import limit" in output
    assert "2 chunks" in output

    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)
    set_request_tenant(workspace.tenant_id)
    try:
        assert (
            Requirement.objects.filter(
                uid__in=["REQ-L1-300", "REQ-L1-301", "REQ-L1-302"],
                artifact__workspace_id=workspace.id,
            ).count()
            == 3
        )
    finally:
        clear_request_tenant()


def test_repair_hash_indent_dry_run_reports_only(tmp_path):
    """``--dry-run`` counts the candidates and writes nothing."""
    _write(
        tmp_path / "L1" / "Gesamtsystem" / "L1_Gesamtsystem_Requirements.md",
        "# System Requirements\n\n### REQ-L1-401: Migrated\nBody.\n",
    )
    call_command("seed_demo")
    _run(tmp_path)

    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)
    scarred = "Body.\n #Heading\nMore."
    requirement = _scarred_requirement(workspace, "REQ-L1-401", scarred)
    set_request_tenant(workspace.tenant_id)
    try:
        versions_before = ArtifactVersion.objects.filter(
            artifact_id=requirement.artifact_id
        ).count()
    finally:
        clear_request_tenant()

    # A hand-maintained artifact whose uid does NOT derive from docs/se must
    # never be a candidate, even though it carries the same pattern.
    set_request_tenant(workspace.tenant_id)
    try:
        ImportService().import_rows(
            [{"title": "Hand made", "uid": "REQ-HAND-1"}],
            "Requirement",
            workspace.id,
            _admin_ctx(workspace),
        )
        hand_made = Requirement.objects.get(
            uid="REQ-HAND-1", artifact__workspace_id=workspace.id
        )
        Requirement.objects.filter(id=hand_made.id).update(
            description="Hand written.\n #Not a scar."
        )
        hand_made.refresh_from_db()
        hand_made_versions = ArtifactVersion.objects.filter(
            artifact_id=hand_made.artifact_id
        ).count()
    finally:
        clear_request_tenant()

    output = _run(tmp_path, repair_hash_indent=True)

    assert "candidates=1 repaired=0" in output
    assert "no data was written" in output

    set_request_tenant(workspace.tenant_id)
    try:
        assert (
            Requirement.objects.get(id=requirement.id).description == scarred
        )
        assert (
            Requirement.objects.get(id=hand_made.id).description
            == "Hand written.\n #Not a scar."
        )
        assert (
            ArtifactVersion.objects.filter(
                artifact_id=requirement.artifact_id
            ).count()
            == versions_before
        )
        assert (
            ArtifactVersion.objects.filter(
                artifact_id=hand_made.artifact_id
            ).count()
            == hand_made_versions
        )
    finally:
        clear_request_tenant()


def test_repair_hash_indent_apply_creates_one_new_version(tmp_path):
    """``--apply`` rewrites the scar through the service (one new version)."""
    _write(
        tmp_path / "L1" / "Gesamtsystem" / "L1_Gesamtsystem_Requirements.md",
        "# System Requirements\n\n### REQ-L1-501: Migrated\nBody.\n",
    )
    call_command("seed_demo")
    _run(tmp_path)

    workspace = Workspace.unscoped.get(id=DEFAULT_WORKSPACE_ID)
    requirement = _scarred_requirement(
        workspace, "REQ-L1-501", "Body.\n #Heading\nMore."
    )
    set_request_tenant(workspace.tenant_id)
    try:
        versions_before = ArtifactVersion.objects.filter(
            artifact_id=requirement.artifact_id
        ).count()
    finally:
        clear_request_tenant()

    output = _run(tmp_path, repair_hash_indent=True, apply=True)

    assert "candidates=1 repaired=1" in output
    assert "no data was written" not in output

    set_request_tenant(workspace.tenant_id)
    try:
        repaired = Requirement.objects.get(id=requirement.id)
        assert repaired.description == "Body.\n#Heading\nMore."
        versions_after = ArtifactVersion.objects.filter(
            artifact_id=requirement.artifact_id
        )
        assert versions_after.count() == versions_before + 1
        latest = versions_after.order_by("-revision").first()
        assert latest.change_reason == "F5 repair"
    finally:
        clear_request_tenant()


def _admin_ctx(workspace):
    """Minimal admin AuthContext for direct service calls in test setup."""
    from auth_tenancy.context import AuthContext, AuthMethod
    from auth_tenancy.models import ROLE_ADMIN
    from persistence.models import User

    user = User.objects.get(username="admin")
    return AuthContext(
        user_id=user.id,
        tenant_id=workspace.tenant_id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
        tenant_name=getattr(workspace.tenant, "name", ""),
    )

"""
ARCH-L1-011 AuthAndTenancy — seed_demo management command tests (REQ-L1-010).

Verifies the demo seed is idempotent and provisions a working admin login, and
that the built-in demo password is refused unless explicitly opted into
(issue #89).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
import yaml
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from attribute_definitions.models import (
    GlobalAttributeDefinition,
    WorkspaceAttributeDefinition,
)
from auth_tenancy.models import ROLE_ADMIN, ROLE_EDITOR, UserRole
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace
from workflow.models import GlobalWorkflowDefinition, WorkflowEngineDefinition

#: Exact refusal message required by issue #89 / ENT-D9 = B.
REFUSAL_MESSAGE = (
    "seed_demo refuses the built-in demo password; set SYSTEM_ADMIN_PASSWORD "
    "or SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1 (test only)."
)

_ALLOW_DEFAULT_PASSWORD_ENV = "SEED_DEMO_ALLOW_DEFAULT_PASSWORD"

#: Plan E / WP E3.8 (#1308): opt-in MFA E2E account.
_E2E_MFA_PASSWORD_ENV = "E2E_MFA_PASSWORD"
_E2E_MFA_USERNAME = "e2e-mfa"

# backend/auth_tenancy/tests/test_seed_demo.py ->
#   parents[0] = tests/  parents[1] = auth_tenancy/  parents[2] = backend/
#   parents[3] = repo root
# On the host that is <repo>; inside the test container the mounted backend
# lives at /app, so it resolves to / and the deploy files are absent. The guard
# therefore SKIPS there instead of erroring — same pattern as
# backend/tests/test_bluepencil_deploy_contract.py.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROD_COMPOSE = _REPO_ROOT / "deploy" / "docker-compose.yml"
_MINIMAL_COMPOSE = _REPO_ROOT / "deploy" / "docker-compose.minimal.yml"
_DEV_OVERRIDE_COMPOSE = _REPO_ROOT / "deploy" / "docker-compose.override.yml"
_COMPOSE_FILES = [_PROD_COMPOSE, _MINIMAL_COMPOSE, _DEV_OVERRIDE_COMPOSE]


@pytest.fixture(autouse=True)
def _allow_default_password(monkeypatch):
    """Opt in to the built-in demo password for this module's legacy cases.

    Every test below that exercises the *default* password path would
    otherwise be refused by the issue-#89 guard. The guard-specific tests
    delete this variable again to prove the refusal.
    """
    monkeypatch.setenv(_ALLOW_DEFAULT_PASSWORD_ENV, "1")
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv(_E2E_MFA_PASSWORD_ENV, raising=False)


def _seeded_counts(tenant_id) -> dict[str, int]:
    """Row counts for every entity ``seed_demo`` provisions.

    Covers persistence rows (tenant/workspace/user/role) AND the definition rows
    the command seeds (workflow + attribute definitions). Tenant-scoped models
    are counted under an active tenant context (``objects`` is tenant-filtered).
    """
    set_request_tenant(tenant_id)
    try:
        admin = User.objects.get(username="admin")
        return {
            "tenants": Tenant.objects.filter(slug="demo").count(),
            "users": User.objects.filter(username="admin").count(),
            "workspaces": Workspace.objects.filter(name="Demo Workspace").count(),
            "user_roles": UserRole.objects.filter(
                user=admin, role=ROLE_ADMIN
            ).count(),
            "workflow_engine_definitions": WorkflowEngineDefinition.objects.count(),
            "global_workflow_definitions": GlobalWorkflowDefinition.objects.count(),
            "global_attribute_definitions": GlobalAttributeDefinition.objects.count(),
            "workspace_attribute_definitions": (
                WorkspaceAttributeDefinition.objects.count()
            ),
        }
    finally:
        clear_request_tenant()


def _canonical(value) -> str:
    """Stable, key-order-insensitive serialization of a JSON-ish value."""
    return json.dumps(value, sort_keys=True, default=str)


def _env_keys(environment) -> set[str]:
    """Environment variable names of a compose service, dict or list form."""
    if isinstance(environment, dict):
        return {str(key) for key in environment}
    if isinstance(environment, list):
        return {str(entry).split("=", 1)[0] for entry in environment}
    return set()


class _ComposeLoader(yaml.SafeLoader):
    """``SafeLoader`` that tolerates Compose's own YAML tags.

    ``deploy/docker-compose.override.yml`` uses ``!override`` / ``!reset``,
    which plain ``safe_load`` rejects. These tags only change how Compose MERGES
    a document; for this guard the underlying value is all that matters, so the
    tag is simply ignored.
    """


def _compose_node(loader: yaml.SafeLoader, _tag_suffix: str, node: yaml.Node):
    """Construct the tagged node by its ordinary type, ignoring the tag."""
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_scalar(node)


_ComposeLoader.add_multi_constructor("!", _compose_node)


def _load_compose(compose_path: Path) -> dict:
    """Parse a deploy compose file, tolerating Compose-specific tags."""
    return yaml.load(  # noqa: S506 — SafeLoader subclass, no arbitrary objects
        compose_path.read_text(encoding="utf-8"), Loader=_ComposeLoader
    )


def _seeded_content_signature(tenant_id, workspace_id) -> dict:
    """Canonical CONTENT signature of every definition ``seed_demo`` seeds.

    Row counts alone cannot prove "run twice -> identical end state": a re-run
    that rewrote a definition in place would leave the counts unchanged and slip
    through. This captures the canonical content instead:

    * ``GlobalAttributeDefinition`` — ``definition_json`` + ``version`` per
      ``(item_type, preset)``.
    * ``WorkspaceAttributeDefinition`` — ``definition_json`` + ``is_customized``
      + ``version`` per ``(workspace_id, item_type)``. Empty on a fresh tenant
      today (``GlobalAttributeDefinitionStore.initialize`` creates globals only),
      but included so the net stays complete if materialization ever changes.
    * ``WorkflowEngineDefinition`` — the ``states`` / ``transitions`` lists per
      ``item_type`` for the seeded workspace.
    """
    set_request_tenant(tenant_id)
    try:
        return {
            "global_attribute_definitions": {
                (obj.item_type, obj.preset): {
                    "definition_json": _canonical(obj.definition_json),
                    "version": obj.version,
                }
                for obj in GlobalAttributeDefinition.objects.order_by(
                    "item_type", "preset"
                )
            },
            "workspace_attribute_definitions": {
                (str(obj.workspace_id), obj.item_type): {
                    "definition_json": _canonical(obj.definition_json),
                    "is_customized": obj.is_customized,
                    "version": obj.version,
                }
                for obj in WorkspaceAttributeDefinition.objects.order_by(
                    "workspace_id", "item_type"
                )
            },
            "workflow_engine_definitions": {
                obj.item_type: {
                    "states": _canonical(obj.workflow_json.get("states")),
                    "transitions": _canonical(obj.workflow_json.get("transitions")),
                }
                for obj in WorkflowEngineDefinition.objects.filter(
                    workspace_id=workspace_id
                ).order_by("item_type")
            },
        }
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_creates_admin_and_is_idempotent():
    call_command("seed_demo")

    assert Tenant.objects.filter(slug="demo").count() == 1
    assert User.objects.filter(username="admin").count() == 1

    tenant = Tenant.objects.get(slug="demo")
    set_request_tenant(tenant.id)
    try:
        assert Workspace.objects.filter(name="Demo Workspace").count() == 1
        workspace = Workspace.objects.get(name="Demo Workspace")
        admin = User.objects.get(username="admin")
        assert UserRole.objects.filter(user=admin, role=ROLE_ADMIN).count() == 1
    finally:
        clear_request_tenant()

    # Snapshot the COMPLETE seeded end state after the first run: row counts
    # AND the canonical content of every seeded definition.
    first_counts = _seeded_counts(tenant.id)
    assert first_counts["workflow_engine_definitions"] >= 1
    assert first_counts["global_attribute_definitions"] >= 1

    first_signature = _seeded_content_signature(tenant.id, workspace.id)
    assert first_signature["global_attribute_definitions"]
    assert first_signature["workflow_engine_definitions"]

    call_command("seed_demo")  # second run must not duplicate anything

    # ... and assert an IDENTICAL end state: same counts AND byte-identical
    # content (a re-run that rewrote a definition in place would fail here even
    # though the row counts stayed the same).
    assert _seeded_counts(tenant.id) == first_counts
    assert _seeded_content_signature(tenant.id, workspace.id) == first_signature


@pytest.mark.django_db
def test_seed_demo_bootstraps_attribute_definitions():
    """#29: seed_demo must seed the tenant's global attribute definitions.

    A database populated only via ``seed_demo`` previously had zero
    ``GlobalAttributeDefinition`` rows, so the custom-fields/attribute feature
    rendered empty. ``application.self_init`` already bootstrapped them;
    ``seed_demo`` now reuses the same shared helper.
    """
    call_command("seed_demo")

    tenant = Tenant.objects.get(slug="demo")
    set_request_tenant(tenant.id)
    try:
        assert (
            GlobalAttributeDefinition.objects.filter(
                tenant_id=tenant.id
            ).count()
            >= 1
        )
        # The gap is only truly closed if a real, populated definition exists
        # for a key the artifact forms actually resolve.
        requirement = GlobalAttributeDefinition.objects.filter(
            tenant_id=tenant.id, item_type="Requirement", preset="standard"
        ).first()
        assert requirement is not None
        assert requirement.definition_json.get("attributes")
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_initializes_workflow_definitions():
    """#41: seed_demo left workflow definitions empty (states=[], transitions=[],
    initialized=True) until a separate POST /workflows/definition/initialize/
    per entity type. Same fix application.self_init.run_self_init() already
    applies after its own provision_admin() call."""
    from auth_tenancy.provisioning import DEFAULT_WORKSPACE_ID
    from workflow.services import get_definition

    call_command("seed_demo")

    set_request_tenant(Tenant.objects.get(slug="demo").id)
    try:
        # Raises WorkflowDefinitionError if unconfigured -- the bug this
        # regression guards against.
        definition = get_definition(
            workspace_id=DEFAULT_WORKSPACE_ID, item_type="Requirement"
        )
        assert definition.states, "Requirement workflow has no states"
        assert definition.transitions, "Requirement workflow has no transitions"
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_admin_password_is_usable(monkeypatch):
    # Default password when no admin-password env var is set.
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")
    admin = User.objects.get(username="admin")
    assert admin.check_password("admin12345") is True
    assert admin.is_active is True


@pytest.mark.django_db
def test_seed_demo_is_create_only_by_default(monkeypatch):
    """A second seed_demo run must not overwrite a changed password."""
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")

    admin = User.objects.get(username="admin")
    admin.set_password("changed-via-ui")
    admin.save(update_fields=["password", "modified_at"])

    call_command("seed_demo")  # default is create-only

    admin.refresh_from_db()
    assert admin.check_password("changed-via-ui") is True


@pytest.mark.django_db
def test_seed_demo_reset_password_flag_reapplies(monkeypatch):
    """--reset-password re-applies the demo password on an existing user."""
    monkeypatch.delenv("SYSTEM_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("DEMO_ADMIN_PASSWORD", raising=False)
    call_command("seed_demo")

    admin = User.objects.get(username="admin")
    admin.set_password("changed-via-ui")
    admin.save(update_fields=["password", "modified_at"])

    call_command("seed_demo", "--reset-password")

    admin.refresh_from_db()
    assert admin.check_password("admin12345") is True


# ---------------------------------------------------------------------------
# Issue #89 / ENT-D9 = B — the built-in demo password needs an explicit opt-in
# (SEED_DEMO_ALLOW_DEFAULT_PASSWORD=1), independent of DEBUG.
# ---------------------------------------------------------------------------


def test_refuses_default_password_without_debug(monkeypatch):
    """No env password + no opt-in => refuse instead of a known credential."""
    monkeypatch.delenv(_ALLOW_DEFAULT_PASSWORD_ENV, raising=False)

    with override_settings(DEBUG=False):
        with pytest.raises(CommandError) as excinfo:
            call_command("seed_demo")

    assert str(excinfo.value) == REFUSAL_MESSAGE


@override_settings(DEBUG=True)
def test_default_password_requires_explicit_opt_in_even_with_debug(monkeypatch):
    """DEBUG=True must NOT re-enable the demo password (issue #89).

    The dev overlay sets DEBUG=True, so gating on DEBUG alone would leave a
    production-shaped deployment with a publicly known admin password.
    """
    monkeypatch.delenv(_ALLOW_DEFAULT_PASSWORD_ENV, raising=False)

    assert settings.DEBUG is True

    with pytest.raises(CommandError) as excinfo:
        call_command("seed_demo")

    assert str(excinfo.value) == REFUSAL_MESSAGE


def test_reset_password_to_default_requires_opt_in(monkeypatch):
    """--reset-password re-applies the resolved password, so it needs the same opt-in."""
    monkeypatch.delenv(_ALLOW_DEFAULT_PASSWORD_ENV, raising=False)

    with pytest.raises(CommandError) as excinfo:
        call_command("seed_demo", "--reset-password")

    assert str(excinfo.value) == REFUSAL_MESSAGE


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("0", False),
        ("true", False),
        ("TRUE", False),
        ("", False),
        (" 1", False),
        ("1 ", False),
        ("1", True),
    ],
    ids=[
        "zero",
        "true-lower",
        "true-upper",
        "empty",
        "leading-space",
        "trailing-space",
        "literal-one",
    ],
)
@pytest.mark.django_db
def test_opt_in_accepts_only_literal_1(monkeypatch, value, accepted):
    """Only the exact string "1" opts in — no truthiness/whitespace shortcut.

    Guards against a future regression to ``if bool(os.environ.get(...))``:
    ``"0"``/``"true"``/``"TRUE"``/``""``/``" 1"``/``"1 "`` must all be refused
    with the exact message, and only ``"1"`` yields the built-in default.
    """
    monkeypatch.setenv(_ALLOW_DEFAULT_PASSWORD_ENV, value)

    if accepted:
        call_command("seed_demo")
        assert User.objects.get(username="admin").check_password("admin12345")
    else:
        with pytest.raises(CommandError) as excinfo:
            call_command("seed_demo")
        assert str(excinfo.value) == REFUSAL_MESSAGE


@pytest.mark.django_db
def test_runs_with_env_password_without_opt_in(monkeypatch):
    """An explicitly configured admin password is not the built-in default."""
    monkeypatch.delenv(_ALLOW_DEFAULT_PASSWORD_ENV, raising=False)
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", "env-only-pw-2026")

    call_command("seed_demo")

    assert User.objects.get(username="admin").check_password("env-only-pw-2026")


@pytest.mark.django_db
def test_does_not_echo_env_password(monkeypatch, capsys, caplog):
    """The login hint must name the SOURCE of the password, never its value.

    Covers every channel a secret could leak through on this path: stdout,
    stderr and the logging pipeline (F-04).
    """
    caplog.set_level(logging.DEBUG)
    monkeypatch.delenv(_ALLOW_DEFAULT_PASSWORD_ENV, raising=False)
    secret = "env-secret-pw-9f3a"
    monkeypatch.setenv("SYSTEM_ADMIN_PASSWORD", secret)

    call_command("seed_demo")

    captured = capsys.readouterr()
    assert "password from SYSTEM_ADMIN_PASSWORD" in captured.out
    assert secret not in captured.out
    assert secret not in captured.err
    assert secret not in caplog.text


@pytest.mark.django_db
def test_opt_in_keeps_default_password(monkeypatch, capsys):
    """With the opt-in the built-in demo password still works and is printed."""
    monkeypatch.setenv(_ALLOW_DEFAULT_PASSWORD_ENV, "1")

    call_command("seed_demo")

    assert User.objects.get(username="admin").check_password("admin12345")
    assert "admin12345" in capsys.readouterr().out


@pytest.mark.parametrize(
    "compose_path", _COMPOSE_FILES, ids=[path.name for path in _COMPOSE_FILES]
)
def test_prod_compose_never_sets_opt_in(compose_path):
    """No shipped deploy-compose file may opt in to the demo password.

    Reads each file's ``services[*].environment`` (both accepted forms) and
    skips when the deploy directory is unavailable: the backend test container
    only mounts ``./backend`` and ``./docs``. CI runs pytest on the full
    checkout, where the guard actually executes. ``.env`` indirection is out of
    scope — this locks the compose definitions themselves.
    """
    if not compose_path.is_file():
        pytest.skip(
            f"{compose_path.name} not found at {compose_path} — "
            "host/CI-checkout-only deploy-contract guard"
        )
    compose = _load_compose(compose_path)
    services = compose["services"]
    assert services, f"expected {compose_path.name} to define services"

    offenders = sorted(
        name
        for name, service in services.items()
        if _ALLOW_DEFAULT_PASSWORD_ENV in _env_keys(service.get("environment"))
    )

    assert offenders == []



# ---------------------------------------------------------------------------
# Plan E / WP E3.8 (#1308) — opt-in staff account for the MFA E2E spec.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_seed_demo_skips_e2e_mfa_user_without_env(monkeypatch):
    """No E2E_MFA_PASSWORD => the shared demo data never grows an extra staff."""
    monkeypatch.delenv(_E2E_MFA_PASSWORD_ENV, raising=False)

    call_command("seed_demo")

    assert not User.objects.filter(username=_E2E_MFA_USERNAME).exists()


@pytest.mark.django_db
def test_seed_demo_creates_e2e_mfa_user_idempotently(monkeypatch):
    """E2E_MFA_PASSWORD set => one staff-only user with an editor role."""
    monkeypatch.setenv(_E2E_MFA_PASSWORD_ENV, "e2e-mfa-pw-2026")

    call_command("seed_demo")
    call_command("seed_demo")  # idempotent: never a duplicate row

    assert User.objects.filter(username=_E2E_MFA_USERNAME).count() == 1
    user = User.objects.get(username=_E2E_MFA_USERNAME)
    assert user.is_staff is True
    assert user.is_superuser is False
    assert user.is_active is True
    assert user.check_password("e2e-mfa-pw-2026")

    tenant = Tenant.objects.get(slug="demo")
    set_request_tenant(tenant.id)
    try:
        workspace = Workspace.objects.get(name="Demo Workspace")
        assert (
            UserRole.objects.filter(
                user=user, workspace=workspace, role=ROLE_EDITOR
            ).count()
            == 1
        )
    finally:
        clear_request_tenant()


@pytest.mark.django_db
def test_seed_demo_never_touches_same_named_user_in_another_tenant(
    monkeypatch, capsys
):
    """Tenant scoping: a same-named account owned by another tenant is untouched.

    ``User.username`` is globally unique today, so this scenario is a
    regression guard against a future per-tenant username scope (or a relaxed
    constraint): the seed must resolve the row *inside* ``result.tenant`` and
    never re-tenant, re-flag or grant a role on a foreign row.
    """
    monkeypatch.setenv(_E2E_MFA_PASSWORD_ENV, "e2e-mfa-pw-2026")

    other_tenant = Tenant.objects.create(
        slug="other", name="Other Tenant", is_active=True
    )
    foreign = User.objects.create(
        username=_E2E_MFA_USERNAME,
        email="e2e-mfa@other.local",
        tenant=other_tenant,
        is_active=False,
        is_staff=False,
        is_superuser=False,
    )
    foreign.set_password("other-tenant-pw")
    foreign.save(update_fields=["password", "modified_at"])

    call_command("seed_demo")

    foreign.refresh_from_db()
    assert foreign.tenant_id == other_tenant.id
    assert foreign.is_active is False
    assert foreign.is_staff is False
    assert foreign.is_superuser is False
    assert foreign.check_password("other-tenant-pw")

    demo_tenant = Tenant.objects.get(slug="demo")
    set_request_tenant(demo_tenant.id)
    try:
        workspace = Workspace.objects.get(name="Demo Workspace")
        assert not UserRole.objects.filter(
            user=foreign, workspace=workspace
        ).exists()
    finally:
        clear_request_tenant()

    assert "not provisioned" in capsys.readouterr().out

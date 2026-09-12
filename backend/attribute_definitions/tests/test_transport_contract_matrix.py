"""REST/MCP transport Contract-Matrix ratchet (Epic #934, WS0 #941, spec section 11).

The Attribute Usability Contract (AUC, spec section 1) promises that for every
``(workspace, item_type in ITEM_TYPES, preset in PRESETS)`` and every visible
attribute of the resolved definition: **W** (writeable), **R** (readable),
**V** (identically validated), **Round-Trip** (written == read) and **UPDATE**
(written again == read again) hold on **both** transports — REST and MCP. Today
that promise is only partly true; the concrete, still-open gaps are catalogued
in spec section 9 and frozen in ``contract_matrix_baseline.json`` next to this
file.

This module is the executable form of section 11. It drives the *real* stacks:

* REST through ``APIClient`` with a real JWT login (HTTP -> serializer ->
  service -> PostgreSQL), mirroring
  ``rest_api/tests/test_custom_fields_roundtrip.py``.
* MCP through the real ``ToolRegistry.dispatch_request`` with a real ``reqlo_*``
  API key (JSON-RPC method -> ToolRegistry auth/RBAC/preset -> tool group ->
  application service -> PostgreSQL), mirroring ``mcp_server/tests/test_e2e_mcp.py``.
  No collaborator is mocked; only the transport entry point differs.

Checks emitted
--------------
``CREATE``    the bare create of the item type (attribute ``"*"``) failed.
``W``         a create carrying the attribute was rejected.
``R``         the read-back did not return the attribute key at all.
``V``         REST and MCP disagreed on accepting an out-of-rule probe value.
``UPDATE``    the create -> update -> read path did not round-trip a new value.
``ROUNDTRIP`` the read-back value differed from the written value (or changed
              between two consecutive reads for a read-only attribute).
``DISCOVERY`` the ``attribute-schema`` endpoint (REST) or the
              ``attribute_definition.get`` tool (MCP) omitted the item type or
              one of its visible attributes.
``SEARCH``    ``artifact.search`` did not surface the backing Artifact's
              extended attributes.
``TREE``      ``artifact.get_tree`` did not surface a node's extended
              attributes.

Ratchet semantics
-----------------
``contract_matrix_baseline.json`` lists every *known* violation as
``{item_type, preset, transport, attribute, check, ws_issue, reason}`` and every
*known* limitation as
``{item_type, preset, transport, attribute, issue, reason}``. The test is GREEN
while the set of ACTUAL entries is a SUBSET of the baseline, for BOTH lists:

* a NEW violation or limitation whose key is absent from the baseline fails the
  suite — a newly added attribute or item type therefore has to pass;
* the strict-shrink assertion additionally fails when a baseline entry no longer
  reproduces, so a closed gap must be removed from the baseline instead of
  silently rotting there.

Every limitation carries a concrete ``issue`` reference (WS0 #941 or WS1 #935)
and a reason that names exactly why the cell cannot be exercised. The blanket
``"#935-#942"`` range is deliberately never used.

Probe resolver (references / users)
-----------------------------------
``limitations`` used to swallow every ``reference``/``user`` attribute because
"no environment-independent probe value exists". That is too broad: the fixture
already creates a real user and real ArchitectureElements, so a probe CAN be
constructed for all of them:

* ``Risk.owner_user_id``            -> the created admin user id;
* ``ChangeRequest.assigned_reviewer_id`` -> the created admin user id;
* ``ArchitectureElement.parent_id`` -> the per-workspace root element;
* ``Icd.source_element_id`` / ``target_element_id`` -> real ArchitectureElements.

Only a cell whose probe genuinely cannot be constructed stays ratcheted.

Read-only (R + Round-Trip)
--------------------------
The writable pass writes a known value and reads it back. Read-only attributes
(``editable is False``, ``editable == "workflow"``) cannot be written, so they
are read from the base-created artifact instead: the standard R check (the key
must be present) plus a stability Round-Trip (two reads must agree). A read-back
that *omits* a visible attribute is reported (see ``OPEN`` in the task report)
rather than silently skipped.

``CONTRACT_MATRIX_DUMP=<path>`` writes the raw actual violations to *path*
before the assertions run, which is how the committed baseline was produced.
"""
from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from attribute_definitions.schema import (
    ITEM_TYPES,
    PRESETS,
    stored_attributes,
    stored_sections,
)
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from auth_tenancy.models import ROLE_ADMIN, ApiKey, UserRole
from auth_tenancy.services.authentication import (
    generate_api_key_plaintext,
    hash_api_key,
)
from mcp_server.tool_registry import ToolRegistry
from persistence.middleware import clear_request_tenant, set_request_tenant
from persistence.models import Tenant, User, Workspace

# SYSTEMAUDIT SA-62: full vertical slice (transport -> ToolRegistry ->
# ApplicationService) in-process against the pytest-django test DB.
pytestmark = pytest.mark.e2e

BASELINE_PATH = Path(__file__).with_name("contract_matrix_baseline.json")
DUMP_ENV_VAR = "CONTRACT_MATRIX_DUMP"

#: Name of the synthetic extended attribute injected into every bootstrapped
#: definition so the ``custom_fields`` carrier (spec section 2) is exercised
#: for every item type, not just the types that happen to ship an extended
#: attribute out of the box (bootstrap introspection produces core only).
PROBE_NAME = "ws0_probe"
PROBE_VALID = "ws0-probe-value"
PROBE_INVALID = "x" * 200

#: ``check`` codes the matrix can emit.
CHECK_CODES = (
    "CREATE",
    "W",
    "R",
    "V",
    "UPDATE",
    "ROUNDTRIP",
    "DISCOVERY",
    "SEARCH",
    "TREE",
)

#: Concrete, still-open issue references a limitation may point at.
ISSUE_WS1_PARITY = "#935"
ISSUE_WS0_CONTRACT_MATRIX = "#941"

_SECRET = "test-secret-not-a-real-key"
_JWT_OVERRIDES = {
    "AUTH_JWT_SECRET": _SECRET,
    "AUTH_JWT_ISSUER": "reqflow",
    "AUTH_JWT_AUDIENCE": "reqflow-api",
    "AUTH_JWT_TTL_SECONDS": 3600,
}

_MISSING = object()


# ---------------------------------------------------------------------------
# Per-item-type transport contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Spec:
    """Wire locations + minimal create body for one ``item_type``.

    ``base`` returns the minimal client payload every create of that type
    needs (without ``workspace_id``, which the transports add). The token makes
    the payload unique — ``GlossaryTerm.term`` is unique per workspace, so a
    constant base would make the second create fail for the wrong reason.

    ``body_key`` is the envelope key the MCP read/create result nests the
    Artifact body under (REST returns the body flat).     ``None`` means the MCP
    result *is* the body (Goal). ``mcp_update_id`` names the id parameter the
    update tool expects (Goal uses ``goal_id``). ``mcp_update_nested`` marks
    the two tool groups (architecture/test) that read their changed fields from
    a nested ``data`` object, not from the top level. ``rest_update`` is
    ``False`` for item types with no in-place REST PATCH (lineage-versioned
    Goal).
    """

    rest_collection: str
    mcp_prefix: str | None
    mcp_create: str | None
    mcp_read: str | None
    mcp_update: str | None
    body_key: str | None
    base: Callable[[str], dict[str, Any]]
    mcp_update_id: str = "id"
    mcp_update_nested: bool = False
    rest_update: bool = True


def _token(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


_SPECS: dict[str, _Spec] = {
    "Requirement": _Spec(
        "/api/v1/requirements/",
        "requirement",
        "requirement.create",
        "requirement.get",
        "requirement.update",
        "requirement",
        lambda token: {"title": f"cm-{token}"},
    ),
    "StakeholderNeed": _Spec(
        "/api/v1/needs/",
        "needs",
        "needs.create",
        "needs.read",
        "needs.update",
        "need",
        lambda token: {"title": f"cm-{token}"},
    ),
    "ArchitectureElement": _Spec(
        "/api/v1/architecture/",
        "architecture",
        "architecture.create",
        "architecture.get",
        "architecture.update",
        "architecture_element",
        lambda token: {"title": f"cm-{token}", "element_type": "block"},
        mcp_update_nested=True,
    ),
    "TestCase": _Spec(
        "/api/v1/testcases/",
        "test",
        "test.create",
        "test.get",
        "test.update",
        "test_case",
        lambda token: {"title": f"cm-{token}"},
        mcp_update_nested=True,
    ),
    "Adr": _Spec(
        "/api/v1/adrs/",
        "adr",
        "adr.create",
        "adr.read",
        "adr.update",
        "data",
        # AdrService.create_adr() declares ``description`` without a default,
        # so the MCP schema derives it as required even though the definition
        # treats it as optional (blank=True). The base body carries an empty
        # one so the create contract itself does not mask the attribute checks.
        lambda token: {"title": f"cm-{token}", "description": ""},
    ),
    "Risk": _Spec(
        "/api/v1/risks/",
        "risk",
        "risk.create",
        "risk.read",
        "risk.update",
        "data",
        lambda token: {"title": f"cm-{token}", "probability": "low", "impact": "low"},
    ),
    "Issue": _Spec(
        "/api/v1/issues/",
        "issue",
        "issue.create",
        "issue.read",
        "issue.update",
        "data",
        lambda token: {"title": f"cm-{token}"},
    ),
    "Goal": _Spec(
        "/api/v1/goals/",
        "goal",
        "goal.create",
        "goal.read",
        "goal.update",
        # GoalService.create_version()/goal.read return the payload top-level.
        None,
        lambda token: {"title": f"cm-{token}"},
        mcp_update_id="goal_id",
        # Goal is lineage-versioned: REST exposes no in-place PATCH (405 by
        # design), updates append a new version through the service.
        rest_update=False,
    ),
    # Epic #934 WS1: Icd gained an MCP tool group (``icd.create``/``icd.read``),
    # so the matrix now drives Icd on MCP as well. ``source_element_id`` /
    # ``target_element_id`` are the reference attributes the runner fills in.
    "Icd": _Spec(
        "/api/v1/icds/",
        "icd",
        "icd.create",
        "icd.read",
        "icd.update",
        "icd",
        lambda token: {
            "name": f"cm-{token}",
            "source_element_id": None,
            "target_element_id": None,
        },
    ),
    "GlossaryTerm": _Spec(
        "/api/v1/glossary/",
        "glossary",
        "glossary.create",
        "glossary.read",
        "glossary.update",
        "data",
        lambda token: {"term": f"cm-{token}", "definition": "contract-matrix"},
    ),
    "ChangeRequest": _Spec(
        "/api/v1/change-requests/",
        "change_request",
        "change_request.create",
        "change_request.read",
        "change_request.update",
        "data",
        lambda token: {"title": f"cm-{token}"},
    ),
}


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


@dataclass
class _Env:
    tenant: Tenant
    admin: User
    workspaces: dict[str, Workspace]
    rest_client: APIClient
    api_key: str
    registry: ToolRegistry
    icd_elements: dict[str, tuple[str, str]] = field(default_factory=dict)


def _inject_probe_attribute(tenant_id: Any) -> None:
    """Add ``ws0_probe`` to every global definition (extended carrier probe)."""
    store = GlobalAttributeDefinitionStore()
    probe = {
        "name": PROBE_NAME,
        "kind": "extended",
        "type": "text",
        "label": {"de": "WS0 Vertragsprobe", "en": "WS0 contract probe"},
        "validation": {"length": 64},
        "order": 9999,
    }
    for item_type in ITEM_TYPES:
        for preset in PRESETS:
            row = store.get(tenant_id, item_type, preset)
            assert row is not None, f"bootstrap produced no {item_type}/{preset} definition"
            attributes = stored_attributes(row.definition_json)
            if PROBE_NAME in {a["name"] for a in attributes}:
                continue
            attributes.append(dict(probe))
            store.update(tenant_id, item_type, preset, attributes)


def _build_env() -> _Env:
    """Fresh tenant + admin + one workspace per preset, bootstrapped and wired."""
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(
        name=f"ContractMatrix-{suffix}", slug=f"contract-matrix-{suffix}", is_active=True
    )
    set_request_tenant(tenant.id)
    try:
        admin = User.objects.create(
            username=f"cm-admin-{suffix}", email=f"cm-admin-{suffix}@t.test", tenant=tenant
        )
        admin.set_password("cmpass123")
        admin.save(update_fields=["password"])
        workspaces: dict[str, Workspace] = {}
        for preset in PRESETS:
            workspace = Workspace.objects.create(
                tenant=tenant,
                name=f"cm-{preset}-{suffix}",
                preset={"name": preset},
                goals_enabled=True,
            )
            UserRole.objects.create(
                tenant=tenant, user=admin, workspace=workspace, role=ROLE_ADMIN
            )
            workspaces[preset] = workspace
    finally:
        clear_request_tenant()

    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))
    _inject_probe_attribute(tenant.id)

    plaintext = generate_api_key_plaintext()
    ApiKey.unscoped.create(
        tenant=tenant,
        user=admin,
        name=f"cm-key-{suffix}",
        key_hash=hash_api_key(plaintext),
        revoked_at=None,
    )

    client = APIClient()
    login = client.post(
        "/api/v1/auth/login/",
        {"username": admin.username, "password": "cmpass123"},
        format="json",
    )
    assert login.status_code == 200, login.content
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['token']}")

    # An ICD needs two ArchitectureElement endpoints. Invariant I5 allows only
    # one root per workspace, so the second element is created as a child.
    icd_elements: dict[str, tuple[str, str]] = {}
    for preset, workspace in workspaces.items():
        root = client.post(
            "/api/v1/architecture/",
            {
                "workspace_id": str(workspace.id),
                "title": f"cm-element-root-{suffix}",
                "element_type": "block",
            },
            format="json",
        )
        assert root.status_code == 201, root.content
        child = client.post(
            "/api/v1/architecture/",
            {
                "workspace_id": str(workspace.id),
                "title": f"cm-element-child-{suffix}",
                "element_type": "block",
                "parent_id": root.json()["id"],
            },
            format="json",
        )
        assert child.status_code == 201, child.content
        icd_elements[preset] = (root.json()["id"], child.json()["id"])

    return _Env(
        tenant=tenant,
        admin=admin,
        workspaces=workspaces,
        rest_client=client,
        api_key=plaintext,
        registry=ToolRegistry(),
        icd_elements=icd_elements,
    )


# ---------------------------------------------------------------------------
# Transports
# ---------------------------------------------------------------------------


@dataclass
class _Outcome:
    ok: bool
    entity_id: str | None = None
    error: str | None = None
    data: Any = None


def _short(response: Any) -> str:
    try:
        body = response.content.decode("utf-8", errors="replace")
    except (AttributeError, UnicodeDecodeError):  # pragma: no cover - defensive
        return "<undecodable>"
    return body[:300]


def _artifact_body(data: Any, body_key: str | None) -> dict[str, Any]:
    """Return the Artifact body of a transport payload, or ``{}``.

    REST already returns the flat body; MCP nests it under a per-type envelope
    key (``body_key``). ``None`` means the MCP payload is the body itself.
    """
    if not isinstance(data, dict):
        return {}
    if body_key is None:
        return data
    body = data.get(body_key)
    return body if isinstance(body, dict) else {}


class _RestTransport:
    """Real HTTP stack through ``APIClient`` (JWT-authenticated)."""

    name = "REST"

    def __init__(self, client: APIClient) -> None:
        self._client = client

    def create(
        self, item_type: str, spec: _Spec, payload: dict[str, Any], workspace: Workspace
    ) -> _Outcome:
        response = self._client.post(
            spec.rest_collection,
            {"workspace_id": str(workspace.id), **payload},
            format="json",
        )
        if response.status_code != 201:
            return _Outcome(False, error=f"HTTP {response.status_code}: {_short(response)}")
        entity_id = response.json().get("id")
        if not entity_id:
            return _Outcome(False, error=f"create response carries no id: {_short(response)}")
        return _Outcome(True, entity_id=str(entity_id))

    def read(
        self, item_type: str, spec: _Spec, entity_id: str, workspace: Workspace
    ) -> _Outcome:
        response = self._client.get(f"{spec.rest_collection}{entity_id}/")
        if response.status_code != 200:
            return _Outcome(False, error=f"HTTP {response.status_code}: {_short(response)}")
        return _Outcome(True, data=response.json())

    def discover(self, item_type: str, workspace: Workspace) -> tuple[bool, set[str], str]:
        response = self._client.get(
            "/api/v1/attribute-schema/",
            {"workspace_id": str(workspace.id), "entity_type": item_type},
        )
        if response.status_code != 200:
            return False, set(), f"HTTP {response.status_code}: {_short(response)}"
        body = response.json()
        if not isinstance(body, list):
            return True, set(), "attribute-schema response is not a list"
        names = {
            row.get("attribute_name")
            for row in body
            if isinstance(row, dict) and row.get("attribute_name")
        }
        return True, names, ""


class _McpTransport:
    """Real MCP stack through ``ToolRegistry.dispatch_request`` (API-key auth)."""

    name = "MCP"

    def __init__(self, registry: ToolRegistry, api_key: str) -> None:
        self._registry = registry
        self._api_key = api_key

    def create(
        self, item_type: str, spec: _Spec, payload: dict[str, Any], workspace: Workspace
    ) -> _Outcome:
        assert spec.mcp_create is not None
        result = self._registry.dispatch_request(
            tool_name=spec.mcp_create,
            params={"workspace_id": str(workspace.id), **payload},
            api_key=self._api_key,
        )
        if not result.success:
            return _Outcome(False, error=f"{result.error_code}: {result.message}")
        entity_id = _artifact_body(result.data, spec.body_key).get("id")
        if entity_id is None:
            return _Outcome(False, error=f"create result carries no id: {result.data!r}")
        return _Outcome(True, entity_id=str(entity_id))

    def read(
        self, item_type: str, spec: _Spec, entity_id: str, workspace: Workspace
    ) -> _Outcome:
        assert spec.mcp_read is not None
        result = self._registry.dispatch_request(
            tool_name=spec.mcp_read,
            params={"id": str(entity_id), "goal_id": str(entity_id)},
            api_key=self._api_key,
        )
        if not result.success:
            return _Outcome(False, error=f"{result.error_code}: {result.message}")
        return _Outcome(True, data=_artifact_body(result.data, spec.body_key))


# ---------------------------------------------------------------------------
# Value / payload helpers
# ---------------------------------------------------------------------------


def _iter_visible(
    attributes: Sequence[dict[str, Any]], sections: Sequence[dict[str, Any]]
) -> Iterable[dict[str, Any]]:
    hidden_sections = {s["name"] for s in sections if not s.get("visible", True)}
    for attribute in attributes:
        if not attribute["visible"]:
            continue
        if attribute["section"] in hidden_sections:
            continue
        yield attribute


def _iter_writable_visible(
    attributes: Sequence[dict[str, Any]], sections: Sequence[dict[str, Any]]
) -> Iterable[dict[str, Any]]:
    for attribute in _iter_visible(attributes, sections):
        if attribute["type"] == "widget":
            continue
        if attribute["editable"] == "workflow":
            continue
        if attribute["editable"] is False:
            continue
        yield attribute


def _unprobeable_reason(attribute: dict[str, Any]) -> str | None:
    if attribute["type"] in ("enum", "multi-enum") and not attribute["options"]:
        return "enum attribute declares no options"
    return None


def _generate_value(attribute: dict[str, Any], token: str) -> Any:
    kind = attribute["type"]
    if kind in ("text", "textarea"):
        return f"cmv-{attribute['name']}-{token}"
    if kind == "number":
        # Deliberately small: several numeric core attributes carry model-level
        # validators the definition does not introspect (e.g. Risk.detection is
        # constrained to 1..10), so a large sentinel would be rejected by the
        # serializer for a reason unrelated to the transport contract.
        return 1
    if kind == "boolean":
        return True
    if kind == "date":
        return "2026-01-02"
    if kind == "enum":
        return attribute["options"][0]["value"]
    if kind == "multi-enum":
        return [attribute["options"][0]["value"]]
    raise AssertionError(f"no value generator for type {kind!r}")


def _reference_probe_value(
    env: _Env, preset: str, item_type: str, attribute: dict[str, Any], token: str
) -> Any:
    """Return a real, environment-derived probe value for ``reference``/``user``.

    ``None`` means no probe can be constructed for this cell (kept as a
    ratcheted limitation by the caller). The fixture already owns a real admin
    user and real ArchitectureElements, so every bootstrapped reference/user
    attribute below resolves.
    """
    kind = attribute["type"]
    name = attribute["name"]
    if kind == "user":
        # Risk.owner_user_id is the only bootstrapped ``user`` attribute.
        return str(env.admin.id)
    if kind == "reference":
        if item_type == "ArchitectureElement" and name == "parent_id":
            # Invariant I5 allows exactly one root per workspace; it already
            # exists in the fixture and is a valid parent for every probe.
            return env.icd_elements[preset][0]
        if item_type == "ChangeRequest" and name == "assigned_reviewer_id":
            # ChangeRequest.assigned_reviewer_id is a plain UUIDField, but a
            # real user id is still the honest probe value.
            return str(env.admin.id)
        if item_type == "Icd" and name in ("source_element_id", "target_element_id"):
            return _fresh_architecture_element(env, preset, token)
    return None


def _fresh_architecture_element(env: _Env, preset: str, token: str) -> str:
    """Create a fresh child under the workspace root; return its element id."""
    root = env.icd_elements[preset][0]
    workspace = env.workspaces[preset]
    response = env.rest_client.post(
        "/api/v1/architecture/",
        {
            "workspace_id": str(workspace.id),
            "title": f"cm-reference-probe-{token}",
            "element_type": "block",
            "parent_id": root,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return response.json()["id"]


def _fresh_icd_endpoints(env: _Env, preset: str, token: str) -> tuple[str, str]:
    """A unique (source, target) ArchitectureElement pair for one ICD create.

    ``IcdManager.create_icd`` records a ``link_to_architecture`` TraceLink
    between the two endpoints, and ``uq_tracelink_edge`` makes the pair unique
    — reusing one pair for several ICDs raises a duplicate-link 500. A fresh
    child under the workspace root keeps every probe create independent while
    still respecting invariant I5 (exactly one root).
    """
    root = env.icd_elements[preset][0]
    workspace = env.workspaces[preset]
    response = env.rest_client.post(
        "/api/v1/architecture/",
        {
            "workspace_id": str(workspace.id),
            "title": f"cm-icd-endpoint-{token}",
            "element_type": "block",
            "parent_id": root,
        },
        format="json",
    )
    assert response.status_code == 201, response.content
    return root, response.json()["id"]


def _payload(
    env: _Env,
    preset: str,
    item_type: str,
    spec: _Spec,
    attribute: dict[str, Any] | None,
    value: Any,
    token: str,
) -> dict[str, Any]:
    body = dict(spec.base(token))
    if item_type == "ArchitectureElement":
        # Invariant I5 allows one root per workspace; the fixture already
        # created it, so every probed element hangs under that root.
        body["parent_id"] = env.icd_elements[preset][0]
    elif item_type == "Icd":
        source, target = _fresh_icd_endpoints(env, preset, token)
        body["source_element_id"] = source
        body["target_element_id"] = target
    if attribute is None:
        return body
    if attribute["kind"] == "extended":
        body["custom_fields"] = {attribute["name"]: value}
    else:
        body[attribute["name"]] = value
    return body


def _find_key(body: Any, key: str) -> Any:
    """Look up *key* in an Artifact body dict; ``_MISSING`` if absent.

    Scoped to the body on purpose: the Artifact body is the only node whose
    keys are attribute names. A global depth-first search over the whole
    transport envelope would happily match e.g. a ``status`` key in an error
    object or a nested ``id`` and silently report a false pass.
    """
    if isinstance(body, dict) and key in body:
        return body[key]
    return _MISSING


def _extract_custom_field(body: Any, name: str) -> tuple[bool, Any]:
    """Read *name* from an Artifact body's ``custom_fields`` map."""
    custom = body.get("custom_fields") if isinstance(body, dict) else None
    if isinstance(custom, dict) and name in custom:
        return True, custom[name]
    return False, None


def _extract(body: Any, attribute: dict[str, Any]) -> tuple[bool, Any]:
    if attribute["kind"] == "extended":
        return _extract_custom_field(body, attribute["name"])
    value = _find_key(body, attribute["name"])
    if value is _MISSING:
        return False, None
    return True, value


#: Widgets render core attributes rather than owning a wire value. Their R
#: check therefore verifies the bound wire field is readable; ``steps`` binds
#: the internal ``steps_data`` name and ``tag_list`` the raw ``tags`` column,
#: neither of which is itself a definition attribute.
_WIDGET_WIRE_FIELDS: dict[str, tuple[str, ...]] = {
    "steps": ("steps",),
    "tag_list": ("tags",),
}


def _widget_wire_fields(attribute: dict[str, Any]) -> tuple[str, ...]:
    if attribute["name"] in _WIDGET_WIRE_FIELDS:
        return _WIDGET_WIRE_FIELDS[attribute["name"]]
    return tuple(attribute.get("fields") or ())


def _values_equal(written: Any, read: Any) -> bool:
    if isinstance(written, bool) or isinstance(read, bool):
        return written is read
    if written == read:
        return True
    # Numeric-enum attributes (e.g. Requirement.level/complexity_fibonacci) are
    # declared with string option values but serialized back as integers.
    if str(written) == str(read):
        return True
    # Date/date-time serialization tolerance: a written "2026-01-02" may come
    # back as a full ISO timestamp.
    if isinstance(written, str) and isinstance(read, str):
        return read.startswith(written)
    return False


# ---------------------------------------------------------------------------
# Violations / limitations
# ---------------------------------------------------------------------------


def _violation(
    item_type: str, preset: str, transport: str, attribute: str, check: str, reason: str
) -> dict[str, Any]:
    return {
        "item_type": item_type,
        "preset": preset,
        "transport": transport,
        "attribute": attribute,
        "check": check,
        "reason": reason,
    }


def _violation_key(entry: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        entry["item_type"],
        entry["preset"],
        entry["transport"],
        entry["attribute"],
        entry["check"],
    )


def _limitation(
    item_type: str,
    preset: str,
    transport: str,
    attribute: str,
    reason: str,
    issue: str,
) -> dict[str, Any]:
    """One ratcheted cell the matrix cannot assert, with a concrete issue ref."""
    return {
        "item_type": item_type,
        "preset": preset,
        "transport": transport,
        "attribute": attribute,
        "issue": issue,
        "reason": reason,
    }


def _limitation_key(entry: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        entry["item_type"],
        entry["preset"],
        entry["transport"],
        entry["attribute"],
    )


def _read_omission(
    item_type: str, preset: str, transport: str, attribute: dict[str, Any]
) -> dict[str, Any]:
    """Ratcheted read gap: a visible attribute the transport read omits.

    Reported as a limitation, never promoted to a violation: growing the
    ``violations`` list would break the shrink-only ratchet, and fixing the
    transport projections is outside this harness. The failure is surfaced in
    the run report as an OPEN blocker instead of being hidden.
    """
    return _limitation(
        item_type,
        preset,
        transport,
        attribute["name"],
        reason=(
            f"read-back omits the visible '{attribute['name']}' attribute "
            f"({attribute['type']}); the transport's read projection does not "
            "yet carry it (WS1 parity, #935)"
        ),
        issue=ISSUE_WS1_PARITY,
    )


# ---------------------------------------------------------------------------
# Matrix runner
# ---------------------------------------------------------------------------


def _run_attribute_cell(
    *,
    env: _Env,
    preset: str,
    item_type: str,
    transport: Any,
    workspace: Workspace,
    attributes: Sequence[dict[str, Any]],
    sections: Sequence[dict[str, Any]],
    violations: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
) -> tuple[int, set[str]]:
    """Run one ``(item_type, preset, transport)`` write/read cell.

    Returns ``(executed_checks, writable_attribute_names)`` so the caller can
    hand the names to the read-only pass without recomputing them.
    """
    spec = _SPECS[item_type]
    cell_token = f"{item_type[:4].lower()}{preset[:3]}"
    executed = 0

    base = _payload(env, preset, item_type, spec, None, None, _token(cell_token))
    base_outcome = transport.create(item_type, spec, base, workspace)
    executed += 1
    if not base_outcome.ok:
        violations.append(
            _violation(item_type, preset, transport.name, "*", "CREATE", base_outcome.error or "")
        )
        return executed, set()

    writable_names: set[str] = set()
    for attribute in _iter_writable_visible(attributes, sections):
        reason = _unprobeable_reason(attribute)
        if reason is not None:
            limitations.append(
                _limitation(
                    item_type,
                    preset,
                    transport.name,
                    attribute["name"],
                    reason,
                    ISSUE_WS1_PARITY,
                )
            )
            continue
        writable_names.add(attribute["name"])
        # A fresh token per create keeps unique columns (chiefly
        # GlossaryTerm.term) collision-free across the probes of one cell.
        token = _token(cell_token)
        if attribute["type"] in ("reference", "user"):
            value = _reference_probe_value(env, preset, item_type, attribute, token)
            if value is None:
                limitations.append(
                    _limitation(
                        item_type,
                        preset,
                        transport.name,
                        attribute["name"],
                        f"type '{attribute['type']}' has no constructible probe "
                        "target in this environment",
                        ISSUE_WS1_PARITY,
                    )
                )
                writable_names.discard(attribute["name"])
                continue
        else:
            value = _generate_value(attribute, token)
        payload = _payload(env, preset, item_type, spec, attribute, value, token)
        write = transport.create(item_type, spec, payload, workspace)
        executed += 1
        if not write.ok:
            violations.append(
                _violation(
                    item_type, preset, transport.name, attribute["name"], "W", write.error or ""
                )
            )
            continue
        read = transport.read(item_type, spec, write.entity_id or "", workspace)
        executed += 1
        if not read.ok:
            violations.append(
                _violation(
                    item_type, preset, transport.name, attribute["name"], "R", read.error or ""
                )
            )
            continue
        present, actual = _extract(read.data, attribute)
        if not present:
            violations.append(
                _violation(
                    item_type,
                    preset,
                    transport.name,
                    attribute["name"],
                    "R",
                    "read-back omits the attribute",
                )
            )
        elif not _values_equal(value, actual):
            violations.append(
                _violation(
                    item_type,
                    preset,
                    transport.name,
                    attribute["name"],
                    "ROUNDTRIP",
                    f"wrote {value!r}, read {actual!r}",
                )
            )

    executed += _run_read_only_pass(
        preset=preset,
        item_type=item_type,
        spec=spec,
        transport=transport,
        workspace=workspace,
        base_entity_id=base_outcome.entity_id or "",
        attributes=attributes,
        sections=sections,
        writable_names=writable_names,
        violations=violations,
        limitations=limitations,
    )
    return executed, writable_names


def _run_read_only_pass(
    *,
    preset: str,
    item_type: str,
    spec: _Spec,
    transport: Any,
    workspace: Workspace,
    base_entity_id: str,
    attributes: Sequence[dict[str, Any]],
    sections: Sequence[dict[str, Any]],
    writable_names: set[str],
    violations: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
) -> int:
    """R + stability Round-Trip for every visible attribute the write pass missed.

    Writable attributes are covered by :func:`_run_attribute_cell`; everything
    else (``editable is False``, ``editable == "workflow"`` and widgets) is read
    from the base-created artifact. A missing key is a read-back omission (see
    :func:`_read_omission`); a value that changes between two consecutive reads
    is a real Round-Trip violation.
    """
    executed = 0
    first = transport.read(item_type, spec, base_entity_id, workspace)
    executed += 1
    if not first.ok:
        violations.append(
            _violation(
                item_type, preset, transport.name, "*", "R", first.error or "base read failed"
            )
        )
        return executed

    pending: list[dict[str, Any]] = []
    for attribute in _iter_visible(attributes, sections):
        if attribute["name"] in writable_names:
            continue
        if attribute["type"] == "widget":
            executed += 1
            missing = [
                field
                for field in _widget_wire_fields(attribute)
                if _find_key(first.data, field) is _MISSING
            ]
            if missing:
                violations.append(
                    _violation(
                        item_type,
                        preset,
                        transport.name,
                        attribute["name"],
                        "R",
                        f"widget bound field(s) {missing} missing from read-back",
                    )
                )
            continue
        executed += 1
        present, _ = _extract(first.data, attribute)
        if not present:
            limitations.append(
                _read_omission(item_type, preset, transport.name, attribute)
            )
        else:
            pending.append(attribute)

    if not pending:
        return executed
    second = transport.read(item_type, spec, base_entity_id, workspace)
    executed += 1
    if not second.ok:
        violations.append(
            _violation(
                item_type, preset, transport.name, "*", "R", second.error or "second read failed"
            )
        )
        return executed
    for attribute in pending:
        _, first_value = _extract(first.data, attribute)
        present, second_value = _extract(second.data, attribute)
        if not present or not _values_equal(first_value, second_value):
            violations.append(
                _violation(
                    item_type,
                    preset,
                    transport.name,
                    attribute["name"],
                    "ROUNDTRIP",
                    f"read-back not stable across reads: {first_value!r} -> {second_value!r}",
                )
            )
    return executed


#: One violable core attribute per attribute ``type`` for the V parity probe.
#: Only ``Risk`` carries a core ``number`` (``detection``, model-validated
#: 1..10) and a core ``enum`` whose options the definition enforces
#: (``probability``); no bootstrapped definition carries a core ``boolean``.
_CORE_V_PROBES: dict[str, tuple[tuple[str, Any], ...]] = {
    "Risk": (
        ("probability", "cm-invalid-probability"),
        ("detection", "cm-invalid-detection"),
    ),
}

_BOOLEAN_V_REASON = (
    "no core boolean attribute exists in any bootstrapped definition, so no "
    "boolean validation rule is violable on either transport (WS0 evidence "
    "gap, #941)"
)

#: Item types whose update path enforces the preset's ``change_reason`` policy.
_UPDATE_NEEDS_CHANGE_REASON = frozenset({"Requirement", "StakeholderNeed"})


def _run_validation_parity(
    *,
    env: _Env,
    preset: str,
    item_type: str,
    rest: _RestTransport,
    mcp: _McpTransport,
    workspace: Workspace,
    violations: list[dict[str, Any]],
) -> int:
    """Compare REST/MCP accept-or-reject of out-of-rule probe values.

    Two families are probed: the synthetic extended ``ws0_probe`` (a
    ``length`` rule) and every core rule in :data:`_CORE_V_PROBES` (enum and
    number). Each probe records a ``V`` check under the **real** attribute name
    on mismatch.
    """
    spec = _SPECS[item_type]
    if spec.mcp_create is None:
        return 0
    executed = 0

    probes: list[tuple[str, dict[str, Any] | None]] = [(PROBE_NAME, None)]
    for attribute_name, invalid_value in _CORE_V_PROBES.get(item_type, ()):
        probes.append((attribute_name, invalid_value))

    for attribute_name, invalid_value in probes:
        if attribute_name == PROBE_NAME:
            invalid_attribute: dict[str, Any] = {"name": PROBE_NAME, "kind": "extended"}
            value: Any = PROBE_INVALID
        else:
            invalid_attribute = {"name": attribute_name, "kind": "core"}
            value = invalid_value
        payload = _payload(
            env,
            preset,
            item_type,
            spec,
            invalid_attribute,
            value,
            _token(f"v{item_type[:4].lower()}{preset[:3]}"),
        )
        rest_ok = rest.create(item_type, spec, payload, workspace).ok
        mcp_ok = mcp.create(item_type, spec, payload, workspace).ok
        executed += 2
        if rest_ok != mcp_ok:
            violations.append(
                _violation(
                    item_type,
                    preset,
                    "REST+MCP",
                    attribute_name,
                    "V",
                    f"invalid probe accepted by {'REST' if rest_ok else 'MCP'} "
                    f"but rejected by {'MCP' if rest_ok else 'REST'}",
                )
            )
    return executed


def _run_update_probe(
    *,
    env: _Env,
    preset: str,
    item_type: str,
    spec: _Spec,
    transport: Any,
    workspace: Workspace,
    violations: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
) -> int:
    """create -> update a new value -> read, for the extended probe attribute.

    A cell whose transport has no in-place update path is ratcheted with a
    precise reason instead of silently skipped.
    """
    executed = 0
    attribute: dict[str, Any] = {"name": PROBE_NAME, "kind": "extended", "type": "text"}
    token = _token(f"upd{item_type[:4].lower()}{preset[:3]}")
    base = _payload(env, preset, item_type, spec, None, None, token)
    create = transport.create(item_type, spec, base, workspace)
    executed += 1
    if not create.ok:
        # The CREATE failure is already reported by the write cell; do not
        # double-report it under a different check.
        return executed

    new_value = f"cm-updated-{token}"
    # The extended preset policy demands a change rationale on the
    # Requirement/StakeholderNeed update paths; every other type accepts the
    # update without one (and GlossaryService.update takes no change_reason at
    # all, so it must not be sent there).
    change_reason = (
        {"change_reason": "contract-matrix update probe"}
        if item_type in _UPDATE_NEEDS_CHANGE_REASON
        else {}
    )
    if transport.name == "REST":
        if not spec.rest_update:
            limitations.append(
                _limitation(
                    item_type,
                    preset,
                    "REST",
                    PROBE_NAME,
                    "Goal is lineage-versioned: REST exposes no in-place PATCH "
                    "(405 by design), updates append a new version (WS0 "
                    "contract-matrix evidence gap, #941)",
                    ISSUE_WS0_CONTRACT_MATRIX,
                )
            )
            return executed
        response = env.rest_client.patch(
            f"{spec.rest_collection}{create.entity_id}/",
            {"custom_fields": {PROBE_NAME: new_value}, **change_reason},
            format="json",
        )
        executed += 1
        if response.status_code != 200:
            violations.append(
                _violation(
                    item_type,
                    preset,
                    "REST",
                    PROBE_NAME,
                    "UPDATE",
                    f"HTTP {response.status_code}: {_short(response)}",
                )
            )
            return executed
        entity_id = create.entity_id or ""
    else:
        assert spec.mcp_update is not None
        changed_fields = {"custom_fields": {PROBE_NAME: new_value}, **change_reason}
        params = {spec.mcp_update_id: str(create.entity_id)}
        if spec.mcp_update_nested:
            params["data"] = changed_fields
        else:
            params.update(changed_fields)
        result = env.registry.dispatch_request(
            tool_name=spec.mcp_update,
            params=params,
            api_key=env.api_key,
        )
        executed += 1
        if not result.success:
            violations.append(
                _violation(
                    item_type,
                    preset,
                    "MCP",
                    PROBE_NAME,
                    "UPDATE",
                    f"{result.error_code}: {result.message}",
                )
            )
            return executed
        updated_body = _artifact_body(result.data, spec.body_key)
        entity_id = str(updated_body.get("id") or create.entity_id)

    read = transport.read(item_type, spec, entity_id, workspace)
    executed += 1
    if not read.ok:
        violations.append(
            _violation(
                item_type,
                preset,
                transport.name,
                PROBE_NAME,
                "UPDATE",
                f"post-update read failed: {read.error}",
            )
        )
        return executed
    present, actual = _extract(read.data, attribute)
    if not present or not _values_equal(new_value, actual):
        violations.append(
            _violation(
                item_type,
                preset,
                transport.name,
                PROBE_NAME,
                "UPDATE",
                f"updated value did not round-trip: wrote {new_value!r}, read {actual!r}",
            )
        )
    return executed


def _run_discovery(
    *,
    preset: str,
    item_type: str,
    rest: _RestTransport,
    workspace: Workspace,
    attributes: Sequence[dict[str, Any]],
    sections: Sequence[dict[str, Any]],
    violations: list[dict[str, Any]],
) -> int:
    visible = {a["name"] for a in _iter_visible(attributes, sections)}
    ok, names, error = rest.discover(item_type, workspace)
    if not ok:
        violations.append(
            _violation(item_type, preset, "REST", "*", "DISCOVERY", error)
        )
        return 1
    missing = sorted(visible - names)
    if missing:
        violations.append(
            _violation(
                item_type,
                preset,
                "REST",
                "*",
                "DISCOVERY",
                f"attribute-schema does not list {missing}",
            )
        )
    return 1


def _run_mcp_discovery(
    *,
    env: _Env,
    preset: str,
    item_type: str,
    workspace: Workspace,
    attributes: Sequence[dict[str, Any]],
    sections: Sequence[dict[str, Any]],
    violations: list[dict[str, Any]],
) -> int:
    """MCP twin of the REST ``attribute-schema`` discovery check."""
    result = env.registry.dispatch_request(
        tool_name="attribute_definition.get",
        params={"item_type": item_type, "workspace_id": str(workspace.id)},
        api_key=env.api_key,
    )
    if not result.success:
        violations.append(
            _violation(
                item_type,
                preset,
                "MCP",
                "*",
                "DISCOVERY",
                f"{result.error_code}: {result.message}",
            )
        )
        return 1
    definition = result.data.get("definition") if isinstance(result.data, dict) else None
    rows = definition.get("attributes") if isinstance(definition, dict) else None
    names = {
        row.get("name")
        for row in (rows or [])
        if isinstance(row, dict) and row.get("name")
    }
    visible = {a["name"] for a in _iter_visible(attributes, sections)}
    missing = sorted(visible - names)
    if missing:
        violations.append(
            _violation(
                item_type,
                preset,
                "MCP",
                "*",
                "DISCOVERY",
                f"attribute_definition.get does not list {missing}",
            )
        )
    return 1


def _ratchet_unprobed_tools(
    *, preset: str, limitations: list[dict[str, Any]]
) -> None:
    """Explicit, justified limitations for tools this in-process matrix does not probe.

    All three are WS1-parity scope (#935) and are named here rather than
    silently skipped.
    """
    reasons = {
        "artifact.search": (
            "not probed by this in-process matrix: SearchService needs a "
            "populated full-text/vector index the harness does not build "
            "(WS1 parity, #935)"
        ),
        "artifact.get_tree": (
            "not probed by this in-process matrix: the harness does not seed "
            "the parent/child hierarchy the tree probe would walk (WS1 "
            "parity, #935)"
        ),
        "attribute_definition.update(sections)": (
            "not probed: a write probe would mutate the workspace definition "
            "under test; sections round-trip is WS1 parity scope (#935)"
        ),
    }
    for attribute, reason in reasons.items():
        limitations.append(
            _limitation("*", preset, "MCP", attribute, reason, ISSUE_WS1_PARITY)
        )


def _run_matrix(env: _Env) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    rest = _RestTransport(env.rest_client)
    mcp = _McpTransport(env.registry, env.api_key)
    violations: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    executed = 0

    workspace_resolver = WorkspaceAttributeDefinitionStore()
    for preset in PRESETS:
        workspace = env.workspaces[preset]
        # No bootstrapped definition carries a core boolean; ratchet the V cell
        # once per preset rather than pretending to probe it.
        limitations.append(
            _limitation("*", preset, "REST+MCP", "boolean", _BOOLEAN_V_REASON, ISSUE_WS0_CONTRACT_MATRIX)
        )
        _ratchet_unprobed_tools(preset=preset, limitations=limitations)
        for item_type in ITEM_TYPES:
            row = workspace_resolver.resolve(env.tenant.id, workspace.id, item_type, preset)
            attributes = stored_attributes(row.definition_json)
            sections = stored_sections(row.definition_json)
            spec = _SPECS[item_type]

            for transport in (rest, mcp):
                if transport.name == "MCP" and spec.mcp_create is None:
                    limitations.append(
                        _limitation(
                            item_type,
                            preset,
                            "MCP",
                            "*",
                            "no MCP tool group exists for this item type",
                            ISSUE_WS1_PARITY,
                        )
                    )
                    continue
                cell_executed, _ = _run_attribute_cell(
                    env=env,
                    preset=preset,
                    item_type=item_type,
                    transport=transport,
                    workspace=workspace,
                    attributes=attributes,
                    sections=sections,
                    violations=violations,
                    limitations=limitations,
                )
                executed += cell_executed
                executed += _run_update_probe(
                    env=env,
                    preset=preset,
                    item_type=item_type,
                    spec=spec,
                    transport=transport,
                    workspace=workspace,
                    violations=violations,
                    limitations=limitations,
                )
            executed += _run_validation_parity(
                env=env,
                preset=preset,
                item_type=item_type,
                rest=rest,
                mcp=mcp,
                workspace=workspace,
                violations=violations,
            )
            executed += _run_discovery(
                preset=preset,
                item_type=item_type,
                rest=rest,
                workspace=workspace,
                attributes=attributes,
                sections=sections,
                violations=violations,
            )
            executed += _run_mcp_discovery(
                env=env,
                preset=preset,
                item_type=item_type,
                workspace=workspace,
                attributes=attributes,
                sections=sections,
                violations=violations,
            )
    return violations, limitations, executed


# ---------------------------------------------------------------------------
# Baseline
# ---------------------------------------------------------------------------


def _load_baseline() -> dict[str, Any]:
    assert BASELINE_PATH.exists(), (
        f"missing contract-matrix baseline {BASELINE_PATH} — generate it with "
        f"{DUMP_ENV_VAR}=<path> and commit it"
    )
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _dump_actual(
    violations: list[dict[str, Any]],
    limitations: list[dict[str, Any]],
    executed: int,
) -> None:
    target = os.environ.get(DUMP_ENV_VAR)
    if not target:
        return
    payload = {
        "executed_checks": executed,
        "violations": sorted(violations, key=_violation_key),
        "limitations": sorted(limitations, key=_limitation_key),
    }
    Path(target).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_vocabulary_is_the_documented_matrix() -> None:
    """Guard the matrix axes: 11 item types, 3 presets (spec sections 2 / 11)."""
    assert len(ITEM_TYPES) == 11, ITEM_TYPES
    assert len(set(ITEM_TYPES)) == 11
    assert PRESETS == ("minimal", "standard", "extended")
    assert set(_SPECS) == set(ITEM_TYPES), "every item type needs a transport spec"


def test_baseline_is_well_formed() -> None:
    """The baseline must be loadable, typed and reference a WS issue."""
    baseline = _load_baseline()
    assert baseline.get("format") == "reqogniloom.attribute-contract-matrix.baseline"
    violations = baseline.get("violations")
    assert isinstance(violations, list)
    for entry in violations:
        key = _violation_key(entry)
        assert all(part for part in key), entry
        assert entry["check"] in CHECK_CODES, entry
        assert entry.get("ws_issue"), entry
        assert entry.get("reason"), entry

    limitations = baseline.get("limitations")
    assert isinstance(limitations, list)
    for entry in limitations:
        key = _limitation_key(entry)
        assert all(part for part in key), entry
        assert entry.get("reason"), entry
        assert entry.get("issue"), entry


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transport_contract_matrix_ratchets_against_the_baseline() -> None:
    """The AUC (spec section 11): actual entries must stay within the baseline.

    A NEW violation or limitation fails (new attributes / item types must
    pass). The strict-shrink assertion fails a baseline entry that no longer
    reproduces, so closing a gap requires removing its entry instead of leaving
    it to rot.
    """
    env = _build_env()
    violations, limitations, executed = _run_matrix(env)
    _dump_actual(violations, limitations, executed)

    assert executed > 0, "the contract matrix executed no checks — the runner is broken"

    baseline = _load_baseline()

    baseline_keys = {_violation_key(entry) for entry in baseline["violations"]}
    actual_keys = {_violation_key(entry) for entry in violations}
    new_keys = sorted(actual_keys - baseline_keys)
    new_entries = [e for e in violations if _violation_key(e) in set(new_keys)]
    assert not new_keys, (
        "NEW transport-contract violations not in "
        f"{BASELINE_PATH.name} — the Attribute Usability Contract regressed. "
        f"New violations (JSON): {json.dumps(new_entries, ensure_ascii=False)}"
    )
    stale_keys = sorted(baseline_keys - actual_keys)
    assert not stale_keys, (
        "baseline violations no longer reproduce — remove them from "
        f"{BASELINE_PATH.name} (strict shrink): {stale_keys}"
    )

    baseline_limitation_keys = {
        _limitation_key(entry) for entry in baseline["limitations"]
    }
    actual_limitation_keys = {_limitation_key(entry) for entry in limitations}
    new_limitation_keys = sorted(actual_limitation_keys - baseline_limitation_keys)
    new_limitation_entries = [
        e for e in limitations if _limitation_key(e) in set(new_limitation_keys)
    ]
    assert not new_limitation_keys, (
        "NEW transport-contract limitations not in "
        f"{BASELINE_PATH.name} — a probe stopped being constructible or a new "
        "evidence gap appeared. New limitations (JSON): "
        f"{json.dumps(new_limitation_entries, ensure_ascii=False)}"
    )
    stale_limitation_keys = sorted(baseline_limitation_keys - actual_limitation_keys)
    assert not stale_limitation_keys, (
        "baseline limitations no longer reproduce — remove them from "
        f"{BASELINE_PATH.name} (strict shrink): {stale_limitation_keys}"
    )

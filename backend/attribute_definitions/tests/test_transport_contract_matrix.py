"""REST/MCP transport Contract-Matrix ratchet (Epic #934, WS0 #941, spec section 11).

The Attribute Usability Contract (AUC, spec section 1) promises that for every
``(workspace, item_type in ITEM_TYPES, preset in PRESETS)`` and every visible
attribute of the resolved definition: **W** (writeable), **R** (readable),
**V** (identically validated) and **Round-Trip** (written == read) hold on
**both** transports — REST and MCP. Today that promise is only partly true; the
concrete, still-open violations are catalogued in spec section 9 and frozen in
``contract_matrix_baseline.json`` next to this file.

This module is the executable form of section 11. It drives the *real* stacks:

* REST through ``APIClient`` with a real JWT login (HTTP -> serializer ->
  service -> PostgreSQL), mirroring
  ``rest_api/tests/test_custom_fields_roundtrip.py``.
* MCP through the real ``ToolRegistry.dispatch_request`` with a real ``reqlo_*``
  API key (JSON-RPC method -> ToolRegistry auth/RBAC/preset -> tool group ->
  application service -> PostgreSQL), mirroring ``mcp_server/tests/test_e2e_mcp.py``.
  No collaborator is mocked; only the transport entry point differs.

Ratchet semantics
-----------------
``contract_matrix_baseline.json`` lists every *known* violation as
``{item_type, preset, transport, attribute, check, ws_issue, reason}``. The test
is GREEN while the set of ACTUAL violations is a SUBSET of the baseline:

* a NEW violation (any actual key not present in the baseline) fails the suite —
  a newly added attribute or item type therefore has to pass;
* the strict-shrink assertion additionally fails when a baseline entry no longer
  reproduces, so a closed gap must be removed from the baseline instead of
  silently rotting there.

It also records ``limitations`` — cells the test environment genuinely cannot
exercise (e.g. a ``reference`` attribute that needs an environment-specific FK
target). Those are *not* faked into passing checks; they are reported instead.

What is executed per ``(item_type, preset)``
--------------------------------------------
* every visible, writable attribute of the resolved definition (spec section 2
  carriers: ``core`` columns and the synthetic ``extended`` ``ws0_probe``) is
  written and read back once per transport — W / R / Round-Trip;
* one out-of-rule value for the extended probe is submitted on both transports
  and their accept/reject outcomes are compared — V (the bootstrapped core
  attributes carry no ``validation`` rules, so the probe is the only attribute
  V can meaningfully exercise);
* the REST ``attribute-schema`` endpoint must describe the item type and list
  every visible attribute — Discovery.

``CONTRACT_MATRIX_DUMP=<path>`` writes the raw actual violations to *path*
before the assertions run, which is how the committed baseline was produced.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

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
#:
#: ``CREATE``    — the bare create of the item type (attribute ``"*"``) failed.
#: ``W``         — a create carrying the attribute was rejected.
#: ``R``         — the read-back did not return the attribute key at all.
#: ``ROUNDTRIP`` — the read-back returned a different value than written.
#: ``V``         — REST and MCP disagreed on accepting an invalid probe value.
#: ``DISCOVERY`` — the REST ``attribute-schema`` endpoint did not describe the
#:                 item type / did not list every visible attribute.
CHECK_CODES = ("CREATE", "W", "R", "V", "ROUNDTRIP", "DISCOVERY")

_SECRET = "test-secret-not-a-real-key"
_JWT_OVERRIDES = dict(
    AUTH_JWT_SECRET=_SECRET,
    AUTH_JWT_ISSUER="reqflow",
    AUTH_JWT_AUDIENCE="reqflow-api",
    AUTH_JWT_TTL_SECONDS=3600,
)

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
    """

    rest_collection: str
    mcp_prefix: str | None
    mcp_create: str | None
    mcp_read: str | None
    base: Callable[[str], dict[str, Any]]


def _token(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


_SPECS: dict[str, _Spec] = {
    "Requirement": _Spec(
        "/api/v1/requirements/",
        "requirement",
        "requirement.create",
        "requirement.get",
        lambda token: {"title": f"cm-{token}"},
    ),
    "StakeholderNeed": _Spec(
        "/api/v1/needs/",
        "needs",
        "needs.create",
        "needs.read",
        lambda token: {"title": f"cm-{token}"},
    ),
    "ArchitectureElement": _Spec(
        "/api/v1/architecture/",
        "architecture",
        "architecture.create",
        "architecture.get",
        lambda token: {"title": f"cm-{token}", "element_type": "block"},
    ),
    "TestCase": _Spec(
        "/api/v1/testcases/",
        "test",
        "test.create",
        "test.get",
        lambda token: {"title": f"cm-{token}"},
    ),
    "Adr": _Spec(
        "/api/v1/adrs/",
        "adr",
        "adr.create",
        "adr.read",
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
        lambda token: {"title": f"cm-{token}", "probability": "low", "impact": "low"},
    ),
    "Issue": _Spec(
        "/api/v1/issues/",
        "issue",
        "issue.create",
        "issue.read",
        lambda token: {"title": f"cm-{token}"},
    ),
    "Goal": _Spec(
        "/api/v1/goals/",
        "goal",
        "goal.create",
        "goal.read",
        lambda token: {"title": f"cm-{token}"},
    ),
    # Epic #934 WS1: Icd gained an MCP tool group (``icd.create``/``icd.read``),
    # so the matrix now drives Icd on MCP as well. ``source_element_id`` /
    # ``target_element_id`` are the reference attributes the runner fills in.
    "Icd": _Spec(
        "/api/v1/icds/",
        "icd",
        "icd.create",
        "icd.read",
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
        lambda token: {"term": f"cm-{token}", "definition": "contract-matrix"},
    ),
    "ChangeRequest": _Spec(
        "/api/v1/change-requests/",
        "change_request",
        "change_request.create",
        "change_request.read",
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
    except Exception:  # pragma: no cover - defensive
        return "<undecodable>"
    return body[:300]


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
        entity_id = _find_key(result.data, "id")
        if entity_id is _MISSING or entity_id is None:
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
        return _Outcome(True, data=result.data)


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
    if attribute["type"] in ("reference", "user"):
        return (
            f"type '{attribute['type']}' needs an environment-specific FK target; "
            "no environment-independent probe value exists"
        )
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


def _find_key(obj: Any, key: str) -> Any:
    """Depth-first search for *key* in nested dict/list data; ``_MISSING`` if absent."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _find_key(value, key)
            if found is not _MISSING:
                return found
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found = _find_key(item, key)
            if found is not _MISSING:
                return found
    return _MISSING


def _extract_custom_field(obj: Any, name: str) -> tuple[bool, Any]:
    if isinstance(obj, dict):
        custom = obj.get("custom_fields")
        if isinstance(custom, dict):
            if name in custom:
                return True, custom[name]
        for value in obj.values():
            found, extracted = _extract_custom_field(value, name)
            if found:
                return found, extracted
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            found, extracted = _extract_custom_field(item, name)
            if found:
                return found, extracted
    return False, None


def _extract(data: Any, attribute: dict[str, Any]) -> tuple[bool, Any]:
    if attribute["kind"] == "extended":
        return _extract_custom_field(data, attribute["name"])
    value = _find_key(data, attribute["name"])
    if value is _MISSING:
        return False, None
    return True, value


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
# Violations
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
    item_type: str, preset: str, transport: str, attribute: str, reason: str
) -> dict[str, Any]:
    return {
        "item_type": item_type,
        "preset": preset,
        "transport": transport,
        "attribute": attribute,
        "reason": reason,
    }


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
) -> int:
    """Run one ``(item_type, preset, transport)`` cell; return executed checks."""
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
        return executed

    for attribute in _iter_writable_visible(attributes, sections):
        reason = _unprobeable_reason(attribute)
        if reason is not None:
            limitations.append(
                _limitation(item_type, preset, transport.name, attribute["name"], reason)
            )
            continue
        # A fresh token per create keeps unique columns (chiefly
        # GlossaryTerm.term) collision-free across the probes of one cell.
        token = _token(cell_token)
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
    return executed


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
    """Compare REST/MCP accept-or-reject of an out-of-rule probe value."""
    spec = _SPECS[item_type]
    if spec.mcp_create is None:
        return 0
    invalid_attribute = {"name": PROBE_NAME, "kind": "extended"}
    invalid = _payload(
        env,
        preset,
        item_type,
        spec,
        invalid_attribute,
        PROBE_INVALID,
        _token(f"v{item_type[:4].lower()}{preset[:3]}"),
    )

    rest_ok = rest.create(item_type, spec, invalid, workspace).ok
    mcp_ok = mcp.create(item_type, spec, invalid, workspace).ok
    if rest_ok != mcp_ok:
        violations.append(
            _violation(
                item_type,
                preset,
                "REST+MCP",
                PROBE_NAME,
                "V",
                f"invalid probe accepted by {'REST' if rest_ok else 'MCP'} "
                f"but rejected by {'MCP' if rest_ok else 'REST'}",
            )
        )
    return 2


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


def _run_matrix(env: _Env) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    rest = _RestTransport(env.rest_client)
    mcp = _McpTransport(env.registry, env.api_key)
    violations: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = []
    executed = 0

    workspace_resolver = WorkspaceAttributeDefinitionStore()
    for preset in PRESETS:
        workspace = env.workspaces[preset]
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
                        )
                    )
                    continue
                executed += _run_attribute_cell(
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
        "limitations": limitations,
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
    assert isinstance(baseline.get("limitations", []), list)


@override_settings(**_JWT_OVERRIDES)
@pytest.mark.django_db
def test_transport_contract_matrix_ratchets_against_the_baseline() -> None:
    """The AUC (spec section 11): actual violations must stay within the baseline.

    A NEW violation fails (new attributes / item types must pass). The
    strict-shrink assertion fails a baseline entry that no longer reproduces, so
    closing a gap requires removing its entry instead of leaving it to rot.
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
        "baseline entries no longer reproduce — remove them from "
        f"{BASELINE_PATH.name} (strict shrink): {stale_keys}"
    )

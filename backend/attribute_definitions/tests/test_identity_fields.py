"""Identity fields: ``id`` transport parity and ``uid`` import-key semantics.

Attribut v3 WS2 (#936), spec sections 3 and 5 (Teil C).

Two invariants the bootstrapped definitions already declare but no focused test
pinned yet:

* **``id``** is the sole identity (the Artifact UUID the routes address). Its
  synthetic definition attribute is ``visible=false`` / ``editable="system"``
  (spec section 5: hidden by default, revealed on demand), yet the value must be
  present in the read payload of **every** item type on **both** transports. A
  client write must never overwrite it.
* **``uid``** is an *external import key* (ReqIF) only. Nothing auto-generates
  it (no ``REQ-NNN`` number-circle), it stays read-only to clients, and its
  ``help_text`` says so on every model and serializer.

The transport pass drives the same real REST + MCP stacks as
``test_transport_contract_matrix`` (in-process ``APIClient`` + JWT and
``ToolRegistry.dispatch_request`` + ``reqlo_*`` API key), so a regression names
the exact type/transport/attribute instead of only failing the aggregate
ratchet.
"""
from __future__ import annotations

import uuid

import pytest
from django.test import override_settings

from attribute_definitions.schema import ITEM_TYPES
from attribute_definitions.tests.test_transport_contract_matrix import (
    _JWT_OVERRIDES,
    _McpTransport,
    _RestTransport,
    _SPECS,
    _build_env,
    _payload,
    _token,
)

pytestmark = [pytest.mark.e2e, pytest.mark.django_db]

#: The shared truth statement every ``uid`` field/declaration must carry (spec
#: section 3): external import key, never auto-generated, ``id`` is identity.
UID_HELP_TEXT_FRAGMENT = "External import key (ReqIF)"

#: The 8 special models that carry a ``uid`` column (spec section 3). Keyed by
#: ``(app_label, model_name)`` so the same list resolves through ``apps.get_model``.
_UID_MODELS = (
    ("persistence", "StakeholderNeed"),
    ("persistence", "Requirement"),
    ("persistence", "ArchitectureElement"),
    ("persistence", "TestCase"),
    ("persistence", "TestRun"),
    ("persistence", "Adr"),
    ("persistence", "Risk"),
    ("persistence", "Issue"),
)


def _transports(env):
    return (
        _RestTransport(env.rest_client),
        _McpTransport(env.registry, env.api_key),
    )


def _base_payload(env, item_type, token):
    """A fresh minimal create body for *item_type*.

    Must be called once per create, not once per type: an ``Icd`` payload is
    built by creating a fresh ArchitectureElement endpoint pair (each create
    records a ``decomposes`` TraceLink, and ``uq_tracelink_edge`` makes the pair
    unique), so reusing one payload across two transports is a duplicate-link
    500 for the second create — the same reason the contract matrix rebuilds it
    per cell.
    """
    spec = _SPECS[item_type]
    return spec, _payload(env, "standard", item_type, spec, None, None, token)


def test_id_attribute_is_hidden_by_default_but_always_transported() -> None:
    """``id`` is ``visible=false`` in every definition yet present on read.

    Spec section 5: the ``id`` system field is hidden by default (revealed on
    demand). The Attribute Usability Contract only iterates *visible* attributes,
    so this guard is what keeps the value identifiable even though the renderer
    does not draw it by default.
    """
    from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
        introspect_core_attributes,
    )

    with override_settings(**_JWT_OVERRIDES):
        env = _build_env()
        workspace = env.workspaces["standard"]
        failures: list[str] = []

        for item_type in sorted(ITEM_TYPES):
            definition = {
                attribute["name"]: attribute
                for attribute in introspect_core_attributes(item_type, "standard")
            }
            id_attribute = definition.get("id")
            if id_attribute is None:
                failures.append(f"{item_type}: definition exposes no 'id' attribute")
            elif id_attribute["visible"] is not False:
                failures.append(
                    f"{item_type}: 'id' must default to visible=false "
                    f"(got {id_attribute['visible']!r})"
                )
            elif id_attribute["editable"] != "system":
                failures.append(
                    f"{item_type}: 'id' must be editable='system' "
                    f"(got {id_attribute['editable']!r})"
                )

            for transport in _transports(env):
                spec, payload = _base_payload(
                    env, item_type, _token(f"id{item_type[:4]}")
                )
                created = transport.create(item_type, spec, payload, workspace)
                if not created.ok:
                    failures.append(
                        f"{item_type}/{transport.name}: create failed: {created.error}"
                    )
                    continue
                read = transport.read(
                    item_type, spec, created.entity_id or "", workspace
                )
                if not read.ok:
                    failures.append(
                        f"{item_type}/{transport.name}: read failed: {read.error}"
                    )
                    continue
                body = read.data if isinstance(read.data, dict) else {}
                value = body.get("id")
                if not isinstance(value, str) or not value.strip():
                    failures.append(
                        f"{item_type}/{transport.name}: read payload carries no "
                        f"string 'id' (got {value!r})"
                    )
                elif value != created.entity_id:
                    failures.append(
                        f"{item_type}/{transport.name}: read id {value!r} != "
                        f"created id {created.entity_id!r}"
                    )

        assert not failures, "Identity transport failures:\n" + "\n".join(failures)


def test_rest_never_rewrites_id_and_rejects_uid() -> None:
    """REST ignores a client ``id`` on create and rejects it on PATCH (#269).

    A ``uid`` write is refused the same way (read-only import key): the PATCH
    guard names it a protected field instead of dropping it silently.
    """
    with override_settings(**_JWT_OVERRIDES):
        env = _build_env()
        workspace = env.workspaces["standard"]
        client = env.rest_client
        supplied_id = str(uuid.uuid4())

        created = client.post(
            "/api/v1/requirements/",
            {
                "workspace_id": str(workspace.id),
                "title": f"cm-{_token('idwrite')}",
                "id": supplied_id,
            },
            format="json",
        )
        assert created.status_code == 201, created.content
        entity_id = created.json()["id"]
        assert entity_id != supplied_id, "a client-supplied id was accepted as identity"

        other_id = str(uuid.uuid4())
        rejected = client.patch(
            f"/api/v1/requirements/{entity_id}/",
            {"id": other_id},
            format="json",
        )
        assert rejected.status_code == 400, rejected.content
        assert rejected.json()["error"]["details"][0]["field"] == "id"

        uid_rejected = client.patch(
            f"/api/v1/requirements/{entity_id}/",
            {"uid": "REQ-9999"},
            format="json",
        )
        assert uid_rejected.status_code == 400, uid_rejected.content
        assert uid_rejected.json()["error"]["details"][0]["field"] == "uid"

        read = client.get(f"/api/v1/requirements/{entity_id}/")
        assert read.status_code == 200, read.content
        body = read.json()
        assert body["id"] == entity_id
        assert body["uid"] is None, "PATCH with uid must not have stored it"


def test_mcp_create_never_uses_a_client_supplied_id() -> None:
    """MCP either rejects an ``id`` param or generates its own — never reuses it."""
    with override_settings(**_JWT_OVERRIDES):
        env = _build_env()
        workspace = env.workspaces["standard"]
        transport = _McpTransport(env.registry, env.api_key)
        spec, payload = _base_payload(env, "Adr", _token("mcp-idwrite"))
        supplied_id = str(uuid.uuid4())
        payload["id"] = supplied_id

        outcome = transport.create("Adr", spec, payload, workspace)
        if outcome.ok:
            assert outcome.entity_id != supplied_id, (
                "MCP create accepted the client-supplied id as the identity"
            )
        else:
            assert outcome.error, "a rejected write must carry a reason"


def test_uid_is_never_auto_generated_on_create() -> None:
    """Every transported type is created with a null ``uid`` (spec section 3)."""
    with override_settings(**_JWT_OVERRIDES):
        env = _build_env()
        workspace = env.workspaces["standard"]
        failures: list[str] = []

        for item_type in sorted(ITEM_TYPES):
            for transport in _transports(env):
                spec, payload = _base_payload(
                    env, item_type, _token(f"uid{item_type[:4]}")
                )
                created = transport.create(item_type, spec, payload, workspace)
                if not created.ok:
                    failures.append(
                        f"{item_type}/{transport.name}: create failed: {created.error}"
                    )
                    continue
                read = transport.read(
                    item_type, spec, created.entity_id or "", workspace
                )
                if not read.ok:
                    failures.append(
                        f"{item_type}/{transport.name}: read failed: {read.error}"
                    )
                    continue
                body = read.data if isinstance(read.data, dict) else {}
                if body.get("uid"):
                    failures.append(
                        f"{item_type}/{transport.name}: create auto-generated uid "
                        f"{body['uid']!r}"
                    )

        assert not failures, "uid auto-generation failures:\n" + "\n".join(failures)


def test_uid_model_fields_document_the_import_key_relationship() -> None:
    """All 8 ``uid`` columns state reality; none claims auto-generation."""
    from django.apps import apps

    failures: list[str] = []
    for app_label, model_name in _UID_MODELS:
        field = apps.get_model(app_label, model_name)._meta.get_field("uid")
        help_text = field.help_text or ""
        if UID_HELP_TEXT_FRAGMENT not in help_text:
            failures.append(f"{model_name}.uid help_text is {help_text!r}")
        if "read-only, auto-generated" in help_text:
            failures.append(f"{model_name}.uid still claims auto-generation")

    assert not failures, "uid model help_text failures:\n" + "\n".join(failures)


def test_uid_serializer_fields_are_read_only_and_documented() -> None:
    """Every entity serializer exposes ``uid`` read-only with the shared text."""
    from rest_api.serializers import (
        UID_HELP_TEXT,
        AdrSerializer,
        ArchitectureElementSerializer,
        IssueSerializer,
        RequirementSerializer,
        RiskSerializer,
        StakeholderNeedSerializer,
        TestCaseSerializer,
        TestRunSerializer,
    )

    for serializer_cls in (
        RequirementSerializer,
        StakeholderNeedSerializer,
        ArchitectureElementSerializer,
        TestCaseSerializer,
        AdrSerializer,
        RiskSerializer,
        TestRunSerializer,
        IssueSerializer,
    ):
        field = serializer_cls().fields["uid"]
        assert field.read_only is True, f"{serializer_cls.__name__}.uid is writable"
        assert field.help_text == UID_HELP_TEXT, serializer_cls.__name__

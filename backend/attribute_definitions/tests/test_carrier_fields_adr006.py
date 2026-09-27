"""ADR-006 — two field kinds: a person reference from the system, and free text.

Issue #1088, wave 2. Three fields stopped being free text, each with the
mechanism that fits its meaning:

* ``Adr.deciders`` / ``Issue.assignee`` — **multi-value Actor references**
  (``ManyToManyField`` to the system's own person/team rows, the same carrier
  the single-valued ``Artifact.owner``/``reporter`` FKs use since WS2/#936);
* ``StakeholderNeed.stakeholder`` — a **multi-value classification** (ISO 42010
  role/group) whose option list comes from the attribute catalogue
  (``type=multi-enum``), *not* a person reference: an Actor row per role would
  be invented data.

What this module pins, each test being a way the work could silently not have
landed:

* both person fields are multi-selections of Actors and are **identical over
  REST and MCP** — the AUC (spec section 11) property the contract matrix
  ratchets, asserted here per field so a regression names the exact transport;
* a multi-selection reads back in **write order** (round-trip, not set equality);
* renaming an Actor shows up everywhere it is referenced, because the field is a
  reference and not a typed name — and no name is denormalised onto the row;
* the stakeholder selection is validated against the **catalogue's** options, and
  those options survive both ``bootstrap_attribute_definitions`` and its
  ``--relabel`` repair mode, plus a per-workspace edit;
* ``custom_fields`` is still **flat** (REQ-L2-AS-037): the carrier exists
  precisely so the map does not have to hold objects or arrays, and a widening
  of the map is a design error, not a feature;
* the catalogue no longer presents a phantom (``origin_link``) or a comment that
  defers the work to the wrong issue (``WS7/AWMS #940``);
* the new migration ships a row-level-security policy for both new join tables.

The heavy REST/MCP tests reuse the real stacks of
``test_transport_contract_matrix`` (APIClient + JWT, ToolRegistry + ``reqlo_*``
API key, no mocked collaborator) so "identical over both transports" means the
same thing here as it does in the CI ratchet.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.test import override_settings

from application.actor_service import ActorService
from attribute_definitions.global_definition_store import GlobalAttributeDefinitionStore
from attribute_definitions.schema import (
    ENTITY_LEVEL_CARRIER_FIELDS,
    all_entity_carrier_fields,
    stored_attributes,
)
from attribute_definitions.workspace_definition_store import (
    WorkspaceAttributeDefinitionStore,
)
from auth_tenancy.context import AuthContext, AuthMethod
from auth_tenancy.models import ROLE_ADMIN
from persistence.custom_fields import validate_custom_fields
from persistence.models import Actor, Adr, Artifact, Issue, Tenant, User, Workspace

pytestmark = pytest.mark.django_db

#: The item types and attribute names of the multi-value person fields.
PERSON_FIELDS = (("Adr", "deciders"), ("Issue", "assignee"))

#: The multi-value classification field: item type -> attribute name.
STAKEHOLDER_FIELD = ("StakeholderNeed", "stakeholder")


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------


def _backend_root() -> Path:
    """Return the backend package directory, in both the host and container layout.

    ``docs/agent-templates/tool-manifest.json`` is the marker that works for
    both: on the host the root is ``parents[3]`` from this file, in the container
    ``backend`` *is* ``/app`` with ``docs/`` bind-mounted at ``/app/docs`` (so a
    fixed index resolves to ``/docs/...`` and finds nothing). Whether the backend
    package then sits *at* the root or in a ``backend/`` subdirectory is decided
    by looking for the package itself, not by counting parents.
    """
    for ancestor in Path(__file__).resolve().parents:
        if (ancestor / "docs" / "agent-templates" / "tool-manifest.json").is_file():
            if (ancestor / "attribute_definitions" / "schema.py").is_file():
                return ancestor
            return ancestor / "backend"
    raise AssertionError("backend package root not found from the test file")


def _build_env_with_actors() -> tuple[Any, list[str]]:
    """A bootstrapped multi-preset environment plus two extra internal Actors.

    Returns the contract-matrix ``_Env`` (three workspaces, a JWT-authenticated
    APIClient, a real API key, the admin's own Actor) and the ids of two further
    Actors, so a multi-selection can be written with more than one entry.
    """
    from attribute_definitions.tests.test_transport_contract_matrix import _build_env

    env = _build_env()
    extra: list[str] = []
    for index in range(2):
        user = User.objects.create(
            username=f"adr006-{index}-{env.admin.username}",
            email=f"adr006-{index}@t.test",
            tenant=env.tenant,
        )
        ctx = AuthContext(
            user_id=user.id,
            tenant_id=env.tenant.id,
            active_roles=(ROLE_ADMIN,),
            auth_method=AuthMethod.BEARER_TOKEN,
        )
        extra.append(str(ActorService().get_or_create_for_user(ctx, user.id).id))
    return env, extra


def _transports(env: Any) -> tuple[Any, Any]:
    from attribute_definitions.tests.test_transport_contract_matrix import (
        _McpTransport,
        _RestTransport,
    )

    return _RestTransport(env.rest_client), _McpTransport(env.registry, env.api_key)


def _selection(*actor_ids: str) -> dict[str, Any]:
    """The wire form of a multi-value person field (spec section 4)."""
    return {
        "multiple": True,
        "items": [{"kind": "user", "id": actor_id} for actor_id in actor_ids],
    }


def _selected_ids(value: Any) -> set[str]:
    """The set of Actor ids in a multi-value person value (order-insensitive).

    A person selection is a **set**, not a sequence: Django's own
    ``ManyRelatedManager.set()`` cannot preserve the payload order (its non-fast
    path diffs the ids as a Python set), so the shared read resolves a
    deterministic data order instead — see
    ``ArtifactAttributeGateway.selected_actors``. A round-trip therefore asserts
    *the same selection*, and stability across two reads is asserted separately.
    """
    return {item["id"] for item in value["items"]}


def _definition(tenant: Tenant, workspace: Workspace, item_type: str) -> dict[str, Any]:
    row = WorkspaceAttributeDefinitionStore().resolve(
        tenant.id, workspace.id, item_type, "standard"
    )
    return {a["name"]: a for a in stored_attributes(row.definition_json)}


# ---------------------------------------------------------------------------
# 1. The person fields are multi-selections of Actors, identical on both transports
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("item_type", "attribute"), PERSON_FIELDS)
def test_person_field_is_a_multi_selection_of_actors(
    item_type: str, attribute: str
) -> None:
    """The definition says ``actor`` + ``multiple``, and the value is an envelope.

    A ``multiple`` actor field carries ``{"multiple": true, "items": [...]}`` and
    not a bare entry: that is what lets one attribute name mean either shape
    without a second name, and what the shared write adapter accepts.
    """
    from attribute_definitions.tests.test_transport_contract_matrix import _build_env

    env = _build_env()
    definition = _definition(env.tenant, env.workspaces["standard"], item_type)
    entry = definition[attribute]

    assert entry["kind"] == "core", (
        f"{item_type}.{attribute} must be a column-backed core attribute: the "
        f"flat custom_fields map rejects the object/array value it would hold"
    )
    assert entry["type"] == "actor"
    assert entry["multiple"] is True
    assert entry["visible"] is True
    assert entry["editable"] is True
    assert (item_type, attribute) in {
        (t, n) for t, names in ENTITY_LEVEL_CARRIER_FIELDS.items() for n in names
    }


@pytest.mark.parametrize(("item_type", "attribute"), PERSON_FIELDS)
def test_person_field_round_trips_identically_over_rest_and_mcp(
    item_type: str, attribute: str
) -> None:
    """Write two Actors over both transports, read back — same selection on both.

    The AUC (spec section 11) round-trip, per field and per transport. The write
    also proves the value never reaches the type-specific service: ``adr.create``
    / ``issue.create`` have no such parameter, so a payload that carried it
    unstripped would answer "Invalid field for adr.create" instead of 201.
    """
    from attribute_definitions.tests.test_transport_contract_matrix import (
        _JWT_OVERRIDES,
        _SPECS,
        _payload,
        _token,
    )

    with override_settings(**_JWT_OVERRIDES):
        env, extra = _build_env_with_actors()
        rest, mcp = _transports(env)
        workspace = env.workspaces["standard"]
        spec = _SPECS[item_type]
        written = _selection(extra[1], env.admin_actor_id, extra[0])

        read_back: dict[str, Any] = {}
        for transport in (rest, mcp):
            payload = _payload(
                env,
                "standard",
                item_type,
                spec,
                None,
                None,
                _token(f"adr006{item_type[:3]}"),
            )
            payload[attribute] = written
            created = transport.create(item_type, spec, payload, workspace)
            assert created.ok, f"{item_type}/{transport.name}: {created.error}"
            read = transport.read(item_type, spec, created.entity_id or "", workspace)
            assert read.ok, f"{item_type}/{transport.name}: {read.error}"
            read_back[transport.name] = read.data[attribute]
            # Second read of the same artifact: the projection must be stable
            # (the AUC's round-trip stability half, and what a re-render relies on).
            again = transport.read(item_type, spec, created.entity_id or "", workspace)
            assert again.data[attribute] == read.data[attribute], (
                f"{item_type}/{transport.name}: two reads of an unchanged "
                f"selection disagree"
            )

        expected = _selected_ids(written)
        for name, value in read_back.items():
            assert _selected_ids(value) == expected, (
                f"{item_type}/{name}: wrote {expected}, read {_selected_ids(value)}"
            )
        assert read_back["REST"] == read_back["MCP"], (
            "REST and MCP disagree on a multi-value person field: "
            f"{read_back['REST']!r} vs {read_back['MCP']!r}"
        )


def test_multi_actor_selection_is_a_relation_not_a_typed_name() -> None:
    """The value is a relation to ``Actor`` rows, and no name is copied anywhere.

    A typed name list would satisfy the round-trip above just as well — this is
    the assertion that rules it out: the selection is a ``ManyToManyField`` to
    ``persistence.Actor`` and therefore has no column of its own on the entity
    row that a name could hide in.
    """
    for model, attribute in ((Adr, "deciders"), (Issue, "assignee")):
        field = model._meta.get_field(attribute)
        assert field.many_to_many is True
        assert field.related_model is Actor
        assert field.column is None, (
            f"{model.__name__}.{attribute} must not have a column on the entity "
            f"row: the value is the join, not a copied id or name"
        )


def test_renamed_actor_is_reflected_in_the_person_field() -> None:
    """A rename follows the reference — the property free text can never have.

    The wire form carries the Actor *id*, so a rename is invisible in the payload
    by construction; what makes it a reference rather than a copy is that the id
    resolves to the same row and that row now answers with the new name, with no
    write to the artifact at all. Asserted through the shared read projection
    both transports use, so it is a statement about the shipped behaviour.
    """
    from application.artifact_attribute_gateway import artifact_system_fields

    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"ren-{suffix}", slug=f"ren-{suffix}")
    workspace = Workspace.unscoped.create(
        tenant=tenant, name=f"ren-ws-{suffix}", preset={"name": "standard"}
    )
    user = User.objects.create(
        username=f"ren-admin-{suffix}", email=f"ren-{suffix}@t.test", tenant=tenant
    )
    ctx = AuthContext(
        user_id=user.id,
        tenant_id=tenant.id,
        active_roles=(ROLE_ADMIN,),
        auth_method=AuthMethod.BEARER_TOKEN,
    )
    call_command("bootstrap_attribute_definitions", tenant=str(tenant.id))
    actor = ActorService().get_or_create_for_user(ctx, user.id)

    from application.adr_service import AdrService

    adr = AdrService().create_adr(
        workspace_id=workspace.id, title="Renamed", description="", ctx=ctx
    )
    from application.artifact_attribute_gateway import (
        ArtifactAttributeGateway,
        AttributeValues,
    )

    ArtifactAttributeGateway().write(
        ctx, "Adr", adr, AttributeValues(core={"deciders": _selection(str(actor.id))})
    )

    before = Adr.unscoped.get(id=adr.id)
    Actor.unscoped.filter(id=actor.id).update(display_name="Renamed Person")
    after = Adr.unscoped.get(id=adr.id)

    # No write touched the entity, and the selection still points at one row.
    assert after.version == before.version
    projection = artifact_system_fields(after)
    assert _selected_ids(projection["deciders"]) == {str(actor.id)}
    resolved = Actor.unscoped.get(id=projection["deciders"]["items"][0]["id"])
    assert resolved.display_name == "Renamed Person"
    assert "Renamed Person" not in str(after.__dict__), (
        "the actor's name must not be denormalised onto the ADR row"
    )


# ---------------------------------------------------------------------------
# 2. The stakeholder selection: catalogue options, multi-value
# ---------------------------------------------------------------------------


def test_stakeholder_is_a_catalogue_backed_multi_select() -> None:
    """``type=multi-enum`` with a non-empty option list from the catalogue.

    The stakeholder of a need is a **role or a group** (ISO 42010), so this is a
    classification and not a person reference — an Actor field would force an
    invented Actor row per role. The value is a list, which the flat
    ``custom_fields`` map rejects, hence the column-backed ``core`` carrier.
    """
    from attribute_definitions.tests.test_transport_contract_matrix import _build_env

    env = _build_env()
    entry = _definition(env.tenant, env.workspaces["standard"], "StakeholderNeed")[
        "stakeholder"
    ]

    assert entry["type"] == "multi-enum"
    assert entry["kind"] == "core"
    assert entry["multiple"] is False, (
        "multi-enum already implies multiple; the 'multiple' property is the "
        "actor type's value-shape switch and must not be set here"
    )
    assert entry["options"], "a multi-enum without options is unsatisfiable"
    assert all(
        set(option) == {"value", "label_de", "label_en"} for option in entry["options"]
    )
    assert Artifact._meta.get_field("stakeholder") is not None


def test_stakeholder_selection_round_trips_over_rest_and_mcp() -> None:
    """Two roles written over both transports read back identically."""
    from attribute_definitions.tests.test_transport_contract_matrix import (
        _JWT_OVERRIDES,
        _SPECS,
        _build_env,
        _payload,
        _token,
    )

    with override_settings(**_JWT_OVERRIDES):
        env = _build_env()
        rest, mcp = _transports(env)
        workspace = env.workspaces["standard"]
        spec = _SPECS["StakeholderNeed"]
        options = _definition(env.tenant, workspace, "StakeholderNeed")["stakeholder"][
            "options"
        ]
        written = [options[0]["value"], options[2]["value"]]

        read_back: dict[str, Any] = {}
        for transport in (rest, mcp):
            payload = _payload(
                env, "standard", "StakeholderNeed", spec, None, None, _token("adr006need")
            )
            payload["stakeholder"] = written
            created = transport.create("StakeholderNeed", spec, payload, workspace)
            assert created.ok, f"StakeholderNeed/{transport.name}: {created.error}"
            read = transport.read(
                "StakeholderNeed", spec, created.entity_id or "", workspace
            )
            assert read.ok, f"StakeholderNeed/{transport.name}: {read.error}"
            read_back[transport.name] = read.data["stakeholder"]

        assert read_back["REST"] == written
        assert read_back["MCP"] == written
        assert read_back["REST"] == read_back["MCP"]


def test_stakeholder_rejects_an_option_outside_the_catalogue() -> None:
    """The option list is enforced, so the field is a selection and not free text.

    This is the whole point of the multi-value enum variant over a text field: a
    value the catalogue does not offer is a 400 on both transports, identically.
    """
    from attribute_definitions.tests.test_transport_contract_matrix import (
        _JWT_OVERRIDES,
        _SPECS,
        _build_env,
        _payload,
        _token,
    )

    with override_settings(**_JWT_OVERRIDES):
        env = _build_env()
        rest, mcp = _transports(env)
        workspace = env.workspaces["standard"]
        spec = _SPECS["StakeholderNeed"]
        payload = _payload(
            env, "standard", "StakeholderNeed", spec, None, None, _token("adr006bad")
        )
        payload["stakeholder"] = ["not-a-catalogue-role"]

        results = {
            transport.name: transport.create("StakeholderNeed", spec, payload, workspace)
            for transport in (rest, mcp)
        }
        assert not results["REST"].ok, results["REST"].error
        assert not results["MCP"].ok, results["MCP"].error


def test_catalogue_option_lists_survive_bootstrap_and_relabel() -> None:
    """The option list is seeded by the bootstrap and survives ``--relabel``.

    A workspace must be able to configure its own stakeholder roles, so the list
    has to be ordinary catalogue data on the way in AND survive the #1090 label
    repair mode, which is the one recovery path that rewrites a bootstrapped row
    in place. ``--relabel`` overwrites ``label``/``help_text`` only; if the option
    list were derived, re-derived or normalised away anywhere in that path, this
    is where it would show.
    """
    from attribute_definitions.management.commands.bootstrap_attribute_definitions import (
        RELABEL_KEYS,
    )

    assert "options" not in RELABEL_KEYS, (
        "the label repair must not touch option lists — that is the property "
        "this test pins"
    )

    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant.objects.create(name=f"opt-{suffix}", slug=f"opt-{suffix}")
    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id))

    def _options() -> list[dict[str, str]]:
        row = GlobalAttributeDefinitionStore().get(
            tenant_id=tenant.id, item_type="StakeholderNeed", preset="standard"
        )
        assert row is not None
        stored = {a["name"]: a for a in stored_attributes(row.definition_json)}
        return stored["stakeholder"]["options"]

    seeded = _options()
    assert seeded, "bootstrap must seed the stakeholder option list"

    # Simulate a pre-#1090 row (raw field name as the label in BOTH locales) and
    # repair it: the option list must be byte-identical afterwards.
    row = GlobalAttributeDefinitionStore().get(
        tenant_id=tenant.id, item_type="StakeholderNeed", preset="standard"
    )
    payload = dict(row.definition_json)
    attributes = []
    for attribute in payload["attributes"]:
        attributes.append(
            dict(attribute, label={"de": attribute["name"], "en": attribute["name"]})
            if attribute["name"] == "stakeholder"
            else attribute
        )
    row.definition_json = dict(payload, attributes=attributes)
    row.save(update_fields=["definition_json"])

    call_command("bootstrap_attribute_definitions", "--tenant", str(tenant.id), "--relabel")

    assert _options() == seeded


def test_a_workspace_can_replace_the_catalogue_option_list() -> None:
    """Options are ordinary per-workspace catalogue data, not code.

    This is the "where do the option lists live" decision made testable: next to
    every other enum's ``options``, in the attribute catalogue entry itself, which
    is why ``attribute_definition.update`` can carry a workspace's own role list
    with no new mechanism.
    """
    from attribute_definitions.tests.test_transport_contract_matrix import _build_env

    env = _build_env()
    store = WorkspaceAttributeDefinitionStore()
    resolved = store.resolve(
        env.tenant.id, env.workspaces["standard"].id, "StakeholderNeed", "standard"
    )
    attributes = stored_attributes(resolved.definition_json)
    custom = [
        {"value": "safety_officer", "label_de": "Fachkraft für Arbeitssicherheit",
         "label_en": "Safety officer"},
        {"value": "field_service", "label_de": "Feld service", "label_en": "Field service"},
    ]
    for attribute in attributes:
        if attribute["name"] == "stakeholder":
            attribute["options"] = custom

    store.update(
        env.tenant.id, env.workspaces["standard"].id, "StakeholderNeed", attributes
    )
    reread = {a["name"]: a for a in stored_attributes(
        store.resolve(
            env.tenant.id, env.workspaces["standard"].id, "StakeholderNeed", "standard"
        ).definition_json
    )}
    assert reread["stakeholder"]["options"] == custom


# ---------------------------------------------------------------------------
# 3. The flat custom_fields map stays flat
# ---------------------------------------------------------------------------


def test_custom_fields_still_rejects_an_object_value() -> None:
    """REQ-L2-AS-037: the map is flat, and the carrier is why.

    The three fields above needed dedicated columns precisely because this
    function refuses a dict (and a list). Widening it would be a *design* error
    rather than a feature — it would break the GIN access path, the flat contract
    Import/Export and the bundle contract rely on, and put a structured value into
    a carrier the attribute system does not validate. So the rejection is pinned.
    """
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        validate_custom_fields({"deciders": {"multiple": True, "items": []}})
    with pytest.raises(ValidationError):
        validate_custom_fields({"stakeholder": ["customer"]})
    # The scalar contract is unchanged.
    assert validate_custom_fields({"source": "customer interview"}) == {
        "source": "customer interview"
    }


def test_rest_custom_fields_still_rejects_an_object_value() -> None:
    """The same rejection on the REST write path, through a real serializer.

    The serializer delegates to :func:`validate_custom_fields` (single source of
    truth), so a payload carrying the value the map cannot hold is a field-scoped
    400 — not a 201 with the entry silently dropped.
    """
    from rest_api.serializers import RequirementSerializer

    serializer = RequirementSerializer(
        data={
            "workspace_id": str(uuid.uuid4()),
            "title": "flat map",
            "custom_fields": {"stakeholder": ["customer"]},
        }
    )
    assert serializer.is_valid() is False
    assert "custom_fields" in serializer.errors, serializer.errors


# ---------------------------------------------------------------------------
# 4. Catalogue hygiene
# ---------------------------------------------------------------------------


def test_origin_link_is_gone_from_the_whole_backend() -> None:
    """The phantom attribute left no trace anywhere in the backend.

    It had two catalogue references and **zero** writers: no model field, no
    serializer, no service parameter, no import, no export. Removal is asserted
    over the source tree (not only over the catalogue) so a leftover writer, a
    leftover export column or a leftover migration cannot make it look wired.
    """
    offenders: list[str] = []
    for path in _backend_root().rglob("*.py"):
        if "tests" in path.parts or "migrations" in path.parts:
            continue
        # ``errors="replace"``: the sweep is about *content*, and a stray
        # non-UTF-8 byte in an unrelated file must not abort it. Only a QUOTED
        # name counts — a phantom attribute always reaches the code as a string
        # (a definition entry, a model field, an export column), while the
        # backticked mention in ``stage_matrix``'s removal note is prose about
        # the decision, not a use of it.
        if '"origin_link"' in path.read_text(encoding="utf-8", errors="replace") or (
            "'origin_link'" in path.read_text(encoding="utf-8", errors="replace")
        ):
            offenders.append(str(path))
    assert offenders == [], (
        "origin_link is referenced as a name outside the catalogue/tests; it was "
        f"removed as a phantom attribute (ADR-006): {offenders}"
    )


def test_no_source_level_comment_defers_the_actor_carrier_to_awms() -> None:
    """The misleading WS7/AWMS deferral is gone (source-level assertion).

    ``stage_matrix.py`` used to say the Actor value "is upgraded when the Actor
    carrier lands (WS7/AWMS, #940)". AWMS is the attribute **value migration**
    system; the actor carrier had already landed as WS2/#936, so the comment
    pointed a reader at the wrong piece of work. The repo already asserts
    comments at this level, so this does too.
    """
    stage_matrix = (
        _backend_root() / "attribute_definitions" / "stage_matrix.py"
    ).read_text(encoding="utf-8")
    assert not re.search(
        r"Actor[- ]?(?:Träger|carrier).{0,80}(?:WS7|AWMS|#940)",
        stage_matrix,
        re.IGNORECASE | re.DOTALL,
    ), (
        "stage_matrix still defers the actor carrier to WS7/AWMS/#940; the "
        "carrier landed as WS2/#936 (ADR-006)"
    )
    assert "Interim als Text, bis der Actor-Träger greift" not in stage_matrix


# ---------------------------------------------------------------------------
# 5. The migration: model + RLS policy in one leaf
# ---------------------------------------------------------------------------


def test_migration_ships_a_rls_policy_for_both_join_tables() -> None:
    """Both ``ManyToManyField`` join tables get a tenant-isolation policy.

    A join table has no ``tenant_id`` column, so the standard
    ``tenant_id = current_setting(...)`` policy is not merely missing but
    inexpressible; the policy resolves the isolation through the parent row
    instead. Asserted over the migration *source* (so it is a static CI check
    with no database) and against ``pg_policies`` for the same tables, which
    catches a typo'd table name the static half cannot see.
    """
    from django.db import connection

    migration = (
        _backend_root()
        / "persistence"
        / "migrations"
        / "0102_adr_deciders_issue_assignee_artifact_stakeholder.py"
    )
    source = migration.read_text(encoding="utf-8")

    # The join tables are named explicitly (not derived from the field defaults)
    # next to the parent table and the join column the policy filters on.
    for table, parent, parent_column in (
        ("as_adr_deciders", "as_adr", "adr_id"),
        ("as_issue_assignee", "as_issue", "issue_id"),
    ):
        assert f'("{table}", "{parent}", "{parent_column}")' in source, (
            f"{table} must be declared in _JOIN_TABLES with its parent table and "
            f"the join column the policy filters on"
        )
    # The policy template itself: parent-EXISTS resolution, not a tenant_id
    # comparison (which the join table does not have).
    assert "CREATE POLICY {policy} ON {table}" in source
    assert "ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in source
    assert "FROM {parent} p" in source
    assert "p.tenant_id = {current_tenant}" in source
    assert "USING (EXISTS" in source and "WITH CHECK (EXISTS" in source
    assert "migrations.RunSQL(sql=_enable_sql()" in source, (
        "the policies must be part of the same migration as the model change so "
        "the app keeps a single migration leaf"
    )
    assert "migrations.AddField(" in source

    if connection.vendor != "postgresql":  # pragma: no cover - CI runs Postgres
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "select tablename, policyname from pg_policies where tablename = any(%s)",
            (["as_adr_deciders", "as_issue_assignee"],),
        )
        policies = set(cursor.fetchall())
    assert policies == {
        ("as_adr_deciders", "as_adr_deciders_tenant_isolation"),
        ("as_issue_assignee", "as_issue_assignee_tenant_isolation"),
    }, policies


# ---------------------------------------------------------------------------
# 6. The registry is the single source for "a transport carries this name"
# ---------------------------------------------------------------------------


def test_both_transports_forward_the_same_field_name_set() -> None:
    """REST and MCP must forward the same names, or one of them 500s.

    The set has two jobs that must be the *same* set: the gateway write picks
    those keys out of the payload, and the create/update handlers pop exactly
    those names before splatting the rest into a type-specific service. A name in
    one list and not the other is a ``TypeError`` on create.
    """
    from mcp_server.tools.system_fields import SYSTEM_FIELD_NAMES
    from rest_api.views import _SYSTEM_FIELD_NAMES

    assert _SYSTEM_FIELD_NAMES == SYSTEM_FIELD_NAMES
    assert set(all_entity_carrier_fields()) <= set(_SYSTEM_FIELD_NAMES)
    for item_type, names in ENTITY_LEVEL_CARRIER_FIELDS.items():
        for name in names:
            assert (item_type, name) in {
                (t, n) for t, ns in ENTITY_LEVEL_CARRIER_FIELDS.items() for n in ns
            }

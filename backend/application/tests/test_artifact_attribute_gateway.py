"""Behaviour tests for the ArtifactAttributeGateway (WS0 #941 / WS1 #935).

Locks the public surface, the shared payload contract (AUC, spec section 11)
and the WS1 carrier-aware behaviour of ``discover``/``read``/``write``. No
database, no Django app registry required: the definition facade is injected as
a fake and the artifact as a structural double (the gateway's
``AttributeArtifact`` protocol is pure Python).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from application.artifact_attribute_gateway import (
    ArtifactAttributeGateway,
    AttributeCarrier,
    AttributeValues,
    carrier_for,
)
from attribute_definitions.field_validation import FieldValidationError
from attribute_definitions.schema import ITEM_TYPES
from auth_tenancy.context import AuthContext, AuthMethod


def _attribute(
    name: str,
    *,
    kind: str = "core",
    type_: str = "text",
    section: str = "general",
    order: int = 0,
    visible: bool = True,
    editable: Any = True,
    required: bool = False,
    options: list[dict[str, str]] | None = None,
    validation: dict[str, Any] | None = None,
    widget_key: str | None = None,
    fields: list[str] | None = None,
    multiple: bool = False,
    allow_external: bool = False,
    copyable: bool = False,
    reveal: str = "always",
    mask: str = "none",
    display_format: str = "text",
) -> dict[str, Any]:
    """One normalized definition entry (shape of ``stored_attributes``)."""
    return {
        "name": name,
        "kind": kind,
        "type": type_,
        "section": section,
        "order": order,
        "visible": visible,
        "editable": editable,
        "required": required,
        "label": {"de": name, "en": name},
        "options": options or [],
        "validation": validation or {},
        "widget_key": widget_key,
        "fields": fields or [],
        "multiple": multiple,
        "allow_external": allow_external,
        "copyable": copyable,
        "reveal": reveal,
        "mask": mask,
        "display_format": display_format,
    }


class _FakeDefinitions:
    """Records delegation without touching the ORM."""

    def __init__(
        self,
        *,
        attributes: list[dict[str, Any]] | None = None,
        sections: list[dict[str, Any]] | None = None,
        validate_error: Exception | None = None,
    ) -> None:
        self.resolved: list[tuple[str, UUID]] = []
        self.validated: list[tuple[Any, ...]] = []
        self._attributes = attributes or []
        self._sections = sections or []
        self._validate_error = validate_error

    def resolve(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> dict[str, Any]:
        self.resolved.append((item_type, workspace_id))
        return {
            "item_type": item_type,
            "preset": "standard",
            "attributes": list(self._attributes),
            "sections": list(self._sections),
        }

    def validate_artifact_fields(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        changed_fields: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> None:
        self.validated.append((item_type, workspace_id, changed_fields, existing))
        if self._validate_error is not None:
            raise self._validate_error


class _FakeBacking:
    """Backing ``Artifact`` double: owns ``custom_fields``."""

    def __init__(self, custom_fields: dict[str, Any] | None = None) -> None:
        self.custom_fields: dict[str, Any] = dict(custom_fields or {})
        self.saves = 0

    def save(self) -> None:
        self.saves += 1


class _FakeArtifact:
    """Type-specific entity double: core columns + a backing ``Artifact``."""

    def __init__(
        self,
        *,
        workspace_id: UUID | None = None,
        backing: _FakeBacking | None = None,
        **values: Any,
    ) -> None:
        self.id = uuid4()
        self.workspace_id = workspace_id if workspace_id is not None else uuid4()
        for key, value in values.items():
            setattr(self, key, value)
        self.artifact = backing if backing is not None else _FakeBacking()
        self.saves = 0

    def save(self) -> None:
        self.saves += 1


class _FakeDirectArtifact:
    """Generic ``Artifact`` double: owns ``custom_fields`` directly."""

    def __init__(self, custom_fields: Any = None, **values: Any) -> None:
        self.id = uuid4()
        self.workspace_id = uuid4()
        self.custom_fields = custom_fields
        for key, value in values.items():
            setattr(self, key, value)

    def save(self) -> None:
        pass


def _ctx() -> AuthContext:
    return AuthContext(
        user_id=uuid4(),
        tenant_id=uuid4(),
        active_roles=("admin",),
        auth_method=AuthMethod.BEARER_TOKEN,
    )


def _visible_section(name: str = "general", *, visible: bool = True) -> dict[str, Any]:
    return {"name": name, "order": 0, "visible": visible, "layout": "full"}


# ---------------------------------------------------------------------------
# Interface / payload contract
# ---------------------------------------------------------------------------


def test_interface_surface_and_carriers() -> None:
    """The five AUC operations exist; the six carriers are the shared vocabulary."""
    for name in ("resolve_definition", "discover", "read", "write", "validate"):
        assert callable(getattr(ArtifactAttributeGateway, name))
    assert {c.value for c in AttributeCarrier} == {
        "core",
        "extended",
        "system",
        "link",
        "widget",
        "entity",
    }


def test_to_payload_nests_extended_under_custom_fields() -> None:
    """The one wire shape REST bodies and MCP params share."""
    values = AttributeValues(core={"title": "t"}, extended={"probe": 1})
    assert values.to_payload() == {"title": "t", "custom_fields": {"probe": 1}}


def test_resolve_definition_delegates() -> None:
    definitions = _FakeDefinitions()
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    workspace_id = uuid4()

    result = gateway.resolve_definition(_ctx(), "Requirement", workspace_id)

    assert result["item_type"] == "Requirement"
    assert definitions.resolved == [("Requirement", workspace_id)]


def test_validate_delegates_to_the_single_validation_path() -> None:
    definitions = _FakeDefinitions()
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    workspace_id = uuid4()
    payload = {"title": "t", "custom_fields": {"probe": "v"}}

    gateway.validate(_ctx(), "Requirement", workspace_id, payload, None)

    assert definitions.validated == [("Requirement", workspace_id, payload, None)]


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("item_type", ITEM_TYPES)
def test_discover_covers_every_item_type_in_definition_order(item_type: str) -> None:
    """Discovery works for all 11 item types, in the definition's own order."""
    workspace_id = uuid4()
    definitions = _FakeDefinitions(
        attributes=[
            _attribute("title", order=0),
            _attribute("rationale", kind="extended", type_="textarea", order=1),
        ],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]

    descriptors = gateway.discover(_ctx(), item_type, workspace_id)

    assert [d.name for d in descriptors] == ["title", "rationale"]
    assert definitions.resolved == [(item_type, workspace_id)]


def test_discover_maps_the_definition_to_the_six_way_carrier_vocabulary() -> None:
    """core/extended/widget/workflow are derived; link/entity are not expressible."""
    definitions = _FakeDefinitions(
        attributes=[
            _attribute("title"),
            _attribute("rationale", kind="extended", type_="textarea"),
            _attribute("steps", kind="core", type_="widget", widget_key="steps_editor"),
            _attribute(
                "status",
                kind="core",
                type_="enum",
                editable="workflow",
                options=[{"value": "draft", "label_de": "D", "label_en": "D"}],
            ),
        ],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]

    carriers = [d.carrier for d in gateway.discover(_ctx(), "Requirement", uuid4())]

    assert carriers == [
        AttributeCarrier.CORE,
        AttributeCarrier.EXTENDED,
        AttributeCarrier.WIDGET,
        AttributeCarrier.SYSTEM,
    ]


def test_carrier_for_never_derives_link_or_entity() -> None:
    """The definition cannot express link/entity; those carriers are never emitted."""
    assert carrier_for(_attribute("x")) is AttributeCarrier.CORE
    assert carrier_for(_attribute("x", kind="extended")) is AttributeCarrier.EXTENDED
    # An extended workflow-owned attribute keeps its JSONB carrier.
    assert (
        carrier_for(_attribute("x", kind="extended", editable="workflow"))
        is AttributeCarrier.EXTENDED
    )


def test_discover_projects_the_descriptor_fields() -> None:
    option = {"value": "a", "label_de": "A", "label_en": "A"}
    definitions = _FakeDefinitions(
        attributes=[
            _attribute(
                "level",
                type_="enum",
                section="classification",
                order=7,
                visible=False,
                editable="workflow",
                required=True,
                options=[option],
                validation={"regex": "a"},
            )
        ],
        sections=[_visible_section("classification")],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]

    (descriptor,) = gateway.discover(_ctx(), "Risk", uuid4())

    assert descriptor.name == "level"
    assert descriptor.kind == "core"
    assert descriptor.type == "enum"
    assert descriptor.section == "classification"
    assert descriptor.order == 7
    assert descriptor.visible is False
    assert descriptor.editable == "workflow"
    assert descriptor.required is True
    assert descriptor.options == [option]
    assert descriptor.validation == {"regex": "a"}


def test_discover_exposes_the_generic_display_properties() -> None:
    """Spec section 5 / WS3 #937: the descriptor carries copyable/reveal/mask/
    display_format, so the renderer receives them on both transports."""
    definitions = _FakeDefinitions(
        attributes=[
            _attribute(
                "id",
                visible=False,
                editable="system",
                copyable=True,
                reveal="click",
                mask="short",
                display_format="mono",
            )
        ],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]

    (descriptor,) = gateway.discover(_ctx(), "Requirement", uuid4())

    assert descriptor.copyable is True
    assert descriptor.reveal == "click"
    assert descriptor.mask == "short"
    assert descriptor.display_format == "mono"


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


def test_read_splits_core_columns_from_backing_custom_fields() -> None:
    definitions = _FakeDefinitions(
        attributes=[_attribute("title"), _attribute("rationale", kind="extended")],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    artifact = _FakeArtifact(
        title="hello", backing=_FakeBacking({"rationale": "why"})
    )

    values = gateway.read(_ctx(), "Requirement", artifact)

    assert values.core == {"title": "hello"}
    assert values.extended == {"rationale": "why"}
    assert values.to_payload() == {
        "title": "hello",
        "custom_fields": {"rationale": "why"},
    }


def test_read_never_omits_a_visible_extended_attribute() -> None:
    """The AUC invariant: a visible extended value is always present."""
    definitions = _FakeDefinitions(
        attributes=[_attribute("probe", kind="extended", visible=True)],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    artifact = _FakeArtifact(backing=_FakeBacking({"probe": "present"}))

    values = gateway.read(_ctx(), "Requirement", artifact)

    assert values.extended["probe"] == "present"


def test_read_skips_invisible_attributes_and_hidden_sections() -> None:
    definitions = _FakeDefinitions(
        attributes=[
            _attribute("title"),
            _attribute("secret", visible=False),
            _attribute("buried", section="internal"),
        ],
        sections=[_visible_section(), _visible_section("internal", visible=False)],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    artifact = _FakeArtifact(
        title="t",
        secret="s",
        buried="b",
        backing=_FakeBacking({"hidden_ext": "x"}),
    )

    values = gateway.read(_ctx(), "Requirement", artifact)

    assert values.core == {"title": "t"}


def test_read_decodes_direct_custom_fields_and_widgets_are_not_columns() -> None:
    definitions = _FakeDefinitions(
        attributes=[
            _attribute("steps", type_="widget", widget_key="steps_editor"),
            _attribute("probe", kind="extended"),
        ],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    artifact = _FakeDirectArtifact(custom_fields='{"probe": "raw-decoded"}')

    values = gateway.read(_ctx(), "Requirement", artifact)

    assert values.core == {}
    assert values.extended == {"probe": "raw-decoded"}


def test_read_requires_a_workspace_id() -> None:
    class _NoWorkspace:
        def __init__(self) -> None:
            self.id = uuid4()
            self.custom_fields: dict[str, Any] = {}

    gateway = ArtifactAttributeGateway(definitions=_FakeDefinitions())  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        gateway.read(_ctx(), "Requirement", _NoWorkspace())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Write / merge
# ---------------------------------------------------------------------------


def test_write_merges_extended_values_and_round_trips() -> None:
    definitions = _FakeDefinitions(
        attributes=[_attribute("title"), _attribute("rationale", kind="extended")],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    backing = _FakeBacking({"rationale": "old", "unrelated": "kept"})
    artifact = _FakeArtifact(title="t0", backing=backing)

    result = gateway.write(
        _ctx(),
        "Requirement",
        artifact,
        AttributeValues(core={"title": "t1"}, extended={"rationale": "new"}),
    )

    assert artifact.title == "t1"
    # merge=True: unspecified stored keys survive.
    assert backing.custom_fields == {"rationale": "new", "unrelated": "kept"}
    assert artifact.saves == 1
    assert backing.saves == 1
    # Round-Trip: the returned values are exactly the read-back.
    assert result == gateway.read(_ctx(), "Requirement", artifact)
    assert result.core == {"title": "t1"}
    assert result.extended == {"rationale": "new"}


def test_write_replace_semantics_drops_unspecified_extended_keys() -> None:
    definitions = _FakeDefinitions(
        attributes=[_attribute("probe", kind="extended")],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    backing = _FakeBacking({"probe": "old", "unrelated": "dropped"})
    artifact = _FakeArtifact(backing=backing)

    gateway.write(
        _ctx(),
        "Requirement",
        artifact,
        AttributeValues(extended={"probe": "new"}),
        merge=False,
    )

    assert backing.custom_fields == {"probe": "new"}


def test_write_validates_first_and_does_not_persist_on_violation() -> None:
    error = FieldValidationError({"probe": ["is not a defined attribute"]})
    definitions = _FakeDefinitions(
        attributes=[_attribute("title"), _attribute("rationale", kind="extended")],
        sections=[_visible_section()],
        validate_error=error,
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    backing = _FakeBacking({"rationale": "untouched"})
    artifact = _FakeArtifact(title="original", backing=backing)

    with pytest.raises(FieldValidationError):
        gateway.write(
            _ctx(),
            "Requirement",
            artifact,
            AttributeValues(core={"title": "changed"}, extended={"rationale": "changed"}),
        )

    assert definitions.validated, "write must run the shared validation path first"
    assert artifact.title == "original"
    assert backing.custom_fields == {"rationale": "untouched"}
    assert artifact.saves == 0
    assert backing.saves == 0


# ---------------------------------------------------------------------------
# Artifact-level system fields + actor adapter (WS2 #936, spec sections 3/4)
# ---------------------------------------------------------------------------


class _FakeActor:
    """Structural ``Actor`` double (kind + identity + display label)."""

    def __init__(self, kind: str = "user", **values: Any) -> None:
        self.id = uuid4()
        self.kind = kind
        self.display_name = values.get("display_name", "Someone")
        self.user_id = values.get("user_id")


def test_actor_to_value_shapes_the_wire_form() -> None:
    assert ArtifactAttributeGateway.actor_to_value(None) is None
    internal_actor = _FakeActor("user")
    assert ArtifactAttributeGateway.actor_to_value(internal_actor) == {
        "kind": "user",
        "id": str(internal_actor.id),
    }
    external = _FakeActor("external", display_name="Frau Mueller (TUEV)")
    assert ArtifactAttributeGateway.actor_to_value(external) == {
        "kind": "external",
        "name": "Frau Mueller (TUEV)",
    }


def test_read_routes_artifact_level_fields_through_the_backing_artifact() -> None:
    """``owner``/``reporter``/``priority`` live on Artifact, not the entity."""
    actor = _FakeActor("user")
    definitions = _FakeDefinitions(
        attributes=[
            _attribute("title"),
            _attribute("owner", type_="actor"),
            _attribute("priority", type_="enum",
                       options=[{"value": "high", "label_de": "H", "label_en": "H"}]),
        ],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    backing = _FakeBacking()
    backing.owner = actor
    backing.priority = "high"
    artifact = _FakeArtifact(title="t", backing=backing)

    values = gateway.read(_ctx(), "Requirement", artifact)

    assert values.core["owner"] == {"kind": "user", "id": str(actor.id)}
    assert values.core["priority"] == "high"


def test_write_sets_priority_on_the_backing_artifact() -> None:
    """A plain Artifact-level core field is written to the Artifact, not the entity."""
    definitions = _FakeDefinitions(
        attributes=[
            _attribute("priority", type_="enum",
                       options=[{"value": "high", "label_de": "H", "label_en": "H"}]),
        ],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    backing = _FakeBacking()
    artifact = _FakeArtifact(backing=backing)

    result = gateway.write(
        _ctx(), "Requirement", artifact, AttributeValues(core={"priority": "high"})
    )

    assert backing.priority == "high"
    assert getattr(artifact, "priority", None) is None
    assert result.core == {"priority": "high"}


def test_write_rejects_a_multiple_actor_on_a_single_fk_system_field() -> None:
    definitions = _FakeDefinitions(
        attributes=[_attribute("owner", type_="actor", multiple=True)],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    artifact = _FakeArtifact(backing=_FakeBacking())

    from persistence.errors import ValidationError

    with pytest.raises(ValidationError):
        gateway.write(
            _ctx(),
            "Requirement",
            artifact,
            AttributeValues(core={"owner": {"multiple": True, "items": []}}),
        )


def test_write_ignores_system_and_workflow_owned_core_fields() -> None:
    """Major 3 (#936 review): ``write`` must not set ``id``/``status``.

    ``validate`` already excludes ``editable="workflow"``/``"system"`` from the
    payload; the write loop used to ignore that and ``setattr`` every core name,
    so the W seam (and anything built on it) could overwrite a server-owned
    column. The documented behaviour is "ignore silently": no exception, no
    ``save`` for the skipped fields.
    """
    definitions = _FakeDefinitions(
        attributes=[
            _attribute("title"),
            _attribute("id", editable="system", visible=False),
            _attribute("status", editable="workflow"),
            _attribute("frozen", editable=False),
        ],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]
    artifact = _FakeArtifact(title="original", backing=_FakeBacking())
    original_id = artifact.id

    result = gateway.write(
        _ctx(),
        "Requirement",
        artifact,
        AttributeValues(
            core={
                "id": "hacked-id",
                "status": "closed",
                "frozen": "hacked",
                "title": "changed",
            }
        ),
    )

    assert artifact.id == original_id
    assert getattr(artifact, "status", None) is None
    assert getattr(artifact, "frozen", None) is None
    assert artifact.title == "changed"
    assert result.core == {"title": "changed"}


# ---------------------------------------------------------------------------
# Layout span discovery (WS4 #938, spec section 7)
# ---------------------------------------------------------------------------


def test_discover_defaults_every_span_to_full_without_a_flow() -> None:
    """A legacy definition (no ``attribute_flow``) still yields a usable layout
    hint: every attribute is ``full``."""
    definitions = _FakeDefinitions(
        attributes=[_attribute("title"), _attribute("note", kind="extended")],
        sections=[_visible_section()],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]

    spans = [d.span for d in gateway.discover(_ctx(), "Requirement", uuid4())]

    assert spans == ["full", "full"]


def test_discover_resolves_the_span_from_the_sections_attribute_flow() -> None:
    section = {
        "name": "general",
        "order": 0,
        "visible": True,
        "layout": "full",
        "attribute_flow": [
            {"kind": "attribute", "name": "title", "span": "half"},
            {"kind": "spacer", "size": "sm"},
            {"kind": "attribute", "name": "note", "span": "quarter"},
        ],
    }
    definitions = _FakeDefinitions(
        attributes=[_attribute("title"), _attribute("note", kind="extended")],
        sections=[section],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]

    by_name = {d.name: d.span for d in gateway.discover(_ctx(), "Requirement", uuid4())}

    assert by_name == {"title": "half", "note": "quarter"}


def test_discover_span_falls_back_to_full_for_an_unpositioned_attribute() -> None:
    section = {
        "name": "general",
        "order": 0,
        "visible": True,
        "layout": "full",
        "attribute_flow": [{"kind": "attribute", "name": "title", "span": "half"}],
    }
    definitions = _FakeDefinitions(
        attributes=[_attribute("title"), _attribute("extra")],
        sections=[section],
    )
    gateway = ArtifactAttributeGateway(definitions=definitions)  # type: ignore[arg-type]

    by_name = {d.name: d.span for d in gateway.discover(_ctx(), "Requirement", uuid4())}

    assert by_name == {"title": "half", "extra": "full"}

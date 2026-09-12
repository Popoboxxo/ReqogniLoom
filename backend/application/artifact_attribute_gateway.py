"""ArtifactAttributeGateway — the single shared seam for artifact attributes.

Epic #934 (Attribut-System v3), WS0 #941 (Fundament). This module fixes the
*interface*; wiring REST views and MCP handlers onto it is WS1 (spec section 13)
and deliberately does not happen here.

Why one gateway
---------------
Spec section 9 catalogues a per-type REST/MCP divergence: ``custom_fields`` is
silently dropped by some serializers/views, some MCP handlers declare
``additionalProperties: false``, some services never learned ``custom_fields``
at all, and definition discovery exists for ``Requirement`` only. The chosen
remedy (ADR-004, option A) is **one** value pipeline that both transports call:
discovery, read, write and validation live here, so a divergence between REST
and MCP is structurally impossible instead of merely discouraged.

Attribute Usability Contract (AUC)
----------------------------------
Per ADR-004 and spec sections 1 and 11, for every
``(workspace, item_type in 11, preset in 3)`` and every *visible* attribute of
the resolved definition the gateway must guarantee **W** (writeable),
**R** (readable), **V** (identically validated) and **Round-Trip**
(write result == read result) — on **both** transports, always, with no silent
drop. Definition discovery must be available for every item type. The promise
is enforced by the parametrised, CI-blocking contract matrix
(``attribute_definitions/tests/test_transport_contract_matrix.py``, spec
section 11), not by convention.

Status of this file
-------------------
IMPLEMENTED (WS0 interface + WS1 #935 carrier-aware behaviour).
``resolve_definition`` and ``validate`` are thin, behaviour-preserving
delegations to the already-central ``AttributeDefinitionService`` (layer 2,
ADR-01). ``discover``, ``read`` and ``write`` are now implemented here and are
the single carrier-aware W/R/discovery path.

Which paths call the gateway (WS1 #935)
---------------------------------------
Wired through the gateway:

* ``application.requirement_bundle_service.describe_attribute_schema`` — REST
  ``GET /api/v1/attribute-schema/`` and MCP
  ``requirement_bundle.attribute_schema`` discovery now come from
  :meth:`ArtifactAttributeGateway.discover`, so every item type is described by
  the same projection (byte-compatible rows).
* ``mcp_server.tools.base.validate_artifact_write`` — every MCP artifact-write
  tool group (including the new ``icd.*`` group) validates through
  :meth:`ArtifactAttributeGateway.validate`.
* ``rest_api.mixins.workflow_transitions.WorkflowTransitionsMixin.\
_validate_attribute_definition`` — every workflow-backed REST ViewSet
  (including ``IcdViewSet``) validates through the gateway too.

Intentionally still direct (documented WS1 decision, no big-bang refactor):

* The four bespoke MCP groups (``requirement``/``needs``/``test``/
  ``architecture``), the generic MCP group and the per-type REST ViewSets keep
  their own read/serialization code; they reach the gateway only through the
  two validation seams above.
* MCP/REST ``Icd`` **reads** keep ``artifact_custom_fields`` / the
  ``custom_fields`` map on the entity: routing them through
  :meth:`read` would add a definition resolve whose ``AttributeDefinitionNotFound``
  (bootstrap not run) would break a read that works today. Icd **writes** keep
  their service-managed persistence (revision creation, audit) and only the
  validation flows through the gateway.
* ``Icd``/``Goal``/``ChangeRequest``/``GlossaryTerm`` write persistence stays
  with the domain services; :meth:`write` is the WS1 contract for the paths that
  adopt it, not a retrofit of every existing persistence path.

References:
    * ADR-004 — ``docs/se/ADR/ADR-004_traeger_modell_und_auc.md``
    * Spec sections 9 (transport gaps) and 11 (contract matrix) —
      ``docs/se/attribut/attribut-umsetzungsspezifikation.md``
    * ADR-01 (Single Entry Point) — the application layer is the only domain
      facade; REST views and MCP handlers must not touch
      ``attribute_definitions.models`` directly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from auth_tenancy.context import AuthContext

if TYPE_CHECKING:
    from application.attribute_definition_service import AttributeDefinitionService


class AttributeCarrier(str, Enum):
    """Storage carrier of an attribute (spec section 2, ADR-004).

    The definition layer only declares ``core`` / ``extended``; the remaining
    four carriers are resolved by WS1 when it maps a definition entry onto the
    six-way model. Kept here as the shared vocabulary both transports report.
    """

    CORE = "core"
    EXTENDED = "extended"
    SYSTEM = "system"
    LINK = "link"
    WIDGET = "widget"
    ENTITY = "entity"


def carrier_for(attribute: dict[str, Any]) -> AttributeCarrier:
    """Resolve the six-way :class:`AttributeCarrier` of a definition entry.

    The definition layer (``attribute_definitions.schema``) only declares
    ``core``/``extended`` in ``kind``, but it can express two more carriers:

    * ``type == "widget"`` -> :attr:`AttributeCarrier.WIDGET` (a structured
      value rendered by a widget component; ``fields``/``widget_key`` name its
      parts).
    * ``kind == "core"`` with ``editable == "workflow"`` ->
      :attr:`AttributeCarrier.SYSTEM` (the bootstrapped, workflow-owned
      ``status``; core storage, read-only through the workflow engine).

    ``link`` (:class:`traceability` ``TraceLink`` rows) and ``entity``
    (independent tables such as ``Measure``/``Actor``) leave no trace in an
    attribute definition entry, so they are never derived here. They are part
    of the shared vocabulary (ADR-004) and belong to a future catalog; the
    gateway's W/R path does not need them today.

    Precedence is widget -> extended -> system -> core: a widget is the most
    specific descriptor, and an extended attribute keeps its JSONB carrier even
    when it happens to be workflow-owned.
    """
    if attribute.get("type") == "widget":
        return AttributeCarrier.WIDGET
    if attribute.get("kind") == "extended":
        return AttributeCarrier.EXTENDED
    if attribute.get("editable") == "workflow":
        return AttributeCarrier.SYSTEM
    return AttributeCarrier.CORE


class AttributeArtifact(Protocol):
    """Minimal artifact surface the gateway operates on (structural typing).

    ``Artifact`` (``persistence.models``) satisfies this protocol. Core
    attribute values are read/written through model fields via ``getattr`` /
    ``setattr``; extended values live in the JSONB ``custom_fields`` map.
    """

    id: UUID
    custom_fields: dict[str, Any]


@dataclass(frozen=True)
class AttributeDescriptor:
    """One discoverable attribute of a resolved definition (discovery result).

    Mirrors the normalized entry contract of
    ``attribute_definitions.schema`` plus the resolved carrier, so discovery is
    identical for every item type and both transports (AUC "Discovery").
    """

    name: str
    kind: str
    type: str
    carrier: AttributeCarrier
    section: str
    visible: bool
    editable: bool | str
    required: bool
    label: dict[str, str]
    options: list[dict[str, str]]
    validation: dict[str, Any]
    order: int


@dataclass(frozen=True)
class AttributeValues:
    """A carrier-split view of one artifact's attribute values.

    ``core`` holds flat ``name -> value`` pairs (columns on the artifact or its
    type-specific model); ``extended`` holds ``name -> value`` pairs that are
    persisted in ``Artifact.custom_fields`` (spec section 2). This split is the
    common internal shape every transport converts to and from, which is what
    makes ``custom_fields`` impossible to silently drop.
    """

    core: dict[str, Any] = field(default_factory=dict)
    extended: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """Return the transport-shaped payload: flat core + ``custom_fields``.

        The single wire shape REST bodies and MCP params share; extended values
        are nested under ``"custom_fields"`` exactly as
        ``attribute_definitions.field_validation`` expects them.
        """
        return {**self.core, "custom_fields": dict(self.extended)}


class ArtifactAttributeGateway:
    """Shared W/R/V/discovery pipeline for artifact attributes (ADR-004, §9/§11).

    Both transports call this class and only this class for attribute work.
    The gateway resolves the effective definition, validates values once
    (so REST and MCP can never disagree — **V**), and is the one place that
    reads (**R**) and writes/merges (**W**) core columns and
    ``Artifact.custom_fields``, guaranteeing **Round-Trip** by returning the
    persisted values for a read-back comparison.

    ``resolve_definition`` and ``validate`` delegate to
    :class:`AttributeDefinitionService`; ``discover``, ``read`` and ``write``
    are the WS1 carrier-aware implementation (Epic #934 / WS1 #935).

    Deliberately does not inherit ``ServiceBase`` and imports the definition
    facade lazily: this module must stay importable without a configured Django
    app registry (its interface is what transports and the contract matrix
    reference), and ``application.base`` transitively loads ORM models.

    Args:
        definitions: Injectable definition facade, for tests; defaults to
            ``AttributeDefinitionService()``.
    """

    def __init__(self, definitions: AttributeDefinitionService | None = None) -> None:
        if definitions is None:
            from application.attribute_definition_service import (
                AttributeDefinitionService,
            )

            definitions = AttributeDefinitionService()
        self._definitions = definitions

    # ---- Definition resolution (shared dependency of every operation) ------

    def resolve_definition(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> dict[str, Any]:
        """Return the effective definition for ``(workspace, item_type, preset)``.

        *preset* is the workspace's active rigor tier, resolved by
        ``AttributeDefinitionService.resolve`` exactly as the contract matrix
        and every existing consumer resolve it; callers never pass it
        separately (ADR-004: the tuple is keyed by workspace, not by a
        caller-chosen preset).

        Returns:
            The resolved definition payload with ``attributes``, ``sections``,
            ``item_type``, ``preset`` and ``version`` keys.

        Raises:
            AttributeDefinitionNotFound: no global default is bootstrapped for
                the workspace's preset.
            AttributeSchemaError: a stored row is malformed.
        """
        return self._definitions.resolve(ctx, item_type, workspace_id)

    # ---- Artifact / carrier helpers ----------------------------------------

    @staticmethod
    def _workspace_id_of(artifact: AttributeArtifact) -> UUID:
        """Return the workspace id carried by *artifact* or its backing Artifact.

        ``read``/``write`` receive the type-specific entity (``Requirement``,
        ``Icd``, ...): its own ``workspace_id`` column is authoritative for the
        definition key. A generic ``Artifact`` carries it too, so the same
        resolution works for both shapes.

        Raises:
            ValueError: the object carries no workspace id (not artifact-shaped).
        """
        workspace_id = getattr(artifact, "workspace_id", None)
        if workspace_id is None:
            backing = getattr(artifact, "artifact", None)
            workspace_id = getattr(backing, "workspace_id", None)
        if workspace_id is None:
            raise ValueError(
                "ArtifactAttributeGateway requires an artifact carrying "
                "'workspace_id' (or a backing '.artifact' that does)"
            )
        return workspace_id

    @staticmethod
    def _custom_fields_owner(artifact: AttributeArtifact) -> Any:
        """Return the object whose ``custom_fields`` map this artifact uses.

        Extended values live on ``Artifact.custom_fields``. Type-specific
        entities reach it through their OneToOne ``artifact`` relation, while a
        generic ``Artifact`` (or a unit-test double) owns the attribute
        directly. Mirrors ``mcp_server.tools.base.artifact_custom_fields`` and
        ``rest_api.views._artifact_custom_fields`` without importing a Layer 3
        module from Layer 2 (ADR-01) — the same fallback rule, resolved locally.
        """
        direct = getattr(artifact, "custom_fields", None)
        if isinstance(direct, (dict, str)):
            return artifact
        backing = getattr(artifact, "artifact", None)
        if backing is not None:
            return backing
        return artifact

    @classmethod
    def _custom_fields_of(cls, artifact: AttributeArtifact) -> dict[str, Any]:
        """Return a normalized ``custom_fields`` dict for *artifact*.

        Uses :func:`persistence.custom_fields.coerce_custom_fields` (Layer 0) so
        a raw DB string is decoded and a missing/NULL/malformed value becomes
        ``{}`` instead of leaking into the payload. Imported lazily: the gateway
        must stay importable without a configured Django app registry.
        """
        from persistence.custom_fields import coerce_custom_fields

        owner = cls._custom_fields_owner(artifact)
        return coerce_custom_fields(getattr(owner, "custom_fields", None))

    @staticmethod
    def _persist(target: Any) -> None:
        """Save *target* when it is persistable; no-op for structural doubles.

        The gateway operates on the ``AttributeArtifact`` protocol, which does
        not promise a ``save`` method — unit tests inject plain doubles. Real
        Django models always have one.
        """
        save = getattr(target, "save", None)
        if callable(save):
            save()

    # ---- Discovery (the ``attribute-schema`` capability) -------------------

    def discover(
        self, ctx: AuthContext, item_type: str, workspace_id: UUID
    ) -> list[AttributeDescriptor]:
        """List the discoverable attributes of ``item_type`` (AUC: Discovery).

        Must work for **every** item type in ``ITEM_TYPES`` — today the REST
        ``attribute-schema`` endpoint only describes ``Requirement`` (spec
        section 9), which is exactly the gap this capability closes. Transports
        project the returned descriptors onto their own wire shape.

        Returns:
            One :class:`AttributeDescriptor` per attribute of the resolved
            definition, in definition order (section, order, name).

        Raises:
            AttributeDefinitionNotFound: propagated from
                :meth:`resolve_definition`.
        """
        definition = self.resolve_definition(ctx, item_type, workspace_id)
        return [
            AttributeDescriptor(
                name=attribute["name"],
                kind=attribute["kind"],
                type=attribute["type"],
                carrier=carrier_for(attribute),
                section=attribute["section"],
                visible=attribute["visible"],
                editable=attribute["editable"],
                required=attribute["required"],
                label=attribute["label"],
                options=attribute["options"],
                validation=attribute["validation"],
                order=attribute["order"],
            )
            for attribute in definition["attributes"]
        ]

    # ---- Read (R) ----------------------------------------------------------

    def read(
        self, ctx: AuthContext, item_type: str, artifact: AttributeArtifact
    ) -> AttributeValues:
        """Read every visible attribute value of *artifact* (AUC: R).

        Reads core columns and ``Artifact.custom_fields`` through the resolved
        definition, so a visible extended attribute can never be omitted on
        either transport (the current MCP ``generic._to_dict`` bug, spec
        section 9).

        Visibility follows the renderer's AND-condition (spec section 4.4): an
        attribute is read when its own ``visible`` flag is true *and* its
        section is not hidden — the same rule ``field_validation.validate_values``
        and the contract matrix apply.

        Returns:
            The artifact's values split by carrier.

        Raises:
            AttributeDefinitionNotFound: propagated from
                :meth:`resolve_definition`.
            ValueError: *artifact* carries no workspace id.
        """
        definition = self.resolve_definition(
            ctx, item_type, self._workspace_id_of(artifact)
        )
        custom_fields = self._custom_fields_of(artifact)
        hidden_sections = {
            section["name"]
            for section in (definition.get("sections") or [])
            if not section.get("visible", True)
        }

        core: dict[str, Any] = {}
        extended: dict[str, Any] = {}
        for attribute in definition["attributes"]:
            name = attribute["name"]
            if not attribute["visible"] or attribute["section"] in hidden_sections:
                continue
            if attribute["kind"] == "extended":
                if name in custom_fields:
                    extended[name] = custom_fields[name]
                continue
            # A widget bundles other attributes and carries no value of its own
            # (field_validation.py); it is never a column lookup.
            if attribute["type"] == "widget":
                continue
            try:
                core[name] = getattr(artifact, name)
            except AttributeError:
                # Definition names a column this model shape does not expose
                # (e.g. a synthetic or stale entry); omit rather than 500.
                continue
        return AttributeValues(core=core, extended=extended)

    # ---- Write / merge (W) -------------------------------------------------

    def write(
        self,
        ctx: AuthContext,
        item_type: str,
        artifact: AttributeArtifact,
        values: AttributeValues,
        *,
        merge: bool = True,
    ) -> AttributeValues:
        """Write or merge attribute values on *artifact* (AUC: W + Round-Trip).

        Validates through :meth:`validate` first (same V path as REST/MCP),
        then persists core columns and ``Artifact.custom_fields``. With
        ``merge=True`` the supplied extended keys are merged into the stored
        map and unspecified keys survive; with ``merge=False`` the stored
        ``custom_fields`` map is replaced by ``values.extended``.

        ``existing`` is the established update presence marker
        (``{"__exists__": True}``): the definition engine only distinguishes
        create from update by *whether* it is ``None``, not by its content
        (``field_validation.validate_values``).

        Returns:
            The persisted values read back through :meth:`read`, so a caller
            (and the contract matrix) can assert Round-Trip.

        Raises:
            FieldValidationError: the values violate the resolved definition.
            AttributeDefinitionNotFound: propagated from
                :meth:`resolve_definition`.
            ValueError: *artifact* carries no workspace id.
        """
        workspace_id = self._workspace_id_of(artifact)
        self.validate(
            ctx,
            item_type,
            workspace_id,
            values.to_payload(),
            {"__exists__": True},
        )
        definition = self.resolve_definition(ctx, item_type, workspace_id)
        by_name = {attribute["name"]: attribute for attribute in definition["attributes"]}

        targets: list[Any] = []

        def _remember(target: Any) -> None:
            if not any(target is seen for seen in targets):
                targets.append(target)

        for name, value in values.core.items():
            attribute = by_name.get(name)
            if attribute is None or attribute["kind"] != "core":
                continue
            if attribute["type"] == "widget":
                continue
            setattr(artifact, name, value)
            _remember(artifact)

        if values.extended or not merge:
            owner = self._custom_fields_owner(artifact)
            current = self._custom_fields_of(artifact)
            merged = {**current, **values.extended} if merge else dict(values.extended)
            setattr(owner, "custom_fields", merged)
            _remember(owner)

        for target in targets:
            self._persist(target)

        return self.read(ctx, item_type, artifact)

    # ---- Validate (V) ------------------------------------------------------

    def validate(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        changed_fields: dict[str, Any],
        existing: dict[str, Any] | None,
    ) -> None:
        """Validate a create/update payload against the resolved definition (V).

        Delegates to ``AttributeDefinitionService.validate_artifact_fields`` —
        the single validation path REST, MCP and the CSV/bulk importer already
        share — so both transports reject and accept identically by
        construction.

        Args:
            ctx: Request identity.
            item_type: One of ``ITEM_TYPES``.
            workspace_id: Workspace whose tier selects the definition.
            changed_fields: Flat payload; extended values nested under
                ``"custom_fields"`` (``field_validation.EXTENDED_PAYLOAD_KEY``).
            existing: Current values, or ``None`` for a create.

        Raises:
            FieldValidationError: ``.errors`` maps attribute name -> messages.
        """
        self._definitions.validate_artifact_fields(
            ctx, item_type, workspace_id, changed_fields, existing
        )


__all__ = [
    "ArtifactAttributeGateway",
    "AttributeArtifact",
    "AttributeCarrier",
    "AttributeDescriptor",
    "AttributeValues",
    "carrier_for",
]

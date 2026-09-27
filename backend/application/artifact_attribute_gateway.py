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

ADR-006 — the third carrier pattern
-----------------------------------
``Artifact.custom_fields`` is deliberately **flat** (REQ-L2-AS-037 rejects nested
objects *and* arrays), so a value that is a person reference or a list of option
values cannot live there. WS2/#936 put the single-valued person fields on the
``Artifact`` row as ``Actor`` FKs; ADR-006 adds the two remaining shapes without
a new concept:

* **multi-value person reference** (``Adr.deciders``, ``Issue.assignee``) — a
  ``ManyToManyField`` to the same ``Actor`` table, declared in the definition as
  ``type="actor"`` + ``multiple=True``. A person selection is a **set**, so the
  read resolves a deterministic data order rather than the payload order
  (:meth:`ArtifactAttributeGateway.selected_actors`).
* **multi-value classification** (``StakeholderNeed.stakeholder``) — a plain
  JSONB list column on ``Artifact`` whose allowed values come from the
  definition's ``options`` (``type="multi-enum"``).

Both are reached through this module and through one registry
(``attribute_definitions.schema.ENTITY_LEVEL_CARRIER_FIELDS``), so REST and MCP
carry them by construction and the *next* such field is a config change: one
model column, one catalogue entry, one registry entry.

References:
    * ADR-004 — ``docs/se/ADR/ADR-004_traeger_modell_und_auc.md``
    * Spec sections 9 (transport gaps) and 11 (contract matrix) —
      ``docs/se/attribut/attribut-umsetzungsspezifikation.md``
    * ADR-01 (Single Entry Point) — the application layer is the only domain
      facade; REST views and MCP handlers must not touch
      ``attribute_definitions.models`` directly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Iterable, Protocol
from uuid import UUID

from auth_tenancy.context import AuthContext
from attribute_definitions.schema import (
    ITEM_TYPES,
    all_entity_carrier_fields,
    entity_carrier_fields,
    resolve_attribute_span,
)

if TYPE_CHECKING:
    from application.attribute_definition_service import AttributeDefinitionService

logger = logging.getLogger(__name__)


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


#: The Artifact-level system field names, in wire order — what a transport must
#: forward in addition to the carrier-backed names of
#: :data:`attribute_definitions.schema.ENTITY_LEVEL_CARRIER_FIELDS`. Public
#: because both transports build their "names this payload carries" set from it
#: (``rest_api.views._SYSTEM_FIELD_NAMES``,
#: ``mcp_server.tools.system_fields.SYSTEM_FIELD_NAMES``), and a second,
 #: hand-typed copy of this list is exactly how the two would drift.
ARTIFACT_SYSTEM_FIELD_NAMES: tuple[str, ...] = (
    "owner",
    "reporter",
    "priority",
    "stakeholder",
)

#: Core attributes whose column lives on the backing ``Artifact`` rather than on
#: the type-specific entity (spec section 3, ADR-004). ``owner``/``reporter`` are
#: ``Actor`` foreign keys; ``priority`` is a plain enum column; ``stakeholder``
#: (ADR-006) is a plain list-of-option-values column. The gateway read/write
#: adapter resolves them through ``_custom_fields_owner`` (the Artifact) and
#: converts actor FKs to/from the wire value form of spec section 4.
#:
#: ``stakeholder`` is here rather than on ``StakeholderNeed`` for a transport
#: reason, not a modelling one: this set is what makes the value resolve
#: identically for an ORM entity **and** for a service DTO (which exposes only
#: its backing ``.artifact`` row), and it is why REST and MCP cannot diverge on
#: it. See ``persistence.models.Artifact.stakeholder``.
_ARTIFACT_LEVEL_CORE_FIELDS: frozenset[str] = frozenset(ARTIFACT_SYSTEM_FIELD_NAMES)


def transport_field_names() -> tuple[str, ...]:
    """Return every attribute name a transport must forward for *any* item type.

    The union of the Artifact-level system fields and the carrier-backed names,
    de-duplicated and in wire order. Both transports build their "names this
    payload carries" set from this one function
    (``rest_api.views._SYSTEM_FIELD_NAMES``,
    ``mcp_server.tools.system_fields.SYSTEM_FIELD_NAMES``), because that set has
    two jobs that must be the *same* set: the gateway write picks those keys out
    of the payload, and the create/update handlers pop exactly those names before
    splatting the rest into a type-specific service. A name in one list and not
    the other is a ``TypeError`` (500) on create.

    Flat rather than per item type because both call sites filter a payload by
    name *presence*; a name only ever means one thing per entity.
    """
    seen: dict[str, None] = {}
    for name in ARTIFACT_SYSTEM_FIELD_NAMES + all_entity_carrier_fields():
        seen.setdefault(name, None)
    return tuple(seen)

#: Of the carrier-backed attribute names (ADR-006), the ones stored as a plain
#: column on the backing ``Artifact`` rather than as a multi-value Actor relation
#: on the entity. Read straight off the Artifact row, so they need no adapter —
#: which is what makes them resolve identically for an ORM entity and for a
#: service DTO that only exposes its ``.artifact``.
_ARTIFACT_COLUMN_CARRIER_FIELDS: frozenset[str] = frozenset({"stakeholder"})

#: The wire value form of a multi-value person field (spec section 4):
#: ``{"multiple": true, "items": [<entry>, ...]}``. The single-valued form is
#: the bare entry; ``multiple`` therefore has to be *stated* in the envelope,
#: which is what lets one attribute name mean either shape without a second
#: attribute name.
_MULTI_ACTOR_KEY = "multiple"
_MULTI_ACTOR_ITEMS_KEY = "items"


def entity_item_type(entity: Any) -> str:
    """Return the ``ITEM_TYPES`` name of *entity*, or ``""`` if it has none.

    Best-effort by design, because the read projection it serves
    (:func:`artifact_system_fields`) is called with whatever the transport
    happens to hold — an ORM model, a service DTO, a test double — and none of
    those carries the item type as data. Class name is the only signal
    available, and a DTO is named after its model (``StakeholderNeedDTO``), so
    the ``DTO`` suffix is stripped. A name outside ``ITEM_TYPES`` (``Artifact``
    itself, a double) resolves to ``""``, which every caller treats as "no
    carrier fields" — never as an error.
    """
    name = type(entity).__name__
    if name.endswith("DTO"):
        name = name[: -len("DTO")]
    return name if name in ITEM_TYPES else ""


def _artifact_of(entity: Any) -> Any:
    """Return the backing ``Artifact`` row of *entity* (or *entity* itself)."""
    artifact = getattr(entity, "artifact", None)
    return entity if artifact is None else artifact


def actors_to_value(actors: Iterable[Any]) -> dict[str, Any]:
    """Return a multi-value actor selection in wire form (spec section 4).

    The empty selection is ``{"multiple": true, "items": []}``, not ``None``:
    an empty team is a *value* of a multi-value field (it clears the field),
    whereas ``None`` is what a single-valued actor field uses for "unset". The
    distinction is the attribute's ``multiple`` property, and the envelope is
    what carries it to the client.
    """
    return {
        _MULTI_ACTOR_KEY: True,
        _MULTI_ACTOR_ITEMS_KEY: [
            ArtifactAttributeGateway.actor_to_value(actor) for actor in actors
        ],
    }


def artifact_system_fields(entity: Any) -> dict[str, Any]:
    """Return the Artifact-level system fields in wire form (spec sections 3/4).

    Shared by REST DTO builders and MCP read projections so ``owner``,
    ``reporter`` and ``priority`` are read identically on both transports (AUC).
    ``entity`` may be a type-specific model (reaches the Artifact through its
    OneToOne ``artifact``) or a generic ``Artifact``.

    ``owner``/``reporter`` are converted to the same Actor value form the write
    adapter accepts (``ArtifactAttributeGateway.actor_to_value``); ``priority``
    and ``stakeholder`` are plain columns and pass through; ``stakeholder`` is
    only emitted for an item type that actually declares it. Unset FKs become
    ``None``, an unset selection an empty list.

    ADR-006 also adds the **carrier-backed** fields of the entity's own item
    type — ``Adr.deciders`` / ``Issue.assignee`` (multi-value Actor references)
    — to the same projection, in the same wire form the write adapter accepts.
    That is deliberate: one shared read function is what makes "identical over
    REST and MCP" a structural property instead of a convention the two
    transports have to keep re-establishing per field (spec section 11).
    """
    artifact = _artifact_of(entity)
    values: dict[str, Any] = {
        "owner": ArtifactAttributeGateway.actor_to_value(
            getattr(artifact, "owner", None)
        ),
        "reporter": ArtifactAttributeGateway.actor_to_value(
            getattr(artifact, "reporter", None)
        ),
        "priority": getattr(artifact, "priority", "") or "",
    }
    item_type = entity_item_type(entity)
    for name in entity_carrier_fields(item_type):
        if name in _ARTIFACT_COLUMN_CARRIER_FIELDS:
            stored = getattr(artifact, name, None)
            values[name] = list(stored) if isinstance(stored, (list, tuple)) else []
        else:
            values[name] = ArtifactAttributeGateway.actors_to_value(
                ArtifactAttributeGateway.selected_actors(entity, name)
            )
    return values


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
    #: Layout span (WS4 #938, spec section 7): the token positioning this
    #: attribute inside its section's 12-column grid — ``full``/``half``/
    #: ``quarter``. Resolved from the section's ``attribute_flow``; ``full``
    #: when the definition carries no flow (the pre-WS4 stacking), so the
    #: descriptor is a usable layout hint for every stored definition.
    span: str
    #: Generic display/interaction properties (spec section 5, WS3 #937). Part
    #: of the discovery contract so a renderer can build the reveal/copy/mask
    #: affordance from the same projection on both transports.
    copyable: bool
    reveal: str
    mask: str
    display_format: str


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

        The backing ``.artifact`` relation is preferred over a direct
        ``custom_fields`` attribute: a service DTO (``GlossaryTermDTO``, WS2
        #936) carries its own ``custom_fields`` *dict* for the wire but has no
        persistence method, so returning the DTO would make every system-field
        write a silent no-op. Preferring the relation means such a DTO only has
        to expose its backing ``Artifact`` (via its ``artifact`` property) and
        the write lands on the real row. A real ``Artifact`` has no ``.artifact``
        attribute, so the generic case still resolves to itself.
        """
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

    # ---- Actor value adapter (spec section 4) ------------------------------

    @staticmethod
    def actor_to_value(actor: Any) -> dict[str, Any] | None:
        """Convert an ``Actor`` FK into the wire value form of spec section 4.

        ``None`` stays ``None`` (unset). An internal actor reads as
        ``{"kind": "user", "id": "<actor-uuid>"}``; an external dummy reads as
        ``{"kind": "external", "name": "<display_name>"}`` — exactly the shapes
        the write adapter and the DB-free validator accept, which is what makes
        the round-trip symmetric.
        """
        if actor is None:
            return None
        if getattr(actor, "kind", None) == "external":
            return {"kind": "external", "name": actor.display_name}
        return {"kind": "user", "id": str(actor.id)}

    @staticmethod
    def actors_to_value(actors: Iterable[Any]) -> dict[str, Any]:
        """Return a multi-value actor selection in wire form (spec section 4).

        Module-level twin of :func:`actors_to_value`, exposed on the class for
        symmetry with :meth:`actor_to_value` (the read projections already reach
        for the class).
        """
        return actors_to_value(actors)

    @staticmethod
    def selected_actors(entity: Any, name: str) -> list[Any]:
        """Return the Actors of a multi-value actor column, in a stable order.

        A multi-value person field is a **selection, not a sequence**, so the read
        order is a deterministic function of the *data* rather than of the write:
        ``(display_name, id)``, case-folded. Two consequences, both wanted:

        * two consecutive reads always agree, which is what the AUC's round-trip
          stability check (and the frontend chip row) depends on;
        * the order is human-meaningful in a UI, and needs neither an index nor a
          database collation (a locale-dependent ``ORDER BY`` would make the wire
          order depend on the database's locale, not on the data).

        Write order is deliberately NOT reproduced: Django's own
        ``ManyRelatedManager.set()`` cannot promise it — its non-fast path
        computes the rows to insert as ``target_ids.difference(...)``, a **set**,
        so the insertion order is hash-dependent (``_get_missing_target_ids``).
        Reproducing it would mean hand-writing the join rows and giving up
        ``m2m_changed``, i.e. re-implementing a Django primitive to carry an order
        the domain does not have. The multi-value *classification* field
        (``stakeholder``) is the opposite case and keeps the user's order, because
        it is stored as a plain list column.

        Falls back to ``manager.all()`` for anything that is not a
        ``ManyToManyField`` (a structural test double has no ``_meta``), which
        keeps this a total function instead of a second, silent failure mode.
        """
        manager = getattr(entity, name, None)
        if manager is None:
            return []
        field_meta = getattr(getattr(entity, "_meta", None), "get_field", None)
        m2m = None
        if callable(field_meta):
            try:
                candidate = field_meta(name)
            except Exception:  # pragma: no cover - defensive
                candidate = None
            if getattr(candidate, "many_to_many", False):
                m2m = candidate
        actors = list(manager.all())
        if m2m is not None:
            # The manager's ``all()`` carries no ORDER BY, so sort here rather
            # than in SQL: the sort key is Python-computed (case folding), and the
            # selection is bounded by the number of people on one artifact.
            actors.sort(
                key=lambda actor: (
                    str(getattr(actor, "display_name", "")).casefold(),
                    str(getattr(actor, "id", "")),
                )
            )
        return actors

    def resolve_actor_write_values(
        self, ctx: AuthContext, attribute: dict[str, Any], value: Any
    ) -> list[Any]:
        """Resolve a wire multi-actor value to concrete ``Actor`` rows.

        The multi-value half of :meth:`resolve_actor_write_value`, sharing its
        existence/policy check (``ActorService.validate_actor_value``) so REST,
        MCP and the gateway cannot disagree about what a valid selection is. The
        resolved order is the payload order, which is *not* preserved by the read
        — see :meth:`selected_actors` for why a person selection is unordered.

        Raises:
            ValidationError: the value is not the ``{"multiple": true,
                "items": [...]}`` envelope, an actor/user is unknown, or an
                external actor was supplied while ``allow_external`` is false.
        """
        from persistence.errors import ValidationError

        if not attribute.get("multiple", False):
            raise ValidationError(
                f"'{attribute['name']}' is a single-valued actor attribute and "
                "cannot be stored in a multi-value actor column"
            )
        from application.actor_service import ActorService

        return ActorService().validate_actor_value(
            ctx,
            value,
            multiple=True,
            allow_external=bool(attribute.get("allow_external", False)),
        )

    def resolve_actor_write_value(
        self, ctx: AuthContext, attribute: dict[str, Any], value: Any
    ) -> Any:
        """Resolve a wire actor value to an ``Actor`` row for a single FK field.

        Reuses ``ActorService.validate_actor_value`` (Layer 2) so REST, MCP and
        the gateway share one existence/policy check. The type-specific entities
        expose ``owner``/``reporter`` as a single FK, so a ``multiple`` actor
        definition cannot be stored here — that is a definition error, raised
        instead of silently dropping all but the first entry.

        Raises:
            ValidationError: unknown actor/user, external while disallowed, or a
                ``multiple`` attribute on a single-valued system field.
        """
        from persistence.errors import ValidationError

        if value is None:
            return None
        if attribute.get("multiple", False):
            raise ValidationError(
                f"'{attribute['name']}' is a multiple actor attribute and cannot "
                "be stored in the single-valued Artifact system field"
            )
        from application.actor_service import ActorService

        actors = ActorService().validate_actor_value(
            ctx,
            value,
            multiple=False,
            allow_external=bool(attribute.get("allow_external", False)),
        )
        return actors[0] if actors else None

    def validate_actor_system_fields(
        self,
        ctx: AuthContext,
        item_type: str,
        workspace_id: UUID,
        changed_fields: dict[str, Any],
    ) -> None:
        """Resolve DB-backed actor references for the system fields *before* a write.

        WS2 review #936 (Major 2): ``validate`` is deliberately DB-free
        (spec section 5), so a well-formed but unknown/foreign-tenant actor UUID
        passed it, the wrapped service created the artifact, and only the
        subsequent system-field write failed — leaving a duplicate on retry.
        This companion performs the Layer-2 half (``validate_actor_value`` /
        ``resolve_reference``) while the payload is still only a payload, so an
        unresolvable actor is rejected *before* the service call. Both
        transports call it from their existing validation seam, which is what
        keeps REST and MCP identical (ADR-004).

        ADR-006 widened the name set: the multi-value person fields
        (``Adr.deciders`` / ``Issue.assignee``) are actor references resolved
        against the DB exactly like ``owner``/``reporter``, so the same
        before-the-service-call guarantee has to cover them or a bad selection
        would only surface after the entity exists. The candidate names come
        from one registry (``schema.all_entity_carrier_fields``), so the next
        person field is covered by declaring it, not by editing this method.

        Only ``visible`` + ``editable`` actor attributes are checked — exactly
        the ones :meth:`write` would apply (Major 3) — so a hidden legacy field
        (e.g. ``Risk.owner``) is neither resolved nor created here.

        Args:
            ctx: Request identity.
            item_type: One of ``ITEM_TYPES``.
            workspace_id: Workspace whose tier selects the definition.
            changed_fields: The payload about to be written.

        Raises:
            FieldValidationError: an actor value could not be resolved (unknown
                actor/user, external while disallowed, or a ``multiple``
                attribute on the single-valued system field). The per-field
                messages mirror the ones :meth:`write` would raise, so both
                transports map them to VALIDATION_ERROR identically.
            AttributeDefinitionNotFound: propagated from
                :meth:`resolve_definition` (callers degrade to a no-op).
        """
        candidates = _ARTIFACT_LEVEL_CORE_FIELDS | frozenset(all_entity_carrier_fields())
        names = [name for name in candidates if name in changed_fields]
        if not names:
            return
        from attribute_definitions.field_validation import FieldValidationError
        from persistence.errors import NotFoundError, ValidationError

        definition = self.resolve_definition(ctx, item_type, workspace_id)
        by_name = {attribute["name"]: attribute for attribute in definition["attributes"]}
        errors: dict[str, list[str]] = {}
        for name in names:
            attribute = by_name.get(name)
            if (
                attribute is None
                or attribute["type"] != "actor"
                or not attribute["visible"]
                or attribute["editable"] is not True
            ):
                continue
            try:
                if attribute.get("multiple", False):
                    self.resolve_actor_write_values(
                        ctx, attribute, changed_fields[name]
                    )
                else:
                    self.resolve_actor_write_value(ctx, attribute, changed_fields[name])
            except (ValidationError, NotFoundError) as exc:
                errors[name] = [str(exc)]
        if errors:
            raise FieldValidationError(errors)

    def _read_core_value(
        self, artifact: AttributeArtifact, attribute: dict[str, Any]
    ) -> Any:
        """Read one core attribute, resolving Artifact-level fields and actors.

        Three carrier shapes, one dispatch on the definition entry (never on the
        model), which is what keeps this generic: a plain column, a single Actor
        FK, and — ADR-006 — a multi-value Actor relation, read in write order.
        """
        name = attribute["name"]
        target: Any = (
            self._custom_fields_owner(artifact)
            if name in _ARTIFACT_LEVEL_CORE_FIELDS
            else artifact
        )
        raw = getattr(target, name)
        if attribute["type"] != "actor":
            return raw
        if attribute.get("multiple", False):
            return self.actors_to_value(self.selected_actors(artifact, name))
        return self.actor_to_value(raw)

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
        # WS4 #938: an attribute's span lives on its *section*'s
        # ``attribute_flow``; resolve it here so both transports receive the
        # same layout hint. A definition without sections/flows (the additive
        # legacy case) yields "full" for every attribute.
        sections_by_name = {
            section["name"]: section
            for section in (definition.get("sections") or [])
        }
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
                span=resolve_attribute_span(
                    attribute["name"], sections_by_name.get(attribute["section"])
                ),
                copyable=attribute["copyable"],
                reveal=attribute["reveal"],
                mask=attribute["mask"],
                display_format=attribute["display_format"],
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
                core[name] = self._read_core_value(artifact, attribute)
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

        # Capture the pre-write owner before the assignment loop so the
        # post-write comparison needs no extra read: the backing Artifact holds
        # ``owner_id`` directly (spec section 3). This is a plain attribute read
        # — an unrelated attribute write adds zero queries.
        owner_holder = self._custom_fields_owner(artifact)
        previous_owner_id = getattr(owner_holder, "owner_id", None)

        for name, value in values.core.items():
            attribute = by_name.get(name)
            if attribute is None or attribute["kind"] != "core":
                continue
            if attribute["type"] == "widget":
                continue
            # WS2 review #936 (Major 3): only a visible *and* editable core
            # attribute is writeable through this seam. ``validate()`` already
            # excludes ``editable in ("workflow", "system")`` from the payload
            # entirely, and ``editable is False`` is rejected on update; this
            # loop used to ignore both and wrote every core name by
            # ``setattr``, so ``core={"id": ...}`` / ``{"status": ...}`` could
            # overwrite a server-owned column. Ignoring them here keeps W
            # symmetric with V (spec section 6: "ID, Status; nie schreibbar").
            if not attribute["visible"] or attribute["editable"] is not True:
                continue
            if name in _ARTIFACT_LEVEL_CORE_FIELDS:
                # ``owner``/``reporter``/``priority``/``stakeholder`` live on the
                # backing Artifact; actors additionally translate the wire value
                # form into the FK row (spec sections 3/4). A ``multiple`` actor
                # definition on one of these is a definition error, raised by
                # ``resolve_actor_write_value`` rather than silently dropped.
                target = self._custom_fields_owner(artifact)
                if attribute["type"] == "actor":
                    value = self.resolve_actor_write_value(ctx, attribute, value)
                setattr(target, name, value)
                _remember(target)
                continue
            if attribute["type"] == "actor" and attribute.get("multiple", False):
                # ADR-006: a multi-value person field. Its column is a
                # ``ManyToManyField`` on the entity, so ``setattr`` would raise
                # ("Direct assignment to the forward side of a many-to-many set
                # is prohibited") and the relation has to be replaced through the
                # manager. Dispatched purely on the definition's ``type`` +
                # ``multiple``, so the next such field needs no change here.
                # ``set()`` writes its own join rows, so no ``_persist`` is
                # needed for the relation itself — the entity is only remembered
                # for a sibling plain-column write in the same payload.
                actors = self.resolve_actor_write_values(ctx, attribute, value)
                getattr(artifact, name).set(actors)
                _remember(artifact)
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

        # Menschen-im-System spec §5: an owner *change* produces an `assigned`
        # notification. The cheap ``owner_id`` comparison runs on every write;
        # the Actor FK (``owner_holder.owner``) is only loaded when the owner
        # actually changed, so an unrelated attribute write adds no query. The
        # call sits after the persist loop — not at the ``setattr`` — so a
        # failing ``_persist`` can never notify an assignment that never landed.
        if getattr(owner_holder, "owner_id", None) != previous_owner_id:
            try:
                # Lazy import: this module must stay importable without a
                # configured Django app registry (see the class docstring).
                from application.notification_service import notify_assigned

                notify_assigned(
                    ctx=ctx,
                    artifact_id=getattr(owner_holder, "id", None),
                    owner=getattr(owner_holder, "owner", None),
                    previous_owner_id=previous_owner_id,
                )
            except Exception:
                logger.exception(
                    "ArtifactAttributeGateway.write: assigned notification "
                    "failed for artifact %s",
                    getattr(owner_holder, "id", None),
                )

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
    "ARTIFACT_SYSTEM_FIELD_NAMES",
    "ArtifactAttributeGateway",
    "AttributeArtifact",
    "AttributeCarrier",
    "AttributeDescriptor",
    "AttributeValues",
    "artifact_system_fields",
    "actors_to_value",
    "carrier_for",
    "entity_item_type",
    "transport_field_names",
]

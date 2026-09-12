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
SKELETON / INTERFACE ONLY (WS0). ``resolve_definition`` and ``validate`` are
thin, behaviour-preserving delegations to the already-central
``AttributeDefinitionService`` (layer 2, ADR-01), because those two operations
already have exactly one implementation. ``discover``, ``read`` and ``write``
raise :class:`NotImplementedError`: their carrier-aware behaviour is WS1's job
and nothing may be wired before then.

References:
    * ADR-004 — ``docs/se/ADR/ADR-004_traeger-modell-und-auc.md``
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
    are WS1's implementation and raise :class:`NotImplementedError` for now.

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
            NotImplementedError: WS1 owns the transport-independent discovery
                implementation.
            AttributeDefinitionNotFound: propagated from
                :meth:`resolve_definition`.
        """
        raise NotImplementedError(
            "ArtifactAttributeGateway.discover is WS1 (#934/#941): implement "
            "transport-independent definition discovery for every item type "
            "before wiring REST/MCP (spec section 9/11)."
        )

    # ---- Read (R) ----------------------------------------------------------

    def read(
        self, ctx: AuthContext, item_type: str, artifact: AttributeArtifact
    ) -> AttributeValues:
        """Read every visible attribute value of *artifact* (AUC: R).

        Reads core columns and ``Artifact.custom_fields`` through the resolved
        definition, so a visible extended attribute can never be omitted on
        either transport (the current MCP ``generic._to_dict`` bug, spec
        section 9).

        Returns:
            The artifact's values split by carrier.

        Raises:
            NotImplementedError: WS1 owns the carrier-aware read.
        """
        raise NotImplementedError(
            "ArtifactAttributeGateway.read is WS1 (#934/#941): read core "
            "columns and Artifact.custom_fields through the resolved "
            "definition (spec section 9/11)."
        )

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

        Returns:
            The persisted values read back through :meth:`read`, so a caller
            (and the contract matrix) can assert Round-Trip.

        Raises:
            NotImplementedError: WS1 owns the carrier-aware write.
            FieldValidationError: the values violate the resolved definition.
        """
        raise NotImplementedError(
            "ArtifactAttributeGateway.write is WS1 (#934/#941): persist core "
            "columns plus Artifact.custom_fields and return the stored "
            "read-back (spec section 9/11)."
        )

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
]

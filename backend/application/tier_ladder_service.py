"""Per-workspace requirement tier ladder (P2, V4/V5/B5).

The ladder is the ordered list of named positions a Requirement's tier can take.
``tier_key`` is the stable machine key written to ``Requirement.tier_key``;
``name`` is the editable ``{de, en}`` label, so renaming never touches data.
The integer alias ``Requirement.level`` is ``position + 1``.

The default ladder is the four positions ``erste``, ``dazwischen``,
``vorletzte`` (from the end = 1) and ``letzte`` (from the end = 0). It is seeded
lazily for a workspace that has none, so workspaces created after the migration
get the same ladder as the migrated ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from django.db import transaction

from application.base import NotFoundError, ServiceBase, ValidationError
from auth_tenancy.context import AuthContext
from auth_tenancy.models import ROLE_ADMIN
from persistence.models import (
    Requirement,
    Workspace,
    WorkspaceTier,
    WorkspaceTierRule,
)

#: ``(tier_key, name, rule, from_end)`` — the four default positions.
DEFAULT_TIERS: tuple[tuple[str, dict[str, str], str, int | None], ...] = (
    ("erste", {"de": "Erste", "en": "First"}, WorkspaceTierRule.FIRST, None),
    (
        "dazwischen",
        {"de": "Dazwischen", "en": "Middle"},
        WorkspaceTierRule.MIDDLE,
        None,
    ),
    (
        "vorletzte",
        {"de": "Vorletzte", "en": "Second to last"},
        WorkspaceTierRule.FROM_END,
        1,
    ),
    (
        "letzte",
        {"de": "Letzte", "en": "Last"},
        WorkspaceTierRule.FROM_END,
        0,
    ),
)

#: The "three names" quick helper: top, middle, bottom.
THREE_NAME_TIERS: tuple[tuple[str, dict[str, str], str, int | None], ...] = (
    ("erste", {"de": "Erste", "en": "First"}, WorkspaceTierRule.FIRST, None),
    ("dazwischen", {"de": "Mitte", "en": "Middle"}, WorkspaceTierRule.MIDDLE, None),
    ("letzte", {"de": "Letzte", "en": "Last"}, WorkspaceTierRule.FROM_END, 0),
)


@dataclass(frozen=True)
class TierLadder:
    """Resolved ladder: ordered entries with a fast key -> position map."""

    entries: tuple[WorkspaceTier, ...]
    position_by_key: dict[str, int]

    def key_at(self, position: int) -> str | None:
        if 0 <= position < len(self.entries):
            return self.entries[position].tier_key
        return None

    def position_of(self, tier_key: str | None) -> int | None:
        if tier_key is None:
            return None
        return self.position_by_key.get(tier_key)

    def first_key(self) -> str | None:
        for entry in self.entries:
            if entry.rule == WorkspaceTierRule.FIRST:
                return entry.tier_key
        return None

    def middle_key(self) -> str | None:
        for entry in self.entries:
            if entry.rule == WorkspaceTierRule.MIDDLE:
                return entry.tier_key
        return None

    def from_end_key(self, height: int) -> str | None:
        for entry in self.entries:
            if entry.rule == WorkspaceTierRule.FROM_END and entry.from_end == height:
                return entry.tier_key
        return None


def _validate_ladder(payload: list[dict]) -> None:
    """Validate a replacement ladder before anything is written."""
    if not payload:
        raise ValidationError("The tier ladder must not be empty.")

    keys = [str(item.get("tier_key") or "").strip() for item in payload]
    if any(not key for key in keys):
        raise ValidationError("Every tier needs a non-empty tier_key.")
    if len(keys) != len(set(keys)):
        raise ValidationError("Tier keys must be unique.")

    rules = [item.get("rule") for item in payload]
    if rules.count(WorkspaceTierRule.FIRST) != 1:
        raise ValidationError("The ladder needs exactly one 'first' tier.")
    if rules.count(WorkspaceTierRule.MIDDLE) > 1:
        raise ValidationError("The ladder has at most one 'middle' tier.")

    from_end_values = [
        item.get("from_end") for item in payload if item.get("rule") == WorkspaceTierRule.FROM_END
    ]
    if from_end_values.count(0) != 1:
        raise ValidationError("The ladder needs exactly one from_end=0 (leaf) tier.")
    if any(value is None or int(value) < 0 for value in from_end_values):
        raise ValidationError("Every from_end tier needs a non-negative from_end value.")
    if len(from_end_values) != len(set(from_end_values)):
        raise ValidationError("from_end values must be unique.")


class TierLadderService(ServiceBase):
    """Read, seed and replace the per-workspace tier ladder."""

    def _workspace(self, workspace_id: UUID) -> Workspace:
        workspace = Workspace.unscoped.filter(id=workspace_id).first()
        if workspace is None:
            raise NotFoundError(f"Workspace {workspace_id} not found")
        return workspace

    def get(self, workspace_id: UUID) -> TierLadder:
        """Return the workspace ladder, seeding the default if it is empty."""
        from persistence.tenancy import TenantContext

        try:
            previous_tenant = TenantContext.get_tenant()
        except Exception:  # noqa: BLE001 - no active tenant is the normal case
            previous_tenant = None
        workspace = self._workspace(workspace_id)
        TenantContext.set_tenant(workspace.tenant_id)
        try:
            self._seed_if_empty(workspace_id)
            entries = tuple(
                WorkspaceTier.objects.filter(workspace_id=workspace_id).order_by(
                    "position", "id"
                )
            )
        finally:
            if previous_tenant is None:
                TenantContext.clear_tenant()
            else:
                TenantContext.set_tenant(previous_tenant)
        return TierLadder(
            entries=entries,
            position_by_key={entry.tier_key: entry.position for entry in entries},
        )

    def _seed_if_empty(self, workspace_id: UUID) -> None:
        if WorkspaceTier.objects.filter(workspace_id=workspace_id).exists():
            return
        workspace = self._workspace(workspace_id)
        with transaction.atomic():
            for position, (tier_key, name, rule, from_end) in enumerate(DEFAULT_TIERS):
                WorkspaceTier.objects.get_or_create(
                    workspace_id=workspace_id,
                    tier_key=tier_key,
                    defaults={
                        "tenant": workspace.tenant,
                        "name": name,
                        "position": position,
                        "rule": rule,
                        "from_end": from_end,
                    },
                )

    def seed_default(self, workspace_id: UUID) -> list[WorkspaceTier]:
        self._seed_if_empty(workspace_id)
        return list(
            WorkspaceTier.objects.filter(workspace_id=workspace_id).order_by("position")
        )

    def apply_three_names(
        self, workspace_id: UUID, names: dict[str, str], ctx: AuthContext
    ) -> list[WorkspaceTier]:
        """Build the ladder from three names (top, middle, bottom)."""
        payload = []
        for index, (tier_key, _default, rule, from_end) in enumerate(THREE_NAME_TIERS):
            label = names.get(tier_key) or names.get(str(index)) or _default["de"]
            payload.append(
                {
                    "tier_key": tier_key,
                    "name": {"de": label, "en": label},
                    "rule": rule,
                    "from_end": from_end,
                }
            )
        return self.replace(workspace_id, payload, ctx)

    def replace(
        self, workspace_id: UUID, tiers: list[dict], ctx: AuthContext
    ) -> list[WorkspaceTier]:
        """Replace the whole ladder (workspace admin only).

        Deleting an entry that is still referenced by a ``Requirement.tier_key``
        is refused with a conflict unless the entry carries ``merge_into``
        (the key of the surviving tier). Requirements of a merged-away key are
        moved to the target before the row is removed.
        """
        self._set_tenant_context(ctx)
        self._assert_permission(ctx, ROLE_ADMIN)
        workspace = self._workspace(workspace_id)
        _validate_ladder(tiers)

        desired_keys = [str(item["tier_key"]) for item in tiers]
        merge_targets: dict[str, str] = {}
        for item in tiers:
            merge_into = item.get("merge_into")
            if merge_into:
                merge_targets[str(item["tier_key"])] = str(merge_into)

        existing = {
            entry.tier_key: entry
            for entry in WorkspaceTier.objects.filter(workspace_id=workspace_id)
        }
        removed = set(existing) - set(desired_keys)
        merged_from: dict[str, str] = {}
        for key in removed:
            target = merge_targets.get(key)
            if target is None:
                if Requirement.objects.filter(
                    workspace_id=workspace_id, tier_key=key
                ).exists():
                    raise ValidationError(
                        f"Tier {key!r} is still referenced by requirements; "
                        "pass merge_into to move them."
                    )
            else:
                if target not in desired_keys:
                    raise ValidationError(
                        f"merge_into target {target!r} is not part of the new ladder."
                    )
                merged_from[key] = target

        with transaction.atomic():
            for key, target in merged_from.items():
                Requirement.objects.filter(
                    workspace_id=workspace_id, tier_key=key
                ).update(tier_key=target)
            WorkspaceTier.objects.filter(
                workspace_id=workspace_id, tier_key__in=removed
            ).delete()
            for position, item in enumerate(tiers):
                entry = existing.get(str(item["tier_key"]))
                if entry is None:
                    entry = WorkspaceTier(
                        workspace_id=workspace_id,
                        tenant=workspace.tenant,
                        tier_key=str(item["tier_key"]),
                    )
                entry.name = item.get("name") or entry.name or {}
                entry.position = position
                entry.rule = item["rule"]
                entry.from_end = item.get("from_end")
                entry.save()
            self._reindex_levels(workspace_id)

        return list(
            WorkspaceTier.objects.filter(workspace_id=workspace_id).order_by("position")
        )

    def _reindex_levels(self, workspace_id: UUID) -> None:
        """Rewrite every requirement's integer alias from its tier position."""
        from application.tier_compute import recompute_workspace_tiers

        recompute_workspace_tiers(workspace_id)

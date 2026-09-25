"""Report the API keys that exist in the database — read-only inventory (CR-03).

Audit track ``CR-03`` (evidence register 09, P1 for new agent/UI keys, P2 for
legacy hardening) asks for exactly two things, in this order:

1. A new REST/MCP key must carry an explicit scope, an explicit workspace fence
   and an explicit expiry decision.
2. A legacy key is *inventoried and rotated*, never silently changed.

This command is the inventory half and nothing else. It has no ``--fix`` and no
write path: it never calls ``create_api_key``, ``revoke_api_key``, any rotation
helper, ``.save()``, ``.delete()``, ``.update()`` or ``bulk_update`` on an
``ApiKey`` row. The only way an existing key changes is through the normal
key-management path (REST ``/api/v1/api-keys/``, MCP key group, or
``AuthenticationService``).

Secret discipline: ``ApiKey.key_hash`` is selected purely to compute the boolean
``secret_present`` and is then dropped. Neither the hash, nor its version
prefix, nor its length, nor any fragment of it ever reaches stdout, the
``--output`` file, or the JSON/CSV payload — the field name does not appear
either, so ``grep -i key_hash`` over an archived report finds nothing.

The command reports *observed* attributes and, separately, which documented
rules those attributes do not satisfy. It deliberately does **not** adjudicate
usability: it never marks a key invalid, broken, unsafe or not agent-capable,
because a row's attribute values do not earn such a verdict. The verdict
belongs to whoever acts on the rotation-candidate list.

A workspace fence counts as *set* only when **every** entry is a canonical,
lower-case, hyphenated UUID string — the normal form
``AuthenticationService.create_api_key`` writes for an agent key.
``ApiKey.workspace_ids`` is a plain ``JSONField`` with no validator, no model
``clean()`` and no DB constraint, and the write path normalises nothing for
``user`` keys, so a fence holding a malformed token, a bare hex id, an
upper-case UUID or an empty string is reported as ``defective`` and counted as
unsatisfied instead of passing as a real fence. A *mixed* fence is
``defective`` too: the rule is a conjunction over all entries, not an
existential. This classifies stored values; it never rewrites them and never
says whether the key works.

Usage::

    python manage.py inventory_api_keys
    python manage.py inventory_api_keys --format json --output keys.json
    python manage.py inventory_api_keys --format csv --output keys.csv
    python manage.py inventory_api_keys --tenant-id <uuid>

Every output format prints the rotation rule and its effective date verbatim,
so a reader can see *why* a key landed in the rotation-candidate list without
having to open this file.
"""
from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Sequence
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from auth_tenancy.models import (
    API_KEY_SCOPE_ADMIN,
    API_KEY_SCOPE_AUTHOR,
    API_KEY_SCOPE_READ,
    API_KEY_SCOPE_READ_ONLY,
    API_KEY_SCOPE_WRITE,
    ApiKey,
)

# ---------------------------------------------------------------------------
# The documented new-key contract (roadmap §4.7 acceptance criterion 3):
# "Ein neuer REST-/MCP-Key muss Scope, Workspace-Fence und Ablauf-/
# Nicht-Ablauf-Entscheidung explizit besitzen".
# ---------------------------------------------------------------------------
#: The three canonical scope tiers. The two legacy aliases (``read``/``write``)
#: are deliberately *not* in here: they are the widest, implicit defaults the
#: contract is meant to replace, and a key still carrying one has not made an
#: explicit canonical scope choice.
CANONICAL_SCOPES = frozenset(
    {API_KEY_SCOPE_READ_ONLY, API_KEY_SCOPE_AUTHOR, API_KEY_SCOPE_ADMIN}
)
LEGACY_SCOPE_ALIASES = frozenset({API_KEY_SCOPE_READ, API_KEY_SCOPE_WRITE})

#: Rule ids reported per key in the ``unsatisfied_rules`` column. One entry per
#: clause of the new-key contract above, in that order.
NEW_KEY_CONTRACT_RULES = (
    "explicit-canonical-scope",
    "workspace-fence-set",
    "expiry-decision-recorded",
)

_REASON_BY_RULE = {
    "explicit-canonical-scope": "no-canonical-scope",
    "workspace-fence-set": "no-workspace-fence",
    "expiry-decision-recorded": "no-expiry-decision",
}

#: Reasons that are not tied to a single rule.
REASON_PRE_RULE = "created-before-rule-effective-date"

#: Stated in the report so the reader knows what "expired" was compared against.
EXPIRY_STATE_NO_EXPIRY = "no_expiry_set"
EXPIRY_STATE_EXPIRED = "expired"
EXPIRY_STATE_FUTURE = "not_yet_expired"

#: Workspace-fence states. ``set`` is reported only when *every* entry is a
#: canonical UUID; a non-empty fence that does not clear that bar is
#: ``defective``. Both ``unset`` and ``defective`` mean the new-key contract's
#: ``workspace-fence-set`` clause is not satisfied.
FENCE_STATE_UNSET = "unset"
FENCE_STATE_SET = "set"
FENCE_STATE_DEFECTIVE = "defective"


@dataclass(frozen=True)
class RotationRule:
    """A dated, named, reviewable rotation rule.

    ``effective_date`` is compared against ``ApiKey.created_at`` in UTC. Keeping
    it a plain date (not a timestamp) makes the boundary an auditable calendar
    day: a key created on the effective date is *not* pre-dated, one created the
    second before is.
    """

    name: str
    effective_date: date
    source_reference: str
    criteria: Sequence[str]

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "effective_date": self.effective_date.isoformat(),
            "source_reference": self.source_reference,
            "criteria": list(self.criteria),
        }


#: The single named rotation rule. Adjusting the policy means editing this
#: constant (and the date in its name) in a reviewable commit — never editing
#: reported data, which this command does not do at all.
LEGACY_KEY_ROTATION_RULE = RotationRule(
    name="CR-03-LEGACY-API-KEY-ROTATION/2026-09-25",
    effective_date=date(2026, 9, 25),
    source_reference="CR-03 (P1 new agent/UI keys, P2 legacy hardening)",
    criteria=(
        "rotation candidate if created before the effective date (UTC), or if "
        "the key does not satisfy one of the new-key contract rules: "
        + ", ".join(NEW_KEY_CONTRACT_RULES),
    ),
)

#: Printed in the report header of every format. Kept out of ``criteria`` so the
#: rule definition stays a description of the classification, not of the remedy.
ACTING_ON_A_CANDIDATE = (
    "rotate through the normal key-management path (REST /api/v1/api-keys/, "
    "MCP key group, AuthenticationService) - never through this command"
)

#: Column order, also the CSV header. Deliberately free of any secret-bearing
#: name: the only thing derived from the hash column is ``secret_present``.
INVENTORY_COLUMNS = (
    "key_id",
    "name",
    "tenant_id",
    "tenant_slug",
    "owner_user_id",
    "owner_username",
    "principal_type",
    "agent_label",
    "scope",
    "scope_is_legacy_alias",
    "workspace_ids",
    "workspace_fence_state",
    "expires_at",
    "expiry_state",
    "created_at",
    "last_used_at",
    "usage_state",
    "revoked_at",
    "status",
    "not_revoked",
    "secret_present",
    "unsatisfied_rules",
    "rotation_candidate",
    "rotation_reasons",
)

#: Fields pulled from the row. ``key_hash`` is read to compute ``secret_present``
#: and is never propagated out of :func:`collect_inventory`.
_VALUE_FIELDS = (
    "id",
    "name",
    "tenant_id",
    "tenant__slug",
    "user_id",
    "user__username",
    "principal_type",
    "agent_label",
    "scope",
    "workspace_ids",
    "expires_at",
    "created_at",
    "last_used_at",
    "revoked_at",
    "key_hash",
)


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def classify_expiry(expires_at: Optional[datetime], now: datetime) -> str:
    """Return the observed expiry state, keeping "unset" apart from "expired".

    ``ApiKey.expires_at is None`` and ``ApiKey.expires_at <= now`` are very
    different facts — the first records no expiry decision, the second records a
    decision that has since passed — and the model itself keeps them apart
    (``ApiKey.is_expired`` returns ``False`` for ``None``). Collapsing them into
    one "invalid" bucket would destroy that distinction, so it is reported as
    three explicit states.
    """
    if expires_at is None:
        return EXPIRY_STATE_NO_EXPIRY
    if expires_at <= now:
        return EXPIRY_STATE_EXPIRED
    return EXPIRY_STATE_FUTURE


def classify_status(revoked_at: Optional[datetime], expiry_state: str) -> str:
    """Return the observed lifecycle state.

    Precedence is revoked > expired > active, and it is *not* the same thing as
    the model's ``ApiKey.is_active``: an expired key is still ``is_active`` (it
    is not revoked), which is why both are reported.
    """
    if revoked_at is not None:
        return "revoked"
    if expiry_state == EXPIRY_STATE_EXPIRED:
        return "expired"
    return "active"


def is_canonical_workspace_id(value: Any) -> bool:
    """Return whether *value* is a canonical, lower-case, hyphenated UUID string.

    Canonicality is decided by round-trip: the entry must be a string *and*
    identical to the ``str(UUID(value))`` normal form. That is deliberately the
    same normal form ``AuthenticationService.create_api_key`` writes for an
    agent key, so the writer and this check cannot disagree about what a fence
    entry looks like.

    It is not redundant with parsing. ``UUID(...)`` *accepts* a bare 32-char hex
    id, an upper-case UUID, a ``{}``-braced and a ``urn:uuid:``-prefixed form,
    and ``str(...)`` silently rewrites each of those into the canonical form —
    so a parse test alone would pass values that are not stored canonically and
    would then never match the workspace ids the row is actually compared
    against. Comparing against the rewritten form is what rejects them. The
    remaining entries (empty string, any non-UUID token, and any non-string
    JSON value such as ``None``/int/bool/list/dict) raise instead, and are
    reported non-canonical rather than crashing the read-only report.
    """
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value
    except (AttributeError, TypeError, ValueError):
        return False


def classify_workspace_fence(workspace_ids: Sequence[Any]) -> str:
    """Return the observed workspace-fence classification.

    Three states, one per way the stored fence can relate to the contract:

    * ``unset``     — no fence recorded (empty list, or a null JSON column).
    * ``set``       — a non-empty fence in which *every* entry is canonical.
    * ``defective`` — a non-empty fence with at least one non-canonical entry.

    The fence rule is a **conjunction, not an existential**, so a *mixed* fence
    (some canonical entries, some not) is ``defective`` and not ``set``: one
    entry that does not resolve to a workspace identity means the fence does not
    fully bind the key, so it cannot serve as the key's authority boundary. A
    fence counts towards the "no workspace fence" total unless it is ``set``.

    This classifies the stored values and reports them verbatim; it never
    rewrites, normalises or repairs a row. It is an observation about the shape
    of a column, in the same class as "no expiry recorded" — not a judgement
    about whether the key works.
    """
    if not workspace_ids:
        return FENCE_STATE_UNSET
    if all(is_canonical_workspace_id(value) for value in workspace_ids):
        return FENCE_STATE_SET
    return FENCE_STATE_DEFECTIVE


def unsatisfied_rules(
    *, scope: str, workspace_ids: Sequence[Any], expires_at: Optional[datetime]
) -> List[str]:
    """Return the new-key contract rules this key's attributes do not satisfy.

    Pure attribute comparison — no capability judgement, no usability verdict.
    The fence clause asks for a *canonical* fence, not merely a non-empty one:
    see :func:`classify_workspace_fence` for why non-emptiness is not enough.
    """
    missing: List[str] = []
    if scope not in CANONICAL_SCOPES:
        missing.append("explicit-canonical-scope")
    if classify_workspace_fence(workspace_ids) != FENCE_STATE_SET:
        missing.append("workspace-fence-set")
    if expires_at is None:
        missing.append("expiry-decision-recorded")
    return missing


def rotation_reasons(
    *, created_at: datetime, missing_rules: Sequence[str]
) -> List[str]:
    """Return why a key is a rotation candidate under the named rule.

    Two independent triggers, matching the audit wording: the key predates the
    rule's effective date, or its attributes fall short of the new-key contract.
    """
    reasons: List[str] = []
    if created_at.date() < LEGACY_KEY_ROTATION_RULE.effective_date:
        reasons.append(REASON_PRE_RULE)
    for rule_id in missing_rules:
        reason = _REASON_BY_RULE.get(rule_id)
        if reason is not None:
            reasons.append(reason)
    return reasons


def collect_inventory(
    *, tenant_id: Optional[UUID] = None, now: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Return one read-only inventory record per ``ApiKey`` row.

    Whole-database by default (``--tenant-id`` narrows it), so it queries
    ``ApiKey.unscoped`` inside a ``SET LOCAL row_security = off`` transaction,
    exactly like ``inventory_link_types`` does for ``TraceLink``: on the
    least-privilege app role this makes an RLS-blinded connection fail loudly
    instead of silently reporting "0 keys, nothing to rotate".

    Read-only by construction: one ``.values()`` read, no model instance is
    saved, deleted or updated, and no service that writes an ``ApiKey`` is
    reachable from this module.
    """
    moment = now or timezone.now()
    queryset = ApiKey.unscoped.all()
    if tenant_id is not None:
        queryset = queryset.filter(tenant_id=tenant_id)
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL row_security = off")
        rows = list(queryset.values(*_VALUE_FIELDS).order_by("created_at", "id"))

    inventory: List[Dict[str, Any]] = []
    for row in rows:
        expires_at = row["expires_at"]
        created_at = row["created_at"]
        workspace_ids = [str(w) for w in (row["workspace_ids"] or [])]
        expiry_state = classify_expiry(expires_at, moment)
        missing = unsatisfied_rules(
            scope=row["scope"],
            workspace_ids=workspace_ids,
            expires_at=expires_at,
        )
        reasons = rotation_reasons(created_at=created_at, missing_rules=missing)
        inventory.append(
            {
                "key_id": str(row["id"]),
                "name": row["name"],
                "tenant_id": str(row["tenant_id"]),
                "tenant_slug": row["tenant__slug"] or "",
                "owner_user_id": str(row["user_id"]),
                "owner_username": row["user__username"] or "",
                "principal_type": row["principal_type"],
                "agent_label": row["agent_label"],
                "scope": row["scope"],
                "scope_is_legacy_alias": row["scope"] in LEGACY_SCOPE_ALIASES,
                "workspace_ids": workspace_ids,
                "workspace_fence_state": classify_workspace_fence(workspace_ids),
                "expires_at": _iso(expires_at),
                "expiry_state": expiry_state,
                "created_at": _iso(created_at),
                "last_used_at": _iso(row["last_used_at"]),
                "usage_state": "used" if row["last_used_at"] else "never_used",
                "revoked_at": _iso(row["revoked_at"]),
                "status": classify_status(row["revoked_at"], expiry_state),
                "not_revoked": row["revoked_at"] is None,
                "secret_present": bool(row["key_hash"]),
                "unsatisfied_rules": missing,
                "rotation_candidate": bool(reasons),
                "rotation_reasons": reasons,
            }
        )
    return inventory


def build_payload(
    inventory: Sequence[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    tenant_id: Optional[UUID] = None,
) -> Dict[str, Any]:
    """Assemble the machine-readable report envelope.

    ``generated_at`` is the only intentionally volatile field; the ``keys`` array
    and the ``totals`` are stable, so archiving two runs and diffing them shows
    real key-state change.
    """
    moment = now or timezone.now()
    candidates = [e for e in inventory if e["rotation_candidate"]]
    return {
        "report": "api-key-inventory",
        "read_only": True,
        "generated_at": moment.isoformat(),
        "tenant_filter": str(tenant_id) if tenant_id else None,
        "columns": list(INVENTORY_COLUMNS),
        "rotation_rule": LEGACY_KEY_ROTATION_RULE.as_dict(),
        "disclosure": {
            "secret_material_emitted": False,
            "secret_present_is_boolean_only": True,
            "capability_judgements_emitted": False,
        },
        "totals": {
            "keys": len(inventory),
            "rotation_candidates": len(candidates),
            "revoked": sum(1 for e in inventory if e["status"] == "revoked"),
            "expired": sum(1 for e in inventory if e["status"] == "expired"),
            "no_expiry_set": sum(
                1 for e in inventory if e["expiry_state"] == EXPIRY_STATE_NO_EXPIRY
            ),
            "never_used": sum(1 for e in inventory if e["usage_state"] == "never_used"),
            # Counts every state that is not a canonical fence, so a defective
            # or mixed fence is not lost from the totals; the per-key
            # ``workspace_fence_state`` column carries the unset/defective split.
            "no_workspace_fence": sum(
                1
                for e in inventory
                if e["workspace_fence_state"] != FENCE_STATE_SET
            ),
        },
        "rotation_candidate_key_ids": [e["key_id"] for e in candidates],
        "keys": list(inventory),
    }


def _render_fence(entry: Dict[str, Any]) -> str:
    """Render the observed fence values together with their classification.

    A defective fence is called out as such rather than being printed like a
    healthy one, so the text report cannot read as if every listed entry were a
    workspace the key may act in.
    """
    workspace_ids = entry["workspace_ids"]
    state = entry["workspace_fence_state"]
    if state == FENCE_STATE_UNSET:
        return "UNSET"
    rendered = f"{len(workspace_ids)} ws [{', '.join(workspace_ids)}]"
    if state != FENCE_STATE_DEFECTIVE:
        return rendered
    non_canonical = sum(1 for value in workspace_ids if not is_canonical_workspace_id(value))
    noun = "entry" if non_canonical == 1 else "entries"
    return f"{rendered} (DEFECTIVE: {non_canonical} non-canonical {noun})"


def render_text(
    inventory: Sequence[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    tenant_id: Optional[UUID] = None,
) -> str:
    """Render the human-readable report."""
    moment = now or timezone.now()
    payload = build_payload(inventory, now=moment, tenant_id=tenant_id)
    rule = payload["rotation_rule"]
    totals = payload["totals"]
    out = io.StringIO()
    rule_line = f"{rule['name']} (effective {rule['effective_date']} UTC)"

    out.write("API-key inventory - READ-ONLY (no key row is created, changed or removed)\n")
    out.write(f"Generated: {moment.isoformat()}\n")
    out.write(f"Tenants: {'all' if tenant_id is None else tenant_id}\n")
    out.write("\nRotation rule applied\n")
    out.write(f"  name          : {rule_line}\n")
    out.write(f"  reference     : {rule['source_reference']}\n")
    for criterion in rule["criteria"]:
        out.write(f"  criteria      : {criterion}\n")
    out.write(f"  acting on one : {ACTING_ON_A_CANDIDATE}\n")
    out.write(
        "\nTotals: "
        f"{totals['keys']} key(s) | "
        f"{totals['rotation_candidates']} rotation candidate(s) | "
        f"{totals['revoked']} revoked | {totals['expired']} expired | "
        f"{totals['no_expiry_set']} with no expiry set | "
        f"{totals['no_workspace_fence']} without workspace fence | "
        f"{totals['never_used']} never used\n"
    )

    out.write(f"\nKEYS ({len(inventory)})\n")
    out.write("-" * 100 + "\n")
    if not inventory:
        out.write("  (no API keys)\n")
    for index, entry in enumerate(inventory, start=1):
        fence = _render_fence(entry)
        label = f'  label="{entry["agent_label"]}"' if entry["agent_label"] else ""
        out.write(f"[{index}] {entry['name']}\n")
        out.write(
            f"    id {entry['key_id']} | tenant {entry['tenant_slug']} "
            f"({entry['tenant_id']}) | owner {entry['owner_username']} "
            f"({entry['owner_user_id']})\n"
        )
        out.write(
            f"    principal {entry['principal_type']}{label} | "
            f"scope {entry['scope']}"
            f"{' (legacy alias)' if entry['scope_is_legacy_alias'] else ' (canonical)'} "
            f"| fence {fence}\n"
        )
        out.write(
            f"    created {entry['created_at']} | expiry "
            f"{entry['expires_at'] or 'none'} ({entry['expiry_state']}) | "
            f"last_used {entry['last_used_at'] or 'never'} "
            f"({entry['usage_state']})\n"
        )
        out.write(
            f"    status {entry['status']} | revoked_at "
            f"{entry['revoked_at'] or 'none'} | secret "
            f"{'present' if entry['secret_present'] else 'absent'}\n"
        )
        rules = (
            ", ".join(entry["unsatisfied_rules"])
            if entry["unsatisfied_rules"]
            else "all satisfied"
        )
        out.write(f"    unsatisfied rules: {rules}\n")
        out.write(
            "    rotation: "
            + (
                f"CANDIDATE: {', '.join(entry['rotation_reasons'])}"
                if entry["rotation_candidate"]
                else "not a candidate"
            )
            + "\n"
        )

    candidates = [e for e in inventory if e["rotation_candidate"]]
    out.write(f"\nROTATION CANDIDATES ({len(candidates)}) - rule: {rule_line}\n")
    out.write("-" * 100 + "\n")
    if not candidates:
        out.write("  (none)\n")
    for entry in candidates:
        out.write(
            f"  {entry['key_id']}  {entry['name']}  "
            f"(tenant {entry['tenant_slug']}, owner {entry['owner_username']})  "
            f"created {entry['created_at']}\n"
        )
        out.write(f"      reasons: {', '.join(entry['rotation_reasons'])}\n")
    return out.getvalue()


def render_json(
    inventory: Sequence[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    tenant_id: Optional[UUID] = None,
) -> str:
    """Render the machine-readable report (stable key order via ``sort_keys``)."""
    payload = build_payload(inventory, now=now, tenant_id=tenant_id)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ";".join(str(item) for item in value)
    return str(value)


def render_csv(
    inventory: Sequence[Dict[str, Any]],
    *,
    now: Optional[datetime] = None,
    tenant_id: Optional[UUID] = None,
) -> str:
    """Render the flat report for spreadsheet/diff workflows.

    The rule and its date are emitted as leading ``#``-prefixed comment rows so
    a CSV reader sees them, while ``csv.DictReader`` on the header row is
    unaffected (the header is the first non-empty line after the comments —
    strip them if your reader does not skip ``#``).
    """
    moment = now or timezone.now()
    payload = build_payload(inventory, now=moment, tenant_id=tenant_id)
    rule = payload["rotation_rule"]
    buffer = io.StringIO()
    for criterion in rule["criteria"]:
        buffer.write(f"# rotation rule: {criterion}\n")
    buffer.write(
        f"# rotation rule name: {rule['name']} (effective {rule['effective_date']} UTC)\n"
    )
    buffer.write(f"# reference: {rule['source_reference']}\n")
    buffer.write("# report: read-only; no key row is created, changed or removed\n")
    writer = csv.DictWriter(
        buffer, fieldnames=list(INVENTORY_COLUMNS), extrasaction="ignore"
    )
    writer.writeheader()
    for entry in inventory:
        writer.writerow({name: _csv_cell(entry[name]) for name in INVENTORY_COLUMNS})
    return buffer.getvalue()


class Command(BaseCommand):
    help = (
        "Read-only inventory of every API key: owner, scope, principal type, "
        "workspace fence, expiry, usage, and which documented new-key contract "
        "rules it does not satisfy. Never creates, changes, revokes, expires or "
        "rotates a key, and never prints key material. Audit track CR-03."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--format",
            dest="output_format",
            choices=("text", "json", "csv"),
            default="text",
            help="Report format (default: text).",
        )
        parser.add_argument(
            "--output",
            dest="output_path",
            default=None,
            help="Write the report to this path instead of stdout.",
        )
        parser.add_argument(
            "--tenant-id",
            dest="tenant_id",
            default=None,
            help="Restrict the inventory to one tenant UUID (default: all tenants).",
        )

    def handle(self, *args, **options) -> None:
        raw_tenant_id = options.get("tenant_id")
        tenant_id: Optional[UUID] = None
        if raw_tenant_id:
            try:
                tenant_id = UUID(str(raw_tenant_id))
            except (AttributeError, TypeError, ValueError) as exc:
                raise CommandError(
                    f"--tenant-id must be a UUID, got {raw_tenant_id!r}."
                ) from exc

        moment = timezone.now()
        output_format = options.get("output_format") or "text"
        output_path = options.get("output_path")

        inventory = collect_inventory(tenant_id=tenant_id, now=moment)
        renderers = {"text": render_text, "json": render_json, "csv": render_csv}
        report = renderers[output_format](
            inventory, now=moment, tenant_id=tenant_id
        )

        if output_path:
            with open(output_path, "w", encoding="utf-8", newline="") as handle:
                handle.write(report)
            self.stdout.write(
                f"Read-only API-key inventory ({output_format}) written to "
                f"{output_path} - {len(inventory)} key(s), no row modified."
            )
            return

        self.stdout.write(report.rstrip("\n"))

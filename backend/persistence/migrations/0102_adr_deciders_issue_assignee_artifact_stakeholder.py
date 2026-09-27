"""ADR-006: multi-value person references + the stakeholder selection.

Issue #1088. Three fields stopped being free text, each with the mechanism that
fits its *meaning* rather than one uniform hack:

* ``Adr.deciders`` / ``Issue.assignee`` — **multi-value Actor references**. The
  same carrier the single-valued ``Artifact.owner``/``reporter`` FKs already use
  (WS2/#936), so a renamed person updates every ADR/issue that names them. They
  are ``ManyToManyField``s, hence the two new join tables.
* ``Artifact.stakeholder`` — a **list of option values** (an ISO 42010 role or
  group, i.e. a classification, never a person). A list cannot live in
  ``Artifact.custom_fields`` (REQ-L2-AS-037 rejects arrays), so it gets its own
  JSONB column; the option list that validates it lives in the attribute
  catalogue (``type=multi-enum``), not in the DB.

Why the join tables get a policy of their own
---------------------------------------------
``pl_adr``/``as_adr`` and ``as_issue`` are ``TenantScopedModel``s, so both are
already FORCE ROW LEVEL SECURITY keyed on ``app.current_tenant``. An
auto-created ``ManyToManyField`` join table, however, is a plain ``Model`` with
**no ``tenant_id`` column at all** — the standard
``tenant_id = NULLIF(current_setting(...))`` policy is therefore not merely
missing but inexpressible, and the table would have been the one un-isolated
table this migration adds. The policy below resolves the isolation through the
*parent* row instead: a join row is visible exactly when the entity it belongs
to is visible to the current tenant.

That is sound rather than merely defensive: the ORM path always reads the
relation through the parent (``adr.deciders.all()``), and both endpoints of the
join (``as_adr``, ``pl_actor``) carry the standard policy themselves, so a query
that bypassed the parent could still not surface a foreign tenant's Actors. The
policy closes the direct-join path, which the ORM does not use but a raw query
could.

``persistence/tests/test_rls_coverage.py`` scans every ``CREATE POLICY ... ON
<table>`` in the migration graph; it cannot demand a policy for these two tables
(they are not ``TenantScopedModel``s) but it does verify that every policy
declared here actually exists in ``pg_policies`` — a typo'd table name is caught.

The whole model change **and** the policies live in one migration so the app
keeps a single migration leaf (same folding as
``0091_attribute_migration_rls_policy`` and
``0101_attributemigration_definition_snapshot``).

Requirements: REQ-L2-PL-010 (RLS on all tenant-scoped tables), REQ-L2-AS-037
(flat custom_fields), REQ-L0-047, REQ-L0-042. ADR-006, ADR-PL-03.
"""
from __future__ import annotations

from django.db import migrations, models

#: ``(join table, parent table, join column holding the parent id)`` for the two
#: multi-value Actor relations. Named explicitly rather than derived from
#: ``ManyToManyField`` defaults so a rename of a model or a field cannot
#: silently move the policy onto a table that no longer exists.
_JOIN_TABLES = (
    ("as_adr_deciders", "as_adr", "adr_id"),
    ("as_issue_assignee", "as_issue", "issue_id"),
)


def _enable_sql() -> str:
    parts = []
    for table, parent, parent_column in _JOIN_TABLES:
        policy = f"{table}_tenant_isolation"
        current_tenant = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"
        parts.append(
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY;\n"
            f"CREATE POLICY {policy} ON {table}\n"
            f"    USING (EXISTS (SELECT 1 FROM {parent} p\n"
            f"                    WHERE p.id = {table}.{parent_column}\n"
            f"                      AND p.tenant_id = {current_tenant}))\n"
            f"    WITH CHECK (EXISTS (SELECT 1 FROM {parent} p\n"
            f"                       WHERE p.id = {table}.{parent_column}\n"
            f"                         AND p.tenant_id = {current_tenant}));"
        )
    return "\n".join(parts)


def _disable_sql() -> str:
    parts = []
    for table, _parent, _parent_column in _JOIN_TABLES:
        policy = f"{table}_tenant_isolation"
        parts.append(
            f"DROP POLICY IF EXISTS {policy} ON {table};\n"
            f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;\n"
            f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;"
        )
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0101_attributemigration_definition_snapshot"),
    ]

    operations = [
        migrations.AddField(
            model_name="adr",
            name="deciders",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "ADR-006: ISO 42010 deciders of this ADR, as Actor "
                    "references (internal users and/or external placeholders). "
                    "A multi-selection, so the attribute definition declares "
                    "type=actor with multiple=true."
                ),
                related_name="+",
                to="persistence.actor",
            ),
        ),
        migrations.AddField(
            model_name="artifact",
            name="stakeholder",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "ADR-006: ISO 42010 stakeholder role/group of the artifact, "
                    "a list of option values. A classification, NOT a person "
                    "reference (an Actor FK would force an invented Actor row "
                    "per role). The option list is defined per (item_type, "
                    "preset) in the attribute catalogue (type=multi-enum), "
                    "which is also what validates it."
                ),
            ),
        ),
        migrations.AddField(
            model_name="issue",
            name="assignee",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "ADR-006: persons/teams this issue is assigned to, as Actor "
                    "references. A multi-selection, so the attribute "
                    "definition declares type=actor with multiple=true. "
                    "Distinct from the legacy 'assignee_id' User UUID, which the "
                    "dedicated assign_issue() service method owns."
                ),
                related_name="+",
                to="persistence.actor",
            ),
        ),
        migrations.RunSQL(sql=_enable_sql(), reverse_sql=_disable_sql()),
    ]

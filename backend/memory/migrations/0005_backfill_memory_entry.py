# AI Long-Term Memory — backfill MemoryEntry from the legacy tables
# (RFC #1002, PR A).
#
# Copies every row of ``mem_workspace_memory`` (scope="workspace") and
# ``mem_user_tenant_memory`` (scope="user") into the unified
# ``mem_memory_entry`` table, PRESERVING the original ``id`` so foreign keys
# (notably the self-referential ``superseded_by``) and any externally stored
# entry ids keep pointing at the same logical fact.
#
# Two details that are load-bearing:
#
# 1. RLS. 0004 enabled ENABLE + FORCE ROW LEVEL SECURITY on
#    ``mem_memory_entry`` in the same migration that created it (Global
#    Constraint). A migration runs as the table OWNER, and FORCE makes the
#    policy apply to the owner too -- with no ``app.current_tenant`` armed
#    (there is none during a migration), every INSERT would fail its WITH
#    CHECK and every SELECT would be filtered to zero rows. Both directions
#    therefore temporarily drop FORCE, do the copy, and restore FORCE again
#    (``NO FORCE`` only affects the owner; the least-privilege application
#    role keeps its policy throughout, and FORCE is restored before the
#    migration commits).
#
# 2. Supersession ordering.  A single INSERT ... SELECT can emit a row that
#    references another row of the same statement before that row exists, and
#    Postgres checks the FK per row. The copy is therefore split into an
#    INSERT with ``superseded_by_id = NULL`` followed by an UPDATE that fills
#    the link in once every row is present.
#
# 3. Deferred FK triggers vs. ALTER TABLE.  Django creates every FK as
#    ``DEFERRABLE INITIALLY DEFERRED``, so the INSERT/UPDATE above leave
#    "pending trigger events" on the target table until COMMIT. Postgres then
#    refuses a following ``ALTER TABLE ... FORCE ROW LEVEL SECURITY`` with
#    "cannot ALTER TABLE ... because it has pending trigger events" (only
#    reachable once there is real data -- an empty migration never hits it).
#    ``SET CONSTRAINTS ALL IMMEDIATE`` flushes those deferred checks before the
#    ALTER, which also turns any latent FK violation into an immediate, loud
#    failure instead of a silent partial copy.
#
# Idempotent by construction (``ON CONFLICT (id) DO NOTHING``) and a no-op on
# an empty legacy table (e.g. a freshly created test database).
from __future__ import annotations

from django.db import migrations


_NO_FORCE = "ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;"
_FORCE = "ALTER TABLE {table} FORCE ROW LEVEL SECURITY;"

#: Flushes deferred (Django-default ``DEFERRABLE INITIALLY DEFERRED``) FK
#: checks so a following ALTER TABLE is not blocked by pending trigger events.
_FLUSH_DEFERRED_CONSTRAINTS = "SET CONSTRAINTS ALL IMMEDIATE;"

# Column list shared by every INSERT into mem_memory_entry, in the exact order
# the SELECTs below emit values.
_ENTRY_COLUMNS = (
    "id, created_at, modified_at, version, scope, content, embedding, language, "
    "confidence, contributor_user_id, source_event_id, source_session_id, "
    "entity_type, backend_ref, created_by_id, modified_by_id, tenant_id, "
    "workspace_id, user_id, artifact_id, superseded_by_id"
)

_FORWARD_WORKSPACE_INSERT = f"""
INSERT INTO mem_memory_entry ({_ENTRY_COLUMNS})
SELECT id, created_at, modified_at, version, 'workspace', content, embedding, '',
       confidence, NULL, source_event_id, NULL, '', NULL,
       created_by_id, modified_by_id, tenant_id, workspace_id, NULL, NULL, NULL
FROM mem_workspace_memory
ON CONFLICT (id) DO NOTHING;
"""

_FORWARD_WORKSPACE_SUPERSEDE = """
UPDATE mem_memory_entry AS e
SET superseded_by_id = m.superseded_by_id
FROM mem_workspace_memory AS m
WHERE e.id = m.id AND e.scope = 'workspace' AND m.superseded_by_id IS NOT NULL;
"""

_FORWARD_USER_INSERT = f"""
INSERT INTO mem_memory_entry ({_ENTRY_COLUMNS})
SELECT id, created_at, modified_at, version, 'user', content, embedding, '',
       confidence, NULL, source_event_id, NULL, '', NULL,
       created_by_id, modified_by_id, tenant_id, NULL, user_id, NULL, NULL
FROM mem_user_tenant_memory
ON CONFLICT (id) DO NOTHING;
"""

_FORWARD_USER_SUPERSEDE = """
UPDATE mem_memory_entry AS e
SET superseded_by_id = m.superseded_by_id
FROM mem_user_tenant_memory AS m
WHERE e.id = m.id AND e.scope = 'user' AND m.superseded_by_id IS NOT NULL;
"""

_REVERSE_WORKSPACE_INSERT = """
INSERT INTO mem_workspace_memory (
    id, created_at, modified_at, version, content, embedding, source_event_id,
    confidence, created_by_id, modified_by_id, tenant_id, workspace_id,
    superseded_by_id
)
SELECT id, created_at, modified_at, version, content, embedding, source_event_id,
       confidence, created_by_id, modified_by_id, tenant_id, workspace_id, NULL
FROM mem_memory_entry
WHERE scope = 'workspace'
ON CONFLICT (id) DO NOTHING;
"""

_REVERSE_WORKSPACE_SUPERSEDE = """
UPDATE mem_workspace_memory AS m
SET superseded_by_id = e.superseded_by_id
FROM mem_memory_entry AS e
WHERE m.id = e.id AND e.scope = 'workspace' AND e.superseded_by_id IS NOT NULL;
"""

_REVERSE_USER_INSERT = """
INSERT INTO mem_user_tenant_memory (
    id, created_at, modified_at, version, content, embedding, source_event_id,
    confidence, created_by_id, modified_by_id, tenant_id, user_id,
    superseded_by_id
)
SELECT id, created_at, modified_at, version, content, embedding, source_event_id,
       confidence, created_by_id, modified_by_id, tenant_id, user_id, NULL
FROM mem_memory_entry
WHERE scope = 'user'
ON CONFLICT (id) DO NOTHING;
"""

_REVERSE_USER_SUPERSEDE = """
UPDATE mem_user_tenant_memory AS m
SET superseded_by_id = e.superseded_by_id
FROM mem_memory_entry AS e
WHERE m.id = e.id AND e.scope = 'user' AND e.superseded_by_id IS NOT NULL;
"""


def _run_statements(schema_editor, statements: list[str]) -> None:
    with schema_editor.connection.cursor() as cursor:
        for statement in statements:
            cursor.execute(statement)


def copy_legacy_into_memory_entry(apps, schema_editor) -> None:
    """Forward: legacy tables -> ``mem_memory_entry``."""
    _run_statements(
        schema_editor,
        [
            _NO_FORCE.format(table="mem_memory_entry"),
            _FORWARD_WORKSPACE_INSERT,
            _FORWARD_WORKSPACE_SUPERSEDE,
            _FORWARD_USER_INSERT,
            _FORWARD_USER_SUPERSEDE,
            _FLUSH_DEFERRED_CONSTRAINTS,
            _FORCE.format(table="mem_memory_entry"),
        ],
    )


def copy_memory_entry_into_legacy(apps, schema_editor) -> None:
    """Reverse: ``mem_memory_entry`` -> the legacy tables.

    The legacy tables are recreated by reversing 0006 immediately before this
    runs, and those recreated tables carry no RLS policy (see 0006's module
    docstring) -- so no ALTER is needed on them here, and touching them again
    AFTER the insert would trip the same pending-trigger-events rule described
    in the module docstring.
    """
    _run_statements(
        schema_editor,
        [
            _NO_FORCE.format(table="mem_memory_entry"),
            _REVERSE_WORKSPACE_INSERT,
            _REVERSE_WORKSPACE_SUPERSEDE,
            _REVERSE_USER_INSERT,
            _REVERSE_USER_SUPERSEDE,
            _FLUSH_DEFERRED_CONSTRAINTS,
            _FORCE.format(table="mem_memory_entry"),
        ],
    )


class Migration(migrations.Migration):

    dependencies = [
        ("memory", "0004_memory_entry"),
    ]

    operations = [
        migrations.RunPython(
            copy_legacy_into_memory_entry,
            reverse_code=copy_memory_entry_into_legacy,
        ),
    ]

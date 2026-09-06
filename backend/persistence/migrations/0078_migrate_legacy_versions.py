"""Copy DiagramVersion/IcdVersion/GlossaryTermVersion into ArtifactVersion.

Datenmodell-Konsolidierung Phase 5, spec section 6.2 ("ohne Historienverlust").
Runs before the three tables are dropped. Every source row must land in the
target or the migration fails — a partial copy would silently delete the only
content history in the system (see finding V-5).

Three guarantees, each enforced by a ``RuntimeError`` rather than a log line:

1. **Full visibility.** All three source tables and their owner tables carry
   ``FORCE ROW LEVEL SECURITY`` (``diagram/0008``, ``icd/0007``,
   ``persistence/0067``), and so does the target (``persistence/0077``, with a
   ``WITH CHECK`` clause). ``SET LOCAL row_security = off`` makes a blinded
   connection raise instead of reading an empty table and reporting a copy of
   zero rows as success — the same guard ``persistence/0073`` and
   ``persistence/0074`` already establish for this plan.
2. **No unbacked row is dropped.** A legacy row whose owning entity has no
   backing Artifact has nowhere to go; those are counted and the migration
   refuses to continue.
3. **No row is silently overwritten.** Task 27 already mirrors every *new*
   Diagram/Icd/GlossaryTerm write into ``ArtifactVersion``, so a database that
   served traffic on the new code before migrating can already hold a row at
   the same ``(artifact, revision)`` coordinate. An identical mirror row is
   accepted as already-migrated; a *differing* one is a numbering collision
   (most likely a GlossaryTerm whose ``term_version`` counter and whose
   ``ArtifactVersion.revision`` counter started from different bases) and
   fails the migration rather than losing one of the two payloads.
"""
from django.db import migrations


def _diagram_payload(row):
    """Return the ``ArtifactVersion`` payload for one ``DiagramVersion``.

    Mirrors ``diagram.manager._record_artifact_revision`` field for field, so a
    migrated revision and a natively recorded one are indistinguishable. The
    key set is ``artifact_diff_service._ENTITY_FIELDS["Diagram"]``.
    """
    return {
        "payload_format": row.payload_format,
        "payload": row.payload,
        "canvas_json": row.canvas_json,
    }


def _icd_payload(row):
    """Return the ``ArtifactVersion`` payload for one ``IcdVersion``.

    Mirrors ``icd.icd_manager._record_artifact_revision``. ``name`` lives on the
    ``Icd`` header, not on the version row, so it is read through the owner —
    the version row has no ``name`` attribute at all.
    """
    return {
        "name": row.icd.name,
        "direction": row.direction,
        "interface_type": row.interface_type,
        "semantic_description": row.semantic_description,
        "preconditions": list(row.preconditions or []),
        "postconditions": list(row.postconditions or []),
        "invariants": list(row.invariants or []),
    }


def _glossary_payload(row):
    """Return the ``ArtifactVersion`` payload for one ``GlossaryTermVersion``.

    The key set is ``_ENTITY_FIELDS["GlossaryTerm"]``. ``term`` is immutable
    identity on the owner (``pl_glossary_term.term``), not snapshotted per
    version, so it is read through the owner.
    """
    return {
        "term": row.term_fk.term,
        "definition": row.definition,
        "synonyms": list(row.synonyms or []),
        "abbreviation": row.abbreviation,
    }


#: (app_label, version_model, owner_attr, revision_attr, payload_builder)
SOURCES = [
    ("diagram", "DiagramVersion", "diagram", "version_number", _diagram_payload),
    ("icd", "IcdVersion", "icd", "version_number", _icd_payload),
    (
        "persistence",
        "GlossaryTermVersion",
        "term_fk",
        "term_version",
        _glossary_payload,
    ),
]


def _require_full_row_visibility(schema_editor):
    """Fail loudly instead of silently migrating nothing under RLS.

    See the module docstring, guarantee 1. Identical to the guard in
    ``persistence/0073_backfill_artifact_backing`` — kept as a local copy
    because a migration must not import from another migration module.
    """
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("SET LOCAL row_security = off")


def migrate_history(apps_registry, schema_editor):
    """Copy every legacy version row into ``ArtifactVersion``.

    Args:
        apps_registry: Historical model registry supplied by ``RunPython``.
        schema_editor: Schema editor for the connection being migrated.

    Raises:
        RuntimeError: if any source row cannot be migrated (unbacked owner or
            a conflicting row already at the same ``(artifact, revision)``), or
            if the source and target counts disagree afterwards.
    """
    _require_full_row_visibility(schema_editor)

    ArtifactVersion = apps_registry.get_model("persistence", "ArtifactVersion")

    # Coordinates Task 27's write path already mirrored, so a re-run (or a
    # database that served traffic on the new code before migrating) is not
    # writing into empty space. Only the keys are held — the payload behind a
    # hit is fetched on demand, so this stays O(rows) small pointers rather
    # than the whole table's JSON.
    existing = set(
        ArtifactVersion.objects.values_list("artifact_id", "revision").iterator()
    )

    copied = 0
    already_present = 0
    unbacked = 0
    source_total = 0
    conflicts = []

    for app_label, model_name, owner_attr, revision_attr, build in SOURCES:
        model = apps_registry.get_model(app_label, model_name)
        for row in model.objects.select_related(owner_attr).iterator():
            source_total += 1
            owner = getattr(row, owner_attr)
            if owner is None or owner.artifact_id is None:
                unbacked += 1
                continue

            revision = getattr(row, revision_attr)
            payload = build(row)
            key = (owner.artifact_id, revision)
            if key in existing:
                stored = (
                    ArtifactVersion.objects.filter(
                        artifact_id=owner.artifact_id, revision=revision
                    )
                    .values_list("payload", flat=True)
                    .first()
                )
                if stored == payload:
                    already_present += 1
                else:
                    conflicts.append(f"{model_name} {row.pk} -> {key}")
                continue

            created = ArtifactVersion.objects.create(
                tenant_id=row.tenant_id,
                artifact_id=owner.artifact_id,
                revision=revision,
                payload=payload,
                change_reason="",
                created_by_id=row.created_by_id,
            )
            # ``created_at``/``modified_at`` are auto_now_add/auto_now, so they
            # cannot be set on create. Without this the whole migrated history
            # collapses onto the migration's own timestamp and every revision
            # list renders as "all changed at once".
            ArtifactVersion.objects.filter(pk=created.pk).update(
                created_at=row.created_at, modified_at=row.modified_at
            )
            existing.add(key)
            copied += 1

    if unbacked:
        raise RuntimeError(
            f"{unbacked} of {source_total} legacy version rows belong to an "
            "entity without a backing Artifact and cannot be migrated. Run "
            "`manage.py check_artifact_backing`, give those entities a "
            "workspace, re-run persistence/0073, then retry."
        )
    if conflicts:
        raise RuntimeError(
            f"{len(conflicts)} legacy version rows collide with a differing "
            "ArtifactVersion row at the same (artifact, revision): "
            f"{', '.join(conflicts[:10])}. Refusing to continue — one of the "
            "two payloads would be lost. Renumber the affected history before "
            "retrying; never drop the conflicting rows."
        )
    if copied + already_present != source_total:
        raise RuntimeError(
            f"copied {copied} and matched {already_present} of {source_total} "
            "legacy version rows; refusing to continue with an incomplete "
            "history."
        )


class Migration(migrations.Migration):
    # Atomic (the default) is load-bearing twice over: ``SET LOCAL`` is scoped
    # to this migration's transaction, and a RuntimeError rolls the whole copy
    # back rather than leaving half a history behind.
    atomic = True

    dependencies = [
        ("persistence", "0077_artifact_version_rls"),
        # The two source apps' leaves at the time of writing. Both are needed
        # so the historical registry can render DiagramVersion/IcdVersion *and*
        # the owner's ``artifact`` FK (diagram/0007, icd/0009) this copy joins
        # through.
        ("diagram", "0008_diagram_rls_policies"),
        ("icd", "0009_icd_artifact_fk"),
    ]

    operations = [
        # Irreversible on purpose: a migrated ArtifactVersion row is
        # indistinguishable from one Task 27's write path recorded natively, so
        # a reverse that deleted rows would destroy live history.
        migrations.RunPython(migrate_history, migrations.RunPython.noop),
    ]

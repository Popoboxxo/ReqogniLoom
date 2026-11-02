# Plan F F3-T7 (#1374): the text-anchor register for inline references.
#
# `InlineAnchor` records the "Fundort" of an inline reference token: the
# source Artifact + markdown field that carries `[[glossary:<uuid>@<rev>]]`,
# the target Artifact and the TraceLink the token implies. The token text is
# stored verbatim (ENT-F3 = a: the display form `[[Begriff]]` is editor-only),
# and the stable identity lives in this table, never in the free text.
#
# The tenant RLS policy ships in the very next migration
# (`0128_inline_anchor_rls_policy`) in the same release (KA-F-13).
import django.db.models.deletion
import django.db.models.manager
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0126_work_item_rls_policy"),
    ]

    operations = [
        migrations.CreateModel(
            name="InlineAnchor",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("modified_at", models.DateTimeField(auto_now=True)),
                ("version", models.IntegerField(default=1)),
                (
                    "field",
                    models.CharField(
                        help_text=(
                            "Markdown field of the source artifact, e.g. 'body' "
                            "or 'description'."
                        ),
                        max_length=64,
                    ),
                ),
                (
                    "token",
                    models.CharField(
                        help_text=(
                            "The stored token text, e.g. "
                            "'[[glossary:<uuid>@<rev>]]'. The display form "
                            "'[[Begriff]]' is editor-only and never stored."
                        ),
                        max_length=512,
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "link",
                    models.ForeignKey(
                        help_text=(
                            "Trace edge implied by the anchor (I-1). Removing the "
                            "edge removes its anchors (I-3)."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inline_anchors",
                        to="persistence.tracelink",
                    ),
                ),
                (
                    "modified_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "source_artifact",
                    models.ForeignKey(
                        help_text=(
                            "Artifact owning the markdown field that carries the "
                            "token."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inline_anchors",
                        to="persistence.artifact",
                    ),
                ),
                (
                    "target_artifact",
                    models.ForeignKey(
                        help_text=(
                            "Referenced artifact. A soft delete keeps this row so "
                            "DOC-P7 can report the anchor as a dead reference (I-5)."
                        ),
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incoming_inline_anchors",
                        to="persistence.artifact",
                    ),
                ),
                (
                    "tenant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_set",
                        to="persistence.tenant",
                    ),
                ),
            ],
            options={
                "db_table": "pl_inline_anchor",
                "indexes": [
                    models.Index(
                        fields=["tenant", "source_artifact", "field"],
                        name="idx_inline_anchor_source_field",
                    ),
                    models.Index(
                        fields=["tenant", "target_artifact"],
                        name="idx_inline_anchor_target",
                    ),
                    models.Index(
                        fields=["tenant", "link"],
                        name="idx_inline_anchor_link",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("source_artifact", "field", "token"),
                        name="uq_inline_anchor_source_field_token",
                    )
                ],
            },
            managers=[
                ("objects", django.db.models.manager.Manager()),
                ("unscoped", django.db.models.manager.Manager()),
            ],
        ),
    ]

"""Phase G / #1374 S3: dual-source and projection fields on ``Document``.

Additive with behaviour-preserving defaults: every existing document stays
loom-owned and is not projected (``owner_mode='loom'``, ``projection_mode='none'``).
No backfill is needed.
"""
from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("persistence", "0145_qualityassessment_auto_triggers"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="owner_mode",
            field=models.CharField(
                choices=[("loom", "Loom"), ("repo_external", "Repository (external)")],
                default="loom",
                help_text="Who owns the content: this server or an external repository file.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="source_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Repository path a repo_external document was imported from.",
                max_length=512,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="source_sha256",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SHA-256 of the repository file at adoption time.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="projection_mode",
            field=models.CharField(
                choices=[("none", "None"), ("generated", "Generated")],
                default="none",
                help_text="Whether this document is rendered to Markdown for a repository.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="projected_sha256",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SHA-256 a client last confirmed it wrote for this projection.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="projected_version",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="Document.version the last confirmed projection was rendered from.",
                null=True,
            ),
        ),
    ]

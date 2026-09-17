"""AttributeDefinition app — Layer 1, analogous to ``backend/workflow/``."""
from __future__ import annotations

from django.apps import AppConfig


class AttributeDefinitionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "attribute_definitions"
    verbose_name = "Attribute Definitions"

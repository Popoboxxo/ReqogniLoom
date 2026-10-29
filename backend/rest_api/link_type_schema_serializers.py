"""OpenAPI shapes for the link-type-catalog REST surface (#1388).

:mod:`rest_api.link_type_views` is a thin adapter over
``application.link_type_facade.LinkTypeFacade``; it returns the facade's dicts
unchanged and resolves nothing itself. These serializers describe those dicts
for the generated contract only.

The ``definition`` member is not a free-form document: ``link_types.schema``
validates it on every write path against a closed key set
(``label``/``allowed_pairs``/``suspect_rule``/``impact_weight`` plus the five
optional flags), so the whole block is transcribed here. ``suspect_rule`` is
the one closed value range (``link_types.builtin.SUSPECT_RULES``) — the
propagation engine branches on it, which is why an unknown value is a 400.
"""
from __future__ import annotations

from rest_framework import serializers

__all__ = [
    "GlobalLinkTypePageSerializer",
    "GlobalLinkTypeSerializer",
    "LinkTypeDefinitionSerializer",
    "LinkTypeLabelSerializer",
    "LinkTypePairSerializer",
    "LinkTypeWriteRequestSerializer",
    "WorkspaceLinkTypePageSerializer",
    "WorkspaceLinkTypeSerializer",
]

#: ``link_types.builtin.SUSPECT_RULES``.
_SUSPECT_RULES = [
    "none",
    "target_change_flags_source",
    "source_change_flags_target",
    "parent_change_flags_children",
]
_LANGUAGES = ["de", "en"]
_PERSPECTIVES = ["downstream", "upstream", "neutral"]


class LinkTypeLabelSerializer(serializers.Serializer):
    """The tri-label display block: ``{de,en} x {downstream,upstream,neutral}``.

    The tri-label shape (not a flat ``{de, en}`` pair) is what the frontend's
    single display source, ``constants/traceLinkLabels.ts``, consumes.
    """

    de = serializers.DictField(
        child=serializers.CharField(),
        help_text=f"Keys: {'/'.join(_PERSPECTIVES)}.",
    )
    en = serializers.DictField(
        child=serializers.CharField(),
        help_text=f"Keys: {'/'.join(_PERSPECTIVES)}.",
    )


class LinkTypePairSerializer(serializers.Serializer):
    """One allowed ``(source_type, target_type)`` pair; ``"*"`` is a wildcard."""

    source_type = serializers.CharField()
    target_type = serializers.CharField()


class LinkTypeDefinitionSerializer(serializers.Serializer):
    """A validated ``definition_json`` (``link_types.schema``)."""

    label = LinkTypeLabelSerializer()
    allowed_pairs = LinkTypePairSerializer(
        many=True,
        help_text="An empty list is legal: the type currently links nothing.",
    )
    suspect_rule = serializers.ChoiceField(
        choices=_SUSPECT_RULES,
        help_text="Suspect-propagation behaviour; the engine branches on it.",
    )
    impact_weight = serializers.FloatField()
    coverage_relevant = serializers.BooleanField(required=False)
    manual_creatable = serializers.BooleanField(required=False)
    system_owned = serializers.BooleanField(required=False)
    active = serializers.BooleanField(required=False)
    built_in = serializers.BooleanField(required=False)


class GlobalLinkTypeSerializer(serializers.Serializer):
    """``LinkTypeFacade._global_to_dict`` — one tenant-wide template."""

    id = serializers.CharField()
    key = serializers.CharField()
    definition = LinkTypeDefinitionSerializer()
    version = serializers.IntegerField()
    propagated_to = serializers.IntegerField(
        required=False,
        help_text="Present on an update that propagated to on-default "
        "workspaces.",
    )


class WorkspaceLinkTypeSerializer(serializers.Serializer):
    """``LinkTypeFacade._workspace_to_dict`` — one workspace's catalog row."""

    id = serializers.CharField()
    workspace_id = serializers.CharField()
    key = serializers.CharField()
    definition = LinkTypeDefinitionSerializer()
    is_customized = serializers.BooleanField()
    source_global_id = serializers.CharField(required=False, allow_null=True)
    version = serializers.IntegerField()


class LinkTypeWriteRequestSerializer(serializers.Serializer):
    """Body of the create/update routes: the key plus its definition.

    ``POST /link-type-defaults/`` requires ``key``; the PUT routes take the key
    from the URL, so they accept the same body with ``key`` omitted.
    """

    key = serializers.CharField(required=False)
    definition = LinkTypeDefinitionSerializer()


class GlobalLinkTypePageSerializer(serializers.Serializer):
    """``StandardPagination`` envelope of ``GET /link-type-defaults/``.

    ``next``/``previous`` are absolute URLs (null on the last/first page);
    ``page_size``/``max_page_size`` echo the applied slice size and the
    endpoint's ceiling (#571).
    """

    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    results = GlobalLinkTypeSerializer(many=True)


class WorkspaceLinkTypePageSerializer(serializers.Serializer):
    """``StandardPagination`` envelope of the workspace catalog route."""

    count = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    page_size = serializers.IntegerField()
    max_page_size = serializers.IntegerField()
    results = WorkspaceLinkTypeSerializer(many=True)

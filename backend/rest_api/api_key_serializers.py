"""
COMP-RA-001 — API-key request/response serializers (REQ-L3-AT001-003).

``ApiKeyViewSet`` predates the serializer family: it read ``request.data`` by
hand, which is why drf-spectacular could not guess a request body and logged
``Error [ApiKeyViewSet]: unable to guess serializer`` (#1439). Worse, the hand
written validation short-circuited on the first problem, so a caller had to
round-trip once per missing field:

    POST {"principal_type": "agent"}  ->  400 Field 'name' is required.
    POST {"principal_type": "agent", "name": "x"}
                                      ->  400 Field 'scope' must be ...
    ... etc.

This module is the single validation seam for ``POST /api/v1/api-keys/``. It
collects every per-field error DRF can find, adds the agent-key cross-field
rules (:func:`~auth_tenancy.services.authentication.canonical_workspace_ids`
and friends — imported, never re-implemented), and — crucially — keeps running
the cross-field rules even when a per-field error already exists, so one
response names every problem.

Backward compatibility (the contract pinned by the #865/#916/#917 tests):

* exactly **one** problem -> the response message is byte-identical to the
  pre-serializer message for that case;
* two or more problems -> one ``400`` with ``message``
  ``"Request validation failed."`` and one ``details`` entry per problem, in
  declaration order (``FIELD_ORDER``; unknown keys first, alphabetically);
* a lone unknown field keeps its historical ``Unknown field '<key>'.`` body
  (including the bare ``{"field", "errors"}`` detail shape).

Every *other* detail entry is an additive superset of the project-wide
``{"field", "errors"}`` shape: it carries ``field``, ``code``, ``message`` and
``errors`` (a list holding the same single message). Generic clients read
``error.details[i].errors[0]`` (``frontend/src/api/client.ts``) and skip entries
without an ``errors`` list (``ArtifactForm/field-errors.ts``), so dropping
``errors`` would degrade every multi-problem response to the generic
"Request validation failed." text in the UI. Both published variants are
declared in :class:`ApiKeyValidationErrorSerializer`.

The one-vs-many decision lives in exactly one place:
:func:`build_api_key_create_error_response`.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from django.utils.dateparse import parse_datetime
from drf_spectacular.extensions import OpenApiSerializerExtension
from drf_spectacular.utils import PolymorphicProxySerializer, extend_schema_field
from rest_framework import serializers
from rest_framework.fields import empty

from auth_tenancy.models import (
    API_KEY_SCOPE_CHOICES,
    PRINCIPAL_TYPE_AGENT,
    PRINCIPAL_TYPE_USER,
    normalize_api_key_scope,
)
from auth_tenancy.services.authentication import (
    AGENT_EXPIRY_REQUIRED_MESSAGE,
    AGENT_SCOPE_REQUIRED_MESSAGE,
    AGENT_WORKSPACE_FENCE_REQUIRED_MESSAGE,
    canonical_workspace_ids,
    is_future_timezone_aware,
)
from rest_api.serializers import build_error_response

# ---------------------------------------------------------------------------
# Per-field messages — the pre-#1439 wording, kept verbatim for the
# single-problem case (the existing tests pin them).
# ---------------------------------------------------------------------------

NAME_REQUIRED_MESSAGE = "Field 'name' is required."
PRINCIPAL_TYPE_INVALID_MESSAGE = "Field 'principal_type' must be 'user' or 'agent'."
SCOPE_INVALID_MESSAGE = (
    "Field 'scope' must be one of 'read_only', 'author', 'admin' "
    "(or the legacy aliases 'read', 'write')."
)
WORKSPACE_IDS_INVALID_MESSAGE = "Field 'workspace_ids' must be a list of UUID strings."
EXPIRES_AT_INVALID_MESSAGE = "Field 'expires_at' must be an ISO-8601 datetime."

#: Message used when two or more problems are reported at once.
MULTI_FIELD_MESSAGE = "Request validation failed."

#: Machine-readable reason of one ``details`` entry. Published as an enum
#: (``ApiKeyValidationErrorDetailSerializer.code``) so the contract is not just
#: prose in a ``help_text`` (#1439 review, F11).
API_KEY_ERROR_CODES: tuple[str, ...] = ("required", "invalid", "unknown_field")

#: Deterministic detail order for a multi-problem response. Unknown keys are
#: rendered before these (and sorted among themselves).
FIELD_ORDER: tuple[str, ...] = (
    "name",
    "principal_type",
    "scope",
    "workspace_ids",
    "expires_at",
    "agent_label",
)


# ---------------------------------------------------------------------------
# Fields
# ---------------------------------------------------------------------------


def _parse_iso8601(value: Any) -> datetime | None:
    """Parse *value* as ISO-8601 without coercing a naive value to aware.

    ``django.utils.dateparse.parse_datetime`` is deliberately used instead of
    DRF's ``DateTimeField`` coercion: a naive ``expires_at`` must stay naive so
    the agent-key rule can reject it (``test_api_key_agent_fields`` pins that).
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    raw = str(value)
    if not raw.strip():
        return None
    return parse_datetime(raw)


class Iso8601DateTimeField(serializers.DateTimeField):
    """ISO-8601 datetime that preserves naive values (see ``_parse_iso8601``)."""

    default_error_messages = {
        **serializers.DateTimeField.default_error_messages,
        "invalid": EXPIRES_AT_INVALID_MESSAGE,
    }

    def to_internal_value(self, value: Any) -> datetime | None:
        # The pre-serializer view guarded with ``if raw_expires_at:``, so an
        # empty string meant "not supplied" rather than "malformed" (#1439
        # review, F10). This field is nullable by definition, so map it to
        # ``None`` — a whitespace-only value stays an error, exactly as before.
        if value == "":
            return None
        parsed = _parse_iso8601(value)
        if parsed is None:
            self.fail("invalid")
        return parsed


class ApiKeyScopeField(serializers.ChoiceField):
    """Choice field that normalises case/whitespace before choosing (#865).

    ``normalize_api_key_scope`` has always been case- and whitespace-tolerant;
    a plain ``ChoiceField`` would reject ``" READ "`` that the endpoint used to
    accept.
    """

    def to_internal_value(self, data: Any) -> Any:
        if isinstance(data, str):
            data = data.strip().lower()
        return super().to_internal_value(data)


class CoercedTextField(serializers.CharField):
    """Text field that stringifies like the old ``str(value or "")`` did."""

    def to_internal_value(self, data: Any) -> str:
        if data is None or data == "":
            return ""
        return str(data)


class StrictNameField(serializers.CharField):
    """``CharField`` that refuses non-string input instead of coercing it.

    DRF's ``CharField`` stringifies ``int``/``float`` input, so a check inside
    ``validate_name`` cannot see ``{"name": 123}`` — it already arrives as
    ``"123"``. The pre-serializer view required a real ``str`` (``isinstance``
    check) and answered 400 for anything else; restoring that needs the check
    before coercion (#1439 review, F10).
    """

    def to_internal_value(self, data: Any) -> str:
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


# ---------------------------------------------------------------------------
# Request serializer
# ---------------------------------------------------------------------------


class ApiKeyCreateSerializer(serializers.Serializer):
    """Request body of ``POST /api/v1/api-keys/`` (#1439).

    Validation is cumulative: :meth:`run_validation` keeps DRF's per-field
    errors *and* appends the agent-key cross-field rules, instead of raising on
    the first problem. The resolved details are exposed through
    :meth:`error_response_body`, which the view emits as the single error
    envelope.
    """

    name = StrictNameField(
        required=True,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=False,
        error_messages={
            "required": NAME_REQUIRED_MESSAGE,
            "null": NAME_REQUIRED_MESSAGE,
            "invalid": NAME_REQUIRED_MESSAGE,
        },
        help_text="Human-readable label for the key.",
    )
    principal_type = serializers.ChoiceField(
        choices=(PRINCIPAL_TYPE_USER, PRINCIPAL_TYPE_AGENT),
        required=False,
        default=PRINCIPAL_TYPE_USER,
        error_messages={
            "invalid_choice": PRINCIPAL_TYPE_INVALID_MESSAGE,
            "null": PRINCIPAL_TYPE_INVALID_MESSAGE,
            "invalid": PRINCIPAL_TYPE_INVALID_MESSAGE,
        },
        help_text="'user' (default) or 'agent'.",
    )
    scope = ApiKeyScopeField(
        choices=API_KEY_SCOPE_CHOICES,
        required=False,
        allow_null=True,
        error_messages={"invalid_choice": SCOPE_INVALID_MESSAGE},
        help_text=(
            "Capability tier: read_only, author or admin (legacy aliases "
            "read/write). Required for agent keys; omitted means write for "
            "user keys."
        ),
    )
    workspace_ids = serializers.ListField(
        child=serializers.UUIDField(
            error_messages={"invalid": WORKSPACE_IDS_INVALID_MESSAGE}
        ),
        required=False,
        allow_null=True,
        error_messages={"not_a_list": WORKSPACE_IDS_INVALID_MESSAGE},
        help_text="Agent keys require at least one workspace UUID (the fence).",
    )
    expires_at = Iso8601DateTimeField(
        required=False,
        allow_null=True,
        help_text="Agent keys require a strictly future timezone-aware value.",
    )
    agent_label = CoercedTextField(
        required=False,
        allow_blank=True,
        allow_null=True,
        trim_whitespace=False,
        help_text="Display label of the agent principal (truncated to 255).",
    )

    # -- per-field validation ---------------------------------------------

    def validate_name(self, value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise serializers.ValidationError(NAME_REQUIRED_MESSAGE)
        return value.strip()

    def validate_scope(self, value: Any) -> str | None:
        # Called only when the key is present (an absent optional field raises
        # ``SkipField`` before ``validate_<field>``). An explicit ``null`` is
        # therefore an invalid scope, exactly as before (#865).
        normalized = normalize_api_key_scope(value)
        if normalized is None:
            raise serializers.ValidationError(SCOPE_INVALID_MESSAGE)
        return normalized

    def validate_workspace_ids(self, value: Any) -> list[str]:
        if value is None:
            return []
        return [str(uuid_value) for uuid_value in value]

    def validate_agent_label(self, value: Any) -> str:
        return str(value or "")[:255]

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Fill the optional defaults the old hand-rolled view applied."""
        attrs.setdefault("scope", None)
        attrs.setdefault("workspace_ids", [])
        attrs.setdefault("expires_at", None)
        attrs.setdefault("agent_label", "")
        attrs.setdefault("principal_type", PRINCIPAL_TYPE_USER)
        return attrs

    # -- cumulative validation --------------------------------------------

    def run_validation(self, data: Any = empty) -> dict[str, Any]:
        """Collect every field problem, then raise once (#1439)."""
        raw: Any = {} if data is empty else data
        unknown = self._unknown_fields(raw)

        field_errors: dict[str, Any] = {}
        attrs: dict[str, Any] = {}
        try:
            attrs = super().to_internal_value(raw)
        except serializers.ValidationError as exc:
            detail = exc.detail
            field_errors = (
                dict(detail) if isinstance(detail, Mapping) else {"non_field_errors": detail}
            )

        self._error_details = self._collect_error_details(raw, unknown, field_errors)
        if self._error_details:
            raise serializers.ValidationError(
                {
                    detail["field"]: [detail["message"]]
                    for detail in self._error_details
                }
            )
        return self.validate(attrs)

    def _unknown_fields(self, raw: Any) -> list[str]:
        if not isinstance(raw, Mapping):
            return []
        return sorted(set(raw) - set(self.fields))

    def _collect_error_details(
        self,
        raw: Any,
        unknown: list[str],
        field_errors: dict[str, Any],
    ) -> list[dict[str, Any]]:
        details: dict[str, dict[str, Any]] = {}

        for field in unknown:
            details[field] = _validation_detail(
                field, "unknown_field", f"Unknown field '{field}'."
            )

        for field in field_errors:
            details.setdefault(field, _field_error_detail(field))

        # Cross-field rules also run when a per-field error exists — that is
        # the whole point of #1439. A field already reported at field level is
        # not reported twice.
        blocked = set(field_errors) | set(unknown)
        for field, detail in self._cross_field_errors(raw, blocked).items():
            details.setdefault(field, detail)

        return [
            *[details[field] for field in sorted(details) if field not in FIELD_ORDER],
            *[details[field] for field in FIELD_ORDER if field in details],
        ]

    def _cross_field_errors(
        self, raw: Any, blocked: set[str]
    ) -> dict[str, dict[str, Any]]:
        """Agent-key lifecycle rules, accumulated rather than raised (#1439)."""
        if not isinstance(raw, Mapping):
            return {}
        if raw.get("principal_type", PRINCIPAL_TYPE_USER) != PRINCIPAL_TYPE_AGENT:
            return {}

        errors: dict[str, dict[str, Any]] = {}

        if "scope" not in blocked and normalize_api_key_scope(raw.get("scope")) is None:
            errors["scope"] = _validation_detail(
                "scope", "required", AGENT_SCOPE_REQUIRED_MESSAGE
            )

        if (
            "workspace_ids" not in blocked
            and canonical_workspace_ids(raw.get("workspace_ids")) is None
        ):
            errors["workspace_ids"] = _validation_detail(
                "workspace_ids", "required", AGENT_WORKSPACE_FENCE_REQUIRED_MESSAGE
            )

        if "expires_at" not in blocked:
            raw_expiry = raw.get("expires_at")
            parsed = _parse_iso8601(raw_expiry)
            if parsed is None:
                errors["expires_at"] = _validation_detail(
                    "expires_at",
                    "required" if not raw_expiry else "invalid",
                    AGENT_EXPIRY_REQUIRED_MESSAGE,
                )
            elif not is_future_timezone_aware(parsed):
                errors["expires_at"] = _validation_detail(
                    "expires_at", "invalid", AGENT_EXPIRY_REQUIRED_MESSAGE
                )

        return errors

    def error_response_body(self) -> dict[str, Any]:
        """Return the single error envelope for the collected problems."""
        return build_api_key_create_error_response(
            getattr(self, "_error_details", [])
        )


def _validation_detail(field: str, code: str, message: str) -> dict[str, Any]:
    """One ``details`` entry: the additive superset of ``{field, errors}``.

    ``errors`` holds the same single message as ``message`` because the
    project-wide detail shape is ``{field, errors: [...]}`` and generic clients
    read exactly that (see the module docstring).
    """
    return {
        "field": field,
        "code": code,
        "message": message,
        "errors": [message],
    }


def _field_error_detail(field: str) -> dict[str, Any]:
    """Canonical detail entry for a declared field's failure."""
    if field == "name":
        return _validation_detail(field, "required", NAME_REQUIRED_MESSAGE)
    if field == "principal_type":
        return _validation_detail(field, "invalid", PRINCIPAL_TYPE_INVALID_MESSAGE)
    if field == "scope":
        return _validation_detail(field, "invalid", SCOPE_INVALID_MESSAGE)
    if field == "workspace_ids":
        return _validation_detail(field, "invalid", WORKSPACE_IDS_INVALID_MESSAGE)
    if field == "expires_at":
        return _validation_detail(field, "invalid", EXPIRES_AT_INVALID_MESSAGE)
    return _validation_detail(field, "invalid", "Invalid value.")


def build_api_key_create_error_response(details: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the one-error-vs-many-error contract (#1439).

    * one unknown field -> the historical ``Unknown field '<key>'.`` body,
      including its bare ``{"field", "errors"}`` detail entry;
    * one problem of any other kind -> that problem's historical message;
    * two or more -> ``"Request validation failed."`` plus every detail.

    Kept as a free function (not a view method) so the rule has exactly one
    implementation and can be unit-tested without HTTP.
    """
    if len(details) == 1 and details[0]["code"] == "unknown_field":
        field = details[0]["field"]
        # Read the already-built message instead of re-deriving it: the detail
        # carries exactly the historical wording (#1439 review, n2).
        message = details[0]["message"]
        return build_error_response(
            code="VALIDATION_ERROR",
            message=message,
            details=[{"field": field, "errors": [message]}],
        )
    if len(details) == 1:
        return build_error_response(
            code="VALIDATION_ERROR",
            message=details[0]["message"],
            details=details,
        )
    return build_error_response(
        code="VALIDATION_ERROR",
        message=MULTI_FIELD_MESSAGE,
        details=details,
    )


# ---------------------------------------------------------------------------
# Response serializers — the contract drf-spectacular publishes (#1439)
# ---------------------------------------------------------------------------


class ApiKeyCreateResponseSerializer(serializers.Serializer):
    """The 201 body: metadata plus the one-time plaintext."""

    id = serializers.UUIDField(help_text="Key UUID.")
    name = serializers.CharField(help_text="Stored key label.")
    plaintext = serializers.CharField(
        help_text="The key itself — returned exactly once, never again."
    )
    warning = serializers.CharField(help_text="Reminder to save the key now.")
    principal_type = serializers.ChoiceField(
        choices=(PRINCIPAL_TYPE_USER, PRINCIPAL_TYPE_AGENT)
    )
    agent_label = serializers.CharField(allow_blank=True)
    scope = serializers.ChoiceField(choices=API_KEY_SCOPE_CHOICES)


class ApiKeyMetadataSerializer(serializers.Serializer):
    """Metadata-only key representation used by ``GET /api/v1/api-keys/``.

    The plaintext is never part of this payload — it exists only in the 201
    body above (REQ-L3-AT001-003). Declaring it gives the list/retrieve routes
    a real response schema instead of drf-spectacular's
    ``unable to guess serializer`` fallback (#1439).
    """

    id = serializers.UUIDField()
    name = serializers.CharField()
    created_at = serializers.DateTimeField(allow_null=True)
    last_used_at = serializers.DateTimeField(allow_null=True)
    revoked = serializers.BooleanField()
    principal_type = serializers.ChoiceField(
        choices=(PRINCIPAL_TYPE_USER, PRINCIPAL_TYPE_AGENT)
    )
    agent_label = serializers.CharField(allow_blank=True)
    scope = serializers.CharField(allow_null=True)
    workspace_ids = serializers.ListField(child=serializers.UUIDField())
    expires_at = serializers.DateTimeField(allow_null=True)
    expired = serializers.BooleanField()


class ApiKeyValidationErrorDetailSerializer(serializers.Serializer):
    """One field problem inside a multi-problem 400 (#1439).

    Additive superset of the project-wide ``{"field", "errors"}`` detail shape:
    ``errors`` carries the same single message as ``message`` so generic
    clients that read ``details[i].errors[0]`` keep working.
    """

    field = serializers.CharField(help_text="The offending request field.")
    code = serializers.ChoiceField(
        choices=API_KEY_ERROR_CODES,
        help_text="'required', 'invalid' or 'unknown_field'.",
    )
    message = serializers.CharField(help_text="Human-readable reason.")
    errors = serializers.ListField(
        child=serializers.CharField(),
        help_text=(
            "The same single message as 'message', in the project-wide "
            "{field, errors} detail shape."
        ),
    )


class ApiKeyLegacyValidationErrorDetailSerializer(serializers.Serializer):
    """The historical ``{field, errors}`` entry emitted for a lone unknown field."""

    field = serializers.CharField(help_text="The offending request field.")
    errors = serializers.ListField(
        child=serializers.CharField(),
        help_text="One entry: \"Unknown field '<key>'.\"",
    )


class ApiKeyLegacyValidationErrorDetailExtension(OpenApiSerializerExtension):
    """Publish the legacy entry as a *closed* object.

    ``oneOf`` accepts a value matching exactly one branch, so the two detail
    variants must be disjoint. An open ``{field, errors}`` schema would also
    accept every additive ``{field, code, message, errors}`` entry (extra keys
    are allowed by default), making each real body match *both* branches and
    therefore fail its own published contract. The body of a lone unknown field
    is exactly ``{field, errors}`` (#1439 review, F1), so closing the schema is
    accurate rather than cosmetic.
    """

    target_class = ApiKeyLegacyValidationErrorDetailSerializer

    def map_serializer(self, auto_schema: Any, direction: Any) -> dict[str, Any]:
        schema = super().map_serializer(auto_schema, direction)
        schema["additionalProperties"] = False
        return schema


@extend_schema_field(
    PolymorphicProxySerializer(
        component_name="ApiKeyValidationErrorDetailItem",
        serializers=[
            ApiKeyValidationErrorDetailSerializer,
            ApiKeyLegacyValidationErrorDetailSerializer,
        ],
        resource_type_field_name=None,
    )
)
class ApiKeyValidationErrorDetailItemField(serializers.Field):
    """Documentation-only field: one ``details`` entry, either variant.

    The runtime body has two legitimate item shapes (#1439 review, F1): the
    additive ``{field, code, message, errors}`` entry for every ordinary
    problem, and the byte-identical historical ``{field, errors}`` entry for a
    lone unknown request field. The published schema has to accept both.
    """


class ApiKeyValidationErrorSerializer(serializers.Serializer):
    """Inner error object of a ``POST /api/v1/api-keys/`` 400.

    Structurally a superset of the canonical envelope body
    (:class:`rest_api.openapi.ErrorBodySerializer`: ``code``, ``message``,
    ``details``, ``request_id``); the runtime body of this route carries no
    ``request_id`` — ``build_error_response`` does not add one — so the
    property is optional and nullable, exactly like the canonical declaration.
    """

    code = serializers.CharField(help_text="Always 'VALIDATION_ERROR'.")
    message = serializers.CharField(
        help_text=(
            "Single problem: that problem's message. Two or more: "
            "'Request validation failed.'"
        )
    )
    details = serializers.ListField(
        child=ApiKeyValidationErrorDetailItemField(),
        help_text=(
            "One entry per problem, in declaration order (unknown request "
            "keys first, alphabetically)."
        ),
    )
    request_id = serializers.CharField(
        required=False,
        allow_null=True,
        help_text=(
            "Correlation id mirrored from the X-Request-ID header "
            "(ADR-014 §1); omitted by this route's error body."
        ),
    )


class ApiKeyErrorResponseSerializer(serializers.Serializer):
    """The project-wide error envelope for the API-key create route."""

    error = ApiKeyValidationErrorSerializer()

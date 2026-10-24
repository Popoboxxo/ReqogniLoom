"""Q1 preference-key registry — code, not a database catalogue (Plan C, T-C2-2).

A *preference key* is the contract between the UI/settings surfaces and the
three-level store in :class:`auth_tenancy.models.PreferenceValue`: it names the
value's type, its default, which levels may carry it, how the levels combine
(``override`` vs ``union``), an optional per-key validator and how the generic
settings section renders it.

Why a code registry: a key has a *type* and a *default*, so it cannot be added
at runtime without a code change anyway; keeping it out of the DB means no
migration per preference, no bootstrapping and no way for a tenant to invent a
key no consumer reads. Consumers import :func:`get_preference_key` /
:func:`resolve_for` instead of hard-coding level semantics.

Registration happens in the owning app's ``AppConfig.ready()`` (Q1 core keys in
``auth_tenancy/apps.py``, Plan A's memory keys in ``memory/apps.py``). Registering
the same key twice is a programming error — :class:`~django.core.exceptions.
ImproperlyConfigured` — because two definitions of one key make resolution
non-deterministic. An *unknown* key is caller input instead, and raises
:class:`persistence.errors.ValidationError` (the REST/MCP layers map that to
400).

This module is deliberately import-light (no models are queried) so
``AppConfig.ready()`` can import it safely. It does import the scope constants
from :mod:`auth_tenancy.models` — the single source of truth for the three level
names — which is fine inside ``ready()`` (the app registry is fully populated by
then) and from any request-time consumer.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Final, Literal, get_args

from django.core.exceptions import ImproperlyConfigured

from auth_tenancy.models import (
    PREFERENCE_SCOPE_GLOBAL,
    PREFERENCE_SCOPE_USER,
    PREFERENCE_SCOPE_WORKSPACE,
)
from persistence.errors import ValidationError

#: The value shapes a preference can carry. ``str_list`` is ordered: its order
#: is part of what the consumer stores, even when ``union`` merges levels.
ValueType = Literal["bool", "enum", "str_list"]

#: How levels combine into the effective value.
#:
#: * ``override`` — the first set level in ``user > workspace > global`` wins,
#:   else the registry default (``source`` = that level or ``"default"``).
#: * ``union`` — the union of every set level plus the default, deduplicated
#:   (``source`` = ``"merged"``). "Minimum wins" for opt-out lists: one level can
#:   disable a slot, no level can re-enable it.
Mode = Literal["override", "union"]

#: Rendering hint for the generic settings section. ``None`` = not rendered
#: there (the key has a dedicated UI or no UI at all).
UiEditor = Literal["checkbox", "select"]

#: Canonical level names, lowest precedence first. Matches
#: :data:`auth_tenancy.models.PREFERENCE_SCOPE_CHOICES`.
PREFERENCE_LEVELS: Final[tuple[str, ...]] = (
    PREFERENCE_SCOPE_GLOBAL,
    PREFERENCE_SCOPE_WORKSPACE,
    PREFERENCE_SCOPE_USER,
)

#: ``"<namespace>.<name>"`` — lower-case, dots/underscores only, length-bounded
#: so a typo or a pathological client-supplied key is rejected at registration.
_KEY_PATTERN = re.compile(r"^[a-z0-9_.]{3,128}$")


@dataclass(frozen=True)
class PreferenceKey:
    """One registered preference key and everything resolution needs.

    Attributes:
        key: ``"<namespace>.<name>"``, matching :data:`_KEY_PATTERN`.
        value_type: ``bool``, ``enum`` or ``str_list``.
        default: The registry default, used when no level is set. ``union`` keys
            use a list here; treat it as read-only — the resolver deep-copies it
            before handing it out.
        levels: Levels that may carry this key (a subset of
            :data:`PREFERENCE_LEVELS`). A level not listed is ignored on read and
            rejected on write.
        mode: ``override`` (default) or ``union``.
        choices: Allowed values for ``enum``; for ``str_list`` the allowed list
            items. ``None`` = unconstrained (only meaningful for ``str_list``).
        validator: Optional extra check, called on every non-``None`` write (and
            on the default at registration). It must raise
            :class:`persistence.errors.ValidationError` on failure.
        ui_editor: ``checkbox`` / ``select`` for the generic settings section,
            ``None`` for "no generic editor".
        owner: Plan/WP marker, documentation only (e.g. ``"C2"``, ``"A1"``).
    """

    key: str
    value_type: ValueType
    default: Any
    levels: frozenset[str]
    mode: Mode = "override"
    choices: tuple[str, ...] | None = None
    validator: Callable[[Any], None] | None = None
    ui_editor: UiEditor | None = None
    owner: str = ""

    def __post_init__(self) -> None:
        """Normalise the collection fields and reject an incoherent definition.

        Runs for every construction, registered or not, so a malformed key fails
        at its definition site rather than on the first request that touches it.
        """
        if not isinstance(self.key, str) or not _KEY_PATTERN.fullmatch(self.key):
            raise ImproperlyConfigured(
                f"Preference key {self.key!r} does not match "
                f"'[a-z0-9_.]{{3,128}}'"
            )
        if self.value_type not in get_args(ValueType):
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: unknown value_type "
                f"{self.value_type!r}; expected one of {list(get_args(ValueType))}"
            )
        if self.mode not in get_args(Mode):
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: unknown mode {self.mode!r}; "
                f"expected one of {list(get_args(Mode))}"
            )
        if not isinstance(self.levels, (set, frozenset)):
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: 'levels' must be a set of level "
                f"names"
            )
        levels = frozenset(self.levels)
        if not levels:
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: at least one level is required"
            )
        unknown_levels = levels - set(PREFERENCE_LEVELS)
        if unknown_levels:
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: unknown level(s) "
                f"{sorted(unknown_levels)}; expected a subset of "
                f"{list(PREFERENCE_LEVELS)}"
            )
        choices = self.choices
        if choices is not None and not isinstance(choices, (list, tuple)):
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: 'choices' must be a sequence or None"
            )
        if self.value_type == "enum" and not choices:
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: an 'enum' key requires 'choices'"
            )
        if self.ui_editor not in (None, "checkbox", "select"):
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: unknown ui_editor "
                f"{self.ui_editor!r}"
            )
        if self.validator is not None and not callable(self.validator):
            raise ImproperlyConfigured(
                f"Preference key {self.key!r}: 'validator' must be callable or None"
            )
        # ``frozen`` only forbids ordinary assignment; normalising here keeps the
        # hashable/immutable contract (a caller may pass a plain set/list).
        object.__setattr__(self, "levels", levels)
        if choices is not None:
            object.__setattr__(self, "choices", tuple(choices))


#: The process-wide registry. Ordered only for construction; every public reader
#: sorts by key so ordering never depends on registration order.
_REGISTRY: dict[str, PreferenceKey] = {}


def validate_preference_value(spec: PreferenceKey, value: Any) -> None:
    """Validate *value* against *spec* (type, choices, then the key validator).

    ``None`` is not validated here: it means "reset the level" and is handled by
    the service before this function is reached.

    Raises:
        ValidationError: the value has the wrong type, is not one of ``choices``,
            or the key's own ``validator`` rejected it.
    """
    if value is None:  # pragma: no cover - defensive; callers filter reset first
        return
    if spec.value_type == "bool":
        if not isinstance(value, bool):
            raise ValidationError(
                f"Preference {spec.key!r} must be a boolean, "
                f"got {type(value).__name__}"
            )
    elif spec.value_type == "enum":
        if not isinstance(value, str) or value not in (spec.choices or ()):
            raise ValidationError(
                f"Preference {spec.key!r} must be one of "
                f"{list(spec.choices or ())}, got {value!r}"
            )
    elif spec.value_type == "str_list":
        if not isinstance(value, list) or not all(
            isinstance(item, str) for item in value
        ):
            raise ValidationError(
                f"Preference {spec.key!r} must be a list of strings, "
                f"got {value!r}"
            )
        if spec.choices is not None:
            unknown = sorted(item for item in value if item not in spec.choices)
            if unknown:
                raise ValidationError(
                    f"Preference {spec.key!r} contains unknown item(s) "
                    f"{unknown}; expected a subset of {list(spec.choices)}"
                )
    if spec.validator is not None:
        # The validator owns its message and is documented to raise ValidationError.
        spec.validator(value)


def register_preference_key(spec: PreferenceKey) -> None:
    """Register *spec* process-wide.

    Raises:
        ImproperlyConfigured: *spec* is not a :class:`PreferenceKey`, its key is
            already registered, or its default does not satisfy its own
            definition. All three are programming errors, not caller input.
        ValidationError: the key's ``validator`` rejected its own default.
    """
    if not isinstance(spec, PreferenceKey):
        raise ImproperlyConfigured(
            f"register_preference_key() expects a PreferenceKey, got "
            f"{type(spec).__name__}"
        )
    if spec.key in _REGISTRY:
        raise ImproperlyConfigured(
            f"Preference key {spec.key!r} is already registered"
        )
    validate_preference_value(spec, spec.default)
    _REGISTRY[spec.key] = spec


def get_preference_key(key: str) -> PreferenceKey:
    """Return the registered *key*.

    Raises:
        ValidationError: *key* is not registered (caller input, HTTP 400).
    """
    try:
        return _REGISTRY[key]
    except KeyError:
        raise ValidationError(f"Unknown preference key {key!r}") from None


def all_preference_keys() -> tuple[PreferenceKey, ...]:
    """Return every registered key, sorted by key (deterministic order)."""
    return tuple(_REGISTRY[name] for name in sorted(_REGISTRY))


__all__ = [
    "PREFERENCE_LEVELS",
    "Mode",
    "PreferenceKey",
    "UiEditor",
    "ValueType",
    "all_preference_keys",
    "get_preference_key",
    "register_preference_key",
    "validate_preference_value",
]

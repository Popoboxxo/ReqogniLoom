"""Plan D / D3.4 (#792 item 18): the health advisory exposes the deployment identity.

The dev overlay must be observable without touching the status code: a
non-production ``DJANGO_ENV`` lands in ``advisory`` and never in ``warnings``.
"""

from django.test import override_settings

from reqogniloom.health import _collect_advisory


def test_django_env_is_advisory_and_never_a_warning() -> None:
    advisory: dict[str, str] = {}
    warnings: list[str] = []
    with override_settings(DJANGO_ENV="development"):
        _collect_advisory(advisory, warnings, db_ok=False)
    assert advisory["django_env"] == "development"
    assert warnings == []


def test_production_is_reported_verbatim() -> None:
    advisory: dict[str, str] = {}
    warnings: list[str] = []
    with override_settings(DJANGO_ENV="production"):
        _collect_advisory(advisory, warnings, db_ok=False)
    assert advisory["django_env"] == "production"
    assert warnings == []

"""
COMP-PL-006 RLSPolicyEnforcer — dedicated least-privilege application DB role.

Requirements:
- REQ-L2-PL-010 (RLS on all tenant-scoped tables)
- ADR-PL-03 (RLS as second isolation layer behind COMP-PL-002 Custom Manager)

Follows up on the NOTE in 0003_rls_policies.py: FORCE ROW LEVEL SECURITY does
not constrain a superuser (superusers bypass RLS unconditionally, regardless
of FORCE). The Docker Postgres bootstrap user (``POSTGRES_USER``) is created
as a superuser during ``initdb``, so runtime traffic authenticated as that
role would silently skip every tenant-isolation policy.

This migration creates a dedicated, non-superuser role
(``persistence.db_roles.APP_DB_ROLE``) with just enough privileges to operate
the schema (CONNECT, USAGE, and CRUD on all tables/sequences), and grants
ownership-independent row access via that CRUD grant plus the existing RLS
policies. Application processes (Django, Celery) must authenticate as this
role for RLS to take effect; the migration runner itself keeps using the
superuser/owner role, since DDL is unaffected by RLS.

Created here (as a migration) rather than only in the Docker Compose init
script so the role also exists in Django's ephemeral test databases (CI runs
``pytest`` against ``DB_USER`` directly, never touching the compose init
script).
"""
from __future__ import annotations

from decouple import config
from django.core.exceptions import ImproperlyConfigured
from django.db import migrations

from persistence.db_roles import APP_DB_ROLE


def _create_app_role(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    app_role_password = config("DB_APP_PASSWORD", default=None)
    if not app_role_password:
        raise ImproperlyConfigured(
            "DB_APP_PASSWORD must be set to create the least-privilege app DB role "
            "(persistence/migrations/0048_app_role.py) — no default is provided."
        )
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", [APP_DB_ROLE]
        )
        role_exists = cursor.fetchone() is not None
        if role_exists:
            cursor.execute(
                f'ALTER ROLE "{APP_DB_ROLE}" WITH LOGIN NOSUPERUSER '
                f"PASSWORD %s",
                [app_role_password],
            )
        else:
            cursor.execute(
                f'CREATE ROLE "{APP_DB_ROLE}" WITH LOGIN NOSUPERUSER '
                f"PASSWORD %s",
                [app_role_password],
            )
        db_name = schema_editor.connection.settings_dict["NAME"]
        cursor.execute(f'GRANT CONNECT ON DATABASE "{db_name}" TO "{APP_DB_ROLE}"')
        cursor.execute(f'GRANT USAGE ON SCHEMA public TO "{APP_DB_ROLE}"')
        cursor.execute(
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{APP_DB_ROLE}"'
        )
        cursor.execute(
            f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{APP_DB_ROLE}"'
        )
        cursor.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{APP_DB_ROLE}"'
        )
        cursor.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'GRANT USAGE, SELECT ON SEQUENCES TO "{APP_DB_ROLE}"'
        )


def _revoke_app_role_grants(apps, schema_editor):
    """Reverse: revoke this database's grants only — never DROP ROLE.

    ``APP_DB_ROLE`` is a cluster-level object shared by every database on the
    Postgres server (e.g. the persistent dev DB and each ephemeral pytest
    ``test_*`` DB). ``DROP ROLE`` fails cluster-wide the instant the role
    still holds a grant in ANY other database, which real dev/CI setups always
    have. Tests that use ``MigrationExecutor`` to move the ``persistence`` app
    back past this migration (e.g. test_prompt_template_migration.py) must be
    able to do so without tearing down a role other databases still rely on.
    """
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM "{APP_DB_ROLE}"'
        )
        cursor.execute(
            f'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM "{APP_DB_ROLE}"'
        )
        cursor.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM "{APP_DB_ROLE}"'
        )
        cursor.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            f'REVOKE USAGE, SELECT ON SEQUENCES FROM "{APP_DB_ROLE}"'
        )
        cursor.execute(f'REVOKE USAGE ON SCHEMA public FROM "{APP_DB_ROLE}"')
        db_name = schema_editor.connection.settings_dict["NAME"]
        cursor.execute(f'REVOKE CONNECT ON DATABASE "{db_name}" FROM "{APP_DB_ROLE}"')


class Migration(migrations.Migration):

    dependencies = [
        ("persistence", "0047_requirement_acceptance_criteria_and_more"),
    ]

    operations = [
        migrations.RunPython(_create_app_role, reverse_code=_revoke_app_role_grants),
    ]

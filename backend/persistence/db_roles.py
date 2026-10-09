"""
Shared constant for the least-privilege application DB role (REQ-L2-PL-010).

Background: the bootstrap ``POSTGRES_USER`` role (Docker Postgres image
convention) is created as a superuser during ``initdb``. Superusers always
bypass Row-Level Security, regardless of ``FORCE ROW LEVEL SECURITY``
(persistence/migrations/0003_rls_policies.py). Runtime traffic must instead
use a dedicated, non-superuser role so the RLS policies actually apply
(defense-in-depth, ADR-PL-03).

The role itself is created/granted by persistence/migrations/0048_app_role.py
so it exists in every database the Django migration runner touches (prod,
dev, and Django's ephemeral test databases in CI).
"""
from __future__ import annotations

from decouple import config

APP_DB_ROLE = config("DB_APP_USER", default="reqogniloom_app")

#: Dedicated owner of every ``SECURITY DEFINER`` function (issue #1180,
#: spec residual R-8 of docs/audit/2026-10/1136-rls-coverage-spec.md).
#:
#: Before this role existed, the pre-auth / refresh / outbox / RLS-control
#: definer functions were owned by the bootstrap ``POSTGRES_USER`` role, which
#: is a superuser. A superuser owner bypasses Row-Level Security
#: unconditionally, so ``NOT rolsuper`` was not assertable for the definer
#: (residual R-8). The dedicated role is ``NOLOGIN NOSUPERUSER`` (and
#: ``NOCREATEDB NOCREATEROLE NOREPLICATION``): nobody can log in as it and the
#: app role is not a member, so it can never be reached via ``SET ROLE``. It
#: carries ``BYPASSRLS`` plus explicit, table-scoped DML grants — that is the
#: narrowest surface that lets the definer bodies read/write exactly the tables
#: they need while still bypassing the (non-FORCE) staged policies.
#:
#: The role is created and every definer function is transferred to it by
#: persistence/migrations/0110_security_definer_owner_role.py.
DEFINER_DB_ROLE = config("DB_DEFINER_USER", default="reqogniloom_definer")

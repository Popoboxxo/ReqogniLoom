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

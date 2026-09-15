"""as_comment / as_notification are covered by row-level security."""
import pytest
from django.db import connection

TABLES = ["as_comment", "as_notification"]


@pytest.mark.django_db
@pytest.mark.parametrize("table", TABLES)
def test_rls_is_enabled_and_forced(table):
    with connection.cursor() as cur:
        cur.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = %s",
            [table],
        )
        row = cur.fetchone()
    assert row is not None, f"{table} does not exist"
    assert row[0] is True, f"{table}: ROW LEVEL SECURITY not enabled"
    assert row[1] is True, f"{table}: FORCE ROW LEVEL SECURITY not set"


@pytest.mark.django_db
@pytest.mark.parametrize("table", TABLES)
def test_tenant_isolation_policy_exists(table):
    with connection.cursor() as cur:
        cur.execute("SELECT policyname FROM pg_policies WHERE tablename = %s", [table])
        names = {r[0] for r in cur.fetchall()}
    assert f"{table}_tenant_isolation" in names

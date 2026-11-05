"""Optional Postgres integration test: proves the RLS policies themselves
(not just the repository filter) isolate tenants.

Skips cleanly unless ALL of these hold:
* FDE_TEST_PG_DSN is set (a NON-superuser app-role DSN, e.g.
  postgresql://fde_app:...@127.0.0.1:5432/fde_test), and
* the server is reachable, and
* migrations/001_rls.sql has been applied to that database.

Run manually with the local Postgres 16.4 binaries in ~/workspace/tools/pgsql.
"""
import os

import pytest

DSN = os.environ.get("FDE_TEST_PG_DSN")

pytestmark = pytest.mark.skipif(
    not DSN, reason="FDE_TEST_PG_DSN not set; Postgres integration disabled"
)


@pytest.fixture()
def pg_store():
    psycopg = pytest.importorskip("psycopg")
    try:
        conn = psycopg.connect(DSN, connect_timeout=3)
        conn.close()
    except Exception as exc:  # server down / role missing -> skip, never fail
        pytest.skip(f"Postgres not reachable: {exc}")

    from fde_multitenant.db import PostgresStore
    from fde_multitenant.fixtures import seed_store

    store = PostgresStore(DSN)
    seed_store(store)
    return store


def test_rls_isolation_on_postgres(pg_store):
    from fde_multitenant.context import TenantContext
    from fde_multitenant.repository import TenantRepository

    with pg_store.session(TenantContext(tenant_id="tenant-a")) as s:
        repo_a = TenantRepository(s)
        assert {p["id"] for p in repo_a.list_projects()} == {"proj-a1", "proj-a2"}

    with pg_store.session(TenantContext(tenant_id="tenant-b")) as s:
        repo_b = TenantRepository(s)
        assert repo_b.get_project("proj-a1") is None
        # Even bypassing the repository filter, RLS returns nothing:
        rows = s.conn.execute(
            "SELECT * FROM projects WHERE id = 'proj-a1'"
        ).fetchall()
        assert rows == []

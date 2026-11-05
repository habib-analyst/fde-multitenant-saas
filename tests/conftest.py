import pytest

from fde_multitenant.context import TenantContext
from fde_multitenant.db import SQLiteStore
from fde_multitenant.fixtures import TENANT_A, TENANT_B, seed_store
from fde_multitenant.repository import TenantRepository


@pytest.fixture()
def store():
    s = SQLiteStore()  # fresh in-memory DB per test
    seed_store(s)
    yield s
    s.close()


@pytest.fixture()
def repo_a(store):
    with store.session(TenantContext(tenant_id=TENANT_A)) as s:
        yield TenantRepository(s)


@pytest.fixture()
def repo_b(store):
    with store.session(TenantContext(tenant_id=TENANT_B)) as s:
        yield TenantRepository(s)

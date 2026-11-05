"""Deterministic seed data used by the demo and the tests.

All ids, timestamps and quantities are fixed constants — the same seed
always produces the same analytics and the same invoice, which is what
lets the tests pin exact numbers.
"""
from __future__ import annotations

from .context import TenantContext
from .repository import TenantRepository

# Fixed "recent" timestamp base; tests use a wide window (default 30 days
# is computed from now, so fixtures record events with occurred_at=None,
# i.e. "now", except where a test pins an explicit timestamp).
TENANT_A = "tenant-a"
TENANT_B = "tenant-b"

USERS = {
    TENANT_A: [("user-a1", "a1@tenant-a.example"), ("user-a2", "a2@tenant-a.example")],
    TENANT_B: [("user-b1", "b1@tenant-b.example")],
}

PROJECTS = {
    TENANT_A: [("proj-a1", "Alpha API", "Tenant A first project"),
               ("proj-a2", "Alpha Storage", "Tenant A second project")],
    TENANT_B: [("proj-b1", "Beta API", "Tenant B first project")],
}

# (tenant, user_id, project_id, meter, quantity)
EVENTS = [
    (TENANT_A, "user-a1", "proj-a1", "api_calls", 600),
    (TENANT_A, "user-a2", "proj-a1", "api_calls", 400),
    (TENANT_A, "user-a1", "proj-a2", "storage_gb", 50),
    (TENANT_A, "user-a2", "proj-a2", "storage_gb", 30),
    (TENANT_A, "user-a1", "proj-a1", "compute_seconds", 1800),
    (TENANT_B, "user-b1", "proj-b1", "api_calls", 250),
    (TENANT_B, "user-b1", "proj-b1", "storage_gb", 10),
]

# Expected values derived from EVENTS, asserted exactly by the tests.
EXPECTED = {
    TENANT_A: {
        "totals": {"api_calls": 1000, "storage_gb": 80, "compute_seconds": 1800},
        "total_events": 5,
        "active_users": 2,
        # api_calls: 1000 x 0.002 = 2.00
        # storage_gb: 80 x 0.10 = 8.00
        # compute_seconds: 1800 x 0.010 = 18.00  -> total 28.00
        "invoice_total": "28.00",
    },
    TENANT_B: {
        "totals": {"api_calls": 250, "storage_gb": 10},
        "total_events": 2,
        "active_users": 1,
        # 250 x 0.002 = 0.50 ; 10 x 0.10 = 1.00 -> total 1.50
        "invoice_total": "1.50",
    },
}


def seed_store(store) -> None:
    """Populate a store (either backend) with the fixture tenants/data."""
    store.seed_tenant(TENANT_A, "Tenant A")
    store.seed_tenant(TENANT_B, "Tenant B")
    for tenant_id, users in USERS.items():
        for user_id, email in users:
            store.seed_user(user_id, tenant_id, email)
    for tenant_id, projects in PROJECTS.items():
        with store.session(TenantContext(tenant_id=tenant_id)) as s:
            repo = TenantRepository(s)
            for pid, name, desc in projects:
                if repo.get_project(pid) is None:
                    repo.create_project(name, desc, project_id=pid)
    for tenant_id, user_id, project_id, meter, qty in EVENTS:
        with store.session(TenantContext(tenant_id=tenant_id)) as s:
            repo = TenantRepository(s)
            repo.record_event(user_id, meter, qty, project_id=project_id)

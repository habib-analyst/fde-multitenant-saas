"""API-level tests through FastAPI's TestClient."""
import pytest
from fastapi.testclient import TestClient

from fde_multitenant.app import create_app

A = {"X-Tenant-Id": "tenant-a", "X-Api-Key": "fixture-key-tenant-a"}
B = {"X-Tenant-Id": "tenant-b", "X-Api-Key": "fixture-key-tenant-b"}


@pytest.fixture()
def client():
    return TestClient(create_app())


def test_health(client):
    assert client.get("/health").status_code == 200


def test_missing_headers_rejected(client):
    assert client.get("/projects").status_code == 422


def test_wrong_key_rejected(client):
    bad = {"X-Tenant-Id": "tenant-a", "X-Api-Key": "fixture-key-tenant-b"}
    assert client.get("/projects", headers=bad).status_code == 401


def test_other_tenants_key_with_own_tenant_id_rejected(client):
    # Tenant B's key + tenant A's id: the key decides identity -> 401.
    bad = {"X-Tenant-Id": "tenant-a", "X-Api-Key": "fixture-key-tenant-b"}
    assert client.get("/analytics/summary", headers=bad).status_code == 401


def test_unknown_tenant_rejected(client):
    bad = {"X-Tenant-Id": "tenant-zzz", "X-Api-Key": "fixture-key-tenant-a"}
    assert client.get("/projects", headers=bad).status_code == 401


def test_list_projects_scoped(client):
    a = client.get("/projects", headers=A).json()
    b = client.get("/projects", headers=B).json()
    assert {p["id"] for p in a} == {"proj-a1", "proj-a2"}
    assert {p["id"] for p in b} == {"proj-b1"}


def test_cross_tenant_get_by_id_is_404_not_403(client):
    # 404 (not 403): the API does not even confirm the project exists.
    assert client.get("/projects/proj-a1", headers=B).status_code == 404
    assert client.get("/projects/proj-a1", headers=A).status_code == 200


def test_cross_tenant_patch_and_delete_are_404(client):
    assert client.patch("/projects/proj-a1", headers=B, json={"name": "X"}).status_code == 404
    assert client.delete("/projects/proj-a1", headers=B).status_code == 404
    assert client.get("/projects/proj-a1", headers=A).json()["name"] == "Alpha API"


def test_project_crud_roundtrip(client):
    created = client.post("/projects", headers=A, json={"name": "New", "description": "d"})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert created.json()["tenant_id"] == "tenant-a"
    assert client.get(f"/projects/{pid}", headers=B).status_code == 404
    patched = client.patch(f"/projects/{pid}", headers=A, json={"name": "Renamed"})
    assert patched.json()["name"] == "Renamed"
    assert client.delete(f"/projects/{pid}", headers=A).status_code == 204
    assert client.get(f"/projects/{pid}", headers=A).status_code == 404


def test_usage_ingest_and_analytics(client):
    before = client.get("/analytics/summary", headers=A).json()
    r = client.post(
        "/usage/events",
        headers=A,
        json={"user_id": "user-a1", "meter": "api_calls", "quantity": 7, "project_id": "proj-a1"},
    )
    assert r.status_code == 201
    assert r.json()["tenant_id"] == "tenant-a"
    after = client.get("/analytics/summary", headers=A).json()
    assert after["total_events"] == before["total_events"] + 1
    by_meter = {m["meter"]: m for m in after["by_meter"]}
    assert by_meter["api_calls"]["total_quantity"] == 1007


def test_usage_ingest_unknown_meter_422(client):
    r = client.post(
        "/usage/events",
        headers=A,
        json={"user_id": "user-a1", "meter": "nope", "quantity": 1},
    )
    assert r.status_code == 422


def test_usage_ingest_cross_tenant_project_422(client):
    r = client.post(
        "/usage/events",
        headers=B,
        json={"user_id": "user-b1", "meter": "api_calls", "quantity": 1, "project_id": "proj-a1"},
    )
    assert r.status_code == 422


def test_analytics_summary_exact_numbers(client):
    s = client.get("/analytics/summary", headers=A).json()
    assert s["total_events"] == 5
    assert s["active_users"] == 2


def test_billing_invoice_exact_total(client):
    inv = client.get("/billing/invoice", headers=A).json()
    assert inv["tenant_id"] == "tenant-a"
    assert inv["total"] == "28.00"
    assert inv["currency"] == "USD"
    meters = {li["meter"]: li for li in inv["line_items"]}
    assert meters["api_calls"]["quantity"] == 1000
    assert meters["storage_gb"]["quantity"] == 80
    inv_b = client.get("/billing/invoice", headers=B).json()
    assert inv_b["total"] == "1.50"

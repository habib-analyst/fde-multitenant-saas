"""Cross-tenant isolation: tenant B must never see, modify, or reference
tenant A's data — including by guessing a direct id."""
import pytest


def test_list_projects_only_own_tenant(repo_a, repo_b):
    a_ids = {p["id"] for p in repo_a.list_projects()}
    b_ids = {p["id"] for p in repo_b.list_projects()}
    assert a_ids == {"proj-a1", "proj-a2"}
    assert b_ids == {"proj-b1"}
    assert a_ids.isdisjoint(b_ids)


def test_get_other_tenants_project_by_direct_id_returns_none(repo_b):
    assert repo_b.get_project("proj-a1") is None
    assert repo_b.get_project("proj-a2") is None


def test_get_own_project_works(repo_a):
    p = repo_a.get_project("proj-a1")
    assert p is not None and p["name"] == "Alpha API"


def test_update_other_tenants_project_is_a_no_op(repo_a, repo_b):
    assert repo_b.update_project("proj-a1", name="Hijacked") is None
    # A's row is untouched.
    assert repo_a.get_project("proj-a1")["name"] == "Alpha API"


def test_delete_other_tenants_project_is_a_no_op(repo_a, repo_b):
    assert repo_b.delete_project("proj-a1") is False
    assert repo_a.get_project("proj-a1") is not None


def test_delete_own_project_works(repo_a):
    assert repo_a.delete_project("proj-a2") is True
    assert repo_a.get_project("proj-a2") is None


def test_events_are_isolated(repo_a, repo_b):
    a_events = repo_a.list_events()
    b_events = repo_b.list_events()
    assert len(a_events) == 5
    assert len(b_events) == 2
    assert all(e["tenant_id"] == "tenant-a" for e in a_events)
    assert all(e["tenant_id"] == "tenant-b" for e in b_events)


def test_event_cannot_reference_other_tenants_project(repo_b):
    with pytest.raises(ValueError):
        repo_b.record_event("user-b1", "api_calls", 5, project_id="proj-a1")


def test_created_project_is_stamped_with_session_tenant(repo_b):
    created = repo_b.create_project("Beta New")
    assert created["tenant_id"] == "tenant-b"


def test_new_project_invisible_to_other_tenant(repo_a, repo_b):
    created = repo_b.create_project("Beta Secret")
    assert repo_a.get_project(created["id"]) is None
    assert created["id"] not in {p["id"] for p in repo_a.list_projects()}

"""Analytics correctness on the deterministic fixtures."""
from fde_multitenant.fixtures import EXPECTED, TENANT_A, TENANT_B


def test_summary_tenant_a(repo_a):
    summary = repo_a.analytics_summary(days=30)
    exp = EXPECTED[TENANT_A]
    assert summary["tenant_id"] == TENANT_A
    assert summary["total_events"] == exp["total_events"]
    assert summary["active_users"] == exp["active_users"]
    by_meter = {m["meter"]: m for m in summary["by_meter"]}
    assert by_meter["api_calls"]["total_quantity"] == 1000
    assert by_meter["api_calls"]["event_count"] == 2
    assert by_meter["storage_gb"]["total_quantity"] == 80
    assert by_meter["storage_gb"]["event_count"] == 2
    assert by_meter["compute_seconds"]["total_quantity"] == 1800
    assert by_meter["compute_seconds"]["event_count"] == 1


def test_summary_tenant_b_has_none_of_a(repo_b):
    summary = repo_b.analytics_summary(days=30)
    exp = EXPECTED[TENANT_B]
    assert summary["total_events"] == exp["total_events"]
    assert summary["active_users"] == exp["active_users"]
    assert {m["meter"] for m in summary["by_meter"]} == {"api_calls", "storage_gb"}


def test_usage_totals_by_meter(repo_a, repo_b):
    assert repo_a.usage_totals_by_meter() == EXPECTED[TENANT_A]["totals"]
    assert repo_b.usage_totals_by_meter() == EXPECTED[TENANT_B]["totals"]


def test_summary_window_excludes_old_events(store, repo_a):
    # An event backdated 90 days must fall outside a 30-day window.
    repo_a.record_event(
        "user-a1", "api_calls", 9999, occurred_at="2000-01-01 00:00:00"
    )
    summary = repo_a.analytics_summary(days=30)
    by_meter = {m["meter"]: m for m in summary["by_meter"]}
    assert by_meter["api_calls"]["total_quantity"] == 1000
    # ...but a wide window sees it.
    wide = repo_a.analytics_summary(days=366 * 40)
    by_meter_wide = {m["meter"]: m for m in wide["by_meter"]}
    assert by_meter_wide["api_calls"]["total_quantity"] == 1000 + 9999


def test_record_event_rejects_negative_quantity(repo_a):
    import pytest

    with pytest.raises(ValueError):
        repo_a.record_event("user-a1", "api_calls", -1)

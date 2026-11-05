"""Billing tier math, pinned exactly with Decimal — including boundaries."""
from decimal import Decimal

import pytest

from fde_multitenant.billing import UnknownMeterError, build_invoice, price_meter
from fde_multitenant.fixtures import EXPECTED, TENANT_A, TENANT_B


def test_zero_quantity_bills_zero():
    item = price_meter("api_calls", 0)
    assert item.amount == Decimal("0")
    assert item.tiers == []


def test_below_first_tier():
    # 500 x 0.002 = 1.00
    assert price_meter("api_calls", 500).amount == Decimal("1.00")


def test_exactly_at_tier_boundary():
    # Exactly 1000 units: everything bills at the first-tier rate.
    item = price_meter("api_calls", 1000)
    assert item.amount == Decimal("2.00")
    assert len(item.tiers) == 1
    assert item.tiers[0].units == 1000


def test_one_unit_over_boundary():
    # 1000 x 0.002 + 1 x 0.001 = 2.001
    item = price_meter("api_calls", 1001)
    assert item.amount == Decimal("2.001")
    assert [t.units for t in item.tiers] == [1000, 1]


def test_well_into_second_tier():
    # 1000 x 0.002 + 500 x 0.001 = 2.50
    assert price_meter("api_calls", 1500).amount == Decimal("2.50")


def test_storage_tiers():
    assert price_meter("storage_gb", 100).amount == Decimal("10.00")
    # 100 x 0.10 + 50 x 0.05 = 12.50
    assert price_meter("storage_gb", 150).amount == Decimal("12.50")


def test_compute_tiers():
    assert price_meter("compute_seconds", 3600).amount == Decimal("36.00")
    # 3600 x 0.010 + 3600 x 0.005 = 54.00
    assert price_meter("compute_seconds", 7200).amount == Decimal("54.00")


def test_unknown_meter_raises():
    with pytest.raises(UnknownMeterError):
        price_meter("bandwidth_parsecs", 10)


def test_negative_quantity_raises():
    with pytest.raises(ValueError):
        price_meter("api_calls", -5)


def test_invoice_from_fixture_totals_tenant_a(repo_a):
    invoice = repo_a.invoice()
    assert invoice.total == Decimal(EXPECTED[TENANT_A]["invoice_total"])
    assert invoice.to_dict()["total"] == EXPECTED[TENANT_A]["invoice_total"]


def test_invoice_from_fixture_totals_tenant_b(repo_b):
    invoice = repo_b.invoice()
    assert invoice.total == Decimal(EXPECTED[TENANT_B]["invoice_total"])


def test_invoice_omits_zero_usage_meters():
    invoice = build_invoice("tenant-x", {"api_calls": 10, "storage_gb": 0})
    assert [li.meter for li in invoice.line_items] == ["api_calls"]
    assert invoice.total == Decimal("0.02")

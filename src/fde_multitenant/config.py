"""Static configuration: fixture auth and tiered pricing.

Fixture API keys are deliberately synthetic (``fixture-key-*``). They exist
so the demo and the test-suite can exercise the auth path without any real
credential ever appearing in the codebase.
"""
from __future__ import annotations

from decimal import Decimal

# tenant_id -> fixture API key. Synthetic values only, by design.
FIXTURE_API_KEYS: dict[str, str] = {
    "tenant-a": "fixture-key-tenant-a",
    "tenant-b": "fixture-key-tenant-b",
}

# Reverse lookup used by the auth dependency.
KEY_TO_TENANT: dict[str, str] = {v: k for k, v in FIXTURE_API_KEYS.items()}

# Tiered pricing. Each meter maps to a list of (tier_cap_units, unit_price)
# tiers evaluated in order; a cap of None means "unbounded remainder".
# Prices are Decimal so billing math is exact — never float.
PRICING_TIERS: dict[str, list[tuple[int | None, Decimal]]] = {
    # First 1,000 API calls at $0.002 each, everything after at $0.001.
    "api_calls": [(1000, Decimal("0.002")), (None, Decimal("0.001"))],
    # First 100 GB at $0.10/GB, everything after at $0.05/GB.
    "storage_gb": [(100, Decimal("0.10")), (None, Decimal("0.05"))],
    # First 3,600 compute-seconds at $0.01 each, then $0.005.
    "compute_seconds": [(3600, Decimal("0.010")), (None, Decimal("0.005"))],
}

KNOWN_METERS: tuple[str, ...] = tuple(PRICING_TIERS.keys())

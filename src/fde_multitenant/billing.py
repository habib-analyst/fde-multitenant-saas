"""Usage-based billing: invoice line items computed from metered events.

Billing here is pure computation. There are no payment calls of any kind —
the output is an invoice document (line items + totals) that a real billing
provider could later be fed with.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")

from .config import PRICING_TIERS


class UnknownMeterError(ValueError):
    pass


@dataclass(frozen=True)
class TierCharge:
    units: int
    unit_price: Decimal
    amount: Decimal


@dataclass(frozen=True)
class LineItem:
    meter: str
    quantity: int
    tiers: list[TierCharge] = field(default_factory=list)

    @property
    def amount(self) -> Decimal:
        return sum((t.amount for t in self.tiers), Decimal("0"))


@dataclass(frozen=True)
class Invoice:
    tenant_id: str
    line_items: list[LineItem]

    @property
    def subtotal(self) -> Decimal:
        raw = sum((li.amount for li in self.line_items), Decimal("0"))
        return raw.quantize(CENT, rounding=ROUND_HALF_UP)

    @property
    def total(self) -> Decimal:
        # No taxes/fees in the demo core: total == subtotal.
        return self.subtotal

    def to_dict(self) -> dict:
        return {
            "tenant_id": self.tenant_id,
            "line_items": [
                {
                    "meter": li.meter,
                    "quantity": li.quantity,
                    "amount": str(li.amount),
                    "tiers": [
                        {
                            "units": t.units,
                            "unit_price": str(t.unit_price),
                            "amount": str(t.amount),
                        }
                        for t in li.tiers
                    ],
                }
                for li in self.line_items
            ],
            "subtotal": str(self.subtotal),
            "total": str(self.total),
            "currency": "USD",
        }


def price_meter(meter: str, quantity: int) -> LineItem:
    """Price ``quantity`` units of ``meter`` through its tiers.

    Tier math: walk tiers in order; each tier bills
    ``min(remaining, cap)`` units at its rate; the final tier (cap None)
    bills whatever remains.
    """
    if meter not in PRICING_TIERS:
        raise UnknownMeterError(f"unknown meter: {meter!r}")
    if quantity < 0:
        raise ValueError("quantity must be >= 0")

    tiers: list[TierCharge] = []
    remaining = quantity
    for cap, rate in PRICING_TIERS[meter]:
        if remaining <= 0:
            break
        units = remaining if cap is None else min(remaining, cap)
        tiers.append(TierCharge(units=units, unit_price=rate, amount=rate * units))
        remaining -= units
    return LineItem(meter=meter, quantity=quantity, tiers=tiers)


def build_invoice(tenant_id: str, usage_totals: dict[str, int]) -> Invoice:
    """Build an invoice from {meter: total_quantity}. Meters with zero
    usage are omitted; unknown meters raise UnknownMeterError."""
    items = [
        price_meter(meter, qty)
        for meter, qty in sorted(usage_totals.items())
        if qty > 0
    ]
    return Invoice(tenant_id=tenant_id, line_items=items)

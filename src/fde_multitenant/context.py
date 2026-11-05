"""Tenant context: the identity every request and repository call runs under."""
from __future__ import annotations

from dataclasses import dataclass


class TenantContextError(ValueError):
    """Raised when a tenant context is missing or malformed."""


@dataclass(frozen=True)
class TenantContext:
    """Immutable per-request tenant identity.

    ``tenant_id`` is the only isolation key. It is set on the database
    connection (Postgres ``app.tenant_id``) or injected as a filter
    (SQLite) by the session wrapper — application code never passes raw
    tenant ids into queries itself.
    """

    tenant_id: str
    user_id: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not isinstance(self.tenant_id, str):
            raise TenantContextError("tenant_id must be a non-empty string")

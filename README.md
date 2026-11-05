# fde-multitenant-saas

A multi-tenant SaaS platform core built to production shape: Postgres
row-level security (RLS) tenant isolation, a FastAPI service where every
request runs inside a tenant context, per-tenant analytics over metered
usage events, and usage-based billing computed from those events.

## What it demonstrates

- **Tenant isolation enforced in the database, not just in code.** Every
  tenant-owned table carries `tenant_id`, RLS is enabled on all of them,
  and policies compare the row's tenant against the per-connection setting
  `app.tenant_id`. The application connects as a non-superuser role
  without `BYPASSRLS`, so a forgotten `WHERE` clause in application code
  still cannot leak another tenant's rows.
- **One repository API, two backends.** The same repository runs against
  Postgres (RLS enforces isolation; the repository's tenant filter is
  defense in depth) and against SQLite (the repository injects the tenant
  filter), which makes the full suite testable anywhere with no live
  database.
- **Metered usage to invoice.** Usage events are ingested per tenant and
  meter, aggregated for analytics, and priced through tiered rate cards
  with exact `Decimal` math to produce invoice line items and totals.
  Billing is computation only — no payment provider is called.

## Architecture

```
                X-Tenant-Id + X-Api-Key (fixture check)
                              │
                       FastAPI app (app.py)
                              │  TenantContext (frozen, one per request)
                       Tenant session (db.py)
                ┌─────────────┴─────────────┐
          Postgres backend             SQLite backend
   set_config('app.tenant_id')     tenant filter injected
          RLS policies                 by the repository
                └─────────────┬─────────────┘
                    TenantRepository (repository.py)
                  projects · usage events · analytics
                              │
                    Billing (billing.py, Decimal tiers)
```

## How isolation works

1. The auth dependency resolves the fixture API key to exactly one
   tenant. A valid key for tenant B presented with tenant A's id is
   rejected: the key, not the header, decides identity.
2. A session is bound to that single `TenantContext` for its whole
   lifetime; there is no API to switch tenant mid-session.
3. On Postgres the session runs
   `SELECT set_config('app.tenant_id', '<tenant>', false)`, arming the
   RLS policies in `migrations/001_rls.sql`. On SQLite the repository
   injects `tenant_id = ?` into every query.
4. Reads, updates and deletes by id are tenant-scoped: another tenant's
   id behaves exactly like a nonexistent id (API answers 404, never
   403), so existence does not leak across tenants.

## Pricing

Defined in `src/fde_multitenant/config.py`, computed in `billing.py`:

| Meter             | First tier            | Remainder         |
|-------------------|-----------------------|-------------------|
| `api_calls`       | 1,000 units @ $0.002  | $0.001 / unit     |
| `storage_gb`      | 100 units @ $0.10     | $0.05 / unit      |
| `compute_seconds` | 3,600 units @ $0.010  | $0.005 / unit     |

## Run it

```bash
pip install -r requirements.txt

# API (SQLite backend, seeded with two fixture tenants)
PYTHONPATH=src uvicorn fde_multitenant.app:app --port 8000

curl -H "X-Tenant-Id: tenant-a" -H "X-Api-Key: fixture-key-tenant-a" \
  http://127.0.0.1:8000/analytics/summary
curl -H "X-Tenant-Id: tenant-a" -H "X-Api-Key: fixture-key-tenant-a" \
  http://127.0.0.1:8000/billing/invoice
```

Postgres: apply `migrations/001_rls.sql` as a DBA (it also documents how
to create the non-superuser `fde_app` role), then use `PostgresStore`
with your DSN in place of `SQLiteStore`.

## Tests

```bash
python3 -m pytest tests/ -q
```

Measured results on the seeded fixtures (two tenants, 7 usage events):

- **41 passed, 1 skipped** — the skip is the optional Postgres
  integration test, which runs when `FDE_TEST_PG_DSN` points at a
  migrated database and skips cleanly otherwise.
- Isolation: tenant B listing, reading, updating, deleting, or
  referencing tenant A's projects and events yields nothing in every
  case, including by direct id.
- Analytics fixture check: tenant A totals are exactly
  `api_calls=1000, storage_gb=80, compute_seconds=1800` across 5 events
  and 2 active users; tenant B sees only its own 2 events.
- Billing fixture check: tenant A's invoice totals exactly **$28.00**,
  tenant B's **$1.50**. Tier boundaries are pinned exactly (1,000th API
  call bills at the first-tier rate, the 1,001st at the second).
- Local in-process benchmark (FastAPI TestClient, SQLite backend):
  `/analytics/summary` sustains ~372 requests/second sequential on a
  2-core VM. That is a correctness-harness number, not a production
  load test.

## Scope honesty

This is a platform core / demonstration service, not a hosted product:
auth is a fixture API-key check with deliberately synthetic keys,
tenants and seed data are fixtures, and billing stops at computing the
invoice. The production-shaped parts — RLS schema, tenant-context
discipline, repository isolation contract, tiered pricing math — are
real and fully tested.

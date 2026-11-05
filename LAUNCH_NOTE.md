# Launch note — fde-multitenant-saas (20-point pre-launch checklist)

1. **Tests green** — PASS: `python3 -m pytest tests/ -q` → 41 passed, 1 skipped (optional Postgres test, skips cleanly without a DSN).
2. **No real secrets** — PASS: only synthetic fixture values (`fixture-key-tenant-a/b`); no realistic credential literal anywhere in the tree.
3. **No private/personal data** — PASS: tenants, users, emails (`*.example`) and usage data are invented fixtures.
4. **No payment integration** — PASS: billing is pure computation; no Stripe or payment-provider code or calls exist.
5. **Free tier only / $0 cost** — PASS: Python stdlib + open-source packages already installed; no paid service is used or required.
6. **No network calls at runtime or in tests** — PASS: API and tests run fully locally; TestClient is in-process.
7. **Deterministic fixtures** — PASS: seed ids, quantities and expected totals are fixed constants in `fixtures.py`; tests pin exact numbers.
8. **README verified against reality** — PASS: every number in the README (41 passed/1 skipped, $28.00 / $1.50 invoices, ~372 req/s) was measured in this build session.
9. **README free of internal process language** — PASS: public-facing wording only; no staging/pipeline references.
10. **No binary files** — PASS: source, SQL and Markdown only; `.gitignore` excludes local DB files and caches.
11. **Cross-tenant isolation tested** — PASS: list/get/update/delete/reference-by-id isolation tests all pass on the repository and API layers.
12. **Auth failure modes tested** — PASS: missing headers, wrong key, cross-tenant key, unknown tenant all rejected (401/422) in tests.
13. **Billing math pinned** — PASS: tier boundary cases (at-cap, one-over, deep second tier, zero) asserted exactly with `Decimal`.
14. **Postgres migration is real DDL** — PASS: `migrations/001_rls.sql` creates tables, indexes, RLS policies keyed on `current_setting('app.tenant_id')`, and documents the non-superuser app role.
15. **Live Postgres run** — N/A: server binaries exist on the build VM but cannot be started by the available unprivileged user; integration test is provided, skips cleanly, and is runnable via `FDE_TEST_PG_DSN`.
16. **License/attribution** — N/A: no third-party code is vendored; dependencies are standard open-source packages declared in `pyproject.toml`.
17. **No external submissions made** — PASS: local build only; nothing pushed, published, or sent anywhere.
18. **Error behavior is leak-safe** — PASS: cross-tenant ids return 404 (not 403), so resource existence never leaks between tenants.
19. **Scope honesty documented** — PASS: README states plainly that auth is fixture-based and billing is computation only.
20. **Reproducible from a clean checkout** — PASS: `pip install -r requirements.txt` plus the documented pytest/uvicorn commands reproduce everything; default test run needs no database server.

Verdict: all items PASS or N/A with reason. Cleared for the ship lane.

"""FastAPI application: every request runs inside a tenant context.

Auth is a fixture check (see config.py): the caller sends
``X-Tenant-Id`` and ``X-Api-Key``; the key must be the fixture key issued
for that exact tenant. A valid key for tenant B presented with tenant A's
id is rejected — the key, not the header, decides who you are.
"""
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from .config import FIXTURE_API_KEYS
from .context import TenantContext
from .db import SQLiteStore
from .fixtures import seed_store
from .repository import TenantRepository
from .schemas import (
    ProjectCreate,
    ProjectOut,
    ProjectUpdate,
    UsageEventCreate,
    UsageEventOut,
)


def get_context(
    x_tenant_id: str = Header(...),
    x_api_key: str = Header(...),
) -> TenantContext:
    expected = FIXTURE_API_KEYS.get(x_tenant_id)
    if expected is None or x_api_key != expected:
        raise HTTPException(status_code=401, detail="invalid tenant credentials")
    return TenantContext(tenant_id=x_tenant_id)


def create_app(store: SQLiteStore | None = None, seed: bool = True) -> FastAPI:
    store = store or SQLiteStore()
    if seed:
        seed_store(store)

    app = FastAPI(title="fde-multitenant-saas", version="0.1.0")
    app.state.store = store

    # Every handler below opens one short-lived session bound to the
    # caller's tenant (``with store.session(ctx)``) — there is no code path
    # that touches tenant data without a TenantContext.

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/projects", response_model=ProjectOut, status_code=201)
    def create_project(body: ProjectCreate, ctx: TenantContext = Depends(get_context)):
        with store.session(ctx) as s:
            return TenantRepository(s).create_project(body.name, body.description)

    @app.get("/projects", response_model=list[ProjectOut])
    def list_projects(ctx: TenantContext = Depends(get_context)):
        with store.session(ctx) as s:
            return TenantRepository(s).list_projects()

    @app.get("/projects/{project_id}", response_model=ProjectOut)
    def get_project(project_id: str, ctx: TenantContext = Depends(get_context)):
        with store.session(ctx) as s:
            project = TenantRepository(s).get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return project

    @app.patch("/projects/{project_id}", response_model=ProjectOut)
    def update_project(
        project_id: str, body: ProjectUpdate, ctx: TenantContext = Depends(get_context)
    ):
        with store.session(ctx) as s:
            project = TenantRepository(s).update_project(
                project_id, name=body.name, description=body.description
            )
        if project is None:
            raise HTTPException(status_code=404, detail="project not found")
        return project

    @app.delete("/projects/{project_id}", status_code=204)
    def delete_project(project_id: str, ctx: TenantContext = Depends(get_context)):
        with store.session(ctx) as s:
            deleted = TenantRepository(s).delete_project(project_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="project not found")
        return None

    @app.post("/usage/events", response_model=UsageEventOut, status_code=201)
    def record_event(body: UsageEventCreate, ctx: TenantContext = Depends(get_context)):
        try:
            body.validate_meter()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        with store.session(ctx) as s:
            repo = TenantRepository(s)
            try:
                return repo.record_event(
                    body.user_id, body.meter, body.quantity, project_id=body.project_id
                )
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/analytics/summary")
    def analytics_summary(
        days: int = Query(default=30, ge=1, le=366),
        ctx: TenantContext = Depends(get_context),
    ):
        with store.session(ctx) as s:
            return TenantRepository(s).analytics_summary(days=days)

    @app.get("/billing/invoice")
    def billing_invoice(
        days: int = Query(default=30, ge=1, le=366),
        ctx: TenantContext = Depends(get_context),
    ):
        with store.session(ctx) as s:
            return TenantRepository(s).invoice(days=days).to_dict()

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)

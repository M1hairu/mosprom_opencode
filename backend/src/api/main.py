"""FastAPI: /api/*. The SPA is served by nginx (service web in docker-compose.yml)."""

import os

from fastapi import FastAPI

from api import analytics, auth, content_edits, leads, site_documents, visits
from api.contracts import Health, PlanDocument, ValidateResponse
from api.validation import validate_plan

app = FastAPI(title="LASSARD showroom")
app.include_router(auth.router)
app.include_router(site_documents.router)
app.include_router(content_edits.router)
app.include_router(visits.router)
app.include_router(leads.router)
app.include_router(analytics.router)


@app.get("/api/health")
def health() -> Health:
    return Health(status="ok", sha=os.environ.get("GIT_SHA", "unknown"))


@app.post("/api/validate")
def validate(plan: PlanDocument) -> ValidateResponse:
    return ValidateResponse(findings=validate_plan(plan))

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from .db import connector_states, initialize
from .demo_data import dashboard

app = FastAPI(
    title="GE360 Analitica API",
    version="0.1.0",
    description="API centrale per analytics, attribuzione e connettori GE360.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    initialize()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "ge360-analitica", "version": "0.1.0"}


@app.get("/api/dashboard")
def get_dashboard(period: str = Query("30d", pattern="^(7d|30d|90d|365d)$")) -> dict:
    return dashboard(period)


@app.get("/api/connectors")
def get_connectors() -> dict:
    return {"items": connector_states()}


@app.get("/")
def root() -> dict:
    return {
        "name": "GE360 Analitica",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }

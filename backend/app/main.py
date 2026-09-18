from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .connectors.registry import diagnostics
from .connectors.wordpress import WordPressConnector
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


@app.get("/api/connectors/diagnostics")
def get_connector_diagnostics() -> dict:
    return {"items": [item.__dict__ for item in diagnostics()]}


@app.post("/api/connectors/wordpress/test")
async def test_wordpress_connector() -> dict:
    connector = WordPressConnector()
    try:
        result = await connector.sync()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"WordPress non raggiungibile: {exc}") from exc

    return {
        "provider": result.provider,
        "ok": result.ok,
        "metrics": result.metrics,
        "message": result.message,
    }


@app.get("/")
def root() -> dict:
    return {
        "name": "GE360 Analitica",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
        "chatgpt_integration": "MCP plugin",
    }

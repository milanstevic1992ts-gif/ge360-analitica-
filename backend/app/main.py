from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .agent import agent_health, ask_agent
from .connectors.registry import diagnostics
from .connectors.wordpress import WordPressConnector
from .db import connector_states, initialize
from .demo_data import dashboard

app = FastAPI(
    title="GE360 Analitica API",
    version="0.1.0",
    description="API centrale per analytics, attribuzione e connettori GE360.",
)

class AgentAskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    period: str = Field(default="30d", pattern="^(7d|30d|90d|365d)$")


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


@app.get("/api/agent/health")
async def get_agent_health() -> dict:
    try:
        return await agent_health()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Agent Bridge non disponibile: {exc}") from exc


@app.post("/api/agent/ask")
async def ask_ge360_agent(request: AgentAskRequest) -> dict:
    context = dashboard(request.period)
    try:
        return await ask_agent(request.question, context)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Errore agente Codex CLI: {exc}") from exc


@app.get("/")
def root() -> dict:
    return {
        "name": "GE360 Analitica",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
    }

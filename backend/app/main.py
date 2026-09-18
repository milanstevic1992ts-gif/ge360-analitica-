from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from . import analytics
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


@app.get("/api/analytics/status")
def analytics_status() -> dict:
    return analytics.status()


@app.get("/api/analytics/metrics")
def analytics_metrics(
    days: int = Query(30, ge=1, le=3650),
    provider: str | None = None,
    metric: str | None = None,
    limit: int = Query(200, ge=1, le=500),
) -> list[dict]:
    return analytics.metrics(days=days, provider=provider, metric=metric, limit=limit)


@app.get("/api/analytics/events-summary")
def analytics_events_summary(days: int = Query(30, ge=1, le=3650)) -> list[dict]:
    return analytics.events_summary(days=days)


@app.get("/api/analytics/leads-summary")
def analytics_leads_summary(days: int = Query(30, ge=1, le=3650)) -> dict:
    return analytics.leads_summary(days=days)


@app.get("/api/analytics/recent-leads")
def analytics_recent_leads(
    days: int = Query(30, ge=1, le=3650),
    limit: int = Query(50, ge=1, le=100),
) -> list[dict]:
    return analytics.recent_leads(days=days, limit=limit)


@app.get("/api/analytics/compare")
def analytics_compare(
    metric: str,
    provider: str | None = None,
    days: int = Query(7, ge=1, le=365),
) -> dict:
    return analytics.compare_periods(metric=metric, provider=provider, days=days)


@app.get("/api/analytics/opportunities")
def analytics_opportunities(
    days: int = Query(30, ge=1, le=365),
    min_views: int = Query(20, ge=1, le=1000000),
    limit: int = Query(20, ge=1, le=50),
) -> list[dict]:
    return analytics.opportunity_radar(days=days, min_views=min_views, limit=limit)


@app.get("/api/analytics/content-performance")
def analytics_content_performance(
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(25, ge=1, le=100),
) -> list[dict]:
    return analytics.content_performance(days=days, limit=limit)


@app.get("/api/analytics/anomalies")
def analytics_anomalies(
    days: int = Query(7, ge=1, le=90),
    threshold_percent: float = Query(30.0, ge=5.0, le=500.0),
    limit: int = Query(30, ge=1, le=100),
) -> list[dict]:
    return analytics.anomalies(days=days, threshold_percent=threshold_percent, limit=limit)


@app.get("/api/analytics/local-seo")
def analytics_local_seo(
    days: int = Query(30, ge=1, le=365),
    contains: str = "trieste",
    limit: int = Query(50, ge=1, le=100),
) -> list[dict]:
    return analytics.local_seo(days=days, contains=contains, limit=limit)


@app.get("/")
def root() -> dict:
    return {
        "name": "GE360 Analitica",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
        "chatgpt_integration": "MCP plugin",
    }

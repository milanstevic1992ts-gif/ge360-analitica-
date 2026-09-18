import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from . import analytics, google_oauth, local_ai, setup_wizard
from .background import auto_sync_enabled, periodic_sync
from .connectors.registry import diagnostics
from .connectors.wordpress import WordPressConnector
from .db import connector_states, initialize
from .dashboard_service import dashboard
from .sync import sync_all, sync_provider

app = FastAPI(
    title="GE360 Analitica API",
    version="0.4.0",
    description="API centrale per analytics, attribuzione e connettori GE360.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


_sync_task: asyncio.Task | None = None


@app.on_event("startup")
def startup() -> None:
    global _sync_task
    initialize()
    if auto_sync_enabled():
        _sync_task = asyncio.create_task(periodic_sync())


@app.on_event("shutdown")
async def shutdown() -> None:
    global _sync_task
    if _sync_task:
        _sync_task.cancel()
        try:
            await _sync_task
        except asyncio.CancelledError:
            pass
        _sync_task = None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "service": "ge360-analitica", "version": "0.4.0"}


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


@app.get("/api/oauth/google/start")
def google_oauth_start() -> dict:
    try:
        return {"authorization_url": google_oauth.authorization_url()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/oauth/google/callback")
async def google_oauth_callback(code: str, state: str):
    try:
        await google_oauth.exchange_code(code, state)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"OAuth Google fallito: {exc}") from exc

    return RedirectResponse("http://127.0.0.1:8788/?google=connected", status_code=302)


@app.post("/api/oauth/google/disconnect")
def google_oauth_disconnect() -> dict:
    google_oauth.disconnect()
    return {"ok": True}


@app.post("/api/sync")
async def run_sync_all() -> dict:
    return await sync_all()


@app.post("/api/sync/{provider}")
async def run_sync_provider(provider: str) -> dict:
    try:
        return await sync_provider(provider)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sync {provider} fallita: {exc}") from exc


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


@app.get("/api/setup/status")
async def setup_status() -> dict:
    return await setup_wizard.status()


@app.post("/api/setup/wordpress")
async def setup_wordpress(request: setup_wizard.WordPressSetupRequest) -> dict:
    try:
        return await setup_wizard.save_and_test_wordpress(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Test WordPress fallito: {exc}") from exc


@app.post("/api/setup/google")
def setup_google(request: setup_wizard.GoogleSetupRequest) -> dict:
    return setup_wizard.save_google(request)


@app.get("/api/setup/google/discover")
async def setup_google_discover() -> dict:
    try:
        return await setup_wizard.discover_google_resources()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scoperta Google fallita: {exc}") from exc


@app.post("/api/setup/meta")
async def setup_meta(request: setup_wizard.MetaSetupRequest) -> dict:
    try:
        return await setup_wizard.save_and_test_meta(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Test Meta fallito: {exc}") from exc


@app.get("/api/local-ai/status")
async def local_ai_status() -> dict:
    return await local_ai.status()


@app.post("/api/local-ai/configure")
def local_ai_configure(request: local_ai.LocalAIConfigureRequest) -> dict:
    try:
        return local_ai.save_settings(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/local-ai/test")
async def local_ai_test() -> dict:
    result = await local_ai.status()
    if not result["ok"]:
        raise HTTPException(status_code=502, detail=result["message"])
    if not result["selected_available"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@app.post("/api/local-ai/report")
async def local_ai_report(request: local_ai.LocalAIReportRequest) -> dict:
    try:
        return await local_ai.generate_report(request)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Analisi locale fallita: {exc}") from exc


@app.get("/api/local-ai/reports")
def local_ai_reports(limit: int = Query(20, ge=1, le=100)) -> dict:
    return {"items": local_ai.reports(limit=limit)}


@app.get("/api/local-ai/reports/{report_id}")
def local_ai_report_detail(report_id: int) -> dict:
    result = local_ai.report(report_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Report non trovato")
    return result


@app.get("/api/info")
def root() -> dict:
    return {
        "name": "GE360 Analitica",
        "status": "running",
        "docs": "/docs",
        "health": "/api/health",
        "local_ai": "Ollama/Qwen",
    }


_frontend_dir = Path(os.getenv("GE360_FRONTEND_DIR", "")).expanduser()
if str(_frontend_dir) and _frontend_dir.is_dir():
    app.mount(
        "/",
        StaticFiles(directory=str(_frontend_dir), html=True),
        name="ge360-dashboard",
    )

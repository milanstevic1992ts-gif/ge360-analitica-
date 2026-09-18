import json
import os
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from mcp.server import MCPServer
from mcp.types import ToolAnnotations


API_BASE = os.getenv("GE360_API_BASE", "http://127.0.0.1:8787").rstrip("/")
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    idempotent_hint=True,
    open_world_hint=False,
)

mcp = MCPServer(
    "GE360 Analitica",
    instructions=(
        "GE360 Analitica espone dati analytics dell'attività in sola lettura. "
        "Usa gli strumenti per basare le risposte su dati reali GE360. "
        "Non inventare metriche o cause. Distingui sempre fatti, confronti e interpretazioni. "
        "Se il database è vuoto o incompleto, dichiaralo chiaramente."
    ),
)


def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    url = f"{API_BASE}{path}"
    if params:
        clean = {key: value for key, value in params.items() if value is not None}
        if clean:
            url = f"{url}?{urlencode(clean)}"

    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GE360-ChatGPT-MCP/0.2",
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=20) as response:
            payload = response.read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(
            "GE360 API non raggiungibile. Verifica che docker compose sia attivo "
            f"e che {API_BASE} risponda. Dettaglio: {exc}"
        ) from exc

    return json.loads(payload)


@mcp.tool(
    title="Stato GE360",
    annotations=READ_ONLY,
)
def ge360_status() -> dict[str, Any]:
    """Controlla quantità di dati, ultimo aggiornamento e stato dei connettori GE360."""
    return _get("/api/analytics/status")


@mcp.tool(
    title="Metriche GE360",
    annotations=READ_ONLY,
)
def ge360_metrics(
    days: int = 30,
    provider: str | None = None,
    metric: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Legge metriche normalizzate per periodo, piattaforma o nome metrica."""
    return _get(
        "/api/analytics/metrics",
        {
            "days": days,
            "provider": provider,
            "metric": metric,
            "limit": limit,
        },
    )


@mcp.tool(
    title="Riepilogo eventi",
    annotations=READ_ONLY,
)
def ge360_events_summary(days: int = 30) -> list[dict[str, Any]]:
    """Riassume visite e azioni tracciate, raggruppate per tipo e sorgente."""
    return _get("/api/analytics/events-summary", {"days": days})


@mcp.tool(
    title="Riepilogo lead",
    annotations=READ_ONLY,
)
def ge360_leads_summary(days: int = 30) -> dict[str, Any]:
    """Riassume lead per canale e sorgente senza esporre payload o dati personali."""
    return _get("/api/analytics/leads-summary", {"days": days})


@mcp.tool(
    title="Lead recenti",
    annotations=READ_ONLY,
)
def ge360_recent_leads(days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    """Restituisce soltanto campi analitici dei lead recenti, senza payload personali."""
    return _get(
        "/api/analytics/recent-leads",
        {"days": days, "limit": limit},
    )


@mcp.tool(
    title="Confronta una metrica",
    annotations=READ_ONLY,
)
def ge360_compare_periods(
    metric: str,
    provider: str | None = None,
    days: int = 7,
) -> dict[str, Any]:
    """Confronta una metrica nel periodo recente con il periodo precedente equivalente."""
    return _get(
        "/api/analytics/compare",
        {"metric": metric, "provider": provider, "days": days},
    )


@mcp.tool(
    title="Opportunity Radar",
    annotations=READ_ONLY,
)
def ge360_opportunity_radar(
    days: int = 30,
    min_views: int = 20,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Trova pagine con traffico significativo ma conversione lead debole."""
    return _get(
        "/api/analytics/opportunities",
        {"days": days, "min_views": min_views, "limit": limit},
    )


@mcp.tool(
    title="Prestazioni contenuti",
    annotations=READ_ONLY,
)
def ge360_content_performance(
    days: int = 30,
    limit: int = 25,
) -> list[dict[str, Any]]:
    """Unisce visite, click WhatsApp, chiamate, moduli e lead per pagina."""
    return _get(
        "/api/analytics/content-performance",
        {"days": days, "limit": limit},
    )


@mcp.tool(
    title="Anomaly Watch",
    annotations=READ_ONLY,
)
def ge360_anomalies(
    days: int = 7,
    threshold_percent: float = 30.0,
    limit: int = 30,
) -> list[dict[str, Any]]:
    """Segnala variazioni anomale tra il periodo recente e quello precedente."""
    return _get(
        "/api/analytics/anomalies",
        {
            "days": days,
            "threshold_percent": threshold_percent,
            "limit": limit,
        },
    )


@mcp.tool(
    title="SEO locale",
    annotations=READ_ONLY,
)
def ge360_local_seo(
    days: int = 30,
    contains: str = "trieste",
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Legge query Search Console locali che contengono una parola o località."""
    return _get(
        "/api/analytics/local-seo",
        {"days": days, "contains": contains, "limit": limit},
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")

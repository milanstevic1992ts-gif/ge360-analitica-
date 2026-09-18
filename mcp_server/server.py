import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mcp.server.mcpserver import MCPServer


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.getenv("GE360_MCP_DB_PATH", ROOT / "data" / "ge360.db")).resolve()

mcp = MCPServer(
    "GE360 Analitica",
    instructions=(
        "GE360 Analitica espone esclusivamente dati analytics locali in sola lettura. "
        "Usa questi strumenti per rispondere a domande su traffico, sorgenti, eventi, lead "
        "e stato dei connettori. Non inventare dati mancanti e segnala quando lo storico "
        "non è ancora sufficiente."
    ),
)


def _connect_readonly() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(
            f"Database GE360 non trovato: {DB_PATH}. Avvia prima GE360 Analitica."
        )

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _cutoff(days: int) -> str:
    days = max(1, min(days, 3650))
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@mcp.tool()
def ge360_status() -> dict[str, Any]:
    """Mostra stato del database e dei connettori GE360 senza esporre credenziali."""
    with _connect_readonly() as conn:
        connectors = conn.execute(
            """
            SELECT provider, status, last_sync, message
            FROM connector_state
            ORDER BY provider
            """
        ).fetchall()

        counts = {}
        for table in ("metric_snapshots", "events", "leads"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    return {
        "database": str(DB_PATH),
        "read_only": True,
        "records": counts,
        "connectors": [dict(row) for row in connectors],
    }


@mcp.tool()
def ge360_metrics(
    days: int = 30,
    provider: str | None = None,
    metric: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Legge le metriche normalizzate GE360 per periodo, provider o nome metrica."""
    limit = max(1, min(limit, 500))
    clauses = ["captured_at >= ?"]
    params: list[Any] = [_cutoff(days)]

    if provider:
        clauses.append("provider = ?")
        params.append(provider)
    if metric:
        clauses.append("metric = ?")
        params.append(metric)

    params.append(limit)
    query = f"""
        SELECT provider, metric, value, dimension, dimension_value, captured_at
        FROM metric_snapshots
        WHERE {' AND '.join(clauses)}
        ORDER BY captured_at DESC
        LIMIT ?
    """

    with _connect_readonly() as conn:
        rows = conn.execute(query, params).fetchall()

    return [dict(row) for row in rows]


@mcp.tool()
def ge360_events_summary(days: int = 30) -> list[dict[str, Any]]:
    """Riassume gli eventi GE360 per tipo e sorgente senza restituire payload grezzi."""
    with _connect_readonly() as conn:
        rows = conn.execute(
            """
            SELECT
                event_type,
                COALESCE(source, 'non_attribuita') AS source,
                COUNT(*) AS events
            FROM events
            WHERE occurred_at >= ?
            GROUP BY event_type, COALESCE(source, 'non_attribuita')
            ORDER BY events DESC
            """,
            (_cutoff(days),),
        ).fetchall()

    return [dict(row) for row in rows]


@mcp.tool()
def ge360_leads_summary(days: int = 30) -> dict[str, Any]:
    """Riassume lead, canali, sorgenti e valore senza esporre dati personali o payload."""
    cutoff = _cutoff(days)

    with _connect_readonly() as conn:
        total_row = conn.execute(
            """
            SELECT
                COUNT(*) AS leads,
                COALESCE(SUM(value), 0) AS total_value
            FROM leads
            WHERE created_at >= ?
            """,
            (cutoff,),
        ).fetchone()

        by_channel = conn.execute(
            """
            SELECT channel, COUNT(*) AS leads, COALESCE(SUM(value), 0) AS total_value
            FROM leads
            WHERE created_at >= ?
            GROUP BY channel
            ORDER BY leads DESC
            """,
            (cutoff,),
        ).fetchall()

        by_source = conn.execute(
            """
            SELECT COALESCE(source, 'non_attribuita') AS source, COUNT(*) AS leads
            FROM leads
            WHERE created_at >= ?
            GROUP BY COALESCE(source, 'non_attribuita')
            ORDER BY leads DESC
            LIMIT 20
            """,
            (cutoff,),
        ).fetchall()

    return {
        "days": max(1, min(days, 3650)),
        "total": dict(total_row),
        "by_channel": [dict(row) for row in by_channel],
        "by_source": [dict(row) for row in by_source],
    }


@mcp.tool()
def ge360_recent_leads(days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    """Elenca solo i campi analitici dei lead recenti; non restituisce payload o dati personali."""
    limit = max(1, min(limit, 100))

    with _connect_readonly() as conn:
        rows = conn.execute(
            """
            SELECT channel, source, landing_page, campaign, status, value, created_at
            FROM leads
            WHERE created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (_cutoff(days), limit),
        ).fetchall()

    return [dict(row) for row in rows]


@mcp.tool()
def ge360_compare_periods(metric: str, provider: str | None = None, days: int = 7) -> dict[str, Any]:
    """Confronta la somma di una metrica tra il periodo recente e quello precedente."""
    days = max(1, min(days, 365))
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    clauses = ["metric = ?"]
    base_params: list[Any] = [metric]
    if provider:
        clauses.append("provider = ?")
        base_params.append(provider)

    where = " AND ".join(clauses)

    with _connect_readonly() as conn:
        current = conn.execute(
            f"""
            SELECT COALESCE(SUM(value), 0)
            FROM metric_snapshots
            WHERE {where} AND captured_at >= ? AND captured_at < ?
            """,
            [*base_params, current_start.isoformat(), now.isoformat()],
        ).fetchone()[0]

        previous = conn.execute(
            f"""
            SELECT COALESCE(SUM(value), 0)
            FROM metric_snapshots
            WHERE {where} AND captured_at >= ? AND captured_at < ?
            """,
            [*base_params, previous_start.isoformat(), current_start.isoformat()],
        ).fetchone()[0]

    change_percent = None
    if previous:
        change_percent = round(((current - previous) / previous) * 100, 2)

    return {
        "metric": metric,
        "provider": provider,
        "days": days,
        "current": current,
        "previous": previous,
        "change_percent": change_percent,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")

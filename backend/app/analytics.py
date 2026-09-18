from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from .db import connect, connector_states


def _days(value: int, maximum: int = 3650) -> int:
    return max(1, min(int(value), maximum))


def _cutoff(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=_days(days))).isoformat()


def status() -> dict[str, Any]:
    with connect() as conn:
        counts = {}
        for table in ("metric_snapshots", "events", "leads"):
            counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

        latest_metric = conn.execute(
            "SELECT MAX(captured_at) FROM metric_snapshots"
        ).fetchone()[0]
        latest_event = conn.execute(
            "SELECT MAX(occurred_at) FROM events"
        ).fetchone()[0]
        latest_lead = conn.execute(
            "SELECT MAX(created_at) FROM leads"
        ).fetchone()[0]

    return {
        "read_only_surface": True,
        "records": counts,
        "latest": {
            "metric": latest_metric,
            "event": latest_event,
            "lead": latest_lead,
        },
        "connectors": connector_states(),
    }


def metrics(
    days: int = 30,
    provider: str | None = None,
    metric: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    days = _days(days)
    limit = max(1, min(int(limit), 500))
    clauses = ["captured_at >= ?"]
    params: list[Any] = [_cutoff(days)]

    if provider:
        clauses.append("provider = ?")
        params.append(provider)
    if metric:
        clauses.append("metric = ?")
        params.append(metric)

    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT provider, metric, value, dimension, dimension_value, captured_at
            FROM metric_snapshots
            WHERE {' AND '.join(clauses)}
            ORDER BY captured_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()

    return [dict(row) for row in rows]


def events_summary(days: int = 30) -> list[dict[str, Any]]:
    with connect() as conn:
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


def leads_summary(days: int = 30) -> dict[str, Any]:
    days = _days(days)
    cutoff = _cutoff(days)

    with connect() as conn:
        total = conn.execute(
            """
            SELECT COUNT(*) AS leads, COALESCE(SUM(value), 0) AS total_value
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
            LIMIT 25
            """,
            (cutoff,),
        ).fetchall()

    return {
        "days": days,
        "total": dict(total),
        "by_channel": [dict(row) for row in by_channel],
        "by_source": [dict(row) for row in by_source],
    }


def recent_leads(days: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 100))
    with connect() as conn:
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


def compare_periods(
    metric: str,
    provider: str | None = None,
    days: int = 7,
) -> dict[str, Any]:
    days = _days(days, 365)
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    clauses = ["metric = ?"]
    base_params: list[Any] = [metric]
    if provider:
        clauses.append("provider = ?")
        base_params.append(provider)
    where = " AND ".join(clauses)

    with connect() as conn:
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


def opportunity_radar(days: int = 30, min_views: int = 20, limit: int = 20) -> list[dict[str, Any]]:
    days = _days(days, 365)
    min_views = max(1, int(min_views))
    limit = max(1, min(int(limit), 50))
    cutoff = _cutoff(days)

    with connect() as conn:
        views = conn.execute(
            """
            SELECT url, COUNT(*) AS views
            FROM events
            WHERE occurred_at >= ?
              AND event_type = 'page_view'
              AND url IS NOT NULL
              AND url != ''
            GROUP BY url
            HAVING COUNT(*) >= ?
            """,
            (cutoff, min_views),
        ).fetchall()

        leads = conn.execute(
            """
            SELECT landing_page, COUNT(*) AS leads
            FROM leads
            WHERE created_at >= ?
              AND landing_page IS NOT NULL
              AND landing_page != ''
            GROUP BY landing_page
            """,
            (cutoff,),
        ).fetchall()

    lead_map = {row["landing_page"]: row["leads"] for row in leads}
    items = []
    for row in views:
        view_count = int(row["views"])
        lead_count = int(lead_map.get(row["url"], 0))
        conversion = (lead_count / view_count * 100) if view_count else 0
        opportunity_score = round(view_count / (1 + lead_count), 2)
        items.append(
            {
                "url": row["url"],
                "views": view_count,
                "leads": lead_count,
                "conversion_percent": round(conversion, 2),
                "opportunity_score": opportunity_score,
            }
        )

    items.sort(key=lambda item: (-item["opportunity_score"], -item["views"]))
    return items[:limit]


def content_performance(days: int = 30, limit: int = 25) -> list[dict[str, Any]]:
    days = _days(days, 365)
    limit = max(1, min(int(limit), 100))
    cutoff = _cutoff(days)

    with connect() as conn:
        event_rows = conn.execute(
            """
            SELECT
                url,
                COUNT(*) AS total_events,
                SUM(CASE WHEN event_type = 'page_view' THEN 1 ELSE 0 END) AS page_views,
                SUM(CASE WHEN event_type = 'whatsapp_click' THEN 1 ELSE 0 END) AS whatsapp_clicks,
                SUM(CASE WHEN event_type = 'phone_click' THEN 1 ELSE 0 END) AS phone_clicks,
                SUM(CASE WHEN event_type = 'form_submit' THEN 1 ELSE 0 END) AS form_submits
            FROM events
            WHERE occurred_at >= ?
              AND url IS NOT NULL
              AND url != ''
            GROUP BY url
            ORDER BY total_events DESC
            LIMIT ?
            """,
            (cutoff, limit),
        ).fetchall()

        lead_rows = conn.execute(
            """
            SELECT landing_page, COUNT(*) AS leads
            FROM leads
            WHERE created_at >= ?
            GROUP BY landing_page
            """,
            (cutoff,),
        ).fetchall()

    lead_map = {row["landing_page"]: row["leads"] for row in lead_rows}
    result = []
    for row in event_rows:
        item = dict(row)
        item["leads"] = int(lead_map.get(item["url"], 0))
        views = int(item.get("page_views") or 0)
        item["lead_conversion_percent"] = round(item["leads"] / views * 100, 2) if views else None
        result.append(item)
    return result


def anomalies(days: int = 7, threshold_percent: float = 30.0, limit: int = 30) -> list[dict[str, Any]]:
    days = _days(days, 90)
    threshold = max(5.0, min(float(threshold_percent), 500.0))
    limit = max(1, min(int(limit), 100))
    now = datetime.now(timezone.utc)
    current_start = now - timedelta(days=days)
    previous_start = current_start - timedelta(days=days)

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT provider, metric, DATE(captured_at) AS day, SUM(value) AS daily_value
            FROM metric_snapshots
            WHERE captured_at >= ?
            GROUP BY provider, metric, DATE(captured_at)
            ORDER BY day
            """,
            (previous_start.isoformat(),),
        ).fetchall()

    series: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(
        lambda: {"current": [], "previous": []}
    )
    for row in rows:
        day = datetime.fromisoformat(f"{row['day']}T00:00:00+00:00")
        bucket = "current" if day >= current_start else "previous"
        series[(row["provider"], row["metric"])][bucket].append(float(row["daily_value"]))

    findings = []
    for (provider, metric), buckets in series.items():
        if not buckets["current"] or not buckets["previous"]:
            continue
        current_avg = sum(buckets["current"]) / len(buckets["current"])
        previous_avg = sum(buckets["previous"]) / len(buckets["previous"])
        if previous_avg == 0:
            continue
        change = ((current_avg - previous_avg) / previous_avg) * 100
        if abs(change) < threshold:
            continue
        findings.append(
            {
                "provider": provider,
                "metric": metric,
                "current_daily_average": round(current_avg, 2),
                "previous_daily_average": round(previous_avg, 2),
                "change_percent": round(change, 2),
                "direction": "up" if change > 0 else "down",
            }
        )

    findings.sort(key=lambda item: abs(item["change_percent"]), reverse=True)
    return findings[:limit]


def local_seo(days: int = 30, contains: str = "trieste", limit: int = 50) -> list[dict[str, Any]]:
    days = _days(days, 365)
    limit = max(1, min(int(limit), 100))
    needle = (contains or "trieste").strip().lower()

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                dimension_value AS query,
                metric,
                SUM(value) AS value
            FROM metric_snapshots
            WHERE captured_at >= ?
              AND provider = 'search_console'
              AND LOWER(COALESCE(dimension, '')) = 'query'
              AND LOWER(COALESCE(dimension_value, '')) LIKE ?
            GROUP BY dimension_value, metric
            ORDER BY value DESC
            LIMIT ?
            """,
            (_cutoff(days), f"%{needle}%", limit),
        ).fetchall()

    return [dict(row) for row in rows]

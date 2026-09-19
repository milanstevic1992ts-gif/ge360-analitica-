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
              -- Una sola serie "totale" per metrica: senza questo filtro le
              -- metriche scomposte per fonte, città, dispositivo, query...
              -- verrebbero sommate più volte (e CTR/posizione sommati tra loro).
              AND (
                    dimension IS NULL
                 OR (provider = 'search_console'
                     AND dimension = 'device'
                     AND metric IN ('search_clicks', 'search_impressions'))
              )
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
                provider,
                dimension_value AS query,
                metric,
                SUM(value) AS total,
                -- per la posizione serve la media pesata sulle impression
                SUM(CASE WHEN metric = 'search_position' THEN value * COALESCE((
                    SELECT i.value FROM metric_snapshots i
                    WHERE i.provider = m.provider
                      AND i.metric = 'search_impressions'
                      AND i.captured_at = m.captured_at
                      AND i.dimension = m.dimension
                      AND i.dimension_value = m.dimension_value
                ), 0) ELSE 0 END) AS weighted
            FROM metric_snapshots m
            WHERE captured_at >= ?
              AND provider IN ('search_console', 'google_business')
              AND LOWER(COALESCE(dimension, '')) = 'query'
              AND LOWER(COALESCE(dimension_value, '')) LIKE ?
            GROUP BY provider, dimension_value, metric
            """,
            (_cutoff(days), f"%{needle}%"),
        ).fetchall()

    # Clic e impression si sommano; CTR e posizione no: si ricalcolano sul
    # periodo (CTR = clic/impression, posizione media pesata sulle impression).
    grouped: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for row in rows:
        values = grouped[(row["provider"], row["query"])]
        values[row["metric"]] = float(row["total"] or 0)
        if row["metric"] == "search_position":
            values["_position_weighted"] = float(row["weighted"] or 0)

    def _reach(item: tuple[tuple[str, str], dict[str, float]]) -> float:
        values = item[1]
        return values.get("search_impressions", values.get("gbp_search_keyword_impressions", 0))

    output = []
    # Query più viste per prime, con tutte le loro metriche vicine.
    for (provider, query), values in sorted(grouped.items(), key=_reach, reverse=True):
        if provider == "search_console":
            impressions = values.get("search_impressions", 0)
            clicks = values.get("search_clicks", 0)
            if "search_ctr" in values:
                values["search_ctr"] = clicks / impressions if impressions else 0
            if "search_position" in values:
                values["search_position"] = (
                    values["_position_weighted"] / impressions if impressions else 0
                )
        for metric, value in values.items():
            if metric.startswith("_"):
                continue
            output.append(
                {
                    "provider": provider,
                    "query": query,
                    "metric": metric,
                    "value": round(value, 4),
                }
            )

    return output[:limit]


def meta_dashboard(days: int = 30) -> dict[str, Any]:
    days = _days(days, 365)
    cutoff = _cutoff(days)

    with connect() as conn:
        metric_rows = conn.execute(
            """
            SELECT metric, value, dimension, dimension_value, captured_at
            FROM metric_snapshots
            WHERE provider = 'meta' AND captured_at >= ?
            ORDER BY captured_at ASC
            """,
            (cutoff,),
        ).fetchall()

        content_rows = conn.execute(
            """
            SELECT external_id, content_type, title, url, published_at
            FROM content_items
            WHERE provider = 'meta'
              AND published_at IS NOT NULL
              AND published_at >= ?
            ORDER BY published_at DESC
            LIMIT 100
            """,
            (cutoff,),
        ).fetchall()

    rows = [dict(row) for row in metric_rows]
    contents = [dict(row) for row in content_rows]

    latest_by_metric: dict[str, dict[str, Any]] = {}
    series_by_metric: dict[str, list[dict[str, Any]]] = defaultdict(list)
    totals_by_metric: dict[str, float] = defaultdict(float)
    media_metrics: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in rows:
        metric = row["metric"]
        value = float(row["value"] or 0)
        latest_by_metric[metric] = row
        series_by_metric[metric].append(
            {"captured_at": row["captured_at"], "value": value}
        )
        totals_by_metric[metric] += value
        if row.get("dimension") == "media_id" and row.get("dimension_value"):
            media_metrics[str(row["dimension_value"])][metric] += value

    content_performance = []
    for item in contents:
        external_id = str(item.get("external_id") or "")
        media_id = external_id.removeprefix("ig:")
        metrics_for_item = dict(media_metrics.get(media_id, {}))
        if not metrics_for_item:
            continue
        engagement = sum(
            metrics_for_item.get(name, 0)
            for name in (
                "instagram_media_total_interactions",
                "instagram_media_like_count",
                "instagram_media_likes",
                "instagram_media_comments_count",
                "instagram_media_comments",
                "instagram_media_shares",
                "instagram_media_saved",
            )
        )
        reach = (
            metrics_for_item.get("instagram_media_reach", 0)
            or metrics_for_item.get("instagram_media_views", 0)
            or metrics_for_item.get("instagram_media_impressions", 0)
        )
        content_performance.append(
            {
                **item,
                "media_id": media_id,
                "reach_or_views": round(reach, 2),
                "engagement": round(engagement, 2),
                "metrics": metrics_for_item,
            }
        )

    content_performance.sort(
        key=lambda item: (item["engagement"], item["reach_or_views"]),
        reverse=True,
    )

    return {
        "days": days,
        "metric_count": len(rows),
        "available_metrics": sorted(latest_by_metric.keys()),
        "latest": {
            key: {
                "value": float(value["value"] or 0),
                "captured_at": value["captured_at"],
                "dimension": value.get("dimension"),
                "dimension_value": value.get("dimension_value"),
            }
            for key, value in latest_by_metric.items()
        },
        "totals": {key: round(value, 2) for key, value in totals_by_metric.items()},
        "series": dict(series_by_metric),
        "content_performance": content_performance[:30],
    }

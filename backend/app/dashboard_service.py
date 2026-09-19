from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Callable

from .analytics import anomalies, opportunity_radar
from .db import connect
from .demo_data import dashboard as demo_dashboard
from .event_types import CONVERSION_SQL


PERIOD_DAYS = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "365d": 365,
}


def _range(days: int, previous: bool = False) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    end = now - timedelta(days=days) if previous else now
    start = end - timedelta(days=days)
    return start.isoformat(), end.isoformat()


def _pct(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return round(((current - previous) / previous) * 100, 1)


def _scalar(query: str, params: tuple = ()) -> float:
    with connect() as conn:
        row = conn.execute(query, params).fetchone()
    return float(row[0] or 0)


def _metric_sum(
    metric_names: list[str],
    start: str,
    end: str,
    dimension: str | None = None,
) -> float:
    placeholders = ",".join("?" for _ in metric_names)
    clauses = [
        f"metric IN ({placeholders})",
        "captured_at >= ?",
        "captured_at < ?",
    ]
    params: list = [*metric_names, start, end]

    if dimension is not None:
        clauses.append("dimension = ?")
        params.append(dimension)

    return _scalar(
        f"""
        SELECT COALESCE(SUM(value), 0)
        FROM metric_snapshots
        WHERE {' AND '.join(clauses)}
        """,
        tuple(params),
    )


def _event_count(
    start: str,
    end: str,
    where: str = "1=1",
    params: tuple = (),
) -> float:
    return _scalar(
        f"""
        SELECT COUNT(*)
        FROM events
        WHERE occurred_at >= ? AND occurred_at < ? AND {where}
        """,
        (start, end, *params),
    )


def _lead_count(start: str, end: str) -> float:
    return _scalar(
        """
        SELECT COUNT(*)
        FROM leads
        WHERE created_at >= ? AND created_at < ?
        """,
        (start, end),
    )


def _visibility(start: str, end: str) -> float:
    search = _metric_sum(
        ["search_impressions"],
        start,
        end,
        dimension="query",
    )
    meta = _metric_sum(
        ["meta_page_media_view"],
        start,
        end,
    )
    if not meta:
        meta = _metric_sum(
            ["meta_page_total_media_view_unique"],
            start,
            end,
        )
    gbp = _metric_sum(
        [
            "gbp_business_impressions_desktop_maps",
            "gbp_business_impressions_desktop_search",
            "gbp_business_impressions_mobile_maps",
            "gbp_business_impressions_mobile_search",
        ],
        start,
        end,
    )
    return search + meta + gbp


def _site_visits(start: str, end: str) -> float:
    tracked = _event_count(start, end, "event_type = ?", ("page_view",))
    if tracked:
        return tracked

    return _metric_sum(
        ["ga4_screenPageViews"],
        start,
        end,
        dimension="landing_page",
    )


def _interactions(start: str, end: str) -> float:
    first_party = _event_count(
        start,
        end,
        f"event_type IN {CONVERSION_SQL}",
        (),
    )
    meta = _metric_sum(
        ["meta_page_post_engagements"],
        start,
        end,
    )
    return first_party + meta


def _has_live_data() -> bool:
    with connect() as conn:
        row = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM metric_snapshots) +
              (SELECT COUNT(*) FROM events) +
              (SELECT COUNT(*) FROM leads)
            """
        ).fetchone()
    return bool(row and row[0])


def _trend(days: int, start: str, end: str) -> list[dict]:
    with connect() as conn:
        visits = conn.execute(
            """
            SELECT DATE(occurred_at) AS day, COUNT(*) AS value
            FROM events
            WHERE occurred_at >= ? AND occurred_at < ?
              AND event_type = 'page_view'
            GROUP BY DATE(occurred_at)
            """,
            (start, end),
        ).fetchall()

        interaction_rows = conn.execute(
            f"""
            SELECT DATE(occurred_at) AS day, COUNT(*) AS value
            FROM events
            WHERE occurred_at >= ? AND occurred_at < ?
              AND event_type IN {CONVERSION_SQL}
            GROUP BY DATE(occurred_at)
            """,
            (start, end),
        ).fetchall()

        lead_rows = conn.execute(
            """
            SELECT DATE(created_at) AS day, COUNT(*) AS value
            FROM leads
            WHERE created_at >= ? AND created_at < ?
            GROUP BY DATE(created_at)
            """,
            (start, end),
        ).fetchall()

        ga4_rows = []
        if not visits:
            ga4_rows = conn.execute(
                """
                SELECT DATE(captured_at) AS day, SUM(value) AS value
                FROM metric_snapshots
                WHERE captured_at >= ? AND captured_at < ?
                  AND provider = 'ga4'
                  AND metric = 'ga4_screenPageViews'
                  AND dimension = 'landing_page'
                GROUP BY DATE(captured_at)
                """,
                (start, end),
            ).fetchall()

    visit_map = {
        row["day"]: float(row["value"] or 0)
        for row in (visits or ga4_rows)
    }
    interaction_map = {
        row["day"]: float(row["value"] or 0)
        for row in interaction_rows
    }
    lead_map = {row["day"]: float(row["value"] or 0) for row in lead_rows}

    start_day = datetime.now(timezone.utc).date() - timedelta(days=days - 1)
    result = []
    for offset in range(days):
        day = (start_day + timedelta(days=offset)).isoformat()
        result.append(
            {
                "date": day,
                "visits": round(visit_map.get(day, 0)),
                "interactions": round(interaction_map.get(day, 0)),
                "leads": round(lead_map.get(day, 0)),
            }
        )
    return result


def _sources(start: str, end: str) -> list[dict]:
    with connect() as conn:
        session_rows = conn.execute(
            """
            SELECT dimension_value AS source, SUM(value) AS visits
            FROM metric_snapshots
            WHERE captured_at >= ? AND captured_at < ?
              AND provider = 'ga4'
              AND metric = 'ga4_sessions'
              AND dimension = 'source'
            GROUP BY dimension_value
            ORDER BY visits DESC
            LIMIT 12
            """,
            (start, end),
        ).fetchall()

        lead_rows = conn.execute(
            """
            SELECT COALESCE(source, 'non_attribuita') AS source, COUNT(*) AS leads
            FROM leads
            WHERE created_at >= ? AND created_at < ?
            GROUP BY COALESCE(source, 'non_attribuita')
            """,
            (start, end),
        ).fetchall()

    leads = {row["source"]: int(row["leads"]) for row in lead_rows}
    result = []

    for row in session_rows:
        source = row["source"] or "non_attribuita"
        result.append(
            {
                "name": source,
                "visits": round(float(row["visits"] or 0)),
                "leads": leads.get(source, 0),
            }
        )

    if not result:
        for source, count in sorted(leads.items(), key=lambda item: item[1], reverse=True):
            result.append({"name": source, "visits": 0, "leads": count})

    return result[:8]


def _top_content(start: str, end: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                e.url,
                SUM(CASE WHEN e.event_type = 'page_view' THEN 1 ELSE 0 END) AS views,
                SUM(CASE WHEN e.event_type IN {CONVERSION_SQL} THEN 1 ELSE 0 END) AS actions
            FROM events e
            WHERE e.occurred_at >= ? AND e.occurred_at < ?
              AND e.url IS NOT NULL AND e.url != ''
            GROUP BY e.url
            ORDER BY views DESC, actions DESC
            LIMIT 12
            """,
            (start, end),
        ).fetchall()

        leads = conn.execute(
            """
            SELECT landing_page, COUNT(*) AS leads
            FROM leads
            WHERE created_at >= ? AND created_at < ?
            GROUP BY landing_page
            """,
            (start, end),
        ).fetchall()

        catalog = conn.execute(
            """
            SELECT url, title, content_type
            FROM content_items
            WHERE url IS NOT NULL
            """
        ).fetchall()

    lead_map = {row["landing_page"]: int(row["leads"]) for row in leads}
    title_map = {
        row["url"]: (row["title"], row["content_type"])
        for row in catalog
    }

    result = []
    for row in rows:
        title, content_type = title_map.get(
            row["url"],
            (row["url"], "Pagina"),
        )
        result.append(
            {
                "title": title or row["url"],
                "type": content_type or "Pagina",
                "views": int(row["views"] or 0),
                "actions": int(row["actions"] or 0),
                "leads": lead_map.get(row["url"], 0),
            }
        )
    return result[:8]


def _insights(days: int, sources: list[dict]) -> list[dict]:
    result = []

    if sources:
        top = sources[0]
        result.append(
            {
                "severity": "positive",
                "title": f"Sorgente principale: {top['name']}",
                "text": (
                    f"{top['visits']} visite e {top['leads']} lead attribuiti "
                    "nel periodo selezionato."
                ),
            }
        )

    opportunities = opportunity_radar(days=days, min_views=10, limit=1)
    if opportunities:
        item = opportunities[0]
        result.append(
            {
                "severity": "info",
                "title": "Opportunità di conversione",
                "text": (
                    f"{item['url']} ha {item['views']} visite e "
                    f"{item['leads']} lead."
                ),
            }
        )

    anomaly_rows = anomalies(days=min(days, 30), threshold_percent=30, limit=1)
    if anomaly_rows:
        item = anomaly_rows[0]
        result.append(
            {
                "severity": "warning" if item["direction"] == "down" else "info",
                "title": "Variazione rilevata",
                "text": (
                    f"{item['metric']} ({item['provider']}) è "
                    f"{item['change_percent']:+.1f}% rispetto al periodo precedente."
                ),
            }
        )

    if not result:
        result.append(
            {
                "severity": "info",
                "title": "Raccolta dati avviata",
                "text": "Servono più dati reali per generare segnali affidabili.",
            }
        )

    return result[:3]


def dashboard(period: str = "30d") -> dict:
    if not _has_live_data():
        return demo_dashboard(period)

    days = PERIOD_DAYS.get(period, 30)
    current_start, current_end = _range(days)
    previous_start, previous_end = _range(days, previous=True)

    current = {
        "visibility": _visibility(current_start, current_end),
        "interactions": _interactions(current_start, current_end),
        "site_visits": _site_visits(current_start, current_end),
        "leads": _lead_count(current_start, current_end),
    }
    previous = {
        "visibility": _visibility(previous_start, previous_end),
        "interactions": _interactions(previous_start, previous_end),
        "site_visits": _site_visits(previous_start, previous_end),
        "leads": _lead_count(previous_start, previous_end),
    }

    labels = {
        "visibility": "Visibilità",
        "interactions": "Interazioni",
        "site_visits": "Visite sito",
        "leads": "Lead",
    }

    kpis = [
        {
            "key": key,
            "label": labels[key],
            "value": round(value),
            "change": _pct(value, previous[key]),
            "format": "number",
        }
        for key, value in current.items()
    ]

    sources = _sources(current_start, current_end)
    actions = _event_count(
        current_start,
        current_end,
        f"event_type IN {CONVERSION_SQL}",
        (),
    )

    funnel = [
        {"label": "Impression", "value": round(current["visibility"])},
        {"label": "Visite", "value": round(current["site_visits"])},
        {"label": "Azioni", "value": round(actions)},
        {"label": "Lead", "value": round(current["leads"])},
    ]

    return {
        "mode": "live",
        "period": period,
        "kpis": kpis,
        "trend": _trend(days, current_start, current_end),
        "sources": sources,
        "funnel": funnel,
        "top_content": _top_content(current_start, current_end),
        "insights": _insights(days, sources),
    }

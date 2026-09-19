"""Analisi approfondite GE360 (0.7).

Tutto è calcolato in modo deterministico sui dati locali: nessuna chiamata
esterna, nessun modello AI. Le funzioni restituiscono strutture pronte per la
dashboard e per il server MCP.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from statistics import median
from typing import Any
from urllib.parse import urlparse

from .db import connect, get_cursor
from .event_types import CONTACT_EVENTS

try:
    from zoneinfo import ZoneInfo

    LOCAL_TZ = ZoneInfo("Europe/Rome")
except Exception:  # pragma: no cover - tzdata assente
    LOCAL_TZ = timezone.utc

WEEKDAYS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]


# --------------------------------------------------------------------------
# utilità
# --------------------------------------------------------------------------

def _days(value: int, maximum: int = 730) -> int:
    return max(1, min(int(value), maximum))


def _since(days: int) -> str:
    """Data di inizio periodo come stringa confrontabile con le date ISO salvate."""
    return (date.today() - timedelta(days=_days(days))).isoformat()


def _ratio(numerator: float, denominator: float, digits: int = 1) -> float:
    return round((numerator / denominator) * 100, digits) if denominator else 0.0


def _path(url: str | None) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        return parsed.path or "/"
    except ValueError:
        return url


def _payload(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _local(ts: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(LOCAL_TZ)


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(pct / 100 * len(ordered)) - 1))
    return ordered[index]


# --------------------------------------------------------------------------
# Pubblico
# --------------------------------------------------------------------------

def _ga4_breakdown(conn, dimension: str, since: str) -> dict[str, dict[str, float]]:
    rows = conn.execute(
        """
        SELECT dimension_value, metric, SUM(value) AS total
        FROM metric_snapshots
        WHERE provider = 'ga4' AND dimension = ? AND captured_at >= ?
        GROUP BY dimension_value, metric
        """,
        (dimension, since),
    ).fetchall()

    out: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        key = row["metric"].removeprefix("ga4_")
        out[row["dimension_value"] or "(non impostato)"][key] = float(row["total"] or 0)
    return out


def _decorate(name: str, values: dict[str, float]) -> dict[str, Any]:
    sessions = values.get("sessions", 0)
    item: dict[str, Any] = {"name": name, **{k: round(v, 2) for k, v in values.items()}}
    if sessions:
        if "engagedSessions" in values:
            item["engagement_rate"] = _ratio(values["engagedSessions"], sessions)
        if "keyEvents" in values:
            item["conversion_rate"] = _ratio(values["keyEvents"], sessions, 2)
        if "userEngagementDuration" in values:
            item["avg_engagement_sec"] = round(values["userEngagementDuration"] / sessions, 1)
    return item


def _ranked(breakdown: dict[str, dict[str, float]], limit: int, key: str = "sessions") -> list[dict]:
    items = [_decorate(name, values) for name, values in breakdown.items()]
    items.sort(key=lambda item: item.get(key, 0), reverse=True)
    return items[:limit]


def audience(days: int = 30) -> dict[str, Any]:
    since = _since(days)

    with connect() as conn:
        totals_rows = conn.execute(
            """
            SELECT metric, SUM(value) AS total
            FROM metric_snapshots
            WHERE provider = 'ga4' AND dimension IS NULL AND captured_at >= ?
            GROUP BY metric
            """,
            (since,),
        ).fetchall()
        totals = {row["metric"].removeprefix("ga4_"): float(row["total"] or 0) for row in totals_rows}

        daily = conn.execute(
            """
            SELECT substr(captured_at, 1, 10) AS day, SUM(value) AS sessions
            FROM metric_snapshots
            WHERE provider = 'ga4' AND dimension IS NULL
              AND metric = 'ga4_sessions' AND captured_at >= ?
            GROUP BY day
            """,
            (since,),
        ).fetchall()

        device = _ga4_breakdown(conn, "device", since)
        city = _ga4_breakdown(conn, "city", since)
        channel = _ga4_breakdown(conn, "channel", since)
        source_medium = _ga4_breakdown(conn, "source_medium", since)
        campaign = _ga4_breakdown(conn, "campaign", since)
        returning = _ga4_breakdown(conn, "new_vs_returning", since)
        hour = _ga4_breakdown(conn, "hour", since)

        first_party = conn.execute(
            """
            SELECT occurred_at, event_type, device, session_id
            FROM events
            WHERE occurred_at >= ? AND (event_type = 'page_view' OR event_type IN ({}))
            """.format(",".join("?" for _ in CONTACT_EVENTS)),
            (since, *CONTACT_EVENTS),
        ).fetchall()

    sessions = totals.get("sessions", 0)
    summary = {
        "sessions": round(sessions),
        "users_daily_sum": round(totals.get("totalUsers", 0)),
        "new_users": round(totals.get("newUsers", 0)),
        "page_views": round(totals.get("screenPageViews", 0)),
        "key_events": round(totals.get("keyEvents", 0)),
        "engagement_rate": _ratio(totals.get("engagedSessions", 0), sessions),
        "avg_engagement_sec": round(totals.get("userEngagementDuration", 0) / sessions, 1) if sessions else 0,
        "pages_per_session": round(totals.get("screenPageViews", 0) / sessions, 2) if sessions else 0,
        "conversion_rate": _ratio(totals.get("keyEvents", 0), sessions, 2),
    }

    weekday_sessions = [0.0] * 7
    for row in daily:
        try:
            weekday_sessions[date.fromisoformat(row["day"]).weekday()] += float(row["sessions"] or 0)
        except ValueError:
            continue

    hours = [
        {"hour": h, "sessions": round(hour.get(f"{h:02d}", hour.get(str(h), {})).get("sessions", 0))}
        for h in range(24)
    ]

    # Dati first-party: sessioni e contatti per dispositivo, orari in ora italiana.
    fp_sessions: dict[str, set] = defaultdict(set)
    fp_contacts: Counter = Counter()
    contact_hours = [0] * 24
    contact_weekdays = [0] * 7
    for row in first_party:
        dev = row["device"] or "sconosciuto"
        if row["event_type"] == "page_view":
            if row["session_id"]:
                fp_sessions[dev].add(row["session_id"])
            continue
        fp_contacts[dev] += 1
        local = _local(row["occurred_at"])
        if local:
            contact_hours[local.hour] += 1
            contact_weekdays[local.weekday()] += 1

    tracker_devices = [
        {
            "name": dev,
            "sessions": len(fp_sessions.get(dev, set())),
            "contacts": fp_contacts.get(dev, 0),
            "contact_rate": _ratio(fp_contacts.get(dev, 0), len(fp_sessions.get(dev, set()))),
        }
        for dev in sorted(set(fp_sessions) | set(fp_contacts))
    ]

    city_ranked = _ranked(city, 30)
    local_sessions = sum(
        item.get("sessions", 0) for item in city_ranked if "trieste" in item["name"].lower()
    )
    all_city_sessions = sum(values.get("sessions", 0) for values in city.values())

    return {
        "days": _days(days),
        "summary": summary,
        "devices": _ranked(device, 10),
        "cities": city_ranked,
        "trieste_share": _ratio(local_sessions, all_city_sessions),
        "channels": _ranked(channel, 15),
        "source_medium": _ranked(source_medium, 25),
        "campaigns": [c for c in _ranked(campaign, 25) if c["name"] not in ("(not set)", "(direct)")],
        "new_vs_returning": _ranked(returning, 5),
        "hours": hours,
        "weekdays": [
            {"day": WEEKDAYS[i], "sessions": round(weekday_sessions[i])} for i in range(7)
        ],
        "tracker_devices": tracker_devices,
        "contact_hours": [{"hour": h, "contacts": contact_hours[h]} for h in range(24)],
        "contact_weekdays": [
            {"day": WEEKDAYS[i], "contacts": contact_weekdays[i]} for i in range(7)
        ],
        "notes": [
            "Gli utenti sono la somma dei valori giornalieri di GA4: la stessa persona "
            "che torna in due giorni diversi è contata due volte.",
        ],
    }


# --------------------------------------------------------------------------
# Percorsi: dalla prima visita al contatto
# --------------------------------------------------------------------------

def _load_sessions(since: str) -> dict[str, dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT session_id, visitor_id, event_type, source, url, device,
                   value, payload_json, occurred_at
            FROM events
            WHERE session_id IS NOT NULL AND occurred_at >= ?
            ORDER BY session_id, occurred_at, id
            """,
            (since,),
        ).fetchall()

    sessions: dict[str, dict[str, Any]] = {}
    for row in rows:
        sid = row["session_id"]
        payload = _payload(row["payload_json"])
        s = sessions.get(sid)
        if s is None:
            s = sessions[sid] = {
                "session_id": sid,
                "visitor_id": row["visitor_id"],
                "started_at": row["occurred_at"],
                "source": row["source"] or "direct",
                "medium": payload.get("medium") or "",
                "campaign": "",
                "device": row["device"] or "sconosciuto",
                "landing": payload.get("landing") or _path(row["url"]),
                "pages": [],
                "engaged_ms": 0.0,
                "max_scroll": 0.0,
                "form_started": False,
                "cta": False,
                "contacts": [],
                "first_contact_at": None,
            }

        kind = row["event_type"]
        if kind == "page_view":
            path = _path(row["url"])
            if not s["pages"] or s["pages"][-1] != path:
                s["pages"].append(path)
        elif kind == "page_engagement":
            s["engaged_ms"] += float(row["value"] or 0)
            s["max_scroll"] = max(s["max_scroll"], float(payload.get("max_scroll") or 0))
        elif kind == "scroll_depth":
            s["max_scroll"] = max(s["max_scroll"], float(row["value"] or 0))
        elif kind == "form_start":
            s["form_started"] = True
        elif kind == "cta_click":
            s["cta"] = True
        elif kind in CONTACT_EVENTS:
            s["contacts"].append(kind)
            if not s["first_contact_at"]:
                s["first_contact_at"] = row["occurred_at"]
                s["pages_before_contact"] = len(s["pages"])

    return sessions


def _seconds_between(start: str, end: str) -> float | None:
    a, b = _local(start), _local(end)
    if not a or not b:
        return None
    return max(0.0, (b - a).total_seconds())


def journeys(days: int = 30, limit: int = 30) -> dict[str, Any]:
    sessions = _load_sessions(_since(days))
    items = list(sessions.values())
    converted = [s for s in items if s["contacts"]]

    def interested(s: dict) -> bool:
        return len(s["pages"]) >= 2 or s["engaged_ms"] >= 30000 or s["max_scroll"] >= 50

    funnel = [
        {"label": "Sessioni", "value": len(items)},
        # Ogni passo include i successivi, così il funnel resta sempre decrescente.
        {
            "label": "Interessate",
            "value": sum(
                1 for s in items if interested(s) or s["form_started"] or s["cta"] or s["contacts"]
            ),
        },
        {
            "label": "Modulo o CTA",
            "value": sum(1 for s in items if s["form_started"] or s["cta"] or s["contacts"]),
        },
        {"label": "Contatto", "value": len(converted)},
    ]

    def group(key_fn) -> list[dict[str, Any]]:
        buckets: dict[str, list[dict]] = defaultdict(list)
        for s in items:
            buckets[key_fn(s)].append(s)
        out = []
        for name, group_items in buckets.items():
            conv = sum(1 for s in group_items if s["contacts"])
            out.append(
                {
                    "name": name,
                    "sessions": len(group_items),
                    "contacts": conv,
                    "contact_rate": _ratio(conv, len(group_items)),
                    "avg_pages": round(sum(len(s["pages"]) for s in group_items) / len(group_items), 1),
                    "avg_engaged_sec": round(
                        sum(s["engaged_ms"] for s in group_items) / len(group_items) / 1000, 1
                    ),
                }
            )
        out.sort(key=lambda item: (item["contacts"], item["sessions"]), reverse=True)
        return out

    paths = Counter()
    for s in converted:
        steps = s["pages"][: s.get("pages_before_contact", len(s["pages"]))][:5]
        label = " → ".join(steps or [s["landing"] or "/"])
        paths[f"{label} ⇒ {s['contacts'][0].replace('_click', '').replace('_submit', '')}"] += 1

    time_to_contact = [
        t
        for s in converted
        if (t := _seconds_between(s["started_at"], s["first_contact_at"])) is not None
    ]
    pages_to_contact = [s.get("pages_before_contact", len(s["pages"])) for s in converted]

    form_started = [s for s in items if s["form_started"]]
    form_done = [s for s in form_started if "form_submit" in s["contacts"]]

    # Visitatori che tornano (solo se l'ID persistente è attivo nel plugin).
    by_visitor: dict[str, list[dict]] = defaultdict(list)
    for s in items:
        if s["visitor_id"]:
            by_visitor[s["visitor_id"]].append(s)
    multi_touch = []
    for visitor_sessions in by_visitor.values():
        visitor_sessions.sort(key=lambda s: s["started_at"])
        first_conv = next((i for i, s in enumerate(visitor_sessions) if s["contacts"]), None)
        if first_conv is None:
            continue
        multi_touch.append(
            {
                "sessions_before_contact": first_conv + 1,
                "first_source": visitor_sessions[0]["source"],
                "last_source": visitor_sessions[first_conv]["source"],
            }
        )
    first_touch = Counter(m["first_source"] for m in multi_touch)
    last_touch = Counter(m["last_source"] for m in multi_touch)

    recent = sorted(converted, key=lambda s: s["first_contact_at"] or "", reverse=True)[:limit]

    return {
        "days": _days(days),
        "tracked_sessions": len(items),
        "converted_sessions": len(converted),
        "contact_rate": _ratio(len(converted), len(items), 2),
        "funnel": funnel,
        "by_source": group(lambda s: s["source"])[:20],
        "by_medium": group(lambda s: s["medium"] or "(non impostato)")[:10],
        "by_device": group(lambda s: s["device"]),
        "by_landing": group(lambda s: s["landing"] or "/")[:25],
        "top_paths": [{"path": p, "count": c} for p, c in paths.most_common(15)],
        "median_seconds_to_contact": round(median(time_to_contact)) if time_to_contact else None,
        "median_pages_to_contact": median(pages_to_contact) if pages_to_contact else None,
        "form_abandonment": {
            "started": len(form_started),
            "submitted": len(form_done),
            "abandon_rate": _ratio(len(form_started) - len(form_done), len(form_started)),
        },
        "returning_visitors": {
            "tracked_visitors": len(by_visitor),
            "converted_visitors": len(multi_touch),
            "avg_sessions_before_contact": round(
                sum(m["sessions_before_contact"] for m in multi_touch) / len(multi_touch), 1
            )
            if multi_touch
            else None,
            "first_touch": [{"source": k, "contacts": v} for k, v in first_touch.most_common(10)],
            "last_touch": [{"source": k, "contacts": v} for k, v in last_touch.most_common(10)],
        },
        "recent_contacts": [
            {
                "at": s["first_contact_at"],
                "source": s["source"],
                "medium": s["medium"],
                "device": s["device"],
                "landing": s["landing"],
                "pages": s["pages"][:8],
                "engaged_sec": round(s["engaged_ms"] / 1000),
                "contact": s["contacts"][0],
            }
            for s in recent
        ],
    }


# --------------------------------------------------------------------------
# Ricerca Google: query → pagina, opportunità, cannibalizzazione
# --------------------------------------------------------------------------

# CTR medio atteso per posizione organica (stima prudente, risultati standard).
EXPECTED_CTR = {1: 0.28, 2: 0.15, 3: 0.10, 4: 0.07, 5: 0.05, 6: 0.04, 7: 0.03, 8: 0.025, 9: 0.02, 10: 0.018}


def _expected_ctr(position: float) -> float:
    if position <= 0:
        return 0.0
    rounded = max(1, round(position))
    return EXPECTED_CTR.get(rounded, 0.01 if rounded <= 20 else 0.003)


def _query_page_rows(since: str, device: str | None = None) -> list[dict[str, Any]]:
    clauses = ["captured_date >= ?"]
    params: list[Any] = [since]
    if device:
        clauses.append("device = ?")
        params.append(device.lower())

    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT query, page,
                   SUM(clicks) AS clicks,
                   SUM(impressions) AS impressions,
                   SUM(position * impressions) / NULLIF(SUM(impressions), 0) AS position
            FROM search_performance
            WHERE {' AND '.join(clauses)}
            GROUP BY query, page
            """,
            params,
        ).fetchall()

    out = []
    for row in rows:
        impressions = float(row["impressions"] or 0)
        clicks = float(row["clicks"] or 0)
        out.append(
            {
                "query": row["query"],
                "page": row["page"],
                "clicks": round(clicks),
                "impressions": round(impressions),
                "ctr": _ratio(clicks, impressions, 2),
                "position": round(float(row["position"] or 0), 1),
            }
        )
    return out


def search_query_page(
    days: int = 90,
    contains: str = "",
    device: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    rows = _query_page_rows(_since(days), device)
    needle = contains.strip().lower()
    if needle:
        rows = [r for r in rows if needle in r["query"].lower() or needle in r["page"].lower()]
    rows.sort(key=lambda r: (r["impressions"], r["clicks"]), reverse=True)
    return rows[: max(1, min(int(limit), 2000))]


def search_opportunities(days: int = 90, min_impressions: int = 30, limit: int = 50) -> list[dict[str, Any]]:
    """Query vicine alla prima pagina o con CTR sotto la media per la loro posizione."""
    rows = _query_page_rows(_since(days))
    by_query: dict[str, dict[str, Any]] = {}
    for r in rows:
        q = by_query.setdefault(
            r["query"], {"query": r["query"], "clicks": 0, "impressions": 0, "pos_weight": 0.0, "pages": Counter()}
        )
        q["clicks"] += r["clicks"]
        q["impressions"] += r["impressions"]
        q["pos_weight"] += r["position"] * r["impressions"]
        q["pages"][r["page"]] += r["impressions"]

    out = []
    for q in by_query.values():
        if q["impressions"] < min_impressions:
            continue
        position = q["pos_weight"] / q["impressions"] if q["impressions"] else 0
        ctr = q["clicks"] / q["impressions"] if q["impressions"] else 0
        expected = _expected_ctr(position)

        kind = None
        if 4 <= position <= 20:
            kind = "vicina alla top 3" if position <= 10 else "vicina alla prima pagina"
            target_ctr = _expected_ctr(3)
        elif position < 4 and ctr < expected * 0.6:
            kind = "CTR basso per la posizione"
            target_ctr = expected
        if not kind:
            continue

        potential = max(0, round(q["impressions"] * (target_ctr - ctr)))
        out.append(
            {
                "query": q["query"],
                "page": q["pages"].most_common(1)[0][0],
                "impressions": q["impressions"],
                "clicks": q["clicks"],
                "ctr": round(ctr * 100, 2),
                "position": round(position, 1),
                "type": kind,
                "potential_clicks": potential,
            }
        )

    out.sort(key=lambda item: item["potential_clicks"], reverse=True)
    return out[:limit]


def cannibalization(days: int = 90, min_impressions: int = 20, limit: int = 50) -> list[dict[str, Any]]:
    """Pagine dello stesso sito che competono per la stessa ricerca.

    Filtri a più livelli (ispirati all'approccio di jmelm93/seo_cannibalization_analysis,
    riscritti da zero):
    1. la query deve avere un volume minimo di impression;
    2. ogni pagina considerata deve avere almeno il 10% delle impression o dei click
       della query (esclude le comparse occasionali);
    3. la query deve pesare almeno il 5% delle impression di ciascuna pagina
       (altrimenti per quella pagina è un argomento marginale);
    4. servono almeno due pagine che superano tutti i filtri.
    """
    rows = _query_page_rows(_since(days))

    page_totals: Counter = Counter()
    by_query: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        page_totals[r["page"]] += r["impressions"]
        by_query[r["query"]].append(r)

    results = []
    for query, pages in by_query.items():
        total_impr = sum(p["impressions"] for p in pages)
        total_clicks = sum(p["clicks"] for p in pages)
        if total_impr < min_impressions or len(pages) < 2:
            continue

        candidates = []
        for p in pages:
            share_impr = p["impressions"] / total_impr if total_impr else 0
            share_clicks = p["clicks"] / total_clicks if total_clicks else 0
            weight_on_page = p["impressions"] / page_totals[p["page"]] if page_totals[p["page"]] else 0
            if max(share_impr, share_clicks) >= 0.10 and weight_on_page >= 0.05:
                candidates.append(
                    {
                        **p,
                        "share_impressions": round(share_impr * 100, 1),
                        "share_clicks": round(share_clicks * 100, 1),
                        "query_weight_on_page": round(weight_on_page * 100, 1),
                    }
                )

        if len(candidates) < 2:
            continue

        candidates.sort(key=lambda c: (c["clicks"], c["impressions"]), reverse=True)
        main = candidates[0]
        strong = [c for c in candidates if c["share_impressions"] >= 20]
        severity = "alta" if len(strong) >= 2 and candidates[1]["share_clicks"] >= 10 else "media"

        main_path = _path(main["page"])
        others = [_path(c["page"]) for c in candidates[1:]]
        if main_path == "/":
            advice = (
                "La home compete con pagine specifiche: rendi la pagina di servizio la "
                "principale per questa ricerca e dalla home linkala con testo mirato."
            )
        else:
            advice = (
                f"Tieni {main_path} come pagina principale. Su {', '.join(others)} riduci il focus "
                "su questa ricerca e aggiungi un link verso la principale; se i contenuti "
                "si sovrappongono molto, valuta di unirli con un redirect 301."
            )

        results.append(
            {
                "query": query,
                "impressions": total_impr,
                "clicks": total_clicks,
                "severity": severity,
                "main_page": main["page"],
                "pages": candidates,
                "advice": advice,
            }
        )

    results.sort(key=lambda r: (r["severity"] == "alta", r["impressions"]), reverse=True)
    return results[:limit]


# --------------------------------------------------------------------------
# Salute del sito
# --------------------------------------------------------------------------

VITAL_THRESHOLDS = {
    # nome: (buono fino a, scarso oltre, unità)
    "LCP": (2500, 4000, "ms"),
    "INP": (200, 500, "ms"),
    "CLS": (0.1, 0.25, ""),
    "FCP": (1800, 3000, "ms"),
    "TTFB": (800, 1800, "ms"),
}


def _rating(name: str, value: float | None) -> str:
    if value is None or name not in VITAL_THRESHOLDS:
        return "n/d"
    good, poor, _ = VITAL_THRESHOLDS[name]
    if value <= good:
        return "buono"
    if value <= poor:
        return "da migliorare"
    return "scarso"


def site_health(days: int = 30) -> dict[str, Any]:
    since = _since(days)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT event_type, url, device, value, payload_json, session_id
            FROM events
            WHERE occurred_at >= ? AND event_type IN (
                'web_vital', 'page_404', 'rage_click', 'page_view',
                'page_engagement', 'scroll_depth', 'outbound_click', 'file_download'
            )
            """,
            (since,),
        ).fetchall()

    vitals: dict[str, list[float]] = defaultdict(list)
    vitals_device: dict[tuple[str, str], list[float]] = defaultdict(list)
    vitals_page: dict[tuple[str, str], list[float]] = defaultdict(list)
    poor_targets: Counter = Counter()
    not_found: Counter = Counter()
    rage: Counter = Counter()
    outbound: Counter = Counter()
    downloads: Counter = Counter()
    views: Counter = Counter()
    engaged: Counter = Counter()
    scroll_max: dict[tuple[str, str], float] = {}

    for row in rows:
        payload = _payload(row["payload_json"])
        path = _path(row["url"])
        kind = row["event_type"]
        value = float(row["value"]) if row["value"] is not None else None

        if kind == "web_vital":
            name = payload.get("metric_name")
            if not name or value is None:
                continue
            vitals[name].append(value)
            vitals_device[(name, row["device"] or "sconosciuto")].append(value)
            vitals_page[(name, path)].append(value)
            if payload.get("metric_rating") == "poor" and payload.get("vital_target"):
                poor_targets[(name, payload["vital_target"])] += 1
        elif kind == "page_404":
            not_found[payload.get("path") or path] += 1
        elif kind == "rage_click":
            rage[(path, payload.get("target") or "")] += 1
        elif kind == "outbound_click":
            outbound[payload.get("target_host") or "?"] += 1
        elif kind == "file_download":
            downloads[(path, payload.get("file_ext") or "")] += 1
        elif kind == "page_view":
            views[path] += 1
        elif kind == "page_engagement" and value is not None:
            engaged[path] += value
        elif kind == "scroll_depth" and value is not None and row["session_id"]:
            key = (row["session_id"], path)
            scroll_max[key] = max(scroll_max.get(key, 0), value)

    overview = []
    for name in ("LCP", "INP", "CLS", "FCP", "TTFB"):
        samples = vitals.get(name, [])
        p75 = _percentile(samples, 75)
        good, poor, unit = VITAL_THRESHOLDS[name]
        overview.append(
            {
                "metric": name,
                "p75": round(p75, 3) if p75 is not None else None,
                "unit": unit,
                "rating": _rating(name, p75),
                "samples": len(samples),
                "poor_share": _ratio(sum(1 for v in samples if v > poor), len(samples)),
                "by_device": {
                    dev: round(_percentile(vals, 75), 3)
                    for (metric, dev), vals in vitals_device.items()
                    if metric == name and vals
                },
            }
        )

    worst_pages = []
    for (name, path), samples in vitals_page.items():
        if name not in ("LCP", "INP", "CLS") or len(samples) < 5:
            continue
        p75 = _percentile(samples, 75)
        if _rating(name, p75) == "buono":
            continue
        worst_pages.append(
            {"metric": name, "page": path, "p75": round(p75, 3), "rating": _rating(name, p75), "samples": len(samples)}
        )
    worst_pages.sort(key=lambda item: (item["rating"] == "scarso", item["samples"]), reverse=True)

    scroll_by_page: dict[str, list[float]] = defaultdict(list)
    for (_, path), value in scroll_max.items():
        scroll_by_page[path].append(value)

    engagement = [
        {
            "page": path,
            "views": count,
            "avg_engaged_sec": round(engaged.get(path, 0) / count / 1000, 1),
            "avg_max_scroll": round(sum(scroll_by_page[path]) / len(scroll_by_page[path]))
            if scroll_by_page.get(path)
            else 0,
        }
        for path, count in views.most_common(40)
    ]

    return {
        "days": _days(days),
        "vitals": overview,
        "worst_pages": worst_pages[:20],
        "poor_elements": [
            {"metric": m, "element": t, "count": c} for (m, t), c in poor_targets.most_common(15)
        ],
        "not_found": [{"path": p, "count": c} for p, c in not_found.most_common(30)],
        "rage_clicks": [
            {"page": p, "element": t, "count": c} for (p, t), c in rage.most_common(20)
        ],
        "outbound": [{"host": h, "count": c} for h, c in outbound.most_common(20)],
        "downloads": [
            {"page": p, "type": t, "count": c} for (p, t), c in downloads.most_common(20)
        ],
        "engagement": engagement,
    }


# --------------------------------------------------------------------------
# Stato dello storico
# --------------------------------------------------------------------------

def history_status() -> list[dict[str, Any]]:
    out = []
    with connect() as conn:
        for provider in ("ga4", "search_console", "google_business", "meta", "wordpress"):
            row = conn.execute(
                """
                SELECT MIN(captured_at) AS first, MAX(captured_at) AS last, COUNT(*) AS rows
                FROM metric_snapshots WHERE provider = ?
                """,
                (provider,),
            ).fetchone()
            cursor = get_cursor(provider)
            out.append(
                {
                    "provider": provider,
                    "first_data": (row["first"] or "")[:10] or None,
                    "last_data": (row["last"] or "")[:10] or None,
                    "datapoints": row["rows"],
                    "history_complete": bool(cursor and str(cursor).startswith("backfill:"))
                    if provider in ("ga4", "search_console", "google_business", "meta")
                    else None,
                }
            )

        sp = conn.execute(
            "SELECT MIN(captured_date), MAX(captured_date), COUNT(*) FROM search_performance"
        ).fetchone()
        ev = conn.execute(
            "SELECT MIN(occurred_at), COUNT(*), COUNT(DISTINCT session_id) FROM events"
        ).fetchone()

    out.append(
        {
            "provider": "search_query_page",
            "first_data": sp[0],
            "last_data": sp[1],
            "datapoints": sp[2],
            "history_complete": None,
        }
    )
    out.append(
        {
            "provider": "tracker_sessions",
            "first_data": (ev[0] or "")[:10] or None,
            "last_data": None,
            "datapoints": ev[1],
            "sessions": ev[2],
            "history_complete": None,
        }
    )
    return out

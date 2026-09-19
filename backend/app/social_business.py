"""Analisi Meta approfondite e Google Business (0.8).

Calcoli deterministici sui dati locali, pronti per dashboard e MCP.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any

from .db import connect
from .event_types import CONTACT_EVENTS
from .insights import LOCAL_TZ, WEEKDAYS, _local

FORMAT_LABELS = {
    "instagram_reel": "Reel Instagram",
    "instagram_image": "Foto Instagram",
    "instagram_carousel": "Carosello Instagram",
    "instagram_video": "Video Instagram",
    "instagram_story": "Storia Instagram",
    "facebook_photo": "Foto Facebook",
    "facebook_video": "Video Facebook",
    "facebook_reel": "Reel Facebook",
    "facebook_album": "Album Facebook",
    "facebook_link": "Link Facebook",
    "facebook_status": "Testo Facebook",
    "facebook_post": "Post Facebook",
}

SOCIAL_SOURCE_SQL = (
    "(LOWER(COALESCE(source, '')) LIKE '%facebook%' OR LOWER(COALESCE(source, '')) LIKE '%instagram%' "
    "OR LOWER(COALESCE(source, '')) IN ('meta', 'fb', 'ig'))"
)

STOPWORDS = set(
    """
    a ad al alla alle anche avere che chi ci con cosa così da dal dalla dei del della delle di
    e è ed era essere fa gli ha hanno ho i il in io la le lo loro ma mi mio molto ne nel nella
    non noi per più poi quale quando questo questa qui se si sia sono su sua suo sul sulla ti
    tra tutto tutti un una uno vi sempre stato stati stata sto sta molto molti ottimo ottima
    lavoro lavori anche ogni stesso dopo prima fatto fatta fare the and translated google by
    original
    """.split()
)


def _days(value: int, maximum: int = 730) -> int:
    return max(1, min(int(value or 30), maximum))


def _iso_since(days: int, offset_days: int = 0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days + offset_days)
    return moment.isoformat()


def _pct_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _ratio(num: float, den: float) -> float:
    return round(num / den * 100, 2) if den else 0.0


def _sum_metrics(conn, provider: str, names: list[str], start: str, end: str) -> dict[str, float]:
    placeholders = ",".join("?" for _ in names)
    rows = conn.execute(
        f"""
        SELECT metric, SUM(value) AS total FROM metric_snapshots
        WHERE provider = ? AND metric IN ({placeholders})
          AND captured_at >= ? AND captured_at < ?
          AND COALESCE(dimension, 'account') IN ('account', '')
        GROUP BY metric
        """,
        (provider, *names, start, end),
    ).fetchall()
    return {row["metric"]: float(row["total"] or 0) for row in rows}


def _compare(conn, provider: str, spec: list[tuple[str, str]], days: int) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc).isoformat()
    start = _iso_since(days)
    prev_start = _iso_since(days, days)
    names = [metric for metric, _ in spec]
    current = _sum_metrics(conn, provider, names, start, now)
    previous = _sum_metrics(conn, provider, names, prev_start, start)
    out = []
    for metric, label in spec:
        if metric not in current and metric not in previous:
            continue
        value = current.get(metric, 0)
        out.append({
            "metric": metric,
            "label": label,
            "value": round(value, 1),
            "previous": round(previous.get(metric, 0), 1),
            "change": _pct_change(value, previous.get(metric, 0)),
        })
    return out


def _latest_snapshot(conn, provider: str, metric: str) -> list[dict[str, Any]]:
    row = conn.execute(
        "SELECT MAX(captured_at) FROM metric_snapshots WHERE provider = ? AND metric = ?",
        (provider, metric),
    ).fetchone()
    if not row or not row[0]:
        return []
    rows = conn.execute(
        """
        SELECT dimension, dimension_value, value FROM metric_snapshots
        WHERE provider = ? AND metric = ? AND captured_at = ?
        """,
        (provider, metric, row[0]),
    ).fetchall()
    return [dict(r) | {"captured_at": row[0]} for r in rows]


def _latest_value(conn, provider: str, metric: str) -> float | None:
    row = conn.execute(
        """
        SELECT value FROM metric_snapshots WHERE provider = ? AND metric = ?
        ORDER BY captured_at DESC LIMIT 1
        """,
        (provider, metric),
    ).fetchone()
    return float(row[0]) if row else None


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------

def _content_values(metrics: dict[str, float], platform: str) -> dict[str, float]:
    g = metrics.get
    if platform == "instagram":
        likes = g("instagram_media_likes", g("instagram_media_like_count", 0))
        comments = g("instagram_media_comments", g("instagram_media_comments_count", 0))
        shares = g("instagram_media_shares", 0)
        saves = g("instagram_media_saved", 0)
        interactions = g("instagram_media_total_interactions") or (likes + comments + shares + saves)
        return {
            "reach": g("instagram_media_reach", 0),
            "views": g("instagram_media_views", g("instagram_media_plays", g("instagram_media_impressions", 0))),
            "interactions": interactions,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "saves": saves,
            "clicks": 0,
            "profile_visits": g("instagram_media_profile_visits", 0),
            "follows": g("instagram_media_follows", 0),
            "replies": g("instagram_media_replies", 0),
            "avg_watch_sec": round(g("instagram_media_ig_reels_avg_watch_time", 0) / 1000, 1),
            "total_watch_min": round(g("instagram_media_ig_reels_video_view_total_time", 0) / 60000, 1),
        }
    reactions = g("facebook_post_reactions", g("facebook_post_reactions_by_type_total", 0))
    comments = g("facebook_post_comments", 0)
    shares = g("facebook_post_shares", 0)
    return {
        "reach": g("facebook_post_total_media_view_unique", 0),
        "views": g("facebook_post_media_view", g("facebook_post_video_views", 0)),
        "interactions": reactions + comments + shares,
        "likes": reactions,
        "comments": comments,
        "shares": shares,
        "saves": 0,
        "clicks": g("facebook_post_clicks", 0),
        "profile_visits": 0,
        "follows": 0,
        "replies": 0,
        "avg_watch_sec": round(g("facebook_post_video_avg_time_watched", 0) / 1000, 1),
        "total_watch_min": 0,
    }


def _contents(conn, since: str) -> list[dict[str, Any]]:
    items = conn.execute(
        """
        SELECT external_id, content_type, title, url, published_at FROM content_items
        WHERE provider = 'meta' AND published_at >= ?
        ORDER BY published_at DESC
        """,
        (since,),
    ).fetchall()
    rows = conn.execute(
        """
        SELECT metric, dimension_value, value FROM metric_snapshots
        WHERE provider = 'meta' AND dimension IN ('post_id', 'media_id') AND captured_at >= ?
        """,
        (since,),
    ).fetchall()
    by_id: dict[str, dict[str, float]] = defaultdict(dict)
    for row in rows:
        by_id[str(row["dimension_value"])][row["metric"]] = float(row["value"] or 0)

    out = []
    for item in items:
        external = str(item["external_id"])
        platform = "instagram" if external.startswith("ig:") else "facebook"
        content_id = external.removeprefix("ig:")
        values = _content_values(by_id.get(content_id, {}), platform)
        base = values["reach"] or values["views"]
        local = _local(item["published_at"])
        out.append({
            "id": content_id,
            "platform": platform,
            "content_type": item["content_type"],
            "format": FORMAT_LABELS.get(item["content_type"], item["content_type"] or "Contenuto"),
            "title": item["title"],
            "url": item["url"],
            "published_at": local.strftime("%d/%m/%Y %H:%M") if local else item["published_at"],
            "weekday": local.weekday() if local else None,
            "hour": local.hour if local else None,
            "has_metrics": bool(by_id.get(content_id)),
            **{k: round(v, 1) for k, v in values.items()},
            "engagement_rate": _ratio(values["interactions"], base),
        })
    return out


def meta_deep(days: int = 30) -> dict[str, Any]:
    days = _days(days)
    since = _iso_since(days)

    with connect() as conn:
        contents = _contents(conn, since)
        measured = [c for c in contents if c["has_metrics"] and c["content_type"] != "instagram_story"]

        # Formati a confronto.
        formats: dict[str, dict[str, Any]] = {}
        for c in measured:
            f = formats.setdefault(c["format"], {"format": c["format"], "count": 0, "reach": 0.0,
                                                 "interactions": 0.0, "er": []})
            f["count"] += 1
            f["reach"] += c["reach"] or c["views"]
            f["interactions"] += c["interactions"]
            f["er"].append(c["engagement_rate"])
        format_rows = [
            {
                "format": f["format"],
                "count": f["count"],
                "avg_reach": round(f["reach"] / f["count"], 1),
                "avg_interactions": round(f["interactions"] / f["count"], 1),
                "avg_engagement_rate": round(sum(f["er"]) / len(f["er"]), 2),
            }
            for f in formats.values()
        ]
        format_rows.sort(key=lambda r: r["avg_interactions"], reverse=True)

        # Giorni e orari di pubblicazione (ora italiana).
        weekday = [{"day": WEEKDAYS[i], "posts": 0, "interactions": 0.0, "reach": 0.0} for i in range(7)]
        hours = [{"hour": f"{h:02d}", "posts": 0, "interactions": 0.0, "reach": 0.0} for h in range(24)]
        slots: dict[tuple[int, int], list[float]] = defaultdict(list)
        for c in measured:
            if c["weekday"] is None:
                continue
            for bucket in (weekday[c["weekday"]], hours[c["hour"]]):
                bucket["posts"] += 1
                bucket["interactions"] += c["interactions"]
                bucket["reach"] += c["reach"] or c["views"]
            slots[(c["weekday"], c["hour"] // 3 * 3)].append(c["interactions"])
        for bucket in (*weekday, *hours):
            n = bucket["posts"] or 1
            bucket["avg_interactions"] = round(bucket["interactions"] / n, 1) if bucket["posts"] else 0
            bucket["avg_reach"] = round(bucket["reach"] / n, 1) if bucket["posts"] else 0
        best_slots = sorted(
            (
                {"slot": f"{WEEKDAYS[d]} {h:02d}-{h + 3:02d}", "posts": len(v),
                 "avg_interactions": round(sum(v) / len(v), 1)}
                for (d, h), v in slots.items() if len(v) >= 2
            ),
            key=lambda r: r["avg_interactions"],
            reverse=True,
        )[:5]

        reels = sorted(
            [c for c in measured if c["content_type"] in ("instagram_reel", "facebook_reel", "facebook_video", "instagram_video")],
            key=lambda c: (c["avg_watch_sec"], c["views"]),
            reverse=True,
        )
        stories = [c for c in contents if c["content_type"] == "instagram_story"]

        facebook_kpis = _compare(conn, "meta", [
            ("meta_page_media_view", "Visualizzazioni contenuti"),
            ("meta_page_total_media_view_unique", "Persone raggiunte"),
            ("meta_page_post_engagements", "Interazioni"),
            ("meta_page_views_total", "Visite alla Pagina"),
            ("meta_page_daily_follows_unique", "Nuovi follower"),
            ("meta_page_daily_unfollows_unique", "Follower persi"),
            ("meta_page_video_views", "Visualizzazioni video"),
        ], days)
        instagram_kpis = _compare(conn, "meta", [
            ("instagram_views", "Visualizzazioni"),
            ("instagram_reach", "Copertura (somma giornaliera)"),
            ("instagram_accounts_engaged", "Account coinvolti"),
            ("instagram_total_interactions", "Interazioni"),
            ("instagram_saves", "Salvataggi"),
            ("instagram_shares", "Condivisioni"),
            ("instagram_profile_links_taps", "Tap su link del profilo"),
            ("instagram_follower_count", "Nuovi follower"),
            ("instagram_daily_unfollows", "Follower persi"),
        ], days)

        # Crescita giorno per giorno.
        growth_rows = conn.execute(
            """
            SELECT SUBSTR(captured_at, 1, 10) AS day, metric, SUM(value) AS value FROM metric_snapshots
            WHERE provider = 'meta' AND captured_at >= ? AND metric IN (
                'instagram_follower_count', 'instagram_daily_follows', 'instagram_daily_unfollows',
                'meta_page_daily_follows_unique', 'meta_page_daily_unfollows_unique')
            GROUP BY day, metric ORDER BY day
            """,
            (since,),
        ).fetchall()
        growth: dict[str, dict[str, Any]] = {}
        for row in growth_rows:
            g = growth.setdefault(row["day"], {"day": row["day"][5:], "ig_new": 0, "ig_lost": 0, "fb_new": 0, "fb_lost": 0})
            key = {
                "instagram_follower_count": "ig_new",
                "instagram_daily_follows": "ig_new",
                "instagram_daily_unfollows": "ig_lost",
                "meta_page_daily_follows_unique": "fb_new",
                "meta_page_daily_unfollows_unique": "fb_lost",
            }[row["metric"]]
            g[key] = max(g[key], float(row["value"] or 0)) if key == "ig_new" else g[key] + float(row["value"] or 0)

        # Pubblico Instagram.
        demo: dict[str, list[dict[str, Any]]] = defaultdict(list)
        demo_date = None
        for row in _latest_snapshot(conn, "meta", "instagram_follower_demographics"):
            demo[row["dimension"]].append({"name": row["dimension_value"], "value": row["value"]})
            demo_date = row["captured_at"]
        demographics = {}
        for key, rows in demo.items():
            total = sum(r["value"] for r in rows) or 1
            rows.sort(key=lambda r: r["value"], reverse=True)
            demographics[key] = [{**r, "share": _ratio(r["value"], total)} for r in rows[:15]]
        trieste = sum(r["share"] for r in demographics.get("city", []) if "triest" in r["name"].lower())

        # online_followers è espresso in ora del Pacifico: +9 ore = ora italiana.
        online = [{"hour": f"{h:02d}", "followers": 0.0} for h in range(24)]
        for row in _latest_snapshot(conn, "meta", "instagram_online_followers"):
            try:
                online[(int(row["dimension_value"]) + 9) % 24]["followers"] = row["value"]
            except (TypeError, ValueError):
                pass

        reactions = conn.execute(
            """
            SELECT dimension_value AS name, SUM(value) AS value FROM metric_snapshots
            WHERE provider = 'meta' AND metric = 'meta_page_actions_post_reactions_total_breakdown'
              AND captured_at >= ? GROUP BY dimension_value ORDER BY value DESC
            """,
            (since,),
        ).fetchall()

        # Effetto sul sito: visite e contatti arrivati da Facebook/Instagram.
        contact_list = ",".join(f"'{e}'" for e in CONTACT_EVENTS)
        site = conn.execute(
            f"""
            SELECT
              COUNT(DISTINCT CASE WHEN event_type = 'page_view' THEN COALESCE(session_id, id) END) AS sessions,
              SUM(CASE WHEN event_type IN ({contact_list}) THEN 1 ELSE 0 END) AS contacts
            FROM events WHERE occurred_at >= ? AND {SOCIAL_SOURCE_SQL}
            """,
            (since,),
        ).fetchone()
        ga4_social = conn.execute(
            """
            SELECT dimension_value AS name, SUM(value) AS sessions FROM metric_snapshots
            WHERE provider = 'ga4' AND metric = 'ga4_sessions' AND dimension = 'source'
              AND captured_at >= ?
              AND (LOWER(dimension_value) LIKE '%facebook%' OR LOWER(dimension_value) LIKE '%instagram%'
                   OR LOWER(dimension_value) IN ('fb', 'ig', 'meta'))
            GROUP BY dimension_value ORDER BY sessions DESC
            """,
            (since,),
        ).fetchall()
        ig_followers = _latest_value(conn, "meta", "instagram_followers")

    sessions = int(site["sessions"] or 0) if site else 0
    contacts = int(site["contacts"] or 0) if site else 0
    top = sorted(measured, key=lambda c: (c["interactions"], c["reach"]), reverse=True)
    best_rate = sorted([c for c in measured if (c["reach"] or c["views"]) >= 30],
                       key=lambda c: c["engagement_rate"], reverse=True)

    notes = []
    if not measured:
        notes.append("Nessun contenuto con metriche nel periodo: avvia la sincronizzazione Meta.")
    if not demographics:
        notes.append("Demografia follower non disponibile: Meta la fornisce solo da 100 follower in su.")

    return {
        "days": days,
        "followers": {"instagram": ig_followers},
        "facebook_kpis": facebook_kpis,
        "instagram_kpis": instagram_kpis,
        "content_count": len(contents),
        "measured_count": len(measured),
        "top_content": top[:30],
        "best_engagement": best_rate[:10],
        "weak_content": list(reversed(top[-5:])) if len(top) >= 10 else [],
        "formats": format_rows,
        "weekdays": weekday,
        "hours": hours,
        "best_slots": best_slots,
        "reels": reels[:20],
        "stories": stories[:20],
        "growth": list(growth.values()),
        "demographics": demographics,
        "demographics_date": (demo_date or "")[:10] or None,
        "trieste_follower_share": round(trieste, 1),
        "online_hours": online,
        "reactions": [dict(r) for r in reactions],
        "site_impact": {
            "tracker_sessions": sessions,
            "tracker_contacts": contacts,
            "contact_rate": _ratio(contacts, sessions),
            "ga4_sources": [{"name": r["name"], "sessions": round(r["sessions"] or 0)} for r in ga4_social],
        },
        "notes": notes,
    }


# --------------------------------------------------------------------------
# Google Business
# --------------------------------------------------------------------------

ACTIONS = [
    ("gbp_call_clicks", "Chiamate"),
    ("gbp_website_clicks", "Click al sito"),
    ("gbp_business_direction_requests", "Indicazioni stradali"),
    ("gbp_business_conversations", "Messaggi"),
    ("gbp_business_bookings", "Prenotazioni"),
]
IMPRESSIONS = [
    ("gbp_business_impressions_mobile_search", "Ricerca da mobile"),
    ("gbp_business_impressions_desktop_search", "Ricerca da computer"),
    ("gbp_business_impressions_mobile_maps", "Maps da mobile"),
    ("gbp_business_impressions_desktop_maps", "Maps da computer"),
]


def _words(texts: list[str], limit: int = 20) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for text in texts:
        # Le recensioni tradotte contengono anche l'originale: si tiene la prima parte.
        text = re.split(r"\(Original\)|\(Originale\)", text)[0]
        seen = set()
        for word in re.findall(r"[a-zà-ù]{4,}", text.lower()):
            if word not in STOPWORDS and word not in seen:
                counter[word] += 1
                seen.add(word)
    return [{"word": w, "count": c} for w, c in counter.most_common(limit)]


def business_overview(days: int = 30) -> dict[str, Any]:
    days = _days(days)
    since = _iso_since(days)

    with connect() as conn:
        actions = _compare(conn, "google_business", ACTIONS, days)
        impressions = _compare(conn, "google_business", IMPRESSIONS, days)
        total_impr = sum(r["value"] for r in impressions)
        total_actions = sum(r["value"] for r in actions)
        prev_impr = sum(r["previous"] for r in impressions)
        prev_actions = sum(r["previous"] for r in actions)

        names = [m for m, _ in ACTIONS] + [m for m, _ in IMPRESSIONS]
        placeholders = ",".join("?" for _ in names)
        daily_rows = conn.execute(
            f"""
            SELECT SUBSTR(captured_at, 1, 10) AS day, metric, SUM(value) AS value FROM metric_snapshots
            WHERE provider = 'google_business' AND captured_at >= ? AND metric IN ({placeholders})
            GROUP BY day, metric ORDER BY day
            """,
            (since, *names),
        ).fetchall()
        daily: dict[str, dict[str, Any]] = {}
        weekday_actions = [{"day": WEEKDAYS[i], "calls": 0.0, "actions": 0.0} for i in range(7)]
        impression_metrics = {m for m, _ in IMPRESSIONS}
        for row in daily_rows:
            d = daily.setdefault(row["day"], {"day": row["day"][5:], "impressions": 0.0, "calls": 0.0,
                                              "website": 0.0, "directions": 0.0, "actions": 0.0})
            value = float(row["value"] or 0)
            if row["metric"] in impression_metrics:
                d["impressions"] += value
                continue
            d["actions"] += value
            key = {"gbp_call_clicks": "calls", "gbp_website_clicks": "website",
                   "gbp_business_direction_requests": "directions"}.get(row["metric"])
            if key:
                d[key] += value
            wd = datetime.fromisoformat(row["day"]).weekday()
            weekday_actions[wd]["actions"] += value
            if row["metric"] == "gbp_call_clicks":
                weekday_actions[wd]["calls"] += value

        # Keyword mese per mese.
        kw_rows = conn.execute(
            """
            SELECT SUBSTR(captured_at, 1, 7) AS month, metric, dimension_value AS keyword, value
            FROM metric_snapshots
            WHERE provider = 'google_business' AND dimension = 'query'
              AND metric IN ('gbp_search_keyword_impressions', 'gbp_search_keyword_below_threshold')
            """
        ).fetchall()
        by_month: dict[str, dict[str, float]] = defaultdict(dict)
        below: set[tuple[str, str]] = set()
        for row in kw_rows:
            if row["metric"] == "gbp_search_keyword_below_threshold":
                below.add((row["month"], row["keyword"]))
            else:
                by_month[row["month"]][row["keyword"]] = float(row["value"] or 0)
        months = sorted(by_month)
        latest_month = months[-1] if months else None
        prev_month = months[-2] if len(months) > 1 else None
        keywords = []
        if latest_month:
            prev = by_month.get(prev_month, {}) if prev_month else {}
            for keyword, value in by_month[latest_month].items():
                before = prev.get(keyword)
                keywords.append({
                    "keyword": keyword,
                    "impressions": value,
                    "below_threshold": (latest_month, keyword) in below,
                    "previous": before,
                    "change": _pct_change(value, before) if before else None,
                    "is_new": prev_month is not None and keyword not in prev,
                })
            keywords.sort(key=lambda r: r["impressions"], reverse=True)
        keyword_trend = [
            {"month": m, "impressions": round(sum(by_month[m].values())), "keywords": len(by_month[m])} for m in months[-18:]
        ]
        rising = sorted([k for k in keywords if k["change"] is not None and k["previous"] and k["previous"] >= 15],
                        key=lambda k: k["change"], reverse=True)[:10]

        # Recensioni.
        reviews = [dict(r) for r in conn.execute(
            """
            SELECT review_id, rating, comment, reviewer, created_at, updated_at, reply_comment, reply_at
            FROM reviews WHERE provider = 'google_business' ORDER BY created_at DESC
            """
        ).fetchall()]
        api_average = _latest_value(conn, "google_business", "gbp_rating_average")
        api_total = _latest_value(conn, "google_business", "gbp_review_total")

    rated = [r for r in reviews if r["rating"]]
    distribution = [{"stars": s, "count": sum(1 for r in rated if r["rating"] == s)} for s in range(5, 0, -1)]
    in_period = [r for r in rated if (r["created_at"] or "") >= since]
    replied = [r for r in reviews if r["reply_comment"]]
    reply_hours = []
    for r in replied:
        try:
            created = datetime.fromisoformat(r["created_at"].replace("Z", "+00:00"))
            reply = datetime.fromisoformat(r["reply_at"].replace("Z", "+00:00"))
            reply_hours.append(max(0.0, (reply - created).total_seconds() / 3600))
        except (AttributeError, TypeError, ValueError):
            pass
    monthly: dict[str, list[int]] = defaultdict(list)
    for r in rated:
        monthly[(r["created_at"] or "")[:7]].append(r["rating"])
    review_trend = [
        {"month": m, "count": len(v), "average": round(sum(v) / len(v), 2)}
        for m, v in sorted(monthly.items()) if m
    ][-18:]

    def _fmt(r: dict[str, Any]) -> dict[str, Any]:
        local = _local(r["created_at"]) if r["created_at"] else None
        return {**r, "date": local.strftime("%d/%m/%Y") if local else None}

    notes = []
    if not reviews:
        notes.append(
            "Nessuna recensione importata. Serve la 'Google My Business API' abilitata nel progetto "
            "Google Cloud (oltre alle API Business Profile già usate)."
        )
    if not months:
        notes.append("Keyword non ancora disponibili: Google le pubblica a mese concluso.")

    return {
        "days": days,
        "actions": actions,
        "impressions": impressions,
        "totals": {
            "impressions": round(total_impr),
            "impressions_change": _pct_change(total_impr, prev_impr),
            "actions": round(total_actions),
            "actions_change": _pct_change(total_actions, prev_actions),
            "action_rate": _ratio(total_actions, total_impr),
            "maps_share": _ratio(sum(r["value"] for r in impressions if "maps" in r["metric"]), total_impr),
            "mobile_share": _ratio(sum(r["value"] for r in impressions if "mobile" in r["metric"]), total_impr),
        },
        "daily": list(daily.values()),
        "weekday_actions": weekday_actions,
        "keywords": {
            "month": latest_month,
            "previous_month": prev_month,
            "top": keywords[:50],
            "rising": rising,
            "new": [k for k in keywords if k["is_new"]][:15],
            "trend": keyword_trend,
        },
        "reviews": {
            "average": round(api_average, 2) if api_average else (
                round(sum(r["rating"] for r in rated) / len(rated), 2) if rated else None),
            "total": int(api_total) if api_total else len(reviews),
            "imported": len(reviews),
            "in_period": len(in_period),
            "in_period_average": round(sum(r["rating"] for r in in_period) / len(in_period), 2) if in_period else None,
            "distribution": distribution,
            "reply_rate": _ratio(len(replied), len(reviews)),
            "median_reply_hours": round(median(reply_hours), 1) if reply_hours else None,
            "unanswered": [_fmt(r) for r in reviews if not r["reply_comment"]][:15],
            "negative": [_fmt(r) for r in rated if r["rating"] <= 3][:15],
            "recent": [_fmt(r) for r in reviews[:20]],
            "trend": review_trend,
            "words": _words([r["comment"] for r in reviews if r["comment"]]),
            "words_negative": _words([r["comment"] for r in rated if r["comment"] and r["rating"] <= 3], 10),
        },
        "notes": notes,
    }

from __future__ import annotations

import asyncio
import os
import zlib
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from .base import Connector, ConnectorResult
from .history import done_cursor, incremental_days, plan_windows
from ..config_store import get as config_get, set_many
from .. import db


# Metriche Pagina Facebook. Meta ne ha dismesse diverse (page_impressions,
# page_fans, page_engaged_users…): quelle rifiutate vengono ricordate in
# api_skips e riprovate solo dopo una settimana.
PAGE_METRICS = [
    "page_media_view",
    "page_total_media_view_unique",
    "page_post_engagements",
    "page_follows",
    "page_daily_follows_unique",
    "page_daily_unfollows_unique",
    "page_views_total",
    "page_video_views",
    "page_video_view_time",
    "page_actions_post_reactions_total",
]

# Instagram: metriche account con serie giornaliera nativa.
IG_TIME_SERIES_METRICS = ["reach"]
# follower_count esiste solo per gli ultimi 30 giorni (e da 100 follower).
IG_FOLLOWER_METRIC = "follower_count"
# Metriche account disponibili solo come totale: si chiedono giorno per giorno.
IG_TOTAL_VALUE_METRICS = [
    "views",
    "accounts_engaged",
    "total_interactions",
    "likes",
    "comments",
    "shares",
    "saves",
    "replies",
    "profile_links_taps",
]
IG_DEMOGRAPHIC_BREAKDOWNS = ["city", "country", "age", "gender"]

# Metriche per singolo contenuto Instagram, per formato.
IG_MEDIA_METRICS = {
    "reel": [
        "reach", "views", "total_interactions", "likes", "comments", "shares",
        "saved", "ig_reels_avg_watch_time", "ig_reels_video_view_total_time",
    ],
    "feed": [
        "reach", "views", "total_interactions", "likes", "comments", "shares",
        "saved", "profile_visits", "follows",
    ],
    "story": ["reach", "views", "replies", "shares", "total_interactions", "navigation"],
}
IG_MEDIA_FALLBACK = ["reach", "likes", "comments", "shares", "saved"]

# Metriche per singolo post Facebook.
POST_METRICS = [
    "post_media_view",
    "post_total_media_view_unique",
    "post_clicks",
    "post_reactions_by_type_total",
    "post_video_views",
    "post_video_avg_time_watched",
]

# Codici Graph API di limite richieste: si interrompe e si riprende al giro dopo.
RATE_LIMIT_CODES = {4, 17, 32, 613, 80001}

MAX_HISTORY_DAYS = 540          # Pagina: Meta conserva circa 2 anni
PAGE_CHUNK_DAYS = 90            # la Graph API accetta finestre fino a 93 giorni
IG_CHUNK_DAYS = 30              # Instagram accetta finestre fino a 30 giorni
IG_HISTORY_DAYS = 365
IG_DAILY_BACKFILL_DAYS = 30     # metriche "totale" chieste giorno per giorno
IG_DAILY_INCREMENTAL_DAYS = 7
RECENT_CONTENT_DAYS = 60        # contenuti recenti: metriche aggiornate a ogni sync


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _day_iso(day: date) -> str:
    return f"{day.isoformat()}T00:00:00+00:00"


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def series_to_metrics(
    payload: dict[str, Any],
    prefix: str,
    dimension: str | None = None,
    dimension_value: str | None = None,
) -> list[dict[str, Any]]:
    """Converte una risposta /insights (period=day) in datapoint.

    I valori a dizionario (es. reazioni per tipo) diventano un totale più una
    serie ``<metrica>_breakdown`` con la chiave come dimensione.
    """
    out: list[dict[str, Any]] = []
    for series in payload.get("data", []) or []:
        name = series.get("name")
        if not name:
            continue
        for item in series.get("values", []) or []:
            captured_at = item.get("end_time") or datetime.now(timezone.utc).isoformat()
            raw = item.get("value")
            if isinstance(raw, dict):
                parts = {k: _numeric(v) for k, v in raw.items()}
                parts = {k: v for k, v in parts.items() if v is not None}
                if not parts:
                    continue
                out.append({"metric": f"{prefix}{name}", "value": sum(parts.values()),
                            "dimension": dimension, "dimension_value": dimension_value,
                            "captured_at": captured_at})
                for key, value in parts.items():
                    out.append({"metric": f"{prefix}{name}_breakdown", "value": value,
                                "dimension": "breakdown", "dimension_value": str(key),
                                "captured_at": captured_at})
                continue
            numeric = _numeric(raw)
            if numeric is None:
                continue
            out.append({"metric": f"{prefix}{name}", "value": numeric,
                        "dimension": dimension, "dimension_value": dimension_value,
                        "captured_at": captured_at})
    return out


def total_values(payload: dict[str, Any]) -> dict[str, float]:
    """Legge le risposte metric_type=total_value (senza breakdown)."""
    out: dict[str, float] = {}
    for series in payload.get("data", []) or []:
        name = series.get("name")
        total = series.get("total_value") or {}
        numeric = _numeric(total.get("value"))
        if name and numeric is not None:
            out[name] = numeric
            continue
        # Alcune metriche per contenuto rispondono con "values".
        values = series.get("values") or []
        if name and values:
            numeric = _numeric(values[-1].get("value"))
            if numeric is not None:
                out[name] = numeric
    return out


def breakdown_values(payload: dict[str, Any]) -> list[tuple[str, float]]:
    """Legge total_value.breakdowns[].results[] (demografia, follow/unfollow)."""
    out: list[tuple[str, float]] = []
    for series in payload.get("data", []) or []:
        for breakdown in (series.get("total_value") or {}).get("breakdowns", []) or []:
            for result in breakdown.get("results", []) or []:
                labels = result.get("dimension_values") or []
                numeric = _numeric(result.get("value"))
                if labels and numeric is not None:
                    out.append((" / ".join(str(x) for x in labels), numeric))
    return out


def facebook_format(post: dict[str, Any]) -> str:
    attachments = ((post.get("attachments") or {}).get("data") or [{}])[0]
    kind = str(attachments.get("media_type") or attachments.get("type") or "").lower()
    status = str(post.get("status_type") or "").lower()
    if "reel" in kind or "reel" in status:
        return "facebook_reel"
    if "video" in kind or "video" in status:
        return "facebook_video"
    if kind in {"album"} or "album" in status:
        return "facebook_album"
    if kind in {"photo"} or "photo" in status:
        return "facebook_photo"
    if kind in {"share", "link"} or "shared_story" in status:
        return "facebook_link"
    return "facebook_status"


def instagram_format(media: dict[str, Any]) -> tuple[str, str]:
    """(content_type, famiglia di metriche)."""
    product = str(media.get("media_product_type") or "").lower()
    media_type = str(media.get("media_type") or "").lower()
    if product == "reels":
        return "instagram_reel", "reel"
    if product == "story":
        return "instagram_story", "story"
    if media_type == "carousel_album":
        return "instagram_carousel", "feed"
    if media_type == "video":
        return "instagram_video", "feed"
    return "instagram_image", "feed"


def needs_refresh(content_id: str, published_at: str | None, known: set[str], today: date) -> bool:
    """Contenuti recenti sempre; vecchi alla prima volta e poi una volta a settimana."""
    if content_id not in known:
        return True
    try:
        published = datetime.fromisoformat(str(published_at).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return True
    if (today - published).days <= RECENT_CONTENT_DAYS:
        return True
    return (zlib.crc32(content_id.encode()) % 7) == today.weekday()


class MetaConnector(Connector):
    provider = "meta"

    def __init__(self) -> None:
        self.page_id = config_get("META_PAGE_ID").strip()
        self.access_token = config_get("META_PAGE_ACCESS_TOKEN").strip()
        self.app_id = config_get("META_APP_ID").strip()
        self.app_secret = config_get("META_APP_SECRET").strip()
        self.instagram_account_id = config_get("META_INSTAGRAM_ACCOUNT_ID").strip()
        self.version = config_get("META_GRAPH_VERSION", "v26.0").strip() or "v26.0"
        self._rate_limited = False
        self._budget_used = 0
        self._probed: set[str] = set()
        self._skips: dict[str, str] = {}
        self._new_skips: dict[str, str] = {}

    def configured(self) -> bool:
        return bool(self.page_id and self.access_token)

    @property
    def graph_base(self) -> str:
        return f"https://graph.facebook.com/{self.version}"

    async def discover_accounts(self) -> dict[str, Any]:
        if not self.configured():
            raise RuntimeError("Servono META_PAGE_ID e META_PAGE_ACCESS_TOKEN")

        async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
            response = await client.get(
                f"{self.graph_base}/{self.page_id}",
                params={
                    "fields": (
                        "id,name,username,"
                        "instagram_business_account{"
                        "id,username,followers_count,media_count"
                        "}"
                    ),
                    "access_token": self.access_token,
                },
            )
            response.raise_for_status()
            payload = response.json()

        ig = payload.get("instagram_business_account") or {}
        ig_id = str(ig.get("id") or "").strip()
        if ig_id:
            self.instagram_account_id = ig_id
            set_many({"META_INSTAGRAM_ACCOUNT_ID": ig_id})

        return {
            "facebook_page": {
                "id": str(payload.get("id") or self.page_id),
                "name": payload.get("name"),
                "username": payload.get("username"),
            },
            "instagram": {
                "connected": bool(ig_id),
                "id": ig_id or None,
                "username": ig.get("username"),
                "followers_count": ig.get("followers_count"),
                "media_count": ig.get("media_count"),
            },
        }

    # ------------------------------------------------------------------
    # chiamate Graph API
    # ------------------------------------------------------------------

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str | None]:
        """GET resiliente: (payload, errore). Segnala il limite di richieste."""
        if self._rate_limited:
            return None, "limite richieste Meta raggiunto"
        query = dict(params or {})
        if "access_token=" not in url:
            query.setdefault("access_token", self.access_token)
        try:
            response = await client.get(url, params=query)
        except httpx.HTTPError as exc:
            return None, f"rete: {exc}"
        if response.status_code < 400:
            try:
                return response.json(), None
            except ValueError:
                return None, "risposta non valida"
        try:
            error = response.json().get("error", {})
        except ValueError:
            error = {}
        code = error.get("code")
        if code in RATE_LIMIT_CODES or response.status_code == 429:
            self._rate_limited = True
        return None, error.get("message") or f"HTTP {response.status_code}"

    async def _paged(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
        max_pages: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        items: list[dict[str, Any]] = []
        next_url: str | None = url
        query: dict[str, Any] | None = params
        for _ in range(max_pages):
            if not next_url:
                break
            payload, error = await self._get(client, next_url, query)
            if error:
                return items, error
            items.extend(payload.get("data", []) or [])
            next_url = (payload.get("paging") or {}).get("next")
            query = None  # il link "next" contiene già tutti i parametri
        return items, None

    def _skip(self, item: str, reason: str) -> None:
        # Un limite di richieste non significa che la metrica non esista.
        if not self._rate_limited:
            self._new_skips[item] = reason

    # ------------------------------------------------------------------
    # Pagina Facebook
    # ------------------------------------------------------------------

    async def _page_insights(
        self,
        client: httpx.AsyncClient,
        windows: list[tuple[date, date]],
    ) -> list[dict[str, Any]]:
        metrics: list[dict[str, Any]] = []
        active = [m for m in PAGE_METRICS if f"page:{m}" not in self._skips]
        for window_start, window_end in windows:
            since = int(datetime.combine(window_start, datetime.min.time(), timezone.utc).timestamp())
            until = int(datetime.combine(window_end + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
            for metric in list(active):
                payload, error = await self._get(
                    client,
                    f"{self.graph_base}/{self.page_id}/insights",
                    {"metric": metric, "period": "day", "since": since, "until": until},
                )
                if error:
                    if self._rate_limited:
                        return metrics
                    # Solo la finestra più recente decide se la metrica esiste.
                    if window_end == windows[0][1]:
                        self._skip(f"page:{metric}", error)
                        active.remove(metric)
                    continue
                metrics.extend(series_to_metrics(payload, "meta_"))
        return metrics

    async def _facebook_posts(
        self,
        client: httpx.AsyncClient,
        since: int,
        today: date,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
        rich_fields = (
            "id,message,created_time,permalink_url,status_type,shares,"
            "reactions.summary(total_count).limit(0),"
            "comments.summary(total_count).limit(0),"
            "attachments{media_type,type}"
        )
        url = f"{self.graph_base}/{self.page_id}/posts"
        posts, error = await self._paged(
            client, url, {"fields": rich_fields, "since": since, "limit": 100}, 30
        )
        if error and not posts:
            # Senza permessi per reazioni/commenti si ripiega sui campi base.
            posts, _ = await self._paged(
                client,
                url,
                {"fields": "id,message,created_time,permalink_url,status_type", "since": since, "limit": 100},
                30,
            )

        items: list[dict[str, Any]] = []
        metrics: list[dict[str, Any]] = []
        # Un post è "già misurato" se ha almeno una metrica da /insights.
        known: set[str] = set()
        for metric in ("facebook_post_media_view", "facebook_post_total_media_view_unique", "facebook_post_clicks"):
            known |= db.known_dimension_values(self.provider, metric, "post_id")
        to_refresh: list[tuple[str, str]] = []

        for post in posts:
            post_id = str(post.get("id") or "")
            if not post_id:
                continue
            created = post.get("created_time") or datetime.now(timezone.utc).isoformat()
            message = str(post.get("message") or "").strip()
            items.append(
                {
                    "external_id": post_id,
                    "content_type": facebook_format(post),
                    "title": message[:140] if message else "Post Facebook",
                    "url": post.get("permalink_url"),
                    "status": "published",
                    "published_at": created,
                    "modified_at": created,
                }
            )
            for name, raw in (
                ("reactions", ((post.get("reactions") or {}).get("summary") or {}).get("total_count")),
                ("comments", ((post.get("comments") or {}).get("summary") or {}).get("total_count")),
                ("shares", (post.get("shares") or {}).get("count", 0 if "shares" in post or "reactions" in post else None)),
            ):
                value = _numeric(raw)
                if value is not None:
                    metrics.append({"metric": f"facebook_post_{name}", "value": value,
                                    "dimension": "post_id", "dimension_value": post_id,
                                    "captured_at": created})
            if needs_refresh(post_id, created, known, today):
                to_refresh.append((post_id, created))

        refreshed = 0
        for post_id, created in to_refresh[: self._content_budget()]:
            values = await self._object_insights(client, post_id, "post", POST_METRICS, [])
            if values is None:
                break
            refreshed += 1
            self._budget_used += 1
            for metric in values:
                metric.update({"dimension": "post_id", "dimension_value": post_id, "captured_at": created})
                metric["metric"] = "facebook_" + metric["metric"]
                metrics.append(metric)
        return items, metrics, refreshed

    # ------------------------------------------------------------------
    # insights di un singolo oggetto (post, media, storia)
    # ------------------------------------------------------------------

    def _content_budget(self) -> int:
        return max(0, _int_env("GE360_META_CONTENT_PER_SYNC", 250) - self._budget_used)

    async def _object_insights(
        self,
        client: httpx.AsyncClient,
        object_id: str,
        family: str,
        wanted: list[str],
        fallback: list[str],
    ) -> list[dict[str, Any]] | None:
        """Metriche di un contenuto. None = limite richieste, stop."""
        metrics = [m for m in wanted if f"{family}:{m}" not in self._skips]
        if not metrics:
            return []
        payload, error = await self._get(
            client, f"{self.graph_base}/{object_id}/insights", {"metric": ",".join(metrics)}
        )
        if self._rate_limited:
            return None
        if error:
            # Una metrica non valida fa fallire tutta la chiamata: si individua
            # quale, una volta sola, e la si ricorda.
            if family not in self._probed:
                self._probed.add(family)
                good: list[str] = []
                for metric in metrics:
                    _, single_error = await self._get(
                        client, f"{self.graph_base}/{object_id}/insights", {"metric": metric}
                    )
                    if self._rate_limited:
                        return None
                    if single_error:
                        self._skip(f"{family}:{metric}", single_error)
                    else:
                        good.append(metric)
                metrics = good
            else:
                metrics = [m for m in fallback if f"{family}:{m}" not in self._skips]
            if not metrics:
                return []
            payload, error = await self._get(
                client, f"{self.graph_base}/{object_id}/insights", {"metric": ",".join(metrics)}
            )
            if self._rate_limited:
                return None
            if error:
                return []

        out: list[dict[str, Any]] = []
        for series in payload.get("data", []) or []:
            name = series.get("name")
            values = series.get("values") or []
            raw = (series.get("total_value") or {}).get("value")
            if raw is None and values:
                raw = values[-1].get("value")
            if isinstance(raw, dict):
                parts = {k: _numeric(v) for k, v in raw.items()}
                parts = {k: v for k, v in parts.items() if v is not None}
                if parts:
                    out.append({"metric": f"{name}", "value": sum(parts.values())})
                continue
            numeric = _numeric(raw)
            if name and numeric is not None:
                out.append({"metric": f"{name}", "value": numeric})
        return out

    # ------------------------------------------------------------------
    # Instagram
    # ------------------------------------------------------------------

    async def _ig_account_series(
        self,
        client: httpx.AsyncClient,
        ig_id: str,
        windows: list[tuple[date, date]],
    ) -> list[dict[str, Any]]:
        metrics: list[dict[str, Any]] = []
        url = f"{self.graph_base}/{ig_id}/insights"
        for index, (window_start, window_end) in enumerate(windows):
            since = int(datetime.combine(window_start, datetime.min.time(), timezone.utc).timestamp())
            until = int(datetime.combine(window_end + timedelta(days=1), datetime.min.time(), timezone.utc).timestamp())
            wanted = [m for m in IG_TIME_SERIES_METRICS if f"ig:{m}" not in self._skips]
            if index == 0 and f"ig:{IG_FOLLOWER_METRIC}" not in self._skips:
                wanted.append(IG_FOLLOWER_METRIC)
            for metric in wanted:
                payload, error = await self._get(
                    client, url, {"metric": metric, "period": "day", "since": since, "until": until}
                )
                if error:
                    if self._rate_limited:
                        return metrics
                    if index == 0:
                        self._skip(f"ig:{metric}", error)
                    continue
                metrics.extend(series_to_metrics(payload, "instagram_", "account", ig_id))
        return metrics

    async def _ig_account_daily_totals(
        self,
        client: httpx.AsyncClient,
        ig_id: str,
        days: int,
        end: date,
    ) -> list[dict[str, Any]]:
        """Metriche disponibili solo come totale: una chiamata per giorno."""
        metrics: list[dict[str, Any]] = []
        url = f"{self.graph_base}/{ig_id}/insights"
        wanted = [m for m in IG_TOTAL_VALUE_METRICS if f"ig:{m}" not in self._skips]
        follow_ok = "ig:follows_and_unfollows" not in self._skips

        for offset in range(days):
            day = end - timedelta(days=offset)
            since = int(datetime.combine(day, datetime.min.time(), timezone.utc).timestamp())
            until = since + 86400
            base = {"period": "day", "metric_type": "total_value", "since": since, "until": until}

            if wanted:
                payload, error = await self._get(client, url, {**base, "metric": ",".join(wanted)})
                if error and not self._rate_limited and offset == 0:
                    good = []
                    for metric in wanted:
                        _, single_error = await self._get(client, url, {**base, "metric": metric})
                        if self._rate_limited:
                            break
                        if single_error:
                            self._skip(f"ig:{metric}", single_error)
                        else:
                            good.append(metric)
                    wanted = good
                    payload, error = (None, "riprova") if not wanted else await self._get(
                        client, url, {**base, "metric": ",".join(wanted)}
                    )
                if self._rate_limited:
                    return metrics
                if not error and payload:
                    for name, value in total_values(payload).items():
                        metrics.append({"metric": f"instagram_{name}", "value": value,
                                        "dimension": "account", "dimension_value": ig_id,
                                        "captured_at": _day_iso(day)})

            if follow_ok:
                payload, error = await self._get(
                    client, url, {**base, "metric": "follows_and_unfollows", "breakdown": "follow_type"}
                )
                if self._rate_limited:
                    return metrics
                if error:
                    if offset == 0:
                        self._skip("ig:follows_and_unfollows", error)
                        follow_ok = False
                else:
                    for label, value in breakdown_values(payload):
                        kind = "follows" if label.upper().startswith("FOLLOWER") else "unfollows"
                        metrics.append({"metric": f"instagram_daily_{kind}", "value": value,
                                        "dimension": "account", "dimension_value": ig_id,
                                        "captured_at": _day_iso(day)})
        return metrics

    async def _ig_audience(
        self,
        client: httpx.AsyncClient,
        ig_id: str,
        today: date,
    ) -> list[dict[str, Any]]:
        """Demografia dei follower e orari online (fotografia del giorno)."""
        metrics: list[dict[str, Any]] = []
        url = f"{self.graph_base}/{ig_id}/insights"
        captured = _day_iso(today)

        if "ig:follower_demographics" not in self._skips:
            for breakdown in IG_DEMOGRAPHIC_BREAKDOWNS:
                params = {"metric": "follower_demographics", "period": "lifetime",
                          "metric_type": "total_value", "breakdown": breakdown}
                payload, error = await self._get(client, url, params)
                if error and not self._rate_limited:
                    payload, error = await self._get(client, url, {**params, "timeframe": "this_month"})
                if self._rate_limited:
                    return metrics
                if error:
                    # Tipicamente: meno di 100 follower. Si riprova tra una settimana.
                    self._skip("ig:follower_demographics", error)
                    break
                for label, value in breakdown_values(payload):
                    metrics.append({"metric": "instagram_follower_demographics", "value": value,
                                    "dimension": breakdown, "dimension_value": label,
                                    "captured_at": captured})

        if "ig:online_followers" not in self._skips:
            payload, error = await self._get(client, url, {"metric": "online_followers", "period": "lifetime"})
            if error:
                if not self._rate_limited:
                    self._skip("ig:online_followers", error)
            else:
                latest: dict[str, Any] = {}
                for series in payload.get("data", []) or []:
                    for item in series.get("values", []) or []:
                        if isinstance(item.get("value"), dict) and item["value"]:
                            latest = item["value"]
                for hour, value in latest.items():
                    numeric = _numeric(value)
                    if numeric is not None:
                        metrics.append({"metric": "instagram_online_followers", "value": numeric,
                                        "dimension": "hour", "dimension_value": str(int(hour)).zfill(2),
                                        "captured_at": captured})
        return metrics

    async def _instagram(
        self,
        client: httpx.AsyncClient,
        today: date,
        is_backfill: bool,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
        ig_id = self.instagram_account_id
        if not ig_id:
            try:
                discovered = await self.discover_accounts()
                ig_id = str(discovered.get("instagram", {}).get("id") or "")
            except Exception:
                return [], [], "Instagram non collegato/rilevabile"
        if not ig_id:
            return [], [], "Instagram professionale non collegato alla Pagina"

        profile, error = await self._get(
            client, f"{self.graph_base}/{ig_id}",
            {"fields": "id,username,followers_count,follows_count,media_count"},
        )
        if error:
            return [], [], f"Instagram non leggibile: {error}"

        captured = _day_iso(today)
        username = profile.get("username") or ig_id
        metrics: list[dict[str, Any]] = []
        for metric, key in (
            ("instagram_followers", "followers_count"),
            ("instagram_follows_count", "follows_count"),
            ("instagram_media_count", "media_count"),
        ):
            value = _numeric(profile.get(key))
            if value is not None:
                metrics.append({"metric": metric, "value": value, "dimension": "account",
                                "dimension_value": username, "captured_at": captured})

        # Serie account: storico lungo solo alla prima sincronizzazione.
        series_days = IG_HISTORY_DAYS if is_backfill else incremental_days()
        start = today - timedelta(days=series_days)
        windows: list[tuple[date, date]] = []
        window_end = today - timedelta(days=1)
        while window_end >= start:
            window_start = max(start, window_end - timedelta(days=IG_CHUNK_DAYS - 1))
            windows.append((window_start, window_end))
            window_end = window_start - timedelta(days=1)
        metrics.extend(await self._ig_account_series(client, ig_id, windows))
        metrics.extend(
            await self._ig_account_daily_totals(
                client, ig_id,
                IG_DAILY_BACKFILL_DAYS if is_backfill else IG_DAILY_INCREMENTAL_DAYS,
                today - timedelta(days=1),
            )
        )
        metrics.extend(await self._ig_audience(client, ig_id, today))

        # Contenuti: tutti, senza il vecchio limite di 50.
        media, _ = await self._paged(
            client,
            f"{self.graph_base}/{ig_id}/media",
            {"fields": "id,caption,media_type,media_product_type,permalink,timestamp,"
                       "like_count,comments_count", "limit": 100},
            _int_env("GE360_META_MEDIA_PAGES", 20),
        )
        stories, _ = await self._paged(
            client,
            f"{self.graph_base}/{ig_id}/stories",
            {"fields": "id,media_type,media_product_type,permalink,timestamp"},
            2,
        )

        content_items: list[dict[str, Any]] = []
        known = db.known_dimension_values(self.provider, "instagram_media_reach", "media_id")
        to_refresh: list[tuple[str, str, str]] = []
        for item in [*media, *[{**s, "media_product_type": "STORY"} for s in stories]]:
            media_id = str(item.get("id") or "")
            if not media_id:
                continue
            content_type, family = instagram_format(item)
            timestamp = item.get("timestamp") or datetime.now(timezone.utc).isoformat()
            caption = str(item.get("caption") or "").strip()
            content_items.append({
                "external_id": f"ig:{media_id}",
                "content_type": content_type,
                "title": caption[:140] if caption else ("Storia Instagram" if family == "story" else "Contenuto Instagram"),
                "url": item.get("permalink"),
                "status": "published",
                "published_at": timestamp,
                "modified_at": timestamp,
            })
            for metric, raw in (("instagram_media_like_count", item.get("like_count")),
                                ("instagram_media_comments_count", item.get("comments_count"))):
                value = _numeric(raw)
                if value is not None:
                    metrics.append({"metric": metric, "value": value, "dimension": "media_id",
                                    "dimension_value": media_id, "captured_at": timestamp})
            # Le storie spariscono dopo 24 ore: si leggono a ogni sincronizzazione.
            if family == "story" or needs_refresh(media_id, timestamp, known, today):
                to_refresh.append((media_id, timestamp, family))

        semaphore = asyncio.Semaphore(4)

        async def fetch(entry: tuple[str, str, str]):
            media_id, timestamp, family = entry
            async with semaphore:
                values = await self._object_insights(
                    client, media_id, family, IG_MEDIA_METRICS[family], IG_MEDIA_FALLBACK
                )
            return media_id, timestamp, values

        # Il primo contenuto di ogni formato va da solo: se una metrica non
        # esiste la si scopre una volta, poi gli altri partono in parallelo.
        budget = to_refresh[: self._content_budget()]
        first_by_family: dict[str, tuple[str, str, str]] = {}
        for entry in budget:
            first_by_family.setdefault(entry[2], entry)
        results = [await fetch(entry) for entry in first_by_family.values()]
        rest = [entry for entry in budget if entry not in first_by_family.values()]
        results.extend(await asyncio.gather(*(fetch(entry) for entry in rest)))

        refreshed = 0
        for media_id, timestamp, values in results:
            if not values:
                continue
            refreshed += 1
            for value in values:
                metrics.append({"metric": f"instagram_media_{value['metric']}", "value": value["value"],
                                "dimension": "media_id", "dimension_value": media_id,
                                "captured_at": timestamp})
        self._budget_used += len(budget)

        note = (
            f"Instagram @{username}: {int(_numeric(profile.get('followers_count')) or 0)} follower, "
            f"{len(content_items)} contenuti, metriche aggiornate per {refreshed}"
        )
        return metrics, content_items, note

    # ------------------------------------------------------------------
    # sincronizzazione
    # ------------------------------------------------------------------

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(provider=self.provider, ok=False, message="Meta/Facebook non configurato")

        self._rate_limited = False
        self._budget_used = 0
        self._probed = set()
        self._new_skips = {}
        self._skips = db.skipped_items(self.provider)

        today = datetime.now(timezone.utc).date()
        windows, is_backfill, history_start = plan_windows(
            cursor, today - timedelta(days=1), MAX_HISTORY_DAYS, PAGE_CHUNK_DAYS
        )
        post_days = 365 if is_backfill else 120
        post_since = int(datetime.combine(today - timedelta(days=post_days), datetime.min.time(), timezone.utc).timestamp())

        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            metrics = await self._page_insights(client, windows)
            posts, post_metrics, posts_refreshed = await self._facebook_posts(client, post_since, today)
            metrics.extend(post_metrics)
            try:
                ig_metrics, ig_content, ig_note = await self._instagram(client, today, is_backfill)
            except Exception as exc:  # Instagram non deve bloccare Facebook
                ig_metrics, ig_content, ig_note = [], [], f"Instagram non sincronizzato: {exc}"
        metrics.extend(ig_metrics)

        db.mark_skipped(self.provider, self._new_skips)

        notes = [ig_note]
        skipped_total = len(self._skips) + len(self._new_skips)
        if skipped_total:
            notes.append(f"{skipped_total} metriche non offerte da Meta per questo account (riprovo tra 7 giorni)")
        if self._rate_limited:
            notes.append("limite richieste Meta raggiunto: il resto al prossimo giro")

        # Lo storico si considera completo solo se non ci siamo fermati a metà.
        if is_backfill and not self._rate_limited:
            new_cursor = done_cursor(history_start)
        else:
            new_cursor = cursor

        mode = "storico completo" if is_backfill else "aggiornamento"
        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            content_items=[*posts, *ig_content],
            cursor=new_cursor,
            message=(
                f"Meta {mode}: {len(metrics)} datapoint, {len(posts)} post Facebook "
                f"(metriche per {posts_refreshed}), {len(ig_content)} contenuti Instagram; "
                + "; ".join(notes)
            ),
        )

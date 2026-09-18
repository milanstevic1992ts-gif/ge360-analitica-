from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .base import Connector, ConnectorResult
from ..config_store import get as config_get, set_many


CANDIDATE_PAGE_METRICS = [
    "page_media_view",
    "page_total_media_view_unique",
    "page_post_engagements",
    "page_follows",
    "page_views_total",
]


class MetaConnector(Connector):
    provider = "meta"

    def __init__(self) -> None:
        self.page_id = config_get("META_PAGE_ID").strip()
        self.access_token = config_get("META_PAGE_ACCESS_TOKEN").strip()
        self.app_id = config_get("META_APP_ID").strip()
        self.app_secret = config_get("META_APP_SECRET").strip()
        self.instagram_account_id = config_get("META_INSTAGRAM_ACCOUNT_ID").strip()
        self.version = config_get("META_GRAPH_VERSION", "v26.0").strip() or "v26.0"

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

    async def _metric(
        self,
        client: httpx.AsyncClient,
        metric: str,
        since: int,
        until: int,
    ) -> tuple[list[dict[str, Any]], str | None]:
        response = await client.get(
            f"{self.graph_base}/{self.page_id}/insights",
            params={
                "metric": metric,
                "period": "day",
                "since": since,
                "until": until,
                "access_token": self.access_token,
            },
        )

        if response.status_code >= 400:
            try:
                error = response.json().get("error", {}).get("message", "")
            except Exception:
                error = response.text[:300]
            return [], error or f"HTTP {response.status_code}"

        payload = response.json()
        metrics = []

        for series in payload.get("data", []):
            metric_name = series.get("name") or metric
            for item in series.get("values", []):
                value = item.get("value", 0)
                if isinstance(value, dict):
                    continue
                try:
                    numeric = float(value or 0)
                except (TypeError, ValueError):
                    continue

                metrics.append(
                    {
                        "metric": f"meta_{metric_name}",
                        "value": numeric,
                        "captured_at": item.get("end_time")
                        or datetime.now(timezone.utc).isoformat(),
                    }
                )

        return metrics, None

    async def _facebook_posts(
        self,
        client: httpx.AsyncClient,
        since: int,
    ) -> list[dict[str, Any]]:
        url = f"{self.graph_base}/{self.page_id}/posts"
        params = {
            "fields": "id,message,created_time,permalink_url",
            "since": since,
            "limit": 100,
            "access_token": self.access_token,
        }
        items = []

        for _ in range(20):
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

            for post in payload.get("data", []):
                message = str(post.get("message", "")).strip()
                title = message[:140] if message else "Post Facebook"
                items.append(
                    {
                        "external_id": post.get("id"),
                        "content_type": "facebook_post",
                        "title": title,
                        "url": post.get("permalink_url"),
                        "status": "published",
                        "published_at": post.get("created_time"),
                        "modified_at": post.get("created_time"),
                    }
                )

            next_url = payload.get("paging", {}).get("next")
            if not next_url:
                break
            url = next_url
            params = {}

        return items

    async def _instagram_profile_and_media(
        self,
        client: httpx.AsyncClient,
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

        profile_response = await client.get(
            f"{self.graph_base}/{ig_id}",
            params={
                "fields": "id,username,followers_count,media_count",
                "access_token": self.access_token,
            },
        )
        profile_response.raise_for_status()
        profile = profile_response.json()

        captured_at = datetime.now(timezone.utc).isoformat()
        metrics = [
            {
                "metric": "instagram_followers",
                "value": float(profile.get("followers_count") or 0),
                "dimension": "account",
                "dimension_value": profile.get("username") or ig_id,
                "captured_at": captured_at,
            },
            {
                "metric": "instagram_media_count",
                "value": float(profile.get("media_count") or 0),
                "dimension": "account",
                "dimension_value": profile.get("username") or ig_id,
                "captured_at": captured_at,
            },
        ]

        url = f"{self.graph_base}/{ig_id}/media"
        params: dict[str, Any] = {
            "fields": (
                "id,caption,media_type,media_product_type,"
                "permalink,timestamp"
            ),
            "limit": 100,
            "access_token": self.access_token,
        }
        content_items: list[dict[str, Any]] = []

        for _ in range(10):
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()

            for media in payload.get("data", []):
                caption = str(media.get("caption") or "").strip()
                product = str(media.get("media_product_type") or "").lower()
                media_type = str(media.get("media_type") or "").lower()
                content_type = (
                    "instagram_reel"
                    if product == "reels"
                    else f"instagram_{media_type or 'media'}"
                )
                content_items.append(
                    {
                        "external_id": f"ig:{media.get('id')}",
                        "content_type": content_type,
                        "title": caption[:140] if caption else "Contenuto Instagram",
                        "url": media.get("permalink"),
                        "status": "published",
                        "published_at": media.get("timestamp"),
                        "modified_at": media.get("timestamp"),
                    }
                )

            next_url = payload.get("paging", {}).get("next")
            if not next_url:
                break
            url = next_url
            params = {}

        return (
            metrics,
            content_items,
            f"Instagram @{profile.get('username') or ig_id}: "
            f"{int(profile.get('followers_count') or 0)} follower, "
            f"{len(content_items)} contenuti importati",
        )

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                message="Meta/Facebook non configurato",
            )

        now = datetime.now(timezone.utc)
        since_dt = now - timedelta(days=32)
        since = int(since_dt.timestamp())
        until = int(now.timestamp())

        metrics = []
        skipped = {}

        async with httpx.AsyncClient(timeout=35, follow_redirects=True) as client:
            for metric in CANDIDATE_PAGE_METRICS:
                values, error = await self._metric(client, metric, since, until)
                if error:
                    skipped[metric] = error
                    continue
                metrics.extend(values)

            try:
                posts = await self._facebook_posts(client, since)
            except httpx.HTTPStatusError:
                posts = []

            try:
                ig_metrics, ig_content, ig_note = await self._instagram_profile_and_media(client)
            except Exception as exc:
                ig_metrics, ig_content = [], []
                ig_note = f"Instagram non sincronizzato: {exc}"

        metrics.extend(ig_metrics)
        content_items = [*posts, *ig_content]

        note = f"; {ig_note}"
        if skipped:
            note += f"; {len(skipped)} metriche Page non disponibili"

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            content_items=content_items,
            message=(
                f"Meta sincronizzato: {len(metrics)} datapoint, "
                f"{len(posts)} post Facebook, {len(ig_content)} contenuti Instagram"
                f"{note}"
            ),
        )

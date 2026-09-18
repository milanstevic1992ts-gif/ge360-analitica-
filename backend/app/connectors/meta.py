import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from .base import Connector, ConnectorResult


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
        self.page_id = os.getenv("META_PAGE_ID", "").strip()
        self.access_token = os.getenv("META_PAGE_ACCESS_TOKEN", "").strip()
        self.version = os.getenv("META_GRAPH_VERSION", "v26.0").strip()

    def configured(self) -> bool:
        return bool(self.page_id and self.access_token)

    @property
    def graph_base(self) -> str:
        return f"https://graph.facebook.com/{self.version}"

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
                    # Alcune metriche breakdown non sono scalari: non sommiamo
                    # categorie semanticamente diverse in automatico.
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

    async def _posts(
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

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                message="Meta Page non configurata",
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
                posts = await self._posts(client, since)
            except httpx.HTTPStatusError:
                posts = []

        note = ""
        if skipped:
            note = f"; {len(skipped)} metriche non disponibili"

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            content_items=posts,
            message=(
                f"Meta sincronizzato: {len(metrics)} datapoint, "
                f"{len(posts)} post{note}"
            ),
        )

import html
import os
import re
from datetime import datetime, timezone
from typing import Any

import httpx

from .base import Connector, ConnectorResult
from ..config_store import get as config_get


_TAG_RE = re.compile(r"<[^>]+>")


def _wp_datetime(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        ).isoformat()
    except ValueError:
        return value


def _plain_title(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("rendered", "")
    value = html.unescape(str(value or ""))
    return _TAG_RE.sub("", value).strip()


class WordPressConnector(Connector):
    provider = "wordpress"

    def __init__(self) -> None:
        self.base_url = config_get("WORDPRESS_BASE_URL").rstrip("/")
        self.username = config_get("WORDPRESS_USERNAME")
        self.app_password = config_get("WORDPRESS_APP_PASSWORD")
        self.ge360_key = config_get("WORDPRESS_GE360_KEY")

    def configured(self) -> bool:
        return bool(self.base_url)

    def _auth(self):
        if self.username and self.app_password:
            return (self.username, self.app_password)
        return None

    async def _fetch_collection(
        self,
        client: httpx.AsyncClient,
        collection: str,
    ) -> list[dict[str, Any]]:
        endpoint = f"{self.base_url}/wp-json/wp/v2/{collection}"
        page = 1
        items: list[dict[str, Any]] = []

        while True:
            response = await client.get(
                endpoint,
                params={
                    "per_page": 100,
                    "page": page,
                    "_fields": "id,type,link,slug,status,date_gmt,modified_gmt,title",
                },
            )

            if response.status_code == 400 and page > 1:
                break

            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                break

            items.extend(batch)
            total_pages = int(response.headers.get("X-WP-TotalPages", "1"))
            if page >= total_pages or not batch:
                break
            page += 1

        return items

    async def _fetch_tracker_events(
        self,
        client: httpx.AsyncClient,
        cursor: str | None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        if not self.ge360_key:
            return [], cursor

        after_id = int(cursor or 0)
        events: list[dict[str, Any]] = []

        while True:
            response = await client.get(
                f"{self.base_url}/wp-json/ge360/v1/events",
                params={"after_id": after_id, "limit": 500},
                headers={"X-GE360-Key": self.ge360_key},
            )

            if response.status_code == 404:
                # Il plugin tracker non è ancora installato sul sito.
                return [], cursor

            response.raise_for_status()
            payload = response.json()
            batch = payload.get("events", []) if isinstance(payload, dict) else []

            for event in batch:
                events.append(
                    {
                        "external_id": str(event.get("id")),
                        "event_type": event.get("event_type"),
                        "source": event.get("source") or None,
                        "campaign": event.get("campaign") or None,
                        "content_id": event.get("content_id") or None,
                        "url": event.get("url") or None,
                        "occurred_at": _wp_datetime(event.get("occurred_at")),
                    }
                )

            last_id = int(payload.get("last_id", after_id))
            if last_id > after_id:
                after_id = last_id

            if not payload.get("has_more") or not batch:
                break

        return events, str(after_id)

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                message="WORDPRESS_BASE_URL non configurato",
            )

        async with httpx.AsyncClient(
            timeout=30,
            follow_redirects=True,
            auth=self._auth(),
        ) as client:
            posts = await self._fetch_collection(client, "posts")
            pages = await self._fetch_collection(client, "pages")
            events, next_cursor = await self._fetch_tracker_events(client, cursor)

        content_items = []
        for content_type, batch in (("post", posts), ("page", pages)):
            for item in batch:
                content_items.append(
                    {
                        "external_id": str(item.get("id")),
                        "content_type": content_type,
                        "title": _plain_title(item.get("title")),
                        "url": item.get("link"),
                        "status": item.get("status"),
                        "published_at": item.get("date_gmt"),
                        "modified_at": item.get("modified_gmt"),
                    }
                )

        tracker_note = (
            f", {len(events)} nuovi eventi tracker"
            if self.ge360_key
            else ", tracker non configurato"
        )

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=[
                {"metric": "wordpress_posts", "value": len(posts)},
                {"metric": "wordpress_pages", "value": len(pages)},
            ],
            events=events,
            content_items=content_items,
            cursor=next_cursor,
            message=(
                f"WordPress sincronizzato: {len(pages)} pagine, "
                f"{len(posts)} articoli{tracker_note}"
            ),
        )

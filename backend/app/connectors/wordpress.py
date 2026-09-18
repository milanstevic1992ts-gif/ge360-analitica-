import os

import httpx

from .base import Connector, ConnectorResult


class WordPressConnector(Connector):
    provider = "wordpress"

    def __init__(self) -> None:
        self.base_url = os.getenv("WORDPRESS_BASE_URL", "").rstrip("/")
        self.username = os.getenv("WORDPRESS_USERNAME", "")
        self.app_password = os.getenv("WORDPRESS_APP_PASSWORD", "")

    def configured(self) -> bool:
        return bool(self.base_url)

    async def sync(self) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                metrics=[],
                events=[],
                message="WORDPRESS_BASE_URL non configurato",
            )

        endpoint = f"{self.base_url}/wp-json/wp/v2"
        auth = None
        if self.username and self.app_password:
            auth = (self.username, self.app_password)

        async with httpx.AsyncClient(timeout=20, follow_redirects=True, auth=auth) as client:
            posts_response = await client.get(
                f"{endpoint}/posts",
                params={"per_page": 1, "_fields": "id"},
            )
            pages_response = await client.get(
                f"{endpoint}/pages",
                params={"per_page": 1, "_fields": "id"},
            )
            posts_response.raise_for_status()
            pages_response.raise_for_status()

        posts_total = int(posts_response.headers.get("X-WP-Total", 0))
        pages_total = int(pages_response.headers.get("X-WP-Total", 0))

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=[
                {"metric": "wordpress_posts", "value": posts_total},
                {"metric": "wordpress_pages", "value": pages_total},
            ],
            events=[],
            message="WordPress raggiungibile",
        )

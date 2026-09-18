import os
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from .base import Connector, ConnectorResult
from .google_auth import GoogleAuth
from ..config_store import get as config_get


class SearchConsoleConnector(Connector):
    provider = "search_console"

    def __init__(self) -> None:
        self.site_url = config_get("SEARCH_CONSOLE_SITE_URL").strip()
        self.auth = GoogleAuth()

    def configured(self) -> bool:
        return bool(self.site_url and self.auth.configured())

    async def _query(
        self,
        client: httpx.AsyncClient,
        dimensions: list[str],
    ) -> dict[str, Any]:
        end = date.today() - timedelta(days=2)
        start = end - timedelta(days=32)

        response = await client.post(
            "https://www.googleapis.com/webmasters/v3/sites/"
            f"{quote(self.site_url, safe='')}/searchAnalytics/query",
            headers=await self.auth.headers(),
            json={
                "startDate": start.isoformat(),
                "endDate": end.isoformat(),
                "dimensions": dimensions,
                "rowLimit": 25000,
                "dataState": "final",
            },
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _normalize(
        payload: dict[str, Any],
        dimension: str,
    ) -> list[dict[str, Any]]:
        metrics = []
        for row in payload.get("rows", []):
            keys = row.get("keys", [])
            if len(keys) < 2:
                continue

            captured_at = f"{keys[0]}T00:00:00+00:00"
            dimension_value = keys[1]

            for name in ("clicks", "impressions", "ctr", "position"):
                metrics.append(
                    {
                        "metric": f"search_{name}",
                        "value": float(row.get(name, 0) or 0),
                        "dimension": dimension,
                        "dimension_value": dimension_value,
                        "captured_at": captured_at,
                    }
                )

        return metrics

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                message="Search Console non configurato",
            )

        async with httpx.AsyncClient(timeout=45) as client:
            query_payload = await self._query(client, ["date", "query"])
            page_payload = await self._query(client, ["date", "page"])

        metrics = self._normalize(query_payload, "query")
        metrics.extend(self._normalize(page_payload, "page"))

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            message=f"Search Console sincronizzato: {len(metrics)} datapoint",
        )

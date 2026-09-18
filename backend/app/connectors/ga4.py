import os
from datetime import datetime, timezone
from typing import Any

import httpx

from .base import Connector, ConnectorResult
from .google_auth import GoogleAuth
from ..config_store import get as config_get


def _ga_date(value: str) -> str:
    try:
        dt = datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:
        return value


class GA4Connector(Connector):
    provider = "ga4"

    def __init__(self) -> None:
        self.property_id = config_get("GA4_PROPERTY_ID").strip()
        self.auth = GoogleAuth()

    def configured(self) -> bool:
        return bool(self.property_id and self.auth.configured())

    async def _report(
        self,
        client: httpx.AsyncClient,
        dimensions: list[str],
        metrics: list[str],
    ) -> dict[str, Any]:
        response = await client.post(
            f"https://analyticsdata.googleapis.com/v1beta/properties/{self.property_id}:runReport",
            headers=await self.auth.headers(),
            json={
                "dateRanges": [{"startDate": "32daysAgo", "endDate": "yesterday"}],
                "dimensions": [{"name": name} for name in dimensions],
                "metrics": [{"name": name} for name in metrics],
                "limit": "100000",
                "keepEmptyRows": False,
            },
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _rows(
        payload: dict[str, Any],
        dimensions: list[str],
        metrics: list[str],
        dimension_name: str,
        metric_prefix: str,
    ) -> list[dict[str, Any]]:
        output = []

        for row in payload.get("rows", []):
            dim_values = [
                item.get("value", "") for item in row.get("dimensionValues", [])
            ]
            metric_values = [
                item.get("value", "0") for item in row.get("metricValues", [])
            ]

            if not dim_values:
                continue

            date_value = dim_values[0]
            dimension_value = dim_values[1] if len(dim_values) > 1 else ""

            for index, metric in enumerate(metrics):
                try:
                    numeric = float(metric_values[index])
                except (IndexError, TypeError, ValueError):
                    numeric = 0

                output.append(
                    {
                        "metric": f"{metric_prefix}_{metric}",
                        "value": numeric,
                        "dimension": dimension_name,
                        "dimension_value": dimension_value,
                        "captured_at": _ga_date(date_value),
                    }
                )

        return output

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                message="GA4 non configurato",
            )

        async with httpx.AsyncClient(timeout=40) as client:
            source_payload = await self._report(
                client,
                ["date", "sessionSource"],
                ["sessions", "totalUsers", "keyEvents"],
            )
            landing_payload = await self._report(
                client,
                ["date", "landingPagePlusQueryString"],
                ["sessions", "screenPageViews", "keyEvents"],
            )

        metrics = []
        metrics.extend(
            self._rows(
                source_payload,
                ["date", "sessionSource"],
                ["sessions", "totalUsers", "keyEvents"],
                "source",
                "ga4",
            )
        )
        metrics.extend(
            self._rows(
                landing_payload,
                ["date", "landingPagePlusQueryString"],
                ["sessions", "screenPageViews", "keyEvents"],
                "landing_page",
                "ga4",
            )
        )

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            message=f"GA4 sincronizzato: {len(metrics)} datapoint",
        )

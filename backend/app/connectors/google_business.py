import os
from datetime import date, timedelta
from typing import Any

import httpx

from .base import Connector, ConnectorResult
from .google_auth import GoogleAuth


DAILY_METRICS = [
    "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
    "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
    "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
    "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
    "BUSINESS_DIRECTION_REQUESTS",
    "CALL_CLICKS",
    "WEBSITE_CLICKS",
]


def _date_from_parts(parts: dict[str, Any]) -> str | None:
    if not parts:
        return None
    try:
        return (
            f"{int(parts['year']):04d}-{int(parts['month']):02d}-{int(parts['day']):02d}"
            "T00:00:00+00:00"
        )
    except Exception:
        return None


class GoogleBusinessConnector(Connector):
    provider = "google_business"

    def __init__(self) -> None:
        self.location = os.getenv("GOOGLE_BUSINESS_LOCATION_NAME", "").strip()
        self.auth = GoogleAuth()

    def configured(self) -> bool:
        return bool(self.location and self.auth.configured())

    async def _daily_metrics(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        end = date.today() - timedelta(days=1)
        start = end - timedelta(days=32)

        params: list[tuple[str, str]] = []
        for metric in DAILY_METRICS:
            params.append(("dailyMetrics", metric))

        params.extend(
            [
                ("dailyRange.start_date.year", str(start.year)),
                ("dailyRange.start_date.month", str(start.month)),
                ("dailyRange.start_date.day", str(start.day)),
                ("dailyRange.end_date.year", str(end.year)),
                ("dailyRange.end_date.month", str(end.month)),
                ("dailyRange.end_date.day", str(end.day)),
            ]
        )

        response = await client.get(
            "https://businessprofileperformance.googleapis.com/v1/"
            f"{self.location}:fetchMultiDailyMetricsTimeSeries",
            headers=await self.auth.headers(),
            params=params,
        )
        response.raise_for_status()
        payload = response.json()

        metrics = []
        for group in payload.get("multiDailyMetricTimeSeries", []):
            for series in group.get("dailyMetricTimeSeries", []):
                metric_name = str(series.get("dailyMetric", "")).lower()
                for point in series.get("timeSeries", {}).get("datedValues", []):
                    captured_at = _date_from_parts(point.get("date", {}))
                    if not captured_at:
                        continue
                    try:
                        value = float(point.get("value", 0) or 0)
                    except (TypeError, ValueError):
                        value = 0

                    metrics.append(
                        {
                            "metric": f"gbp_{metric_name}",
                            "value": value,
                            "captured_at": captured_at,
                        }
                    )

        return metrics

    async def _search_keywords(self, client: httpx.AsyncClient) -> list[dict[str, Any]]:
        today = date.today()
        end_month = date(today.year, today.month, 1)
        start_month = end_month - timedelta(days=370)
        start_month = date(start_month.year, start_month.month, 1)

        base_params = [
            ("monthlyRange.start_month.year", str(start_month.year)),
            ("monthlyRange.start_month.month", str(start_month.month)),
            ("monthlyRange.end_month.year", str(end_month.year)),
            ("monthlyRange.end_month.month", str(end_month.month)),
            ("pageSize", "100"),
        ]

        metrics = []
        page_token = None

        while True:
            params = list(base_params)
            if page_token:
                params.append(("pageToken", page_token))

            response = await client.get(
                "https://businessprofileperformance.googleapis.com/v1/"
                f"{self.location}/searchkeywords/impressions/monthly",
                headers=await self.auth.headers(),
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

            for item in payload.get("searchKeywordsCounts", []):
                keyword = item.get("searchKeyword", "")
                insights = item.get("insightsValue", {})
                raw = insights.get("value")
                threshold = False
                if raw is None:
                    raw = insights.get("threshold", 0)
                    threshold = True

                try:
                    value = float(raw or 0)
                except (TypeError, ValueError):
                    value = 0

                metrics.append(
                    {
                        "metric": "gbp_search_keyword_impressions",
                        "value": value,
                        "dimension": "query",
                        "dimension_value": keyword,
                        "captured_at": end_month.isoformat() + "T00:00:00+00:00",
                        "payload": {"threshold": threshold},
                    }
                )

            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        return metrics

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                message="Google Business Profile non configurato",
            )

        async with httpx.AsyncClient(timeout=45) as client:
            metrics = await self._daily_metrics(client)
            try:
                metrics.extend(await self._search_keywords(client))
                keyword_note = " incluse keyword mensili"
            except httpx.HTTPStatusError as exc:
                # Le keyword possono non essere disponibili per tutte le schede/quota.
                keyword_note = f"; keyword non disponibili ({exc.response.status_code})"

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            message=f"Google Business sincronizzato: {len(metrics)} datapoint{keyword_note}",
        )

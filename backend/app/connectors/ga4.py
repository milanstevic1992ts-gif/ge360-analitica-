from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from .base import Connector, ConnectorResult
from .google_auth import GoogleAuth
from .history import done_cursor, plan_windows
from ..config_store import get as config_get

# Ogni report: (nome dimensione in GE360, dimensione GA4, metriche).
# Le metriche sono solo "sommabili" (niente medie o percentuali): tassi e
# durate medie si calcolano poi in GE360 sul periodo scelto.
REPORTS: list[tuple[str | None, str | None, list[str]]] = [
    (
        None,
        None,
        [
            "sessions",
            "totalUsers",
            "newUsers",
            "engagedSessions",
            "screenPageViews",
            "userEngagementDuration",
            "keyEvents",
            "eventCount",
        ],
    ),
    ("source", "sessionSource", ["sessions", "totalUsers", "keyEvents"]),
    (
        "landing_page",
        "landingPagePlusQueryString",
        [
            "sessions",
            "screenPageViews",
            "keyEvents",
            "engagedSessions",
            "userEngagementDuration",
            "newUsers",
        ],
    ),
    (
        "channel",
        "sessionDefaultChannelGroup",
        ["sessions", "totalUsers", "newUsers", "engagedSessions", "keyEvents"],
    ),
    ("source_medium", "sessionSourceMedium", ["sessions", "engagedSessions", "keyEvents"]),
    ("campaign", "sessionCampaignName", ["sessions", "engagedSessions", "keyEvents"]),
    (
        "device",
        "deviceCategory",
        ["sessions", "totalUsers", "engagedSessions", "keyEvents", "userEngagementDuration"],
    ),
    ("city", "city", ["sessions", "totalUsers", "engagedSessions", "keyEvents"]),
    ("new_vs_returning", "newVsReturning", ["sessions", "totalUsers", "keyEvents"]),
    ("hour", "hour", ["sessions", "keyEvents"]),
    ("event_name", "eventName", ["eventCount"]),
    (
        "page_path",
        "pagePath",
        ["screenPageViews", "userEngagementDuration", "keyEvents"],
    ),
]

PAGE_SIZE = 100000
# GA4 Data API: i report standard coprono ben oltre i 14 mesi delle esplorazioni.
MAX_HISTORY_DAYS = 540
CHUNK_DAYS = 60


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
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        """Scarica tutte le righe di un report, pagina per pagina."""
        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            response = await client.post(
                "https://analyticsdata.googleapis.com/v1beta/"
                f"properties/{self.property_id}:runReport",
                headers=await self.auth.headers(),
                json={
                    "dateRanges": [
                        {"startDate": start.isoformat(), "endDate": end.isoformat()}
                    ],
                    "dimensions": [{"name": name} for name in dimensions],
                    "metrics": [{"name": name} for name in metrics],
                    "limit": str(PAGE_SIZE),
                    "offset": str(offset),
                    "keepEmptyRows": False,
                },
            )
            response.raise_for_status()
            payload = response.json()
            batch = payload.get("rows", []) or []
            rows.extend(batch)

            total = int(payload.get("rowCount", 0) or 0)
            offset += len(batch)
            if not batch or offset >= total:
                break

        return rows

    @staticmethod
    def _normalize(
        rows: list[dict[str, Any]],
        metrics: list[str],
        dimension_name: str | None,
    ) -> list[dict[str, Any]]:
        output = []

        for row in rows:
            dim_values = [item.get("value", "") for item in row.get("dimensionValues", [])]
            metric_values = [item.get("value", "0") for item in row.get("metricValues", [])]
            if not dim_values:
                continue

            captured_at = _ga_date(dim_values[0])
            dimension_value = dim_values[1] if len(dim_values) > 1 else None

            for index, metric in enumerate(metrics):
                try:
                    numeric = float(metric_values[index])
                except (IndexError, TypeError, ValueError):
                    numeric = 0.0

                output.append(
                    {
                        "metric": f"ga4_{metric}",
                        "value": numeric,
                        "dimension": dimension_name,
                        "dimension_value": dimension_value,
                        "captured_at": captured_at,
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

        end = date.today() - timedelta(days=1)
        windows, is_backfill, history_start = plan_windows(
            cursor, end, MAX_HISTORY_DAYS, CHUNK_DAYS
        )

        metrics: list[dict[str, Any]] = []
        skipped: dict[str, str] = {}

        async with httpx.AsyncClient(timeout=90) as client:
            for window_start, window_end in windows:
                for dimension_name, ga_dimension, report_metrics in REPORTS:
                    key = dimension_name or "totali"
                    if key in skipped:
                        continue

                    dimensions = ["date"] + ([ga_dimension] if ga_dimension else [])
                    try:
                        rows = await self._report(
                            client, dimensions, report_metrics, window_start, window_end
                        )
                    except httpx.HTTPStatusError as exc:
                        # 400 = combinazione non supportata da questa property:
                        # si salta il report senza fermare gli altri.
                        if exc.response.status_code == 400:
                            skipped[key] = exc.response.text[:200]
                            continue
                        raise

                    metrics.extend(self._normalize(rows, report_metrics, dimension_name))

        mode = "storico completo" if is_backfill else "aggiornamento"
        note = f"; {len(skipped)} report non disponibili" if skipped else ""

        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            cursor=done_cursor(history_start) if is_backfill else cursor,
            message=(
                f"GA4 {mode} dal {history_start.isoformat()}: "
                f"{len(metrics)} datapoint, {len(REPORTS) - len(skipped)} report{note}"
            ),
        )

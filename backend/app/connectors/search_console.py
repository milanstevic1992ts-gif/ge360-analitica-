from __future__ import annotations

from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

import httpx

from .base import Connector, ConnectorResult
from .google_auth import GoogleAuth
from .history import done_cursor, plan_windows
from ..config_store import get as config_get

ROW_LIMIT = 25000
# Search Console conserva 16 mesi di dati.
MAX_HISTORY_DAYS = 486
CHUNK_DAYS = 30

# Report salvati come metriche giornaliere per singola dimensione.
DIMENSION_REPORTS = ["query", "page", "device", "country"]


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
        start: date,
        end: date,
    ) -> list[dict[str, Any]]:
        """Scarica tutte le righe, oltre il limite di 25.000 per richiesta."""
        rows: list[dict[str, Any]] = []
        start_row = 0

        while True:
            response = await client.post(
                "https://www.googleapis.com/webmasters/v3/sites/"
                f"{quote(self.site_url, safe='')}/searchAnalytics/query",
                headers=await self.auth.headers(),
                json={
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "dimensions": dimensions,
                    "rowLimit": ROW_LIMIT,
                    "startRow": start_row,
                    # "all" include anche i giorni più recenti; al passaggio
                    # successivo i valori definitivi sovrascrivono quelli provvisori.
                    "dataState": "all",
                },
            )
            response.raise_for_status()
            batch = response.json().get("rows", []) or []
            rows.extend(batch)

            if len(batch) < ROW_LIMIT:
                break
            start_row += ROW_LIMIT

        return rows

    @staticmethod
    def _normalize(rows: list[dict[str, Any]], dimension: str) -> list[dict[str, Any]]:
        metrics = []
        for row in rows:
            keys = row.get("keys", [])
            if len(keys) < 2:
                continue

            captured_at = f"{keys[0]}T00:00:00+00:00"
            for name in ("clicks", "impressions", "ctr", "position"):
                metrics.append(
                    {
                        "metric": f"search_{name}",
                        "value": float(row.get(name, 0) or 0),
                        "dimension": dimension,
                        "dimension_value": keys[1],
                        "captured_at": captured_at,
                    }
                )
        return metrics

    @staticmethod
    def _search_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        output = []
        for row in rows:
            keys = row.get("keys", [])
            if len(keys) < 4:
                continue
            output.append(
                {
                    "date": keys[0],
                    "query": keys[1],
                    "page": keys[2],
                    "device": str(keys[3]).lower(),
                    "clicks": row.get("clicks", 0),
                    "impressions": row.get("impressions", 0),
                    "ctr": row.get("ctr", 0),
                    "position": row.get("position", 0),
                }
            )
        return output

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(
                provider=self.provider,
                ok=False,
                message="Search Console non configurato",
            )

        end = date.today() - timedelta(days=1)
        windows, is_backfill, history_start = plan_windows(
            cursor, end, MAX_HISTORY_DAYS, CHUNK_DAYS
        )

        metrics: list[dict[str, Any]] = []
        search_rows: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=90) as client:
            for window_start, window_end in windows:
                for dimension in DIMENSION_REPORTS:
                    rows = await self._query(
                        client, ["date", dimension], window_start, window_end
                    )
                    metrics.extend(self._normalize(rows, dimension))

                detail = await self._query(
                    client,
                    ["date", "query", "page", "device"],
                    window_start,
                    window_end,
                )
                search_rows.extend(self._search_rows(detail))

        mode = "storico completo" if is_backfill else "aggiornamento"
        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            search_rows=search_rows,
            cursor=done_cursor(history_start) if is_backfill else cursor,
            message=(
                f"Search Console {mode} dal {history_start.isoformat()}: "
                f"{len(metrics)} datapoint, {len(search_rows)} righe query+pagina"
            ),
        )

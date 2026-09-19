"""Google Business Profile: azioni giornaliere, keyword mese per mese e recensioni."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from .base import Connector, ConnectorResult
from .google_auth import GoogleAuth
from .history import done_cursor, plan_windows
from ..config_store import get as config_get, set_many


DAILY_METRICS = [
    "BUSINESS_IMPRESSIONS_DESKTOP_MAPS",
    "BUSINESS_IMPRESSIONS_DESKTOP_SEARCH",
    "BUSINESS_IMPRESSIONS_MOBILE_MAPS",
    "BUSINESS_IMPRESSIONS_MOBILE_SEARCH",
    "BUSINESS_DIRECTION_REQUESTS",
    "CALL_CLICKS",
    "WEBSITE_CLICKS",
]
# Non disponibili per tutte le schede: se la chiamata le rifiuta si riprova senza.
OPTIONAL_DAILY_METRICS = ["BUSINESS_CONVERSATIONS", "BUSINESS_BOOKINGS"]

MAX_HISTORY_DAYS = 540     # Google conserva circa 18 mesi
CHUNK_DAYS = 180
KEYWORD_BACKFILL_MONTHS = 18
KEYWORD_INCREMENTAL_MONTHS = 3
MAX_REVIEW_PAGES = 40      # 50 recensioni per pagina

STAR_RATING = {"ONE": 1, "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5}

PERFORMANCE_BASE = "https://businessprofileperformance.googleapis.com/v1"
REVIEWS_BASE = "https://mybusiness.googleapis.com/v4"
ACCOUNTS_URL = "https://mybusinessaccountmanagement.googleapis.com/v1/accounts"


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


def _month_start(day: date, months_back: int) -> date:
    index = day.year * 12 + (day.month - 1) - months_back
    return date(index // 12, index % 12 + 1, 1)


def parse_daily_series(payload: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = []
    for group in payload.get("multiDailyMetricTimeSeries", []) or []:
        for series in group.get("dailyMetricTimeSeries", []) or []:
            metric_name = str(series.get("dailyMetric", "")).lower()
            for point in (series.get("timeSeries") or {}).get("datedValues", []) or []:
                captured_at = _date_from_parts(point.get("date", {}))
                if not captured_at:
                    continue
                try:
                    value = float(point.get("value", 0) or 0)
                except (TypeError, ValueError):
                    value = 0
                metrics.append({"metric": f"gbp_{metric_name}", "value": value, "captured_at": captured_at})
    return metrics


def parse_keywords(payload: dict[str, Any], month: date) -> list[dict[str, Any]]:
    metrics = []
    for item in payload.get("searchKeywordsCounts", []) or []:
        keyword = str(item.get("searchKeyword", "")).strip()
        if not keyword:
            continue
        insights = item.get("insightsValue", {}) or {}
        raw = insights.get("value")
        # Sotto soglia Google non dà il numero ma un tetto ("meno di N").
        below_threshold = raw is None
        if below_threshold:
            raw = insights.get("threshold", 0)
        try:
            value = float(raw or 0)
        except (TypeError, ValueError):
            value = 0
        metrics.append({
            "metric": "gbp_search_keyword_impressions",
            "value": value,
            "dimension": "query",
            "dimension_value": keyword,
            "captured_at": f"{month.isoformat()}T00:00:00+00:00",
        })
        if below_threshold:
            metrics.append({
                "metric": "gbp_search_keyword_below_threshold",
                "value": 1,
                "dimension": "query",
                "dimension_value": keyword,
                "captured_at": f"{month.isoformat()}T00:00:00+00:00",
            })
    return metrics


def parse_review(item: dict[str, Any]) -> dict[str, Any] | None:
    review_id = item.get("reviewId") or str(item.get("name") or "").rsplit("/", 1)[-1]
    if not review_id:
        return None
    reviewer = item.get("reviewer") or {}
    reply = item.get("reviewReply") or {}
    name = None if reviewer.get("isAnonymous") else reviewer.get("displayName")
    return {
        "review_id": str(review_id),
        "rating": STAR_RATING.get(str(item.get("starRating") or "").upper()),
        "comment": (item.get("comment") or "").strip() or None,
        "reviewer": name,
        "created_at": item.get("createTime"),
        "updated_at": item.get("updateTime"),
        "reply_comment": (reply.get("comment") or "").strip() or None,
        "reply_at": reply.get("updateTime"),
    }


class GoogleBusinessConnector(Connector):
    provider = "google_business"

    def __init__(self) -> None:
        self.location = config_get("GOOGLE_BUSINESS_LOCATION_NAME").strip()
        self.account = config_get("GOOGLE_BUSINESS_ACCOUNT_NAME").strip()
        self.auth = GoogleAuth()

    def configured(self) -> bool:
        return bool(self.location and self.auth.configured())

    @property
    def location_id(self) -> str:
        return self.location.rsplit("/", 1)[-1]

    async def _daily_metrics(self, client: httpx.AsyncClient, start: date, end: date) -> list[dict[str, Any]]:
        def params_for(names: list[str]) -> list[tuple[str, str]]:
            params = [("dailyMetrics", metric) for metric in names]
            params.extend([
                ("dailyRange.start_date.year", str(start.year)),
                ("dailyRange.start_date.month", str(start.month)),
                ("dailyRange.start_date.day", str(start.day)),
                ("dailyRange.end_date.year", str(end.year)),
                ("dailyRange.end_date.month", str(end.month)),
                ("dailyRange.end_date.day", str(end.day)),
            ])
            return params

        url = f"{PERFORMANCE_BASE}/{self.location}:fetchMultiDailyMetricsTimeSeries"
        headers = await self.auth.headers()
        response = await client.get(url, headers=headers, params=params_for(DAILY_METRICS + OPTIONAL_DAILY_METRICS))
        if response.status_code == 400:
            response = await client.get(url, headers=headers, params=params_for(DAILY_METRICS))
        response.raise_for_status()
        return parse_daily_series(response.json())

    async def _keywords_for_month(self, client: httpx.AsyncClient, month: date) -> list[dict[str, Any]]:
        base = [
            ("monthlyRange.start_month.year", str(month.year)),
            ("monthlyRange.start_month.month", str(month.month)),
            ("monthlyRange.end_month.year", str(month.year)),
            ("monthlyRange.end_month.month", str(month.month)),
            ("pageSize", "100"),
        ]
        metrics: list[dict[str, Any]] = []
        page_token = None
        for _ in range(20):
            params = list(base) + ([("pageToken", page_token)] if page_token else [])
            response = await client.get(
                f"{PERFORMANCE_BASE}/{self.location}/searchkeywords/impressions/monthly",
                headers=await self.auth.headers(),
                params=params,
            )
            response.raise_for_status()
            payload = response.json()
            metrics.extend(parse_keywords(payload, month))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return metrics

    async def _resolve_account(self, client: httpx.AsyncClient) -> str:
        """Le recensioni vivono sotto accounts/X/locations/Y: serve l'account."""
        if self.account:
            return self.account
        response = await client.get(ACCOUNTS_URL, headers=await self.auth.headers())
        response.raise_for_status()
        accounts = [a.get("name") for a in response.json().get("accounts", []) if a.get("name")]
        for account in accounts:
            probe = await client.get(
                f"{REVIEWS_BASE}/{account}/locations/{self.location_id}/reviews",
                headers=await self.auth.headers(),
                params={"pageSize": 1},
            )
            if probe.status_code < 400:
                self.account = account
                set_many({"GOOGLE_BUSINESS_ACCOUNT_NAME": account})
                return account
        raise RuntimeError("nessun account Google Business con accesso a questa scheda")

    async def _reviews(self, client: httpx.AsyncClient, today: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        account = await self._resolve_account(client)
        url = f"{REVIEWS_BASE}/{account}/locations/{self.location_id}/reviews"
        reviews: list[dict[str, Any]] = []
        summary: dict[str, Any] = {}
        page_token = None
        for _ in range(MAX_REVIEW_PAGES):
            params: dict[str, Any] = {"pageSize": 50, "orderBy": "updateTime desc"}
            if page_token:
                params["pageToken"] = page_token
            response = await client.get(url, headers=await self.auth.headers(), params=params)
            response.raise_for_status()
            payload = response.json()
            if not summary:
                summary = payload
            for item in payload.get("reviews", []) or []:
                parsed = parse_review(item)
                if parsed:
                    reviews.append(parsed)
            page_token = payload.get("nextPageToken")
            if not page_token:
                break

        captured = f"{today.isoformat()}T00:00:00+00:00"
        metrics = []
        for metric, key in (("gbp_rating_average", "averageRating"), ("gbp_review_total", "totalReviewCount")):
            if summary.get(key) is not None:
                try:
                    metrics.append({"metric": metric, "value": float(summary[key]), "captured_at": captured})
                except (TypeError, ValueError):
                    pass
        return reviews, metrics

    async def sync(self, cursor: str | None = None) -> ConnectorResult:
        if not self.configured():
            return ConnectorResult(provider=self.provider, ok=False, message="Google Business Profile non configurato")

        today = datetime.now(timezone.utc).date()
        windows, is_backfill, history_start = plan_windows(
            cursor, today - timedelta(days=1), MAX_HISTORY_DAYS, CHUNK_DAYS
        )
        notes: list[str] = []
        metrics: list[dict[str, Any]] = []
        reviews: list[dict[str, Any]] = []

        async with httpx.AsyncClient(timeout=60) as client:
            for window_start, window_end in windows:
                metrics.extend(await self._daily_metrics(client, window_start, window_end))

            # Keyword: un mese alla volta, così si vede l'andamento.
            months = KEYWORD_BACKFILL_MONTHS if is_backfill else KEYWORD_INCREMENTAL_MONTHS
            keyword_rows = 0
            for back in range(1, months + 1):
                month = _month_start(today, back)
                try:
                    rows = await self._keywords_for_month(client, month)
                except httpx.HTTPStatusError as exc:
                    notes.append(f"keyword non disponibili ({exc.response.status_code})")
                    break
                keyword_rows += len(rows)
                metrics.extend(rows)
            if keyword_rows:
                notes.append(f"{keyword_rows} keyword mensili")

            try:
                reviews, review_metrics = await self._reviews(client, today)
                metrics.extend(review_metrics)
                notes.append(f"{len(reviews)} recensioni")
            except httpx.HTTPStatusError as exc:
                code = exc.response.status_code
                hint = " (abilita 'Google My Business API' nel progetto Google Cloud)" if code in (403, 404) else ""
                notes.append(f"recensioni non disponibili: HTTP {code}{hint}")
            except Exception as exc:
                notes.append(f"recensioni non disponibili: {exc}")

        mode = "storico completo" if is_backfill else "aggiornamento"
        return ConnectorResult(
            provider=self.provider,
            ok=True,
            metrics=metrics,
            reviews=reviews,
            cursor=done_cursor(history_start) if is_backfill else cursor,
            message=f"Google Business {mode}: {len(metrics)} datapoint; " + "; ".join(notes),
        )

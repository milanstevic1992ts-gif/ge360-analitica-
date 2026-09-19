"""Test del blocco 2: Meta completo, Google Business con recensioni, nuove analisi."""

import asyncio
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import httpx

from app import db, social_business
from app.connectors import google_business as gbp_module
from app.connectors import meta as meta_module
from app.connectors.base import ConnectorResult
from app.connectors.google_business import GoogleBusinessConnector, parse_keywords, parse_review
from app.connectors.meta import (
    MetaConnector, breakdown_values, facebook_format, instagram_format, needs_refresh,
    series_to_metrics, total_values,
)


def _iso(days_ago: int = 0, hour: int = 10) -> str:
    moment = datetime.now(timezone.utc).replace(hour=hour, minute=0, second=0, microsecond=0)
    return (moment - timedelta(days=days_ago)).isoformat()


class TempDb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, "ge360.db")
        db.initialize()

    def tearDown(self):
        db.DB_PATH = self.old
        self.tmp.cleanup()


def _patch_client(module, handler):
    """Fa usare ai connettori un AsyncClient con trasporto finto."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    module.httpx.AsyncClient = factory
    return lambda: setattr(module.httpx, "AsyncClient", real)


def _error(code=100, message="metrica non valida"):
    return httpx.Response(400, json={"error": {"code": code, "message": message}})


# ---------------------------------------------------------------------------
# parser
# ---------------------------------------------------------------------------

class ParserTests(unittest.TestCase):
    def test_series_with_dict_values_gives_total_and_breakdown(self):
        payload = {"data": [{"name": "page_actions_post_reactions_total",
                             "values": [{"value": {"like": 3, "love": 2}, "end_time": "2026-09-10T07:00:00+0000"}]}]}
        rows = series_to_metrics(payload, "meta_")
        total = [r for r in rows if r["metric"] == "meta_page_actions_post_reactions_total"]
        parts = [r for r in rows if r["metric"].endswith("_breakdown")]
        self.assertEqual(total[0]["value"], 5)
        self.assertEqual({p["dimension_value"] for p in parts}, {"like", "love"})

    def test_total_and_breakdown_values(self):
        self.assertEqual(total_values({"data": [{"name": "views", "total_value": {"value": 42}}]}), {"views": 42})
        payload = {"data": [{"total_value": {"breakdowns": [{"results": [
            {"dimension_values": ["Trieste, Friuli-Venezia Giulia"], "value": 80},
            {"dimension_values": ["Udine"], "value": 20}]}]}}]}
        self.assertEqual(breakdown_values(payload)[0], ("Trieste, Friuli-Venezia Giulia", 80))

    def test_formats(self):
        self.assertEqual(instagram_format({"media_product_type": "REELS", "media_type": "VIDEO"}), ("instagram_reel", "reel"))
        self.assertEqual(instagram_format({"media_type": "CAROUSEL_ALBUM"}), ("instagram_carousel", "feed"))
        self.assertEqual(facebook_format({"attachments": {"data": [{"media_type": "photo"}]}}), "facebook_photo")
        self.assertEqual(facebook_format({"status_type": "added_video"}), "facebook_video")

    def test_refresh_policy(self):
        today = date(2026, 9, 19)
        self.assertTrue(needs_refresh("new", "2020-01-01T00:00:00+0000", set(), today))
        self.assertTrue(needs_refresh("x", "2026-09-01T00:00:00+0000", {"x"}, today))
        old = [needs_refresh(f"id{i}", "2024-01-01T00:00:00+0000", {f"id{i}"}, today) for i in range(70)]
        self.assertTrue(0 < sum(old) < 70)  # i vecchi ruotano, non tutti insieme

    def test_review_and_keyword_parsing(self):
        review = parse_review({
            "reviewId": "abc", "starRating": "FOUR", "comment": " Ottimo bagno ",
            "reviewer": {"displayName": "Mario", "isAnonymous": False},
            "createTime": "2026-09-01T10:00:00Z", "updateTime": "2026-09-01T10:00:00Z",
            "reviewReply": {"comment": "Grazie!", "updateTime": "2026-09-02T10:00:00Z"},
        })
        self.assertEqual((review["rating"], review["comment"], review["reply_comment"]), (4, "Ottimo bagno", "Grazie!"))
        rows = parse_keywords({"searchKeywordsCounts": [
            {"searchKeyword": "impresa edile trieste", "insightsValue": {"value": "120"}},
            {"searchKeyword": "tadelakt", "insightsValue": {"threshold": "15"}},
        ]}, date(2026, 8, 1))
        self.assertEqual(rows[0]["captured_at"], "2026-08-01T00:00:00+00:00")
        self.assertTrue(any(r["metric"] == "gbp_search_keyword_below_threshold" for r in rows))


# ---------------------------------------------------------------------------
# connettore Meta con Graph API finta
# ---------------------------------------------------------------------------

def _graph_handler(calls, rate_limit_posts=False):
    def handler(request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        path = url.path.split("/v26.0", 1)[-1]
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        metric = q.get("metric", "")
        calls.append((path, metric))

        if path == "/PAGE/insights":
            if metric in ("page_video_view_time", "page_views_total"):
                return _error()
            value = {"like": 2, "love": 1} if metric == "page_actions_post_reactions_total" else 5
            return httpx.Response(200, json={"data": [{"name": metric, "values": [
                {"value": value, "end_time": _iso(2)}]}]})
        if path == "/PAGE/posts":
            if rate_limit_posts:
                return _error(4, "Application request limit reached")
            return httpx.Response(200, json={"data": [{
                "id": "PAGE_1", "message": "Bagno finito a Trieste", "created_time": _iso(5),
                "permalink_url": "https://fb.com/1", "status_type": "added_photos",
                "reactions": {"summary": {"total_count": 12}}, "comments": {"summary": {"total_count": 3}},
                "shares": {"count": 2}, "attachments": {"data": [{"media_type": "photo"}]},
            }]})
        if path == "/PAGE_1/insights":
            if "post_video_avg_time_watched" in metric:
                return _error()
            return httpx.Response(200, json={"data": [
                {"name": name, "values": [{"value": 100}]} for name in metric.split(",")]})
        if path == "/IG":
            return httpx.Response(200, json={"id": "IG", "username": "edilmilan", "followers_count": 420,
                                             "follows_count": 50, "media_count": 2})
        if path == "/IG/insights":
            if q.get("metric_type") == "total_value":
                if metric == "follower_demographics":
                    return httpx.Response(200, json={"data": [{"total_value": {"breakdowns": [{"results": [
                        {"dimension_values": ["Trieste, Friuli-Venezia Giulia"], "value": 300},
                        {"dimension_values": ["Udine, Friuli-Venezia Giulia"], "value": 100}]}]}}]})
                if metric == "follows_and_unfollows":
                    return httpx.Response(200, json={"data": [{"total_value": {"breakdowns": [{"results": [
                        {"dimension_values": ["FOLLOWER"], "value": 4},
                        {"dimension_values": ["NON_FOLLOWER"], "value": 1}]}]}}]})
                if "replies" in metric.split(","):
                    return _error()
                return httpx.Response(200, json={"data": [
                    {"name": name, "total_value": {"value": 10}} for name in metric.split(",")]})
            if metric == "online_followers":
                return httpx.Response(200, json={"data": [{"values": [{"value": {"0": 5, "10": 30}}]}]})
            return httpx.Response(200, json={"data": [{"name": metric, "values": [
                {"value": 7, "end_time": _iso(1)}]}]})
        if path == "/IG/media":
            return httpx.Response(200, json={"data": [
                {"id": "M1", "caption": "Reel tadelakt", "media_type": "VIDEO", "media_product_type": "REELS",
                 "permalink": "https://ig/1", "timestamp": _iso(3, 18), "like_count": 30, "comments_count": 4},
                {"id": "M2", "caption": "Foto marmorino", "media_type": "IMAGE", "media_product_type": "FEED",
                 "permalink": "https://ig/2", "timestamp": _iso(4, 9), "like_count": 10, "comments_count": 1},
            ]})
        if path == "/IG/stories":
            return httpx.Response(200, json={"data": [{"id": "S1", "media_type": "IMAGE", "timestamp": _iso(0, 8)}]})
        if path in ("/M1/insights", "/M2/insights", "/S1/insights"):
            names = metric.split(",")
            if "navigation" in names and len(names) > 1:
                return _error()
            if metric == "navigation":
                return _error()
            base = {"M1": 900, "M2": 200, "S1": 60}[path.split("/")[1]]
            return httpx.Response(200, json={"data": [
                {"name": n, "values": [{"value": base if n in ("reach", "views") else 12000 if "watch" in n else 20}]}
                for n in names]})
        return httpx.Response(404, json={"error": {"message": f"inatteso {path}"}})
    return handler


class MetaConnectorTests(TempDb):
    def _connector(self):
        connector = MetaConnector()
        connector.page_id, connector.access_token, connector.instagram_account_id = "PAGE", "TOKEN", "IG"
        connector.version = "v26.0"
        return connector

    def test_full_sync_collects_everything_and_remembers_rejected_metrics(self):
        calls = []
        restore = _patch_client(meta_module, _graph_handler(calls))
        try:
            result = asyncio.run(self._connector().sync(cursor=None))
        finally:
            restore()
        db.persist_result(result)
        metrics = {m["metric"] for m in result.metrics}

        for expected in (
            "meta_page_media_view", "meta_page_actions_post_reactions_total_breakdown",
            "facebook_post_reactions", "facebook_post_media_view", "facebook_post_clicks",
            "instagram_reach", "instagram_views", "instagram_daily_follows",
            "instagram_follower_demographics", "instagram_online_followers",
            "instagram_media_ig_reels_avg_watch_time", "instagram_media_reach",
        ):
            self.assertIn(expected, metrics)
        self.assertNotIn("instagram_replies", metrics)
        self.assertTrue(result.cursor.startswith("backfill:"))
        types = {c["content_type"] for c in result.content_items}
        self.assertEqual(types, {"facebook_photo", "instagram_reel", "instagram_image", "instagram_story"})

        skipped = db.skipped_items("meta")
        for item in ("page:page_video_view_time", "page:page_views_total", "ig:replies",
                     "post:post_video_avg_time_watched", "story:navigation"):
            self.assertIn(item, skipped)

        # Seconda sincronizzazione: le metriche rifiutate non vengono più chieste.
        calls.clear()
        restore = _patch_client(meta_module, _graph_handler(calls))
        try:
            asyncio.run(self._connector().sync(cursor=result.cursor))
        finally:
            restore()
        self.assertNotIn(("/PAGE/insights", "page_views_total"), calls)
        self.assertFalse(any("replies" in m.split(",") for p, m in calls if p == "/IG/insights"))

    def test_rate_limit_keeps_history_incomplete(self):
        restore = _patch_client(meta_module, _graph_handler([], rate_limit_posts=True))
        try:
            result = asyncio.run(self._connector().sync(cursor=None))
        finally:
            restore()
        self.assertIsNone(result.cursor)
        self.assertIn("limite richieste", result.message)
        # Il limite non deve far credere che le metriche non esistano.
        db.persist_result(result)
        self.assertFalse(any(k.startswith("post:") for k in db.skipped_items("meta")))


# ---------------------------------------------------------------------------
# connettore Google Business con API finte
# ---------------------------------------------------------------------------

class FakeAuth:
    def configured(self):
        return True

    async def headers(self):
        return {"Authorization": "Bearer x"}


def _gbp_handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        calls.append(url.path)
        if url.path.endswith(":fetchMultiDailyMetricsTimeSeries"):
            names = parse_qs(url.query).get("dailyMetrics", [])
            if "BUSINESS_BOOKINGS" in names:
                return httpx.Response(400, json={"error": {"message": "metric not supported"}})
            day = date.today() - timedelta(days=3)
            return httpx.Response(200, json={"multiDailyMetricTimeSeries": [{"dailyMetricTimeSeries": [
                {"dailyMetric": name, "timeSeries": {"datedValues": [
                    {"date": {"year": day.year, "month": day.month, "day": day.day}, "value": "4"}]}}
                for name in names]}]})
        if url.path.endswith("/searchkeywords/impressions/monthly"):
            return httpx.Response(200, json={"searchKeywordsCounts": [
                {"searchKeyword": "ristrutturazione bagno trieste", "insightsValue": {"value": "80"}}]})
        if url.path == "/v1/accounts":
            return httpx.Response(200, json={"accounts": [{"name": "accounts/1"}, {"name": "accounts/2"}]})
        if url.path == "/v4/accounts/1/locations/99/reviews":
            return httpx.Response(404, json={})
        if url.path == "/v4/accounts/2/locations/99/reviews":
            return httpx.Response(200, json={
                "averageRating": 4.8, "totalReviewCount": 2,
                "reviews": [
                    {"reviewId": "r1", "starRating": "FIVE", "comment": "Bagno perfetto, puntuali",
                     "createTime": _iso(10), "reviewer": {"displayName": "Anna"},
                     "reviewReply": {"comment": "Grazie Anna", "updateTime": _iso(9)}},
                    {"reviewId": "r2", "starRating": "THREE", "comment": "Lavoro buono ma ritardi",
                     "createTime": _iso(2), "reviewer": {"isAnonymous": True}},
                ]})
        return httpx.Response(404, json={})
    return handler


class GoogleBusinessTests(TempDb):
    def test_sync_resolves_account_and_imports_reviews(self):
        calls = []
        restore = _patch_client(gbp_module, _gbp_handler(calls))
        saved = {}
        old_set = gbp_module.set_many
        gbp_module.set_many = saved.update
        try:
            connector = GoogleBusinessConnector()
            connector.location, connector.account, connector.auth = "locations/99", "", FakeAuth()
            result = asyncio.run(connector.sync(cursor=None))
        finally:
            restore()
            gbp_module.set_many = old_set

        self.assertEqual(saved["GOOGLE_BUSINESS_ACCOUNT_NAME"], "accounts/2")
        self.assertEqual(len(result.reviews), 2)
        self.assertIsNone(result.reviews[1]["reviewer"])  # anonimo
        metrics = {m["metric"] for m in result.metrics}
        self.assertIn("gbp_call_clicks", metrics)
        self.assertIn("gbp_rating_average", metrics)
        months = {m["captured_at"][:7] for m in result.metrics if m["metric"] == "gbp_search_keyword_impressions"}
        self.assertEqual(len(months), gbp_module.KEYWORD_BACKFILL_MONTHS)

        counts = db.persist_result(result)
        self.assertEqual(counts["reviews"], 2)
        # Riscrivere la stessa recensione la aggiorna, non la duplica.
        db.persist_result(result)
        with db.connect() as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0], 2)

        overview = social_business.business_overview(days=30)
        r = overview["reviews"]
        self.assertEqual(r["average"], 4.8)
        self.assertEqual(r["reply_rate"], 50.0)
        self.assertEqual(len(r["unanswered"]), 1)
        self.assertEqual(len(r["negative"]), 1)
        self.assertIn("bagno", {w["word"] for w in r["words"]})
        self.assertEqual(overview["keywords"]["top"][0]["keyword"], "ristrutturazione bagno trieste")
        self.assertGreater(overview["totals"]["actions"], 0)


class MigrationTests(unittest.TestCase):
    def test_old_yearly_keyword_totals_are_removed_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = db.DB_PATH
            db.DB_PATH = os.path.join(tmp, "ge360.db")
            try:
                db.initialize()
                with db.connect() as conn:
                    conn.execute("PRAGMA user_version = 0")
                    conn.execute(
                        "INSERT INTO metric_snapshots(provider, metric, value, dimension, dimension_value, captured_at) "
                        "VALUES ('google_business', 'gbp_search_keyword_impressions', 900, 'query', 'x', '2026-05-01')")
                    conn.execute("INSERT INTO connector_cursor VALUES ('google_business', 'backfill:2025', '2026')")
                    conn.commit()
                db.initialize()
                with db.connect() as conn:
                    self.assertEqual(conn.execute("SELECT COUNT(*) FROM metric_snapshots").fetchone()[0], 0)
                    self.assertIsNone(conn.execute("SELECT 1 FROM connector_cursor").fetchone())
                    self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
            finally:
                db.DB_PATH = old


# ---------------------------------------------------------------------------
# analisi Meta
# ---------------------------------------------------------------------------

class MetaDeepTests(TempDb):
    def test_meta_deep_from_real_sync(self):
        restore = _patch_client(meta_module, _graph_handler([]))
        try:
            connector = MetaConnector()
            connector.page_id, connector.access_token, connector.instagram_account_id = "PAGE", "T", "IG"
            connector.version = "v26.0"
            result = asyncio.run(connector.sync(cursor=None))
        finally:
            restore()
        db.persist_result(result)
        db.persist_result(ConnectorResult(provider="wordpress", ok=True, events=[
            {"external_id": "e1", "event_type": "page_view", "source": "instagram", "session_id": "s1", "occurred_at": _iso(1)},
            {"external_id": "e2", "event_type": "whatsapp_click", "source": "instagram", "session_id": "s1", "occurred_at": _iso(1)},
        ]))

        d = social_business.meta_deep(days=30)
        self.assertEqual(d["top_content"][0]["id"], "M1")        # il reel ha più copertura
        reel = d["top_content"][0]
        self.assertEqual(reel["avg_watch_sec"], 12.0)
        self.assertEqual(reel["format"], "Reel Instagram")
        self.assertEqual(d["followers"]["instagram"], 420)
        self.assertEqual(d["trieste_follower_share"], 75.0)
        self.assertEqual(d["online_hours"][9]["followers"], 5)   # 0 PST -> 9 ora italiana
        self.assertEqual(len(d["stories"]), 1)
        self.assertEqual(d["site_impact"]["tracker_contacts"], 1)
        self.assertEqual(d["site_impact"]["contact_rate"], 100.0)
        self.assertTrue(any(k["metric"] == "instagram_views" for k in d["instagram_kpis"]))
        self.assertTrue(d["formats"])


if __name__ == "__main__":
    unittest.main()

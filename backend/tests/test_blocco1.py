"""Test del blocco 1: storico, upsert, tracker 0.2 e nuove analisi."""

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone

from app import db, insights
from app.connectors.base import ConnectorResult
from app.connectors.ga4 import GA4Connector
from app.connectors.history import backfill_done, done_cursor, plan_windows
from app.connectors.search_console import SearchConsoleConnector


def _iso(days_ago: int = 0, minutes: int = 0) -> str:
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago) + timedelta(minutes=minutes)
    return moment.isoformat()


class TempDbTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.tmp.name, "ge360.db")

    def tearDown(self):
        db.DB_PATH = self.old_path
        self.tmp.cleanup()


class MigrationTests(TempDbTestCase):
    def test_old_database_with_duplicates_is_cleaned_and_upgraded(self):
        # Database in formato 0.6: nessun indice UNIQUE, datapoint duplicati.
        conn = sqlite3.connect(db.DB_PATH)
        conn.executescript(
            """
            CREATE TABLE metric_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL,
                metric TEXT NOT NULL, value REAL NOT NULL, dimension TEXT,
                dimension_value TEXT, captured_at TEXT NOT NULL);
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, provider TEXT NOT NULL,
                external_id TEXT, event_type TEXT NOT NULL, source TEXT, campaign TEXT,
                content_id TEXT, url TEXT, occurred_at TEXT NOT NULL, payload_json TEXT);
            INSERT INTO metric_snapshots(provider, metric, value, dimension, dimension_value, captured_at)
            VALUES ('ga4','ga4_sessions',10,NULL,NULL,'2026-01-01'),
                   ('ga4','ga4_sessions',12,NULL,NULL,'2026-01-01'),
                   ('ga4','ga4_sessions',5,'source','google','2026-01-01');
            """
        )
        conn.commit()
        conn.close()

        db.initialize()

        with db.connect() as conn:
            rows = conn.execute(
                "SELECT value FROM metric_snapshots WHERE dimension IS NULL"
            ).fetchall()
            self.assertEqual([r["value"] for r in rows], [12])
            columns = {r["name"] for r in conn.execute("PRAGMA table_info(events)")}
            self.assertTrue({"session_id", "visitor_id", "device", "value"} <= columns)

        # Una seconda inizializzazione non deve fallire.
        db.initialize()


class PersistenceTests(TempDbTestCase):
    def setUp(self):
        super().setUp()
        db.initialize()

    def test_metric_upsert_replaces_instead_of_adding(self):
        for value in (3, 7):
            db.persist_result(
                ConnectorResult(
                    provider="ga4",
                    ok=True,
                    metrics=[
                        {"metric": "ga4_sessions", "value": value, "captured_at": "2026-05-01T00:00:00+00:00"},
                        {
                            "metric": "ga4_sessions",
                            "value": value * 2,
                            "dimension": "device",
                            "dimension_value": "mobile",
                            "captured_at": "2026-05-01T00:00:00+00:00",
                        },
                    ],
                )
            )
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT dimension, value FROM metric_snapshots ORDER BY dimension"
            ).fetchall()
        self.assertEqual([(r["dimension"], r["value"]) for r in rows], [(None, 7), ("device", 14)])

    def test_search_rows_upsert(self):
        row = {"date": "2026-05-01", "query": "bagno", "page": "https://x.it/bagno", "device": "mobile",
               "clicks": 1, "impressions": 10, "ctr": 0.1, "position": 5}
        db.persist_result(ConnectorResult(provider="search_console", ok=True, search_rows=[row]))
        db.persist_result(
            ConnectorResult(provider="search_console", ok=True, search_rows=[{**row, "clicks": 3}])
        )
        with db.connect() as conn:
            rows = conn.execute("SELECT clicks FROM search_performance").fetchall()
        self.assertEqual([r["clicks"] for r in rows], [3])

    def test_tracker_events_keep_session_fields_and_form_creates_lead(self):
        db.persist_result(
            ConnectorResult(
                provider="wordpress",
                ok=True,
                events=[
                    {
                        "external_id": "1",
                        "event_type": "form_submit",
                        "source": "google",
                        "url": "https://x.it/contatti",
                        "occurred_at": _iso(1),
                        "session_id": "sess-aaaaaaaa",
                        "device": "mobile",
                        "payload": {"medium": "organic"},
                    }
                ],
            )
        )
        with db.connect() as conn:
            event = conn.execute("SELECT session_id, device FROM events").fetchone()
            lead = conn.execute("SELECT payload_json FROM leads").fetchone()
        self.assertEqual(event["session_id"], "sess-aaaaaaaa")
        self.assertEqual(json.loads(lead["payload_json"])["session_id"], "sess-aaaaaaaa")


class HistoryTests(unittest.TestCase):
    def test_first_sync_plans_full_history_in_chunks(self):
        end = date(2026, 9, 18)
        windows, is_backfill, start = plan_windows(None, end, 486, 30)
        self.assertTrue(is_backfill)
        self.assertEqual(start, end - timedelta(days=485))
        self.assertEqual(windows[0][1], end)  # prima la finestra più recente
        self.assertEqual(windows[-1][0], start)
        covered = sum((b - a).days + 1 for a, b in windows)
        self.assertEqual(covered, 486)

    def test_after_backfill_only_recent_window(self):
        end = date(2026, 9, 18)
        cursor = done_cursor(date(2025, 5, 1))
        self.assertTrue(backfill_done(cursor))
        windows, is_backfill, _ = plan_windows(cursor, end, 486, 30)
        self.assertFalse(is_backfill)
        self.assertEqual(len(windows), 1)


class ConnectorNormalizeTests(unittest.TestCase):
    def test_ga4_totals_have_no_dimension(self):
        rows = [{"dimensionValues": [{"value": "20260501"}], "metricValues": [{"value": "4"}]}]
        out = GA4Connector._normalize(rows, ["sessions"], None)
        self.assertEqual(out[0]["dimension"], None)
        self.assertEqual(out[0]["metric"], "ga4_sessions")
        self.assertTrue(out[0]["captured_at"].startswith("2026-05-01"))

    def test_search_console_detail_rows(self):
        rows = [{"keys": ["2026-05-01", "q", "https://x.it/", "MOBILE"], "clicks": 1, "impressions": 3}]
        out = SearchConsoleConnector._search_rows(rows)
        self.assertEqual(out[0]["device"], "mobile")


class InsightTests(TempDbTestCase):
    def setUp(self):
        super().setUp()
        db.initialize()

    def _events(self, events):
        for i, event in enumerate(events):
            event.setdefault("external_id", f"e{i}-{event['event_type']}-{event.get('session_id')}")
        db.persist_result(ConnectorResult(provider="wordpress", ok=True, events=events))

    def test_journeys_and_funnel(self):
        s1 = "sess-11111111"
        s2 = "sess-22222222"
        self._events(
            [
                {"event_type": "page_view", "session_id": s1, "source": "google", "device": "mobile",
                 "url": "https://x.it/bagno", "occurred_at": _iso(2), "payload": {"medium": "organic", "landing": "/bagno"}},
                {"event_type": "page_view", "session_id": s1, "source": "google", "device": "mobile",
                 "url": "https://x.it/contatti", "occurred_at": _iso(2, 2)},
                {"event_type": "page_engagement", "session_id": s1, "value": 45000,
                 "url": "https://x.it/bagno", "occurred_at": _iso(2, 3), "payload": {"max_scroll": 80}},
                {"event_type": "whatsapp_click", "session_id": s1, "source": "google", "device": "mobile",
                 "url": "https://x.it/contatti", "occurred_at": _iso(2, 4)},
                {"event_type": "page_view", "session_id": s2, "source": "facebook", "device": "desktop",
                 "url": "https://x.it/", "occurred_at": _iso(3)},
                {"event_type": "form_start", "session_id": s2, "url": "https://x.it/", "occurred_at": _iso(3, 1)},
            ]
        )
        result = insights.journeys(days=30)
        self.assertEqual(result["tracked_sessions"], 2)
        self.assertEqual(result["converted_sessions"], 1)
        self.assertEqual([f["value"] for f in result["funnel"]], [2, 2, 2, 1])
        self.assertEqual(result["form_abandonment"]["abandon_rate"], 100.0)
        self.assertIn("/bagno → /contatti", result["top_paths"][0]["path"])
        self.assertEqual(result["median_pages_to_contact"], 2)

    def test_site_health_vitals_and_404(self):
        events = [
            {"event_type": "web_vital", "session_id": f"sess-v{i:07d}", "device": "mobile",
             "url": "https://x.it/", "occurred_at": _iso(1), "value": v,
             "payload": {"metric_name": "LCP", "metric_rating": "poor" if v > 4000 else "good",
                         "vital_target": "img.hero"}}
            for i, v in enumerate([1200, 1800, 2200, 5200, 6000])
        ]
        events.append({"event_type": "page_404", "url": "https://x.it/vecchia", "occurred_at": _iso(1),
                       "payload": {"path": "/vecchia"}})
        self._events(events)
        health = insights.site_health(days=30)
        lcp = next(v for v in health["vitals"] if v["metric"] == "LCP")
        self.assertEqual(lcp["p75"], 5200)
        self.assertEqual(lcp["rating"], "scarso")
        self.assertEqual(health["not_found"][0]["path"], "/vecchia")
        self.assertEqual(health["poor_elements"][0]["element"], "img.hero")

    def test_cannibalization_and_opportunities(self):
        day = (date.today() - timedelta(days=3)).isoformat()
        rows = [
            # Due pagine forti sulla stessa ricerca -> cannibalizzazione.
            {"date": day, "query": "rifacimento bagno trieste", "page": "https://x.it/bagno",
             "device": "mobile", "clicks": 10, "impressions": 300, "position": 6},
            {"date": day, "query": "rifacimento bagno trieste", "page": "https://x.it/ristrutturazioni",
             "device": "mobile", "clicks": 4, "impressions": 200, "position": 9},
            # Comparsa occasionale: non deve contare.
            {"date": day, "query": "rifacimento bagno trieste", "page": "https://x.it/blog/altro",
             "device": "mobile", "clicks": 0, "impressions": 5, "position": 40},
            {"date": day, "query": "blog altro", "page": "https://x.it/blog/altro",
             "device": "mobile", "clicks": 20, "impressions": 5000, "position": 2},
        ]
        db.persist_result(ConnectorResult(provider="search_console", ok=True, search_rows=rows))

        found = insights.cannibalization(days=30)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["query"], "rifacimento bagno trieste")
        self.assertEqual(found[0]["main_page"], "https://x.it/bagno")
        self.assertEqual(len(found[0]["pages"]), 2)

        opportunities = {o["query"]: o for o in insights.search_opportunities(days=30)}
        self.assertEqual(opportunities["rifacimento bagno trieste"]["type"], "vicina alla top 3")
        self.assertGreater(opportunities["rifacimento bagno trieste"]["potential_clicks"], 0)
        # Posizione 2 ma CTR 0,4%: titolo/descrizione da rivedere.
        self.assertEqual(opportunities["blog altro"]["type"], "CTR basso per la posizione")

    def test_audience_and_dashboard_still_work(self):
        day = (date.today() - timedelta(days=2)).isoformat() + "T00:00:00+00:00"
        db.persist_result(
            ConnectorResult(
                provider="ga4",
                ok=True,
                metrics=[
                    {"metric": "ga4_sessions", "value": 100, "captured_at": day},
                    {"metric": "ga4_engagedSessions", "value": 60, "captured_at": day},
                    {"metric": "ga4_sessions", "value": 70, "dimension": "city",
                     "dimension_value": "Trieste", "captured_at": day},
                    {"metric": "ga4_sessions", "value": 30, "dimension": "city",
                     "dimension_value": "Udine", "captured_at": day},
                ],
            )
        )
        result = insights.audience(days=30)
        self.assertEqual(result["summary"]["sessions"], 100)
        self.assertEqual(result["summary"]["engagement_rate"], 60.0)
        self.assertEqual(result["trieste_share"], 70.0)

        # Gli eventi di comportamento non devono gonfiare le "azioni" della dashboard.
        self._events(
            [
                {"event_type": "scroll_depth", "session_id": "sess-33333333", "value": 50,
                 "url": "https://x.it/", "occurred_at": _iso(1)},
                {"event_type": "phone_click", "session_id": "sess-33333333",
                 "url": "https://x.it/", "occurred_at": _iso(1)},
            ]
        )
        from app.dashboard_service import dashboard

        payload = dashboard("30d")
        actions = next(item for item in payload["funnel"] if item["label"] == "Azioni")
        self.assertEqual(actions["value"], 1)


if __name__ == "__main__":
    unittest.main()

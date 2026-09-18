import os
import sqlite3
from pathlib import Path

DB_PATH = os.getenv("GE360_DB_PATH", "./data/ge360.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS connector_state (
    provider TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'not_configured',
    last_sync TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS metric_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    dimension TEXT,
    dimension_value TEXT,
    captured_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_provider_metric_time
ON metric_snapshots(provider, metric, captured_at);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    event_type TEXT NOT NULL,
    source TEXT,
    campaign TEXT,
    content_id TEXT,
    url TEXT,
    occurred_at TEXT NOT NULL,
    payload_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_type_time
ON events(event_type, occurred_at);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,
    source TEXT,
    landing_page TEXT,
    campaign TEXT,
    status TEXT NOT NULL DEFAULT 'new',
    value REAL,
    created_at TEXT NOT NULL,
    payload_json TEXT
);
"""

PROVIDERS = [
    "wordpress",
    "meta",
    "google_business",
    "ga4",
    "search_console",
]


def connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def initialize() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        for provider in PROVIDERS:
            conn.execute(
                """
                INSERT OR IGNORE INTO connector_state(provider, status, message)
                VALUES (?, 'not_configured', 'Credenziali non ancora configurate')
                """,
                (provider,),
            )
        conn.commit()


def connector_states() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT provider, status, last_sync, message FROM connector_state ORDER BY provider"
        ).fetchall()
    return [dict(row) for row in rows]

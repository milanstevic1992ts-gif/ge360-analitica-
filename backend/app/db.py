import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DB_PATH = os.getenv("GE360_DB_PATH", "./data/ge360.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS connector_state (
    provider TEXT PRIMARY KEY,
    status TEXT NOT NULL DEFAULT 'not_configured',
    last_sync TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS connector_cursor (
    provider TEXT PRIMARY KEY,
    cursor TEXT,
    updated_at TEXT NOT NULL
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
    external_id TEXT,
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

CREATE UNIQUE INDEX IF NOT EXISTS idx_events_provider_external
ON events(provider, external_id)
WHERE external_id IS NOT NULL;

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

CREATE TABLE IF NOT EXISTS content_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL,
    external_id TEXT NOT NULL,
    content_type TEXT,
    title TEXT,
    url TEXT,
    status TEXT,
    published_at TEXT,
    modified_at TEXT,
    synced_at TEXT NOT NULL,
    UNIQUE(provider, external_id)
);

CREATE INDEX IF NOT EXISTS idx_content_provider_type
ON content_items(provider, content_type);
"""

PROVIDERS = [
    "wordpress",
    "meta",
    "google_business",
    "ga4",
    "search_console",
]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect() -> sqlite3.Connection:
    path = Path(DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


def _migrate(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, "events", "external_id"):
        conn.execute("ALTER TABLE events ADD COLUMN external_id TEXT")

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_events_provider_external
        ON events(provider, external_id)
        WHERE external_id IS NOT NULL
        """
    )


def initialize() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
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


def get_cursor(provider: str) -> str | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT cursor FROM connector_cursor WHERE provider = ?",
            (provider,),
        ).fetchone()
    return row["cursor"] if row else None


def set_cursor(provider: str, cursor: str | None) -> None:
    if cursor is None:
        return
    now = utcnow()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO connector_cursor(provider, cursor, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(provider)
            DO UPDATE SET cursor = excluded.cursor, updated_at = excluded.updated_at
            """,
            (provider, str(cursor), now),
        )
        conn.commit()


def set_connector_state(provider: str, status: str, message: str = "") -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO connector_state(provider, status, last_sync, message)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(provider)
            DO UPDATE SET
                status = excluded.status,
                last_sync = excluded.last_sync,
                message = excluded.message
            """,
            (provider, status, utcnow(), message),
        )
        conn.commit()


def persist_result(result: Any) -> dict[str, int]:
    now = utcnow()
    counts = {"metrics": 0, "events": 0, "content_items": 0}

    with connect() as conn:
        for metric in result.metrics:
            captured_at = metric.get("captured_at") or now
            dimension = metric.get("dimension")
            dimension_value = metric.get("dimension_value")

            # I provider Google risincronizzano finestre storiche: sostituiamo
            # lo stesso datapoint invece di sommarlo più volte.
            conn.execute(
                """
                DELETE FROM metric_snapshots
                WHERE provider = ?
                  AND metric = ?
                  AND COALESCE(dimension, '') = ?
                  AND COALESCE(dimension_value, '') = ?
                  AND captured_at = ?
                """,
                (
                    result.provider,
                    metric["metric"],
                    dimension or "",
                    dimension_value or "",
                    captured_at,
                ),
            )

            conn.execute(
                """
                INSERT INTO metric_snapshots(
                    provider, metric, value, dimension, dimension_value, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    result.provider,
                    metric["metric"],
                    float(metric.get("value", 0)),
                    dimension,
                    dimension_value,
                    captured_at,
                ),
            )
            counts["metrics"] += 1

        for event in result.events:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO events(
                    provider, external_id, event_type, source, campaign,
                    content_id, url, occurred_at, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.provider,
                    str(event.get("external_id")) if event.get("external_id") is not None else None,
                    event["event_type"],
                    event.get("source"),
                    event.get("campaign"),
                    event.get("content_id"),
                    event.get("url"),
                    event.get("occurred_at") or now,
                    json.dumps(event.get("payload"), ensure_ascii=False)
                    if event.get("payload") is not None
                    else None,
                ),
            )
            if cursor.rowcount:
                counts["events"] += 1

                # Un invio form è un lead forte; i click telefono/WhatsApp restano azioni.
                if event["event_type"] == "form_submit":
                    conn.execute(
                        """
                        INSERT INTO leads(
                            channel, source, landing_page, campaign,
                            status, created_at, payload_json
                        ) VALUES (?, ?, ?, ?, 'new', ?, ?)
                        """,
                        (
                            "form",
                            event.get("source"),
                            event.get("url"),
                            event.get("campaign"),
                            event.get("occurred_at") or now,
                            json.dumps(
                                {
                                    "provider": result.provider,
                                    "external_event_id": event.get("external_id"),
                                },
                                ensure_ascii=False,
                            ),
                        ),
                    )

        for item in result.content_items:
            conn.execute(
                """
                INSERT INTO content_items(
                    provider, external_id, content_type, title, url,
                    status, published_at, modified_at, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, external_id)
                DO UPDATE SET
                    content_type = excluded.content_type,
                    title = excluded.title,
                    url = excluded.url,
                    status = excluded.status,
                    published_at = excluded.published_at,
                    modified_at = excluded.modified_at,
                    synced_at = excluded.synced_at
                """,
                (
                    result.provider,
                    str(item["external_id"]),
                    item.get("content_type"),
                    item.get("title"),
                    item.get("url"),
                    item.get("status"),
                    item.get("published_at"),
                    item.get("modified_at"),
                    now,
                ),
            )
            counts["content_items"] += 1

        conn.commit()

    set_cursor(result.provider, result.cursor)
    set_connector_state(
        result.provider,
        "connected" if result.ok else "error",
        result.message,
    )
    return counts

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
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

CREATE TABLE IF NOT EXISTS search_performance (
    captured_date TEXT NOT NULL,
    query TEXT NOT NULL,
    page TEXT NOT NULL,
    device TEXT NOT NULL,
    clicks REAL NOT NULL DEFAULT 0,
    impressions REAL NOT NULL DEFAULT 0,
    ctr REAL NOT NULL DEFAULT 0,
    position REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (captured_date, query, page, device)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_search_perf_query
ON search_performance(query, captured_date);

CREATE INDEX IF NOT EXISTS idx_search_perf_page
ON search_performance(page, captured_date);

CREATE TABLE IF NOT EXISTS local_ai_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    base_url TEXT NOT NULL,
    model TEXT NOT NULL,
    think INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ai_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_type TEXT NOT NULL,
    period_days INTEGER NOT NULL,
    model TEXT NOT NULL,
    report_markdown TEXT NOT NULL,
    handoff_prompt TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ai_reports_created_at
ON ai_reports(created_at DESC);

CREATE TABLE IF NOT EXISTS reviews (
    provider TEXT NOT NULL,
    review_id TEXT NOT NULL,
    rating INTEGER,
    comment TEXT,
    reviewer TEXT,
    created_at TEXT,
    updated_at TEXT,
    reply_comment TEXT,
    reply_at TEXT,
    synced_at TEXT NOT NULL,
    PRIMARY KEY (provider, review_id)
);

CREATE INDEX IF NOT EXISTS idx_reviews_created
ON reviews(provider, created_at);

-- Metriche/endpoint che una piattaforma ha rifiutato: si riprovano dopo
-- qualche giorno invece di sprecare una chiamata API a ogni sincronizzazione.
CREATE TABLE IF NOT EXISTS api_skips (
    provider TEXT NOT NULL,
    item TEXT NOT NULL,
    reason TEXT,
    skipped_at TEXT NOT NULL,
    PRIMARY KEY (provider, item)
);
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
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
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

    # 0.7: dati di sessione del tracker first-party.
    for column, ddl in (
        ("session_id", "TEXT"),
        ("visitor_id", "TEXT"),
        ("device", "TEXT"),
        ("value", "REAL"),
    ):
        if not _column_exists(conn, "events", column):
            conn.execute(f"ALTER TABLE events ADD COLUMN {column} {ddl}")

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id, occurred_at)"
    )

    # 0.7: un solo datapoint per chiave. Prima si puliscono i duplicati storici,
    # poi l'indice UNIQUE permette l'upsert (molto più veloce di DELETE+INSERT).
    has_unique = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_metrics_unique'"
    ).fetchone()
    if not has_unique:
        conn.execute(
            """
            DELETE FROM metric_snapshots
            WHERE id NOT IN (
                SELECT MAX(id) FROM metric_snapshots
                GROUP BY provider, metric, COALESCE(dimension, ''),
                         COALESCE(dimension_value, ''), captured_at
            )
            """
        )
        conn.execute(
            """
            CREATE UNIQUE INDEX idx_metrics_unique ON metric_snapshots(
                provider, metric, COALESCE(dimension, ''),
                COALESCE(dimension_value, ''), captured_at
            )
            """
        )
    # 0.8: le keyword Google Business erano salvate come unico totale annuale
    # con la data del mese di sincronizzazione. Ora sono mese per mese: i vecchi
    # totali vanno tolti e lo storico Business riscaricato.
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version < 2:
        conn.execute(
            "DELETE FROM metric_snapshots WHERE provider = 'google_business' "
            "AND metric = 'gbp_search_keyword_impressions'"
        )
        conn.execute("DELETE FROM connector_cursor WHERE provider = 'google_business'")
        conn.execute("PRAGMA user_version = 2")

    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_metrics_dimension
        ON metric_snapshots(provider, dimension, captured_at)
        """
    )


def initialize() -> None:
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
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


def skipped_items(provider: str, retry_days: int = 7) -> dict[str, str]:
    """Elementi rifiutati di recente dalla piattaforma (da non richiedere)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retry_days)).isoformat()
    with connect() as conn:
        rows = conn.execute(
            "SELECT item, reason FROM api_skips WHERE provider = ? AND skipped_at >= ?",
            (provider, cutoff),
        ).fetchall()
    return {row["item"]: row["reason"] or "" for row in rows}


def mark_skipped(provider: str, items: dict[str, str]) -> None:
    if not items:
        return
    now = utcnow()
    with connect() as conn:
        conn.executemany(
            """
            INSERT INTO api_skips(provider, item, reason, skipped_at) VALUES (?, ?, ?, ?)
            ON CONFLICT(provider, item) DO UPDATE SET
                reason = excluded.reason, skipped_at = excluded.skipped_at
            """,
            [(provider, item, (reason or "")[:300], now) for item, reason in items.items()],
        )
        conn.commit()


def known_dimension_values(provider: str, metric_prefix: str, dimension: str) -> set[str]:
    """Contenuti (post/media) per cui esistono già metriche dettagliate."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT dimension_value FROM metric_snapshots
            WHERE provider = ? AND dimension = ? AND metric LIKE ?
            """,
            (provider, dimension, f"{metric_prefix}%"),
        ).fetchall()
    return {str(row[0]) for row in rows if row[0] is not None}


def reset_cursor(provider: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM connector_cursor WHERE provider = ?", (provider,))
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
    counts = {"metrics": 0, "events": 0, "content_items": 0, "search_rows": 0, "reviews": 0}

    with connect() as conn:
        metric_rows = [
            (
                result.provider,
                metric["metric"],
                float(metric.get("value", 0) or 0),
                metric.get("dimension"),
                metric.get("dimension_value"),
                metric.get("captured_at") or now,
            )
            for metric in result.metrics
        ]
        # Le finestre storiche vengono risincronizzate: lo stesso datapoint
        # viene aggiornato, mai sommato due volte.
        conn.executemany(
            """
            INSERT INTO metric_snapshots(
                provider, metric, value, dimension, dimension_value, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(
                provider, metric, COALESCE(dimension, ''),
                COALESCE(dimension_value, ''), captured_at
            ) DO UPDATE SET value = excluded.value
            """,
            metric_rows,
        )
        counts["metrics"] = len(metric_rows)

        search_rows = [
            (
                row["date"],
                row.get("query") or "",
                row.get("page") or "",
                row.get("device") or "",
                float(row.get("clicks", 0) or 0),
                float(row.get("impressions", 0) or 0),
                float(row.get("ctr", 0) or 0),
                float(row.get("position", 0) or 0),
            )
            for row in getattr(result, "search_rows", []) or []
        ]
        if search_rows:
            conn.executemany(
                """
                INSERT INTO search_performance(
                    captured_date, query, page, device,
                    clicks, impressions, ctr, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(captured_date, query, page, device) DO UPDATE SET
                    clicks = excluded.clicks,
                    impressions = excluded.impressions,
                    ctr = excluded.ctr,
                    position = excluded.position
                """,
                search_rows,
            )
        counts["search_rows"] = len(search_rows)

        for event in result.events:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO events(
                    provider, external_id, event_type, source, campaign,
                    content_id, url, occurred_at, payload_json,
                    session_id, visitor_id, device, value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    event.get("session_id"),
                    event.get("visitor_id"),
                    event.get("device"),
                    event.get("value"),
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
                                    "session_id": event.get("session_id"),
                                    "device": event.get("device"),
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

        review_rows = [
            (
                result.provider,
                str(review["review_id"]),
                review.get("rating"),
                review.get("comment"),
                review.get("reviewer"),
                review.get("created_at"),
                review.get("updated_at"),
                review.get("reply_comment"),
                review.get("reply_at"),
                now,
            )
            for review in getattr(result, "reviews", []) or []
            if review.get("review_id")
        ]
        if review_rows:
            conn.executemany(
                """
                INSERT INTO reviews(
                    provider, review_id, rating, comment, reviewer,
                    created_at, updated_at, reply_comment, reply_at, synced_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider, review_id) DO UPDATE SET
                    rating = excluded.rating,
                    comment = excluded.comment,
                    reviewer = excluded.reviewer,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    reply_comment = excluded.reply_comment,
                    reply_at = excluded.reply_at,
                    synced_at = excluded.synced_at
                """,
                review_rows,
            )
        counts["reviews"] = len(review_rows)

        conn.commit()

    set_cursor(result.provider, result.cursor)
    set_connector_state(
        result.provider,
        "connected" if result.ok else "error",
        result.message,
    )
    return counts

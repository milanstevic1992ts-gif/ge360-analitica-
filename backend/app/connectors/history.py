"""Gestione dello storico per i connettori Google.

Alla prima sincronizzazione (cursore assente) il connettore scarica tutto lo
storico disponibile a blocchi; dalle volte successive riscarica solo una breve
finestra recente, perché Google corregge i dati degli ultimi giorni.

Il cursore salvato ha la forma ``backfill:<data_inizio>`` e segnala che lo
storico è completo.
"""

from __future__ import annotations

import os
from datetime import date, timedelta

CURSOR_PREFIX = "backfill:"


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


def backfill_days(max_days: int) -> int:
    """Giorni di storico richiesti, limitati a quanto conserva la piattaforma."""
    return _int_env("GE360_BACKFILL_DAYS", max_days, 30, max_days)


def incremental_days() -> int:
    return _int_env("GE360_INCREMENTAL_DAYS", 14, 3, 60)


def backfill_done(cursor: str | None) -> bool:
    return bool(cursor and str(cursor).startswith(CURSOR_PREFIX))


def done_cursor(start: date) -> str:
    return f"{CURSOR_PREFIX}{start.isoformat()}"


def plan_windows(
    cursor: str | None,
    end: date,
    max_days: int,
    chunk_days: int,
) -> tuple[list[tuple[date, date]], bool, date]:
    """Restituisce (finestre, è_storico, data_inizio_totale).

    Le finestre sono inclusive e ordinate dalla più recente alla più vecchia,
    così i dati utili compaiono subito anche se lo storico si interrompe.
    """
    is_backfill = not backfill_done(cursor)
    days = backfill_days(max_days) if is_backfill else incremental_days()
    start = end - timedelta(days=days - 1)

    windows: list[tuple[date, date]] = []
    window_end = end
    while window_end >= start:
        window_start = max(start, window_end - timedelta(days=chunk_days - 1))
        windows.append((window_start, window_end))
        window_end = window_start - timedelta(days=1)

    return windows, is_backfill, start

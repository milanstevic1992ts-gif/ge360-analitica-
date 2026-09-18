import asyncio
import os

from .sync import sync_all


def auto_sync_enabled() -> bool:
    return os.getenv("GE360_AUTO_SYNC", "true").lower() in {"1", "true", "yes", "on"}


def interval_seconds() -> int:
    try:
        minutes = int(os.getenv("GE360_SYNC_INTERVAL_MINUTES", "60"))
    except ValueError:
        minutes = 60
    return max(15, minutes) * 60


async def periodic_sync() -> None:
    # Lascia partire prima API, database e dashboard.
    await asyncio.sleep(20)

    while True:
        try:
            await sync_all()
        except asyncio.CancelledError:
            raise
        except Exception:
            # Lo stato errore è già registrato dai singoli connettori.
            pass

        await asyncio.sleep(interval_seconds())

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import SessionLocal
from app.services.ingest import sync_source
from app.sources.registry import enabled_sources

_lock = threading.Lock()
_stop_event = threading.Event()
_thread: threading.Thread | None = None
_last_cycle_at: datetime | None = None
_next_run_at: datetime | None = None
_last_results: list[dict] = []


def run_sync_cycle(force_full: bool = False) -> list[dict]:
    global _last_cycle_at, _last_results, _next_run_at
    if not _lock.acquire(blocking=False):
        return _last_results
    try:
        results: list[dict] = []
        with SessionLocal() as db:
            for source in enabled_sources():
                result = sync_source(
                    db,
                    source,
                    settings.sync_limit_per_source,
                    force_full=force_full,
                )
                results.append(result.model_dump())
        _last_cycle_at = datetime.now(timezone.utc)
        _last_results = results
        _next_run_at = _last_cycle_at + timedelta(minutes=settings.sync_interval_minutes)
        return results
    finally:
        _lock.release()


def _loop() -> None:
    global _next_run_at
    interval_seconds = settings.sync_interval_minutes * 60
    _next_run_at = datetime.now(timezone.utc) + timedelta(seconds=interval_seconds)
    while not _stop_event.wait(interval_seconds):
        run_sync_cycle()


def start_scheduler() -> None:
    global _thread
    if not settings.scheduler_enabled or (_thread and _thread.is_alive()):
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="job-radar-scheduler", daemon=True)
    _thread.start()


def stop_scheduler() -> None:
    global _thread, _next_run_at
    _stop_event.set()
    if _thread and _thread.is_alive():
        _thread.join(timeout=1.0)
    _thread = None
    _next_run_at = None


def scheduler_status() -> dict:
    return {
        "enabled": settings.scheduler_enabled,
        "running": bool(_thread and _thread.is_alive()),
        "interval_minutes": settings.sync_interval_minutes,
        "next_run_at": _next_run_at,
        "last_cycle_at": _last_cycle_at,
        "last_results": _last_results,
    }

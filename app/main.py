from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import desc, func, or_, select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import Base, SessionLocal, engine, get_db
from app.models import Feedback, LearningProfile, Preference, SourceState, Vacancy, VacancySourceRef
from app.schemas import FeedbackIn, PreferenceIn, PreferenceOut, SyncResult, VacancyOut
from app.services.ingest import backfill_source_refs, get_or_create_preferences, rescore_all, sync_source
from app.services.learning import rebuild_learning_profile
from app.services.scheduler import run_sync_cycle, scheduler_status, start_scheduler, stop_scheduler
from app.sources.registry import ALL_SOURCES

STATIC_DIR = Path(__file__).parent / "static"
PLANNED_SOURCES = ["avito", "getmatch", "careerspace", "dreamjob", "telegram", "company-careers"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        get_or_create_preferences(db)
        backfill_source_refs(db)
        if (db.scalar(select(func.count(Vacancy.id))) or 0) == 0:
            sync_source(db, ALL_SOURCES["mock"], 20)
        if db.get(LearningProfile, 1) is None:
            db.add(LearningProfile(id=1))
            db.commit()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Job Radar MVP", version="0.2.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "version": "0.2.0",
        "llm_configured": bool(settings.llm_enabled and settings.openai_api_key),
        "scheduler": scheduler_status(),
    }


@app.get("/api/vacancies", response_model=list[VacancyOut])
def vacancies(
    min_score: float = Query(0, ge=0, le=100),
    source: str | None = None,
    include_reviewed: bool = False,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(Vacancy).where(Vacancy.active.is_(True), Vacancy.score >= min_score)
    if not include_reviewed:
        reviewed = select(Feedback.vacancy_id).where(Feedback.action.in_(["like", "dislike", "skip"]))
        stmt = stmt.where(Vacancy.id.not_in(reviewed))
    if source:
        stmt = stmt.where(or_(
            Vacancy.source == source,
            Vacancy.source_refs.any(VacancySourceRef.source == source),
        ))
    stmt = stmt.order_by(desc(Vacancy.score), desc(Vacancy.published_at), desc(Vacancy.id)).limit(limit)
    return list(db.scalars(stmt).unique().all())


@app.get("/api/vacancies/{vacancy_id}", response_model=VacancyOut)
def vacancy(vacancy_id: int, db: Session = Depends(get_db)):
    row = db.get(Vacancy, vacancy_id)
    if not row:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    return row


@app.post("/api/vacancies/{vacancy_id}/feedback")
def create_feedback(vacancy_id: int, payload: FeedbackIn, db: Session = Depends(get_db)):
    row = db.get(Vacancy, vacancy_id)
    if not row:
        raise HTTPException(status_code=404, detail="Vacancy not found")
    db.add(Feedback(vacancy_id=vacancy_id, action=payload.action, reason=payload.reason))
    db.flush()
    profile = rebuild_learning_profile(db)
    rescore_all(db, use_llm=False)
    return {"ok": True, "learned_from": profile.feedback_count}


@app.get("/api/learning-profile")
def learning_profile(db: Session = Depends(get_db)):
    profile = db.get(LearningProfile, 1) or rebuild_learning_profile(db)
    db.commit()
    return {
        "feedback_count": profile.feedback_count,
        "positive_terms": profile.positive_terms,
        "negative_terms": profile.negative_terms,
        "company_weights": profile.company_weights,
        "updated_at": profile.updated_at,
    }


@app.get("/api/preferences", response_model=PreferenceOut)
def get_preferences(db: Session = Depends(get_db)):
    return get_or_create_preferences(db)


@app.put("/api/preferences", response_model=PreferenceOut)
def update_preferences(payload: PreferenceIn, db: Session = Depends(get_db)):
    pref = get_or_create_preferences(db)
    for key, value in payload.model_dump().items():
        setattr(pref, key, value)
    db.add(pref)
    db.commit()
    db.refresh(pref)
    rescore_all(db, use_llm=False)
    return pref


@app.post("/api/rescore")
def rescore(use_llm: bool = False, db: Session = Depends(get_db)):
    return {"ok": True, "rescored": rescore_all(db, use_llm=use_llm), "llm_requested": use_llm}


@app.post("/api/sync/{source_name}", response_model=SyncResult)
def sync(source_name: str, db: Session = Depends(get_db)):
    source = ALL_SOURCES.get(source_name)
    if not source:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_name}")
    if not getattr(source, "configured", True):
        raise HTTPException(status_code=409, detail=f"Source {source_name} is not configured")
    return sync_source(db, source, settings.sync_limit_per_source)


@app.post("/api/sync-all")
def sync_all():
    return {"ok": True, "results": run_sync_cycle()}


@app.get("/api/scheduler")
def scheduler():
    return scheduler_status()


@app.get("/api/sources")
def source_list(db: Session = Depends(get_db)):
    states = {row.source: row for row in db.scalars(select(SourceState)).all()}
    active_names = set(settings.enabled_sources)
    result = []
    for name, source in ALL_SOURCES.items():
        state = states.get(name)
        result.append({
            "name": name,
            "enabled": name in active_names,
            "configured": bool(getattr(source, "configured", True)),
            "status": "ready" if getattr(source, "configured", True) else "needs_config",
            "last_sync_at": state.last_sync_at if state else None,
            "last_error": state.last_error if state else None,
            "items_seen": state.items_seen if state else 0,
        })
    result.extend({"name": name, "enabled": False, "configured": False, "status": "planned"} for name in PLANNED_SOURCES)
    return result

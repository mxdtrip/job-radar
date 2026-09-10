from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LearningProfile, Preference, SourceState, Vacancy, VacancySourceRef
from app.schemas import SyncResult
from app.services.dedupe import find_cross_source_duplicate, fingerprint
from app.services.llm_scoring import llm_score
from app.services.scoring import score_vacancy
from app.sources.base import RawVacancy, VacancySource


def get_or_create_preferences(db: Session) -> Preference:
    pref = db.get(Preference, 1)
    if pref is None:
        # Search criteria are intentionally empty for a fresh install.
        # The web onboarding fills them before the first real sync.
        pref = Preference(
            id=1,
            desired_terms=[],
            excluded_terms=[],
            locations=[],
            target_companies=[],
            excluded_companies=[],
            min_salary=None,
            remote_ok=True,
            notes="",
        )
        db.add(pref)
        db.commit()
        db.refresh(pref)
    return pref


def to_raw(row: Vacancy) -> RawVacancy:
    return RawVacancy(
        source=row.source, external_id=row.external_id, title=row.title, company=row.company,
        location=row.location, url=row.url, published_at=row.published_at, remote=row.remote,
        salary_from=row.salary_from, salary_to=row.salary_to, currency=row.currency,
        experience=row.experience, employment=row.employment, description=row.description,
        requirements=row.requirements,
    )


def backfill_source_refs(db: Session) -> int:
    inserted = 0
    for row in db.scalars(select(Vacancy)).all():
        existing = db.scalar(select(VacancySourceRef).where(
            VacancySourceRef.source == row.source,
            VacancySourceRef.external_id == row.external_id,
        ))
        if not existing:
            db.add(VacancySourceRef(
                vacancy_id=row.id, source=row.source, external_id=row.external_id, url=row.url
            ))
            inserted += 1
    if inserted:
        db.commit()
    return inserted


def _merge_row(row: Vacancy, raw: RawVacancy) -> bool:
    changed = False
    for attr in ("title", "company", "location", "experience", "employment"):
        incoming = getattr(raw, attr)
        if incoming and incoming != getattr(row, attr):
            setattr(row, attr, incoming)
            changed = True
    if raw.remote and not row.remote:
        row.remote = True
        changed = True
    for attr in ("salary_from", "salary_to", "currency"):
        incoming = getattr(raw, attr)
        if incoming is not None and incoming != getattr(row, attr):
            setattr(row, attr, incoming)
            changed = True
    if raw.description and len(raw.description) > len(row.description or ""):
        row.description = raw.description
        changed = True
    if raw.requirements and len(raw.requirements) > len(row.requirements or ""):
        row.requirements = raw.requirements
        changed = True
    if raw.published_at and (row.published_at is None or raw.published_at < row.published_at):
        row.published_at = raw.published_at
        changed = True
    row.active = True
    row.fetched_at = datetime.now(timezone.utc)
    return changed


def _score(
    row_or_raw: Vacancy | RawVacancy,
    pref: Preference,
    learning: LearningProfile | None,
    use_llm: bool,
) -> tuple[float, list[str]]:
    raw = to_raw(row_or_raw) if isinstance(row_or_raw, Vacancy) else row_or_raw
    heuristic, reasons = score_vacancy(raw, pref, learning)
    if not use_llm or heuristic < settings.llm_min_heuristic_score:
        return heuristic, reasons
    try:
        ai = llm_score(raw, pref)
    except Exception:
        ai = None
    if ai is None:
        return heuristic, reasons
    ai_score, ai_reasons = ai
    final = heuristic * (1.0 - settings.llm_weight) + ai_score * settings.llm_weight
    return round(max(0.0, min(100.0, final)), 1), (ai_reasons + reasons)[:9]


def rescore_all(db: Session, use_llm: bool = False) -> int:
    pref = get_or_create_preferences(db)
    learning = db.get(LearningProfile, 1)
    rows = list(db.scalars(select(Vacancy)))
    for row in rows:
        row.score, row.score_reasons = _score(row, pref, learning, use_llm=use_llm)
    db.commit()
    return len(rows)


def _fetch_rows(
    source: VacancySource,
    pref: Preference,
    limit: int,
    since: datetime | None,
    known_ids: set[str],
) -> list[RawVacancy]:
    """Let sources use user preferences when they support contextual search."""
    contextual_fetch = getattr(source, "fetch_for_preferences", None)
    if callable(contextual_fetch):
        return contextual_fetch(
            preference=pref,
            limit=limit,
            since=since,
            known_ids=known_ids,
        )
    return source.fetch(limit=limit, since=since, known_ids=known_ids)


def sync_source(db: Session, source: VacancySource, limit: int, force_full: bool = False) -> SyncResult:
    inserted = updated = duplicates = 0
    state = db.get(SourceState, source.name)
    previous_sync_at = state.last_sync_at if state else None
    try:
        pref = get_or_create_preferences(db)
        known_ids = set(db.scalars(
            select(VacancySourceRef.external_id).where(VacancySourceRef.source == source.name)
        ).all())
        effective_since = None if force_full else previous_sync_at
        rows = _fetch_rows(source, pref, limit, effective_since, known_ids)
        learning = db.get(LearningProfile, 1)

        for raw in rows:
            fp = fingerprint(raw.company, raw.title)
            source_ref = db.scalar(select(VacancySourceRef).where(
                VacancySourceRef.source == raw.source,
                VacancySourceRef.external_id == raw.external_id,
            ))

            if source_ref:
                canonical = db.get(Vacancy, source_ref.vacancy_id)
                if canonical:
                    changed = _merge_row(canonical, raw)
                    canonical.fingerprint = fingerprint(canonical.company, canonical.title)
                    canonical.score, canonical.score_reasons = _score(
                        canonical, pref, learning, use_llm=changed
                    )
                    source_ref.last_seen_at = datetime.now(timezone.utc)
                    source_ref.url = raw.url or source_ref.url
                    updated += 1
                    continue

            legacy = db.scalar(select(Vacancy).where(
                Vacancy.source == raw.source, Vacancy.external_id == raw.external_id
            ))
            if legacy:
                changed = _merge_row(legacy, raw)
                legacy.fingerprint = fingerprint(legacy.company, legacy.title)
                legacy.score, legacy.score_reasons = _score(legacy, pref, learning, use_llm=changed)
                db.add(VacancySourceRef(
                    vacancy_id=legacy.id, source=raw.source, external_id=raw.external_id, url=raw.url
                ))
                updated += 1
                continue

            canonical = find_cross_source_duplicate(db, raw, fp)
            if canonical:
                duplicates += 1
                changed = _merge_row(canonical, raw)
                canonical.fingerprint = fingerprint(canonical.company, canonical.title)
                canonical.score, canonical.score_reasons = _score(canonical, pref, learning, use_llm=changed)
                db.add(VacancySourceRef(
                    vacancy_id=canonical.id, source=raw.source, external_id=raw.external_id, url=raw.url
                ))
                continue

            score, reasons = _score(raw, pref, learning, use_llm=True)
            canonical = Vacancy(
                source=raw.source, external_id=raw.external_id, title=raw.title, company=raw.company,
                location=raw.location, remote=raw.remote, salary_from=raw.salary_from,
                salary_to=raw.salary_to, currency=raw.currency, experience=raw.experience,
                employment=raw.employment, description=raw.description, requirements=raw.requirements,
                url=raw.url, published_at=raw.published_at, fingerprint=fp, score=score,
                score_reasons=reasons,
            )
            db.add(canonical)
            db.flush()
            db.add(VacancySourceRef(
                vacancy_id=canonical.id, source=raw.source, external_id=raw.external_id, url=raw.url
            ))
            inserted += 1

        state = state or SourceState(source=source.name)
        state.last_sync_at = datetime.now(timezone.utc)
        state.last_error = None
        state.items_seen = (state.items_seen or 0) + len(rows)
        db.add(state)
        db.commit()
        return SyncResult(
            source=source.name,
            fetched=len(rows),
            inserted=inserted,
            updated=updated,
            duplicates=duplicates,
        )
    except Exception as exc:
        db.rollback()
        state = db.get(SourceState, source.name) or SourceState(source=source.name)
        # Critical: a failed request must NOT move the incremental cursor forward.
        state.last_sync_at = previous_sync_at
        state.last_error = str(exc)[:2000]
        db.add(state)
        db.commit()
        return SyncResult(
            source=source.name,
            fetched=0,
            inserted=0,
            updated=0,
            duplicates=0,
            error=str(exc),
        )

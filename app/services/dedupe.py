from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Vacancy
from app.sources.base import RawVacancy

COMPANY_ALIASES = {
    "вконтакте": "vk",
    "вк": "vk",
    "vk company": "vk",
    "тинькофф": "т банк",
    "т банк": "т банк",
    "t bank": "т банк",
    "сбербанк": "сбер",
    "sber": "сбер",
    "ozon офис и коммерция": "ozon",
}

ROLE_NOISE = {
    "senior", "старший", "ведущий", "junior", "младший", "middle", "lead",
    "менеджер", "manager", "специалист", "руководитель", "направления", "отдела",
}


def normalize(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = value.replace("—", " ").replace("–", " ")
    value = re.sub(r"[^a-zа-я0-9]+", " ", value, flags=re.IGNORECASE)
    return " ".join(value.split())


def normalize_company(value: str) -> str:
    text = normalize(value)
    for legal in ("ооо", "ао", "пао", "ано", "гк", "зао"):
        text = re.sub(rf"\b{legal}\b", " ", text)
    text = " ".join(text.split())
    return COMPANY_ALIASES.get(text, text)


def title_tokens(value: str) -> set[str]:
    return {t for t in normalize(value).split() if len(t) > 2 and t not in ROLE_NOISE}


def fingerprint(company: str, title: str) -> str:
    canonical = f"{normalize_company(company)}|{normalize(title)}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def duplicate_confidence(raw: RawVacancy, row: Vacancy) -> float:
    c1, c2 = normalize_company(raw.company), normalize_company(row.company)
    if not c1 or not c2:
        return 0.0
    company_score = max(_similarity(c1, c2), 1.0 if c1 == c2 else 0.0)
    title_seq = _similarity(normalize(raw.title), normalize(row.title))
    title_jac = _jaccard(title_tokens(raw.title), title_tokens(row.title))
    title_score = max(title_seq, title_jac)

    if company_score < 0.72 or title_score < 0.58:
        return 0.0
    return round(company_score * 0.48 + title_score * 0.52, 4)


def find_cross_source_duplicate(db: Session, raw: RawVacancy, fp: str) -> Vacancy | None:
    exact = db.scalar(select(Vacancy).where(Vacancy.fingerprint == fp, Vacancy.active.is_(True)).limit(1))
    if exact:
        return exact

    # Fuzzy matching only against a bounded candidate pool from a similar company name.
    company_norm = normalize_company(raw.company)
    candidates = list(db.scalars(select(Vacancy).where(Vacancy.active.is_(True)).order_by(Vacancy.id.desc()).limit(500)))
    best: tuple[float, Vacancy] | None = None
    for row in candidates:
        if company_norm and normalize_company(row.company):
            confidence = duplicate_confidence(raw, row)
            if confidence >= 0.82 and (best is None or confidence > best[0]):
                best = (confidence, row)
    return best[1] if best else None

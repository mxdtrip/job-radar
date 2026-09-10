from __future__ import annotations

from app.models import LearningProfile, Preference
from app.services.dedupe import normalize
from app.services.learning import learning_adjustment
from app.sources.base import RawVacancy

DEFAULT_DESIRED = [
    "event", "ивент", "мероприят", "спецпроект", "специальных проектов", "конференц", "форум",
    "producer", "продюсер", "event marketing", "событийного маркетинга", "корпоративных мероприятий",
    "внутренних коммуникаций", "external communications", "brand experience",
]
DEFAULT_EXCLUDED = ["свадеб", "банкет", "аниматор", "ведущий мероприятий", "продажа банкетов"]


def score_vacancy(v: RawVacancy, pref: Preference, learning: LearningProfile | None = None) -> tuple[float, list[str]]:
    haystack = normalize(" ".join([v.title, v.company, v.description, v.requirements]))
    title = normalize(v.title)
    company = normalize(v.company)
    desired = pref.desired_terms or DEFAULT_DESIRED
    excluded = pref.excluded_terms or DEFAULT_EXCLUDED

    score = 42.0
    reasons: list[str] = []

    desired_hits = [term for term in desired if normalize(term) in haystack]
    if desired_hits:
        boost = min(30, 9 + len(desired_hits) * 5)
        score += boost
        reasons.append(f"Совпадения по профилю: {', '.join(desired_hits[:4])}")

    title_hits = [term for term in desired if normalize(term) in title]
    if title_hits:
        score += 12
        reasons.append("Релевантное название роли")

    bad_hits = [term for term in excluded if normalize(term) in haystack]
    if bad_hits:
        score -= min(60, 28 + len(bad_hits) * 10)
        reasons.append(f"Нежелательные признаки: {', '.join(bad_hits[:3])}")

    target_hits = [c for c in (pref.target_companies or []) if normalize(c) in company]
    if target_hits:
        score += 15
        reasons.append("Компания в списке приоритетных")

    excluded_companies = [c for c in (pref.excluded_companies or []) if normalize(c) in company]
    if excluded_companies:
        score -= 75
        reasons.append("Компания исключена настройками")

    if pref.locations:
        location_ok = any(normalize(loc) in normalize(v.location) for loc in pref.locations)
        if location_ok:
            score += 5
            reasons.append("Подходящая локация")
        elif not (pref.remote_ok and v.remote):
            score -= 18
            reasons.append("Локация вне предпочтений")

    salary_anchor = v.salary_from or v.salary_to
    if pref.min_salary and salary_anchor:
        if salary_anchor >= pref.min_salary:
            score += 10
            reasons.append("Зарплата соответствует минимуму")
        else:
            score -= 18
            reasons.append("Зарплата ниже заданного минимума")

    if v.remote and pref.remote_ok:
        score += 4
        reasons.append("Удалённый формат допустим")

    adjustment, learned_reasons = learning_adjustment(haystack, v.company, learning)
    score += adjustment
    reasons.extend(learned_reasons)

    return round(max(0.0, min(100.0, score)), 1), reasons

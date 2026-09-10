from __future__ import annotations

import math
import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Feedback, LearningProfile, Vacancy
from app.services.dedupe import normalize, normalize_company

STOPWORDS = {
    "and", "the", "for", "with", "или", "для", "как", "что", "это", "при", "под", "над", "без",
    "работа", "работы", "опыт", "компания", "команде", "команды", "будет", "нужно", "ищем", "менеджер",
    "manager", "специалист", "москва", "moscow", "лет", "года", "года", "от", "до", "по", "на", "в", "с",
}


def _tokens(v: Vacancy) -> list[str]:
    text = normalize(f"{v.title} {v.title} {v.description} {v.requirements}")
    words = [w for w in text.split() if len(w) >= 4 and w not in STOPWORDS and not w.isdigit()]
    # title is intentionally duplicated above to make role terms more influential.
    return words[:700]


def rebuild_learning_profile(db: Session) -> LearningProfile:
    likes: Counter[str] = Counter()
    dislikes: Counter[str] = Counter()
    companies: Counter[str] = Counter()
    feedback_rows = list(db.scalars(select(Feedback).where(Feedback.action.in_(["like", "dislike"]))))

    for fb in feedback_rows:
        vacancy = db.get(Vacancy, fb.vacancy_id)
        if not vacancy:
            continue
        target = likes if fb.action == "like" else dislikes
        target.update(_tokens(vacancy))
        company = normalize_company(vacancy.company)
        if company:
            companies[company] += 1 if fb.action == "like" else -1
        if fb.reason:
            reason_words = [w for w in normalize(fb.reason).split() if len(w) >= 4 and w not in STOPWORDS]
            target.update(reason_words * 2)

    vocabulary = set(likes) | set(dislikes)
    positive: dict[str, float] = {}
    negative: dict[str, float] = {}
    for term in vocabulary:
        # Smoothed log-odds, clipped to avoid one click dominating the model.
        weight = math.log((likes[term] + 1.0) / (dislikes[term] + 1.0))
        weight = round(max(-1.6, min(1.6, weight)), 3)
        if weight >= 0.22:
            positive[term] = weight
        elif weight <= -0.22:
            negative[term] = abs(weight)

    profile = db.get(LearningProfile, 1) or LearningProfile(id=1)
    profile.positive_terms = dict(sorted(positive.items(), key=lambda x: x[1], reverse=True)[:60])
    profile.negative_terms = dict(sorted(negative.items(), key=lambda x: x[1], reverse=True)[:60])
    profile.company_weights = {k: max(-4, min(4, v)) for k, v in companies.most_common(50)}
    profile.feedback_count = len(feedback_rows)
    db.add(profile)
    db.flush()
    return profile


def learning_adjustment(vacancy_text: str, company: str, profile: LearningProfile | None) -> tuple[float, list[str]]:
    if not profile or profile.feedback_count < 2:
        return 0.0, []
    text = normalize(vacancy_text)
    tokens = set(re.findall(r"[a-zа-я0-9]+", text))
    pos = sum(float(w) for term, w in (profile.positive_terms or {}).items() if term in tokens)
    neg = sum(float(w) for term, w in (profile.negative_terms or {}).items() if term in tokens)
    company_weight = float((profile.company_weights or {}).get(normalize_company(company), 0))
    adjustment = max(-14.0, min(14.0, pos * 1.8 - neg * 1.8 + company_weight * 2.0))
    reasons = []
    if adjustment >= 2.0:
        reasons.append("Похоже на вакансии, которые вы лайкали")
    elif adjustment <= -2.0:
        reasons.append("Похоже на вакансии, которые вы отклоняли")
    return round(adjustment, 1), reasons

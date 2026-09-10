from __future__ import annotations

import json

import httpx

from app.config import settings
from app.models import Preference
from app.sources.base import RawVacancy

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "number"},
        "summary": {"type": "string"},
        "pros": {"type": "array", "items": {"type": "string"}},
        "cons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "summary", "pros", "cons"],
    "additionalProperties": False,
}


def available() -> bool:
    return bool(settings.llm_enabled and settings.openai_api_key)


def _extract_output_text(payload: dict) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    raise ValueError("OpenAI response did not contain output_text")


def llm_score(v: RawVacancy, pref: Preference) -> tuple[float, list[str]] | None:
    if not available():
        return None

    candidate_profile = {
        "desired_terms": pref.desired_terms,
        "excluded_terms": pref.excluded_terms,
        "locations": pref.locations,
        "target_companies": pref.target_companies,
        "excluded_companies": pref.excluded_companies,
        "min_salary": pref.min_salary,
        "remote_ok": pref.remote_ok,
        "notes": pref.notes,
    }
    vacancy = {
        "title": v.title,
        "company": v.company,
        "location": v.location,
        "remote": v.remote,
        "salary_from": v.salary_from,
        "salary_to": v.salary_to,
        "currency": v.currency,
        "experience": v.experience,
        "employment": v.employment,
        "description": v.description[:7000],
        "requirements": v.requirements[:5000],
    }
    body = {
        "model": settings.openai_model,
        "store": False,
        "instructions": (
            "Оцени релевантность вакансии конкретному кандидату от 0 до 100. "
            "Не завышай оценку из-за одного совпавшего слова. Учитывай реальные обязанности, уровень, "
            "индустрию, ограничения и переносимость опыта. Ответ строго по JSON schema."
        ),
        "input": json.dumps({"candidate": candidate_profile, "vacancy": vacancy}, ensure_ascii=False),
        "text": {
            "verbosity": "low",
            "format": {"type": "json_schema", "name": "vacancy_score", "strict": True, "schema": SCHEMA},
        },
        "max_output_tokens": 500,
    }
    headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
    with httpx.Client(timeout=35.0) as client:
        response = client.post("https://api.openai.com/v1/responses", headers=headers, json=body)
        response.raise_for_status()
        parsed = json.loads(_extract_output_text(response.json()))

    reasons = [f"AI: {parsed['summary']}"]
    reasons.extend(f"+ {x}" for x in parsed.get("pros", [])[:3])
    reasons.extend(f"− {x}" for x in parsed.get("cons", [])[:2])
    return float(parsed["score"]), reasons

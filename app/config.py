from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./job_radar.db")
    http_user_agent: str = os.getenv(
        "HTTP_USER_AGENT", "JobRadarMVP/0.2 (+personal job search; contact: replace-me@example.com)"
    )

    hh_user_agent: str = os.getenv(
        "HH_USER_AGENT", "JobRadarMVP/0.2 (replace-with-your-email@example.com)"
    )
    hh_search_text: str = os.getenv(
        "HH_SEARCH_TEXT",
        "event manager OR event producer OR менеджер мероприятий OR спецпроекты",
    )
    hh_area: str = os.getenv("HH_AREA", "1")

    superjob_api_key: str | None = os.getenv("SUPERJOB_API_KEY")
    superjob_keyword: str = os.getenv("SUPERJOB_KEYWORD", "event manager")
    superjob_town: str = os.getenv("SUPERJOB_TOWN", "Москва")

    enabled_sources: list[str] = None  # type: ignore[assignment]
    sync_limit_per_source: int = int(os.getenv("SYNC_LIMIT_PER_SOURCE", "40"))
    scheduler_enabled: bool = env_bool("SCHEDULER_ENABLED", True)
    sync_interval_minutes: int = max(1, int(os.getenv("SYNC_INTERVAL_MINUTES", "10")))

    openai_api_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
    llm_enabled: bool = env_bool("LLM_ENABLED", True)
    llm_min_heuristic_score: float = float(os.getenv("LLM_MIN_HEURISTIC_SCORE", "45"))
    llm_weight: float = min(1.0, max(0.0, float(os.getenv("LLM_WEIGHT", "0.65"))))

    def __post_init__(self):
        object.__setattr__(
            self,
            "enabled_sources",
            env_list("ENABLED_SOURCES", "hh,eventru,geekjob,habr,superjob"),
        )


settings = Settings()

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class SourceNotConfigured(RuntimeError):
    pass


@dataclass
class RawVacancy:
    source: str
    external_id: str
    title: str
    company: str
    location: str
    url: str
    published_at: datetime | None = None
    remote: bool = False
    salary_from: int | None = None
    salary_to: int | None = None
    currency: str | None = None
    experience: str | None = None
    employment: str | None = None
    description: str = ""
    requirements: str = ""
    metadata: dict = field(default_factory=dict)


class VacancySource(Protocol):
    name: str
    configured: bool

    def fetch(self, limit: int = 40, since: datetime | None = None, known_ids: set[str] | None = None) -> list[RawVacancy]: ...

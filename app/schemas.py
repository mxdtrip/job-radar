from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VacancyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    sources: list[str]
    title: str
    company: str
    location: str
    remote: bool
    salary_from: int | None
    salary_to: int | None
    currency: str | None
    experience: str | None
    employment: str | None
    url: str
    published_at: datetime | None
    score: float
    score_reasons: list


class PreferenceIn(BaseModel):
    desired_terms: list[str] = Field(default_factory=list)
    excluded_terms: list[str] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    target_companies: list[str] = Field(default_factory=list)
    excluded_companies: list[str] = Field(default_factory=list)
    min_salary: int | None = None
    remote_ok: bool = True
    notes: str = ""


class PreferenceOut(PreferenceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    updated_at: datetime


class FeedbackIn(BaseModel):
    action: Literal["like", "dislike", "skip"]
    reason: str | None = None


class SyncResult(BaseModel):
    source: str
    fetched: int
    inserted: int
    updated: int
    duplicates: int
    error: str | None = None

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Vacancy(Base):
    __tablename__ = "vacancies"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_source_external_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(500), index=True)
    company: Mapped[str] = mapped_column(String(500), default="")
    location: Mapped[str] = mapped_column(String(500), default="")
    remote: Mapped[bool] = mapped_column(Boolean, default=False)
    salary_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_to: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    experience: Mapped[str | None] = mapped_column(String(255), nullable=True)
    employment: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    requirements: Mapped[str] = mapped_column(Text, default="")
    url: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    score_reasons: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    feedback: Mapped[list["Feedback"]] = relationship(back_populates="vacancy", cascade="all, delete-orphan")
    source_refs: Mapped[list["VacancySourceRef"]] = relationship(
        back_populates="vacancy", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def sources(self) -> list[str]:
        values = {self.source}
        values.update(ref.source for ref in self.source_refs)
        return sorted(values)


class VacancySourceRef(Base):
    __tablename__ = "vacancy_source_refs"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_vacancy_source_ref"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    url: Mapped[str] = mapped_column(Text, default="")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vacancy: Mapped[Vacancy] = relationship(back_populates="source_refs")


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    desired_terms: Mapped[list] = mapped_column(JSON, default=list)
    excluded_terms: Mapped[list] = mapped_column(JSON, default=list)
    locations: Mapped[list] = mapped_column(JSON, default=list)
    target_companies: Mapped[list] = mapped_column(JSON, default=list)
    excluded_companies: Mapped[list] = mapped_column(JSON, default=list)
    min_salary: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remote_ok: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LearningProfile(Base):
    __tablename__ = "learning_profile"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    positive_terms: Mapped[dict] = mapped_column(JSON, default=dict)
    negative_terms: Mapped[dict] = mapped_column(JSON, default=dict)
    company_weights: Mapped[dict] = mapped_column(JSON, default=dict)
    feedback_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vacancy_id: Mapped[int] = mapped_column(ForeignKey("vacancies.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vacancy: Mapped[Vacancy] = relationship(back_populates="feedback")


class SourceState(Base):
    __tablename__ = "source_state"

    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    items_seen: Mapped[int] = mapped_column(Integer, default=0)

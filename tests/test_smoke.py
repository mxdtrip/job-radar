import os
from pathlib import Path

TEST_DB = Path("./test_job_radar.db")
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = "sqlite:///./test_job_radar.db"
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["LLM_ENABLED"] = "false"
os.environ["ENABLED_SOURCES"] = "mock"

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import LearningProfile, Vacancy, VacancySourceRef
from app.services.ingest import sync_source
from app.sources.base import RawVacancy


class DuplicateVKSource:
    name = "duplicate-test"
    configured = True

    def fetch(self, limit=40, since=None, known_ids=None):
        return [RawVacancy(
            source=self.name,
            external_id="event-vk-copy",
            title="Event manager",
            company="ВК",
            location="Москва",
            url="https://another.example/vk",
            salary_from=160000,
            description="Организация конференций, спецпроектов и крупных офлайн мероприятий.",
            requirements="Подрядчики, бюджеты, event production.",
        )]


def test_health_and_feed():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True
        assert health.json()["version"] == "0.2.0"

        feed = client.get("/api/vacancies")
        assert feed.status_code == 200
        assert len(feed.json()) >= 1
        assert any(row["company"] == "VK" for row in feed.json())
        assert all("sources" in row for row in feed.json())


def test_feedback_removes_from_feed():
    with TestClient(app) as client:
        before = client.get("/api/vacancies").json()
        vacancy_id = before[0]["id"]
        response = client.post(f"/api/vacancies/{vacancy_id}/feedback", json={"action": "like"})
        assert response.status_code == 200
        assert response.json()["ok"] is True
        after = client.get("/api/vacancies").json()
        assert vacancy_id not in {row["id"] for row in after}


def test_preferences_recalculate_scores():
    with TestClient(app) as client:
        prefs = client.get("/api/preferences").json()
        prefs["target_companies"] = ["Tech Brand"]
        prefs.pop("id", None)
        prefs.pop("updated_at", None)
        response = client.put("/api/preferences", json=prefs)
        assert response.status_code == 200
        rows = client.get("/api/vacancies?min_score=0&include_reviewed=true").json()
        tech = next(r for r in rows if r["company"] == "Tech Brand")
        assert "Компания в списке приоритетных" in tech["score_reasons"]


def test_cross_source_duplicate_merges_into_one_vacancy():
    with TestClient(app):
        with SessionLocal() as db:
            before = db.scalar(select(Vacancy).where(Vacancy.company == "VK"))
            assert before is not None
            result = sync_source(db, DuplicateVKSource(), 20)
            assert result.duplicates == 1
            vk_rows = list(db.scalars(select(Vacancy).where(Vacancy.company.in_(["VK", "ВК"]))))
            assert len(vk_rows) == 1
            refs = list(db.scalars(select(VacancySourceRef).where(VacancySourceRef.vacancy_id == vk_rows[0].id)))
            assert {x.source for x in refs} >= {"mock", "duplicate-test"}


def test_learning_profile_updates_from_feedback():
    with TestClient(app) as client:
        rows = client.get("/api/vacancies?min_score=0&include_reviewed=true").json()
        vk = next(r for r in rows if r["company"] in {"VK", "ВК"})
        wedding = next(r for r in rows if r["company"] == "Wedding Dreams")
        client.post(f"/api/vacancies/{vk['id']}/feedback", json={"action": "like", "reason": "нравятся конференции и крупные бренды"})
        client.post(f"/api/vacancies/{wedding['id']}/feedback", json={"action": "dislike", "reason": "не хочу свадьбы и продажи"})
        profile = client.get("/api/learning-profile").json()
        assert profile["feedback_count"] >= 2
        assert profile["positive_terms"] or profile["negative_terms"]
        with SessionLocal() as db:
            stored = db.get(LearningProfile, 1)
            assert stored is not None and stored.feedback_count >= 2

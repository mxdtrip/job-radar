from __future__ import annotations

from datetime import datetime, timezone

from app.sources.base import RawVacancy


class MockSource:
    name = "mock"
    configured = True

    def fetch(self, limit: int = 40, since: datetime | None = None, known_ids: set[str] | None = None) -> list[RawVacancy]:
        now = datetime.now(timezone.utc)
        rows = [
            RawVacancy(
                source="mock",
                external_id="vk-event-1",
                title="Event Project Manager",
                company="VK",
                location="Москва",
                url="https://example.com/vk-event",
                published_at=now,
                salary_from=160000,
                salary_to=220000,
                currency="RUR",
                description="Организация конференций, спецпроектов и крупных офлайн-мероприятий.",
                requirements="Опыт работы с подрядчиками, бюджетами и event production.",
            ),
            RawVacancy(
                source="mock",
                external_id="wedding-1",
                title="Event manager",
                company="Wedding Dreams",
                location="Москва",
                url="https://example.com/wedding",
                published_at=now,
                salary_from=90000,
                currency="RUR",
                description="Организация свадеб и банкетов.",
                requirements="Продажа банкетов, работа с молодоженами.",
            ),
            RawVacancy(
                source="mock",
                external_id="special-projects-1",
                title="Менеджер специальных проектов",
                company="Tech Brand",
                location="Москва",
                url="https://example.com/special-projects",
                published_at=now,
                salary_from=180000,
                currency="RUR",
                description="Конференции, партнерские спецпроекты, мероприятия для профессионального сообщества.",
                requirements="Управление подрядчиками, таймингами, сметами и производством.",
            ),
        ]
        return rows[:limit]

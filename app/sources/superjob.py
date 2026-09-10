from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.config import settings
from app.sources.base import RawVacancy, SourceNotConfigured


class SuperJobSource:
    name = "superjob"

    @property
    def configured(self) -> bool:
        return bool(settings.superjob_api_key)

    def fetch(self, limit: int = 40, since: datetime | None = None, known_ids: set[str] | None = None) -> list[RawVacancy]:
        if not settings.superjob_api_key:
            raise SourceNotConfigured("SUPERJOB_API_KEY is not configured")
        headers = {"X-Api-App-Id": settings.superjob_api_key, "User-Agent": settings.http_user_agent}
        params = {
            "keyword": settings.superjob_keyword,
            "town": settings.superjob_town,
            "count": min(max(limit, 1), 100),
            "order_field": "date",
            "order_direction": "desc",
        }
        if since:
            params["period"] = 1
        with httpx.Client(timeout=20, headers=headers) as client:
            response = client.get("https://api.superjob.ru/2.0/vacancies/", params=params)
            response.raise_for_status()
            payload = response.json()
        rows: list[RawVacancy] = []
        for item in payload.get("objects", []):
            published = datetime.fromtimestamp(item["date_published"], tz=timezone.utc) if item.get("date_published") else None
            if since and published and published < since:
                continue
            town = (item.get("town") or {}).get("title") or ""
            client = item.get("client") or {}
            payment_from = item.get("payment_from") or None
            payment_to = item.get("payment_to") or None
            rows.append(RawVacancy(
                source=self.name,
                external_id=str(item.get("id")),
                title=item.get("profession") or "",
                company=client.get("title") or item.get("firm_name") or "",
                location=town,
                url=item.get("link") or "",
                published_at=published,
                remote="удален" in (item.get("candidat") or "").lower(),
                salary_from=payment_from,
                salary_to=payment_to,
                currency=(item.get("currency") or "rub").upper(),
                experience=(item.get("experience") or {}).get("title") if isinstance(item.get("experience"), dict) else str(item.get("experience") or ""),
                employment=(item.get("type_of_work") or {}).get("title") if isinstance(item.get("type_of_work"), dict) else "",
                description=item.get("work") or item.get("vacancyRichText") or "",
                requirements=item.get("candidat") or "",
                metadata=item,
            ))
        return rows

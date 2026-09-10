from __future__ import annotations

from datetime import datetime

import httpx

from app.config import settings
from app.sources.base import RawVacancy


class HHSource:
    name = "hh"
    configured = True
    base_url = "https://api.hh.ru/vacancies"

    @staticmethod
    def _search_text(preference) -> str:
        terms = [str(x).strip() for x in (preference.desired_terms or []) if str(x).strip()]
        if not terms:
            return settings.hh_search_text
        # HH supports a search query language. Quoting multi-word phrases keeps titles together.
        parts = [f'"{term}"' if " " in term else term for term in terms[:12]]
        return " OR ".join(parts)

    @staticmethod
    def _resolve_area_ids(client: httpx.Client, locations: list[str]) -> list[str]:
        area_ids: list[str] = []
        for location in locations[:5]:
            value = str(location).strip()
            if not value:
                continue
            try:
                response = client.get(
                    "https://api.hh.ru/suggests/areas",
                    params={"text": value, "locale": "RU"},
                )
                response.raise_for_status()
                items = response.json().get("items", [])
                if not items:
                    continue
                exact = next(
                    (item for item in items if str(item.get("text", "")).casefold() == value.casefold()),
                    items[0],
                )
                area_id = str(exact.get("id") or "").strip()
                if area_id and area_id not in area_ids:
                    area_ids.append(area_id)
            except Exception:
                # Location scoring still protects the feed if autosuggest is temporarily unavailable.
                continue
        return area_ids

    def fetch_for_preferences(
        self,
        preference,
        limit: int = 40,
        since: datetime | None = None,
        known_ids: set[str] | None = None,
    ) -> list[RawVacancy]:
        per_page = min(max(limit, 1), 100)
        headers = {"HH-User-Agent": settings.hh_user_agent, "User-Agent": settings.hh_user_agent}
        with httpx.Client(timeout=20.0, headers=headers) as client:
            params: dict[str, object] = {
                "text": self._search_text(preference),
                "order_by": "publication_time",
                "per_page": per_page,
                "page": 0,
            }
            area_ids = self._resolve_area_ids(client, preference.locations or [])
            if area_ids:
                params["area"] = area_ids
            elif settings.hh_area:
                params["area"] = settings.hh_area
            if since is not None:
                params["date_from"] = since.isoformat()
            response = client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        return self._parse(payload)

    def fetch(
        self,
        limit: int = 40,
        since: datetime | None = None,
        known_ids: set[str] | None = None,
    ) -> list[RawVacancy]:
        per_page = min(max(limit, 1), 100)
        headers = {"HH-User-Agent": settings.hh_user_agent, "User-Agent": settings.hh_user_agent}
        params = {
            "text": settings.hh_search_text,
            "area": settings.hh_area,
            "order_by": "publication_time",
            "per_page": per_page,
            "page": 0,
        }
        if since is not None:
            params["date_from"] = since.isoformat()
        with httpx.Client(timeout=20.0, headers=headers) as client:
            response = client.get(self.base_url, params=params)
            response.raise_for_status()
            payload = response.json()
        return self._parse(payload)

    def _parse(self, payload: dict) -> list[RawVacancy]:
        result: list[RawVacancy] = []
        for item in payload.get("items", []):
            salary = item.get("salary") or {}
            snippet = item.get("snippet") or {}
            schedule = (item.get("schedule") or {}).get("name", "")
            work_format = " ".join(x.get("name", "") for x in (item.get("work_format") or []))
            published = item.get("published_at")
            result.append(
                RawVacancy(
                    source=self.name,
                    external_id=str(item["id"]),
                    title=item.get("name") or "",
                    company=(item.get("employer") or {}).get("name") or "",
                    location=(item.get("area") or {}).get("name") or "",
                    url=item.get("alternate_url") or item.get("url") or "",
                    published_at=datetime.fromisoformat(published) if published else None,
                    remote=("удален" in schedule.lower() or "удален" in work_format.lower()),
                    salary_from=salary.get("from"),
                    salary_to=salary.get("to"),
                    currency=salary.get("currency"),
                    experience=(item.get("experience") or {}).get("name"),
                    employment=(item.get("employment") or {}).get("name"),
                    description=snippet.get("responsibility") or "",
                    requirements=snippet.get("requirement") or "",
                    metadata=item,
                )
            )
        return result

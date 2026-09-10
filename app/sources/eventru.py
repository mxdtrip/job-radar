from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.sources.base import RawVacancy
from app.sources.html_utils import clean_text, parse_salary_ru


class EventRuSource:
    name = "eventru"
    configured = True
    list_url = "https://event.ru/jobs/"

    def _get(self, url: str) -> str:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": settings.http_user_agent}) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    def _detail(self, url: str, list_label: str) -> RawVacancy:
        soup = BeautifulSoup(self._get(url), "html.parser")
        text = clean_text(soup.get_text("\n", strip=True))
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else list_label
        company_match = re.search(r"Компания:\s*([^\n]+)", text, re.I)
        city_match = re.search(r"Город:\s*([^\n]+)", text, re.I)
        salary_match = re.search(r"Зарплата:\s*([^\n]+)", text, re.I)
        salary_from, salary_to, currency = parse_salary_ru(salary_match.group(1) if salary_match else "")
        company = company_match.group(1).strip() if company_match else ""
        location = city_match.group(1).strip() if city_match else ""
        path = urlparse(url).path.rstrip("/")
        external_id = path.split("/")[-1] or path
        requirements = text[text.lower().find("требования:"):] if "требования:" in text.lower() else ""
        return RawVacancy(
            source=self.name, external_id=external_id, title=title, company=company, location=location,
            url=url, salary_from=salary_from, salary_to=salary_to, currency=currency,
            remote="удален" in text.lower(), description=text, requirements=requirements,
        )

    def fetch(self, limit: int = 40, since: datetime | None = None, known_ids: set[str] | None = None) -> list[RawVacancy]:
        soup = BeautifulSoup(self._get(self.list_url), "html.parser")
        seen: set[str] = set()
        candidates: list[tuple[str, str]] = []
        for a in soup.find_all("a", href=True):
            href = urljoin(self.list_url, a["href"])
            if "/job/" not in href or href.rstrip("/") == "https://event.ru/job":
                continue
            if href in seen:
                continue
            seen.add(href)
            ext_id = urlparse(href).path.rstrip("/").split("/")[-1]
            if known_ids and ext_id in known_ids:
                continue
            label = a.get_text(" ", strip=True)
            if label:
                candidates.append((href, label))
            if len(candidates) >= limit:
                break
        return [self._detail(url, label) for url, label in candidates]

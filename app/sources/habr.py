from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.sources.base import RawVacancy
from app.sources.html_utils import clean_text, parse_ru_date, parse_salary_ru


class HabrCareerSource:
    name = "habr"
    configured = True
    list_url = "https://career.habr.com/vacancies/moskva-175313"

    def _get(self, url: str) -> str:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": settings.http_user_agent}) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    @staticmethod
    def _section_text(soup: BeautifulSoup, heading: str) -> str:
        node = soup.find(["h2", "h3"], string=re.compile(heading, re.I))
        if not node:
            return ""
        parts: list[str] = []
        for sibling in node.find_all_next():
            if sibling is not node and sibling.name in {"h2"}:
                break
            if sibling.name in {"p", "li"}:
                value = sibling.get_text(" ", strip=True)
                if value:
                    parts.append(value)
        return "\n".join(parts)

    def _detail(self, url: str) -> RawVacancy:
        soup = BeautifulSoup(self._get(url), "html.parser")
        text = clean_text(soup.get_text("\n", strip=True))
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else ""
        company = ""
        company_heading = soup.find(["h2", "h3"], string=re.compile(r"^Компания$", re.I))
        if company_heading:
            link = company_heading.find_next("a")
            if link:
                company = link.get_text(" ", strip=True)
        published = parse_ru_date("\n".join(text.splitlines()[:20]))
        salary_from, salary_to, currency = parse_salary_ru("\n".join(text.splitlines()[:25]))
        location = "Москва" if re.search(r"\bМосква\b", text[:2500]) else ""
        remote = "можно удал" in text.lower() or "удаленная работа" in text.lower()
        description = self._section_text(soup, "Описание вакансии") or text
        requirements = self._section_text(soup, "Требования")
        external_id = urlparse(url).path.rstrip("/").split("/")[-1]
        return RawVacancy(
            source=self.name, external_id=external_id, title=title, company=company, location=location,
            url=url, published_at=published, remote=remote, salary_from=salary_from, salary_to=salary_to,
            currency=currency, description=description, requirements=requirements,
        )

    def fetch(self, limit: int = 40, since: datetime | None = None, known_ids: set[str] | None = None) -> list[RawVacancy]:
        soup = BeautifulSoup(self._get(self.list_url), "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(self.list_url, a["href"])
            if not re.search(r"/vacancies/\d+/?$", href) or href in seen:
                continue
            seen.add(href)
            ext_id = urlparse(href).path.rstrip("/").split("/")[-1]
            if known_ids and ext_id in known_ids:
                continue
            urls.append(href)
            if len(urls) >= limit:
                break
        rows = [self._detail(url) for url in urls]
        if since:
            rows = [row for row in rows if row.published_at is None or row.published_at >= since]
        return rows

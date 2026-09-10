from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import settings
from app.sources.base import RawVacancy
from app.sources.html_utils import clean_text, parse_ru_date, parse_salary_ru


class GeekJobSource:
    name = "geekjob"
    configured = True
    list_url = "https://geekjob.ru/vacancies/"

    def _get(self, url: str) -> str:
        with httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": settings.http_user_agent}) as client:
            response = client.get(url)
            response.raise_for_status()
            return response.text

    def _detail(self, url: str) -> RawVacancy:
        soup = BeautifulSoup(self._get(url), "html.parser")
        text = clean_text(soup.get_text("\n", strip=True))
        h1 = soup.find("h1")
        title = h1.get_text(" ", strip=True) if h1 else ""
        company = ""
        marker = soup.find(string=re.compile(r"Прямой работодатель", re.I))
        if marker:
            parent = marker.parent
            next_link = parent.find("a") if parent else None
            if not next_link and parent:
                next_link = parent.find_next("a")
            if next_link:
                company = next_link.get_text(" ", strip=True)
        if not company:
            m = re.search(r"Прямой работодатель\s+([^\n(]+)", text, re.I)
            company = m.group(1).strip() if m else ""

        lines = [x.strip() for x in text.splitlines() if x.strip()]
        location = ""
        try:
            title_idx = lines.index(title)
            for line in lines[title_idx + 1:title_idx + 8]:
                if line and not re.search(r"работодатель|джуниор|миддл|сеньор|junior|middle|senior", line, re.I):
                    if not line.startswith("Прямой"):
                        location = line
                        break
        except ValueError:
            pass
        salary_from, salary_to, currency = parse_salary_ru("\n".join(lines[:20]))
        published = parse_ru_date("\n".join(lines[:20]))
        external_id = urlparse(url).path.rstrip("/").split("/")[-1]
        description = text[text.lower().find("описание вакансии"): ] if "описание вакансии" in text.lower() else text
        return RawVacancy(
            source=self.name, external_id=external_id, title=title, company=company, location=location,
            url=url, published_at=published, remote="удален" in text.lower() or "remote" in text.lower(),
            salary_from=salary_from, salary_to=salary_to, currency=currency, description=description,
            requirements=description,
        )

    def fetch(self, limit: int = 40, since: datetime | None = None, known_ids: set[str] | None = None) -> list[RawVacancy]:
        soup = BeautifulSoup(self._get(self.list_url), "html.parser")
        urls: list[str] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = urljoin(self.list_url, a["href"])
            if not re.search(r"/vacancy/[0-9a-z]+/?$", href, re.I) or href in seen:
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

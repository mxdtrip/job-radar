# Job Radar MVP v0.2

Backend-first персональный агрегатор вакансий.

## Что работает

- FastAPI + Swagger `/docs`
- SQLite локально, PostgreSQL через Docker Compose
- автоматический scheduler (по умолчанию каждые 10 минут)
- источники: HH, Event.ru, GeekJob, Habr Career
- SuperJob через официальный API после добавления `SUPERJOB_API_KEY`
- единый canonical vacancy + несколько source refs
- exact + fuzzy cross-source deduplication
- heuristic scoring 0–100
- опциональный LLM scoring через OpenAI Responses API
- fallback без LLM: приложение продолжает работать без API-ключа
- обучение на `like / dislike` и текстовых причинах отказа
- пересчёт рекомендаций после feedback
- минимальный web UI

## Быстрый запуск на Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Открыть: http://127.0.0.1:8000
Swagger: http://127.0.0.1:8000/docs

Если проект v0.1 уже запускался, старый `job_radar.db` можно оставить: v0.2 создаст новые таблицы и автоматически добавит source refs к старым вакансиям.

## Настройка

Открой `.env`.

### HH

Укажи реальный контакт в `HH_USER_AGENT`.

### SuperJob

Нужен Secret key зарегистрированного API-приложения:

```env
SUPERJOB_API_KEY=...
```

### LLM scoring

Не обязателен. Для включения:

```env
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
```

LLM вызывается только для вакансий, прошедших дешевый heuristic pre-filter. Уже известные неизменившиеся вакансии повторно в LLM не отправляются.

## Основные API

- `GET /api/health`
- `GET /api/vacancies?min_score=60`
- `POST /api/vacancies/{id}/feedback`
- `GET /api/learning-profile`
- `GET /api/preferences`
- `PUT /api/preferences`
- `GET /api/sources`
- `GET /api/scheduler`
- `POST /api/sync/hh`
- `POST /api/sync/eventru`
- `POST /api/sync/geekjob`
- `POST /api/sync/habr`
- `POST /api/sync/superjob`
- `POST /api/sync-all`
- `POST /api/rescore?use_llm=false`

## Следующий слой источников

Avito Работа, Getmatch, CareerSpace, Dream Job, Telegram-каналы и career pages компаний помечены как `planned` в `/api/sources`. Их лучше подключать отдельными адаптерами после проверки доступных API/условий и устойчивости HTML, а не завязывать ядро на хрупкий scraping.

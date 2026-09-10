from __future__ import annotations

from app.config import settings
from app.sources.eventru import EventRuSource
from app.sources.geekjob import GeekJobSource
from app.sources.habr import HabrCareerSource
from app.sources.hh import HHSource
from app.sources.mock import MockSource
from app.sources.superjob import SuperJobSource

ALL_SOURCES = {
    "mock": MockSource(),
    "hh": HHSource(),
    "eventru": EventRuSource(),
    "geekjob": GeekJobSource(),
    "habr": HabrCareerSource(),
    "superjob": SuperJobSource(),
}


def enabled_sources(include_mock: bool = False):
    names = list(settings.enabled_sources)
    if include_mock and "mock" not in names:
        names.insert(0, "mock")
    return [ALL_SOURCES[name] for name in names if name in ALL_SOURCES and getattr(ALL_SOURCES[name], "configured", True)]

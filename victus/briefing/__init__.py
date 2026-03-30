"""Briefing script: weather, news, segment builders."""

from .content import (
    build_briefing_segments,
    build_intro_segments,
    build_news_segments,
    fetch_headlines,
    fetch_weather,
    geocode,
    greeting_for_hour,
    resolve_language,
    soften_for_speech,
    spoken_time_for_lang,
    weather_segments,
)

__all__ = [
    "build_briefing_segments",
    "build_intro_segments",
    "build_news_segments",
    "fetch_headlines",
    "fetch_weather",
    "geocode",
    "greeting_for_hour",
    "resolve_language",
    "soften_for_speech",
    "spoken_time_for_lang",
    "weather_segments",
]

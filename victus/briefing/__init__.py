"""Briefing script: weather, news, segment builders."""

from .content import (
    address_with_honorific,
    build_briefing_segments,
    build_intro_segments,
    build_news_segments,
    fetch_headlines,
    fetch_weather,
    geocode,
    greeting_for_hour,
    resolve_gender,
    resolve_language,
    soften_for_speech,
    spoken_time_for_lang,
    weather_segments,
)

__all__ = [
    "address_with_honorific",
    "build_briefing_segments",
    "build_intro_segments",
    "build_news_segments",
    "fetch_headlines",
    "fetch_weather",
    "geocode",
    "greeting_for_hour",
    "resolve_gender",
    "resolve_language",
    "soften_for_speech",
    "spoken_time_for_lang",
    "weather_segments",
]

from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from .runtime_support import http_get_json

WMO_LABELS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "rain",
    65: "heavy rain",
    71: "slight snow",
    73: "snow",
    75: "heavy snow",
    80: "rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}

_ONES = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
)
_TENS = ("", "", "twenty", "thirty", "forty", "fifty")
_HOUR12 = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve"}


def geocode(city: str) -> tuple[float, float, str]:
    data = http_get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        params={"name": city, "count": 1},
        timeout=15,
    )
    results = data.get("results") or []
    if not results:
        raise ValueError(f"No location found for '{city}'. Check spelling in config.json.")
    loc = results[0]
    lat, lon = loc["latitude"], loc["longitude"]
    label = loc.get("name", city)
    if loc.get("admin1"):
        label = f"{label}, {loc['admin1']}"
    return lat, lon, label


def fetch_weather(lat: float, lon: float) -> dict:
    return http_get_json(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,apparent_temperature",
            "daily": "sunrise,sunset,temperature_2m_max,temperature_2m_min",
            "timezone": "auto",
            "forecast_days": 1,
        },
        timeout=15,
    )


def _two_digit_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    t, o = divmod(n, 10)
    if o == 0:
        return _TENS[t]
    return f"{_TENS[t]} {_ONES[o]}"


def _daypart_phrase(h24: int) -> str:
    if h24 < 12:
        return "in the morning"
    if h24 < 17:
        return "in the afternoon"
    return "in the evening"


def _daypart_phrase_hi(h24: int) -> str:
    if h24 < 12:
        return "सुबह"
    if h24 < 17:
        return "दोपहर"
    if h24 < 21:
        return "शाम"
    return "रात"


def greeting_for_hour(h24: int, lang: str = "en") -> str:
    if lang == "hi":
        if h24 < 12:
            return "सुप्रभात"
        if h24 < 17:
            return "शुभ दोपहर"
        return "शुभ संध्या"
    if h24 < 12:
        return "Good morning"
    if h24 < 17:
        return "Good afternoon"
    return "Good evening"


def _spoken_time_natural(h24: int, minute: int) -> str:
    h12 = h24 % 12 or 12
    hw = _HOUR12[h12]
    part = _daypart_phrase(h24)
    if minute == 0:
        return f"{hw} o'clock {part}"
    if minute < 10:
        return f"{hw} oh {_ONES[minute]} {part}"
    return f"{hw} {_two_digit_words(minute)} {part}"


def _spoken_time_hindi(h24: int, minute: int) -> str:
    h12 = h24 % 12 or 12
    part = _daypart_phrase_hi(h24)
    if minute == 0:
        return f"{part} {h12} बजे"
    return f"{part} {h12} बजकर {minute} मिनट"


def spoken_time_for_lang(lang: str, h24: int, minute: int) -> str:
    if lang == "hi":
        return _spoken_time_hindi(h24, minute)
    return _spoken_time_natural(h24, minute)


def weather_segments(data: dict, place_label: str, lang: str = "en") -> list[str]:
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    temp = cur.get("temperature_2m")
    feels = cur.get("apparent_temperature")
    code = cur.get("weather_code")
    hum = cur.get("relative_humidity_2m")
    desc = WMO_LABELS.get(int(code), "mixed conditions") if code is not None else "unknown conditions"

    if lang == "hi":
        segments: list[str] = [f"{place_label} का मौसम।", f"अभी मौसम {desc} है।"]
    else:
        segments = [f"Here's the weather for {place_label}.", f"Right now, it's {desc}."]

    line_bits: list[str] = []
    if temp is not None:
        if lang == "hi":
            line_bits.append(f"तापमान {round(temp)} डिग्री है, महसूस {round(feels)} डिग्री।" if feels is not None else f"तापमान {round(temp)} डिग्री है।")
        else:
            line_bits.append(f"It is {round(temp)} degrees, feeling like {round(feels)}." if feels is not None else f"It is {round(temp)} degrees.")
    if hum is not None:
        line_bits.append(f"नमी {round(hum)} प्रतिशत है।" if lang == "hi" else f"Humidity is at {round(hum)} percent.")
    if line_bits:
        segments.append(" ".join(line_bits))

    sunrises = daily.get("sunrise") or []
    sunsets = daily.get("sunset") or []
    tmax = (daily.get("temperature_2m_max") or [None])[0]
    tmin = (daily.get("temperature_2m_min") or [None])[0]
    day_bits: list[str] = []
    if sunrises:
        sr = sunrises[0].split("T")[-1][:5]
        sh, sm = int(sr[:2]), int(sr[3:5])
        rise_words = spoken_time_for_lang(lang, sh, sm)
        day_bits.append(f"सूर्योदय {rise_words} होता है।" if lang == "hi" else f"The sun rises at {rise_words}.")
    if sunsets:
        ss = sunsets[0].split("T")[-1][:5]
        eh, em = int(ss[:2]), int(ss[3:5])
        set_words = spoken_time_for_lang(lang, eh, em)
        day_bits.append(f"सूर्यास्त {set_words} होता है।" if lang == "hi" else f"The sun sets at {set_words}.")
    if tmax is not None and tmin is not None:
        day_bits.append(
            f"आज अधिकतम {round(tmax)} और न्यूनतम {round(tmin)} डिग्री रहेगा।"
            if lang == "hi"
            else f"Today's high is {round(tmax)} degrees, with a low of {round(tmin)}."
        )
    if day_bits:
        segments.append(" ".join(day_bits))

    return segments


def soften_for_speech(text: str) -> str:
    t = re.sub(r"<[^>]+>", " ", text)
    t = t.replace("|", ", ").replace(" – ", ", ").replace(" - ", ", ")
    t = t.replace("...", ". ").replace("…", ". ")
    t = t.replace("&amp;", "and").replace("&nbsp;", " ").replace("&", " and ")
    t = " ".join(t.split())
    return t.strip()


def _headline_key(title: str) -> str:
    key = re.sub(r"[^a-z0-9]+", " ", title.lower())
    return " ".join(key.split())


def _entry_timestamp_utc(entry: object) -> float | None:
    for attr in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, attr, None)
        if parsed:
            return calendar.timegm(parsed)
    for attr in ("published", "updated", "created"):
        raw = getattr(entry, attr, None)
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(str(raw))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).timestamp()
        except Exception:
            continue
    return None


def fetch_headlines(feed_url: str, count: int) -> list[str]:
    parsed = feedparser.parse(feed_url)
    now_utc = datetime.now(timezone.utc)
    min_recent_ts = (now_utc - timedelta(hours=30)).timestamp()

    recent: list[tuple[float, str]] = []
    seen: set[str] = set()
    for entry in parsed.entries:
        title = soften_for_speech((entry.get("title") or "").strip())
        if not title:
            continue
        key = _headline_key(title)
        if key in seen:
            continue
        ts = _entry_timestamp_utc(entry)
        if ts is None or ts < min_recent_ts:
            continue
        seen.add(key)
        recent.append((ts, title))

    if len(recent) < count:
        for entry in parsed.entries:
            title = soften_for_speech((entry.get("title") or "").strip())
            if not title:
                continue
            key = _headline_key(title)
            if key in seen:
                continue
            seen.add(key)
            ts = _entry_timestamp_utc(entry) or 0
            recent.append((ts, title))
            if len(recent) >= count:
                break

    recent.sort(key=lambda item: item[0], reverse=True)
    return [title for _, title in recent[:count]]


def resolve_language(cfg: dict) -> str:
    lang = str(cfg.get("briefing_language", "en")).lower().strip()
    return lang if lang in {"en", "hi"} else "en"


def build_intro_segments(now: datetime, lang: str, greeting_name: str) -> list[str]:
    day = now.strftime("%A, %B %d")
    time_spoken = spoken_time_for_lang(lang, now.hour, now.minute)
    greet = greeting_for_hour(now.hour, lang=lang)
    return [
        f"{greet}{greeting_name and ', ' + greeting_name or ''}.",
        (f"आज {day} है." if lang == "hi" else f"Today is {day}."),
        (f"अभी समय {time_spoken} है।" if lang == "hi" else f"It's {time_spoken}."),
    ]


def build_news_segments(lang: str, headlines: list[str]) -> list[str]:
    labels_en = ("First", "Second", "Third", "Fourth", "Fifth")
    labels_hi = ("पहली", "दूसरी", "तीसरी", "चौथी", "पाँचवी")
    if not headlines:
        return ["अभी ताज़ा खबरें उपलब्ध नहीं हैं।" if lang == "hi" else "I could not fetch the headlines right now."]

    opener = "आज भारत की सबसे बड़ी खबरें।" if lang == "hi" else "Here are today's top stories from India."
    segments: list[str] = [opener]
    for i, title in enumerate(headlines):
        if lang == "hi":
            label = labels_hi[i] if i < len(labels_hi) else f"खबर नंबर {i + 1}"
        else:
            label = labels_en[i] if i < len(labels_en) else f"Story {i + 1}"
        segments.append(f"{label} — {soften_for_speech(title)}")
    return segments


def build_briefing_segments(cfg: dict) -> list[str]:
    now = datetime.now()
    lang = resolve_language(cfg)
    name = (cfg.get("greeting_name") or "").strip()
    intro_lines = build_intro_segments(now, lang, name)

    lat, lon, place = geocode(cfg["city"])
    wdata = fetch_weather(lat, lon)
    wx_segments = weather_segments(wdata, place, lang=lang)

    count = int(cfg.get("news_count", 3))
    feed = cfg.get("news_feed_url") or "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml"
    headlines = fetch_headlines(feed, count)
    news_segments = build_news_segments(lang, headlines)

    closing = "यही थीं आपकी अपडेट्स। आपका दिन शुभ हो।" if lang == "hi" else "That's everything for your briefing. Wishing you a wonderful day ahead."
    return [*intro_lines, *wx_segments, *news_segments, closing]

